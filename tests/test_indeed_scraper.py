"""Tests for the Indeed job scraper."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup

from src.scrapers.indeed_scraper import IndeedScraper
from tests.conftest import (
    INDEED_CARD_ABSOLUTE_URL,
    INDEED_CARD_DATA_JK_FALLBACK,
    INDEED_CARD_EMPTY_TITLE,
    INDEED_CARD_FULL,
    INDEED_CARD_MINIMAL,
    INDEED_CARD_NO_TITLE_LINK,
    INDEED_CARD_SALARY_NO_MATCH,
    INDEED_DETAIL_PAGE,
    INDEED_DETAIL_PAGE_LOCATION_DASH,
    INDEED_DETAIL_PAGE_MINIMAL,
    INDEED_SEARCH_PAGE,
    INDEED_SEARCH_PAGE_ALT_LAYOUT,
    INDEED_SEARCH_PAGE_DUPLICATE,
    INDEED_SEARCH_PAGE_EMPTY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(html: str):
    """Parse HTML and return the first top-level element as a BS4 Tag."""
    soup = BeautifulSoup(html, "lxml")
    return soup.select_one("div")


def _make_response(html: str, status_code: int = 200) -> httpx.Response:
    """Build a fake httpx.Response with the given HTML body."""
    return httpx.Response(
        status_code=status_code,
        text=html,
        request=httpx.Request("GET", "https://www.indeed.com/jobs"),
    )


# ===================================================================
# _build_search_params
# ===================================================================

class TestBuildSearchParams:
    """Unit tests for IndeedScraper._build_search_params."""

    def setup_method(self):
        self.scraper = IndeedScraper()

    def test_basic_params(self):
        params = self.scraper._build_search_params("Python Developer", "Remote")
        assert params == {"q": "Python Developer", "l": "Remote", "start": "0"}

    def test_start_offset(self):
        params = self.scraper._build_search_params("Engineer", "NYC", start=30)
        assert params["start"] == "30"

    def test_job_type_filter(self):
        params = self.scraper._build_search_params("Dev", "LA", job_type="full-time")
        assert params["jt"] == "fulltime"

    def test_job_type_case_insensitive(self):
        params = self.scraper._build_search_params("Dev", "LA", job_type="Part-Time")
        assert params["jt"] == "parttime"

    def test_salary_min_filter(self):
        params = self.scraper._build_search_params("Dev", "LA", salary_min=80000)
        assert params["salary"] == "80000"

    def test_experience_level_filter(self):
        params = self.scraper._build_search_params("Dev", "LA", experience_level="senior")
        assert params["explvl"] == "senior_level"

    def test_days_ago_filter(self):
        params = self.scraper._build_search_params("Dev", "LA", days_ago=7)
        assert params["fromage"] == "7"

    def test_all_filters_combined(self):
        params = self.scraper._build_search_params(
            "Engineer", "Boston",
            job_type="contract",
            salary_min=100000,
            experience_level="mid",
            days_ago=3,
        )
        assert params["q"] == "Engineer"
        assert params["l"] == "Boston"
        assert params["jt"] == "contract"
        assert params["salary"] == "100000"
        assert params["explvl"] == "mid_level"
        assert params["fromage"] == "3"

    def test_unknown_job_type_ignored(self):
        params = self.scraper._build_search_params("Dev", "LA", job_type="freelance")
        assert "jt" not in params

    def test_unknown_experience_ignored(self):
        params = self.scraper._build_search_params("Dev", "LA", experience_level="wizard")
        assert "explvl" not in params

    def test_empty_filters_ignored(self):
        params = self.scraper._build_search_params("Dev", "LA", job_type="", experience_level="")
        assert "jt" not in params
        assert "explvl" not in params


# ===================================================================
# _parse_card
# ===================================================================

class TestParseCard:
    """Unit tests for IndeedScraper._parse_card."""

    def setup_method(self):
        self.scraper = IndeedScraper()

    def test_full_card(self):
        card = _make_card(INDEED_CARD_FULL)
        listing = self.scraper._parse_card(card)

        assert listing is not None
        assert listing.title == "Senior Python Developer"
        assert listing.company == "Acme Corp"
        assert listing.location == "New York, NY"
        assert "indeed.com" in listing.url
        assert "$120,000" in listing.salary
        assert listing.job_type == "full-time"
        assert "Python microservices" in listing.description
        assert listing.posted_date == "Posted 3 days ago"
        assert listing.source == "indeed"

    def test_minimal_card(self):
        card = _make_card(INDEED_CARD_MINIMAL)
        listing = self.scraper._parse_card(card)

        assert listing is not None
        assert listing.title == "Junior Data Analyst"
        assert listing.company == "DataCo"
        assert listing.location == "Remote"
        assert listing.salary is None
        assert listing.job_type is None
        assert listing.description == ""
        assert listing.posted_date is None

    def test_data_jk_fallback_url(self):
        card = _make_card(INDEED_CARD_DATA_JK_FALLBACK)
        listing = self.scraper._parse_card(card)

        assert listing is not None
        assert listing.title == "DevOps Engineer"
        assert listing.company == "CloudInc"
        assert "ghi789" in listing.url
        assert listing.url == "https://www.indeed.com/viewjob?jk=ghi789"

    def test_no_title_link_returns_none(self):
        card = _make_card(INDEED_CARD_NO_TITLE_LINK)
        listing = self.scraper._parse_card(card)
        assert listing is None

    def test_empty_title_returns_none(self):
        card = _make_card(INDEED_CARD_EMPTY_TITLE)
        listing = self.scraper._parse_card(card)
        assert listing is None

    def test_absolute_url_preserved(self):
        card = _make_card(INDEED_CARD_ABSOLUTE_URL)
        listing = self.scraper._parse_card(card)

        assert listing is not None
        assert listing.title == "Fullstack Engineer"
        assert listing.url == "https://www.indeed.com/viewjob?jk=abs001"

    def test_salary_not_matching_pattern_excluded(self):
        card = _make_card(INDEED_CARD_SALARY_NO_MATCH)
        listing = self.scraper._parse_card(card)

        assert listing is not None
        assert listing.salary is None  # "Competitive benefits" has no $ or year/hour

    def test_relative_url_resolved(self):
        card = _make_card(INDEED_CARD_FULL)
        listing = self.scraper._parse_card(card)

        assert listing is not None
        assert listing.url.startswith("https://www.indeed.com/")


# ===================================================================
# get_job_details
# ===================================================================

class TestGetJobDetails:
    """Tests for IndeedScraper.get_job_details with mocked HTTP."""

    def setup_method(self):
        self.scraper = IndeedScraper()

    @pytest.mark.asyncio
    async def test_full_detail_page(self):
        mock_resp = _make_response(INDEED_DETAIL_PAGE)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        url = "https://www.indeed.com/viewjob?jk=abc123"
        listing = await self.scraper.get_job_details(url)

        assert listing.title == "Senior Python Developer"
        assert listing.company == "Acme Corp"
        assert listing.location == "New York, NY"
        assert "$130,000" in listing.salary
        assert listing.job_type == "full-time"
        assert "Senior Python Developer" in listing.description
        assert "5+ years" in listing.description
        assert listing.source == "indeed"
        assert listing.url == url

    @pytest.mark.asyncio
    async def test_minimal_detail_page_fallbacks(self):
        mock_resp = _make_response(INDEED_DETAIL_PAGE_MINIMAL)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        listing = await self.scraper.get_job_details("https://www.indeed.com/viewjob?jk=x")

        assert listing.title == "Some Job Title"
        assert listing.company == "Unknown Company"
        assert listing.location == ""
        assert listing.salary is None
        assert listing.job_type is None
        assert listing.description == ""

    @pytest.mark.asyncio
    async def test_location_dash_prefix_stripped(self):
        mock_resp = _make_response(INDEED_DETAIL_PAGE_LOCATION_DASH)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        listing = await self.scraper.get_job_details("https://www.indeed.com/viewjob?jk=y")

        assert listing.location == "Seattle, WA"

    @pytest.mark.asyncio
    async def test_http_error_raised(self):
        error_resp = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://www.indeed.com/viewjob?jk=bad"),
        )
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=error_resp)

        with pytest.raises(httpx.HTTPStatusError):
            await self.scraper.get_job_details("https://www.indeed.com/viewjob?jk=bad")


# ===================================================================
# search (integration with mocked HTTP)
# ===================================================================

class TestSearch:
    """Tests for IndeedScraper.search with mocked HTTP client."""

    def setup_method(self):
        self.scraper = IndeedScraper()

    @pytest.mark.asyncio
    @patch("src.scrapers.indeed_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_returns_listings(self, mock_sleep):
        mock_resp = _make_response(INDEED_SEARCH_PAGE)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        with patch("src.scrapers.indeed_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 1
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Engineer", "Remote")

        assert len(listings) == 2
        assert listings[0].title == "Backend Engineer"
        assert listings[0].company == "StartupX"
        assert listings[1].title == "Frontend Engineer"

    @pytest.mark.asyncio
    @patch("src.scrapers.indeed_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_stops_on_empty_page(self, mock_sleep):
        mock_resp = _make_response(INDEED_SEARCH_PAGE_EMPTY)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        with patch("src.scrapers.indeed_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 5
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Ghost Job", "Nowhere")

        assert len(listings) == 0
        # Should have stopped after first empty page — only 1 call
        assert self.scraper._client.get.call_count == 1

    @pytest.mark.asyncio
    @patch("src.scrapers.indeed_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_deduplicates_by_url(self, mock_sleep):
        mock_resp = _make_response(INDEED_SEARCH_PAGE_DUPLICATE)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        with patch("src.scrapers.indeed_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 1
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Engineer", "Remote")

        # Two cards with identical URLs — only one should be kept
        assert len(listings) == 1

    @pytest.mark.asyncio
    @patch("src.scrapers.indeed_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_paginates(self, mock_sleep):
        page1 = _make_response(INDEED_SEARCH_PAGE)
        page2 = _make_response(INDEED_SEARCH_PAGE_EMPTY)

        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(side_effect=[page1, page2])

        with patch("src.scrapers.indeed_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 3
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Engineer", "Remote")

        assert len(listings) == 2
        # Page 1 had results (1 call), then delay + page 2 was empty (2nd call)
        assert self.scraper._client.get.call_count == 2

    @pytest.mark.asyncio
    @patch("src.scrapers.indeed_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_alt_layout_selector(self, mock_sleep):
        """Indeed sometimes uses div[data-jk] instead of div.job_seen_beacon."""
        mock_resp = _make_response(INDEED_SEARCH_PAGE_ALT_LAYOUT)
        self.scraper._client = AsyncMock()
        self.scraper._client.get = AsyncMock(return_value=mock_resp)

        with patch("src.scrapers.indeed_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 1
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("ML", "Boston")

        assert len(listings) == 1
        assert listings[0].title == "ML Engineer"
        assert listings[0].company == "AILabs"


# ===================================================================
# close
# ===================================================================

class TestClose:

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self):
        scraper = IndeedScraper()
        scraper._client = AsyncMock()
        await scraper.close()
        scraper._client.aclose.assert_awaited_once()
