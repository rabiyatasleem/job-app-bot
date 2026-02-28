"""Tests for the LinkedIn job scraper."""

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from src.scrapers.base_scraper import JobListing
from src.scrapers.linkedin_scraper import LinkedInScraper
from tests.conftest import LINKEDIN_DETAIL_PAGE_FIELDS


# ---------------------------------------------------------------------------
# Helpers for mocking Playwright locators
# ---------------------------------------------------------------------------

def _make_locator(text: str = "", href: str | None = None, count: int = 1):
    """Create a mock Playwright Locator that behaves like a real one.

    Args:
        text: The text returned by inner_text().
        href: Value returned by get_attribute("href").
        count: Value returned by count() — 0 means "element not found".
    """
    loc = AsyncMock()
    loc.inner_text = AsyncMock(return_value=text)
    loc.get_attribute = AsyncMock(return_value=href)
    loc.count = AsyncMock(return_value=count)
    loc.first = loc  # .first returns itself for chaining
    return loc


def _make_card_locator(
    title: str = "Software Engineer",
    href: str = "/jobs/view/12345/?refId=abc",
    company: str = "TechCo",
    location: str = "San Francisco, CA",
    company_count: int = 1,
    location_count: int = 1,
):
    """Create a mock Playwright Locator for a LinkedIn job card."""
    card = AsyncMock()

    title_loc = _make_locator(text=title, href=href)
    company_loc = _make_locator(text=company, count=company_count)
    location_loc = _make_locator(text=location, count=location_count)

    def locator_side_effect(selector: str):
        if "job-card-container__link" in selector:
            return title_loc
        if "primary-description" in selector:
            return company_loc
        if "metadata-item" in selector:
            return location_loc
        return _make_locator(count=0)

    card.locator = MagicMock(side_effect=locator_side_effect)
    return card


def _make_detail_page_mock(fields: dict):
    """Create a mock Playwright Page pre-loaded with job detail selectors.

    Args:
        fields: Dict with keys title, company, location, description,
                salary (optional), job_type (optional).
    """
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()

    # Build locator mocks keyed by CSS selector substring
    selector_text_map = {
        "job-details-jobs-unified-top-card__job-title": fields.get("title", ""),
        "top-card-layout__title": "",  # fallback shouldn't match if first does
        "job-details-jobs-unified-top-card__company-name": fields.get("company", ""),
        "topcard__org-name-link": "",
        "topcard__flavor": "",
        "job-details-jobs-unified-top-card__bullet": fields.get("location", ""),
        "topcard__flavor--bullet": "",
        "jobs-description__content": fields.get("description", ""),
        "description__text": "",
        "show-more-less-html__markup": "",
    }

    salary_text = fields.get("salary")
    job_type_text = fields.get("job_type")

    def make_page_locator(selector: str):
        # Salary locator
        if "salary" in selector.lower() and "salaryInfo" not in selector:
            loc = _make_locator(
                text=salary_text or "",
                count=1 if salary_text else 0,
            )
            return loc

        # Job insight metadata (returns list via .all())
        if "job-insight" in selector:
            loc = AsyncMock()
            if job_type_text:
                item = AsyncMock()
                item.inner_text = AsyncMock(return_value=job_type_text)
                loc.all = AsyncMock(return_value=[item])
            else:
                loc.all = AsyncMock(return_value=[])
            return loc

        # Match by longest substring match
        for key, text in selector_text_map.items():
            if key in selector:
                has_content = bool(text)
                return _make_locator(text=text, count=1 if has_content else 0)

        return _make_locator(count=0)

    page.locator = MagicMock(side_effect=make_page_locator)
    return page


# ===================================================================
# _build_search_url
# ===================================================================

class TestBuildSearchUrl:
    """Unit tests for LinkedInScraper._build_search_url."""

    def setup_method(self):
        self.scraper = LinkedInScraper()

    def _parse(self, url: str) -> dict:
        parsed = urlparse(url)
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def test_basic_url(self):
        url = self.scraper._build_search_url("Python", "Remote")
        params = self._parse(url)

        assert "linkedin.com/jobs/search" in url
        assert params["keywords"] == "Python"
        assert params["location"] == "Remote"
        assert params["start"] == "0"

    def test_start_offset(self):
        url = self.scraper._build_search_url("Dev", "NYC", start=50)
        params = self._parse(url)
        assert params["start"] == "50"

    def test_experience_level_filter(self):
        url = self.scraper._build_search_url("Dev", "LA", experience_level="entry")
        params = self._parse(url)
        assert params["f_E"] == "2"

    def test_experience_level_case_insensitive(self):
        url = self.scraper._build_search_url("Dev", "LA", experience_level="Mid-Senior")
        params = self._parse(url)
        assert params["f_E"] == "4"

    def test_job_type_filter(self):
        url = self.scraper._build_search_url("Dev", "LA", job_type="contract")
        params = self._parse(url)
        assert params["f_JT"] == "C"

    def test_work_mode_filter(self):
        url = self.scraper._build_search_url("Dev", "LA", work_mode="remote")
        params = self._parse(url)
        assert params["f_WT"] == "2"

    def test_time_posted_filter(self):
        url = self.scraper._build_search_url("Dev", "LA", time_posted="week")
        params = self._parse(url)
        assert params["f_TPR"] == "r604800"

    def test_all_filters(self):
        url = self.scraper._build_search_url(
            "Engineer", "Boston",
            experience_level="director",
            job_type="full-time",
            work_mode="hybrid",
            time_posted="day",
        )
        params = self._parse(url)
        assert params["f_E"] == "5"
        assert params["f_JT"] == "F"
        assert params["f_WT"] == "3"
        assert params["f_TPR"] == "r86400"

    def test_unknown_experience_ignored(self):
        url = self.scraper._build_search_url("Dev", "LA", experience_level="guru")
        params = self._parse(url)
        assert "f_E" not in params

    def test_unknown_job_type_ignored(self):
        url = self.scraper._build_search_url("Dev", "LA", job_type="freelance")
        params = self._parse(url)
        assert "f_JT" not in params

    def test_unknown_work_mode_ignored(self):
        url = self.scraper._build_search_url("Dev", "LA", work_mode="mars")
        params = self._parse(url)
        assert "f_WT" not in params

    def test_unknown_time_posted_ignored(self):
        url = self.scraper._build_search_url("Dev", "LA", time_posted="century")
        params = self._parse(url)
        assert "f_TPR" not in params

    def test_empty_filter_values_ignored(self):
        url = self.scraper._build_search_url("Dev", "LA", job_type="", work_mode="")
        params = self._parse(url)
        assert "f_JT" not in params
        assert "f_WT" not in params


# ===================================================================
# _parse_card
# ===================================================================

class TestParseCard:
    """Tests for LinkedInScraper._parse_card with mocked Playwright locators."""

    def setup_method(self):
        self.scraper = LinkedInScraper()

    @pytest.mark.asyncio
    async def test_full_card(self):
        card = _make_card_locator(
            title="Backend Developer",
            href="/jobs/view/99999/?refId=xyz",
            company="MegaCorp",
            location="Austin, TX",
        )
        listing = await self.scraper._parse_card(card)

        assert listing is not None
        assert listing.title == "Backend Developer"
        assert listing.company == "MegaCorp"
        assert listing.location == "Austin, TX"
        assert listing.url == "https://www.linkedin.com/jobs/view/99999/"
        assert listing.source == "linkedin"
        assert listing.description == ""  # populated later by get_job_details

    @pytest.mark.asyncio
    async def test_relative_href_cleaned(self):
        card = _make_card_locator(href="/jobs/view/123/?trackingId=abc&refId=def")
        listing = await self.scraper._parse_card(card)

        assert listing is not None
        assert "?" not in listing.url
        assert listing.url.endswith("/jobs/view/123/")

    @pytest.mark.asyncio
    async def test_absolute_href_preserved(self):
        card = _make_card_locator(href="https://www.linkedin.com/jobs/view/555/")
        listing = await self.scraper._parse_card(card)

        assert listing is not None
        assert listing.url == "https://www.linkedin.com/jobs/view/555/"

    @pytest.mark.asyncio
    async def test_missing_company_defaults_to_unknown(self):
        card = _make_card_locator(company="", company_count=0)
        listing = await self.scraper._parse_card(card)

        assert listing is not None
        assert listing.company == "Unknown"

    @pytest.mark.asyncio
    async def test_missing_location_defaults_to_empty(self):
        card = _make_card_locator(location="", location_count=0)
        listing = await self.scraper._parse_card(card)

        assert listing is not None
        assert listing.location == ""

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        card = AsyncMock()
        card.locator = MagicMock(side_effect=RuntimeError("boom"))
        listing = await self.scraper._parse_card(card)
        assert listing is None


# ===================================================================
# get_job_details
# ===================================================================

class TestGetJobDetails:
    """Tests for LinkedInScraper.get_job_details with mocked Playwright."""

    def setup_method(self):
        self.scraper = LinkedInScraper()

    @pytest.mark.asyncio
    async def test_full_detail_page(self):
        page = _make_detail_page_mock(LINKEDIN_DETAIL_PAGE_FIELDS)
        self.scraper._page = page

        url = "https://www.linkedin.com/jobs/view/12345/"
        listing = await self.scraper.get_job_details(url)

        assert listing.title == "Staff Software Engineer"
        assert listing.company == "BigTech Inc"
        assert listing.location == "San Jose, CA"
        assert "cloud infrastructure" in listing.description
        assert listing.salary == "$180,000 - $250,000/yr"
        assert listing.job_type == "full-time"
        assert listing.source == "linkedin"
        assert listing.url == url

    @pytest.mark.asyncio
    async def test_detail_page_no_salary(self):
        fields = {**LINKEDIN_DETAIL_PAGE_FIELDS, "salary": None}
        page = _make_detail_page_mock(fields)
        self.scraper._page = page

        listing = await self.scraper.get_job_details("https://linkedin.com/jobs/view/1/")
        assert listing.salary is None

    @pytest.mark.asyncio
    async def test_detail_page_no_job_type(self):
        fields = {**LINKEDIN_DETAIL_PAGE_FIELDS, "job_type": None}
        page = _make_detail_page_mock(fields)
        self.scraper._page = page

        listing = await self.scraper.get_job_details("https://linkedin.com/jobs/view/2/")
        assert listing.job_type is None

    @pytest.mark.asyncio
    async def test_detail_page_minimal_fallbacks(self):
        """When no selectors match, should return safe defaults."""
        page = _make_detail_page_mock({
            "title": "",
            "company": "",
            "location": "",
            "description": "",
        })
        self.scraper._page = page

        listing = await self.scraper.get_job_details("https://linkedin.com/jobs/view/3/")
        assert listing.title == "Unknown Title"
        assert listing.company == "Unknown Company"
        assert listing.location == ""
        assert listing.description == ""

    @pytest.mark.asyncio
    async def test_navigates_to_correct_url(self):
        page = _make_detail_page_mock(LINKEDIN_DETAIL_PAGE_FIELDS)
        self.scraper._page = page

        url = "https://www.linkedin.com/jobs/view/77777/"
        await self.scraper.get_job_details(url)

        page.goto.assert_awaited_once_with(url, wait_until="domcontentloaded")

    @pytest.mark.asyncio
    async def test_waits_for_description_selector(self):
        page = _make_detail_page_mock(LINKEDIN_DETAIL_PAGE_FIELDS)
        self.scraper._page = page

        await self.scraper.get_job_details("https://linkedin.com/jobs/view/1/")

        page.wait_for_selector.assert_awaited()
        first_call_args = page.wait_for_selector.call_args_list[0]
        assert "jobs-description" in first_call_args[0][0]


# ===================================================================
# search
# ===================================================================

class TestSearch:
    """Tests for LinkedInScraper.search with mocked Playwright page."""

    def setup_method(self):
        self.scraper = LinkedInScraper()

    @pytest.mark.asyncio
    @patch("src.scrapers.linkedin_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_returns_parsed_cards(self, mock_sleep):
        card1 = _make_card_locator(title="Job A", href="/jobs/view/1/", company="Co1")
        card2 = _make_card_locator(title="Job B", href="/jobs/view/2/", company="Co2")

        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()

        # Locator for job-card-container returns list of card mocks
        cards_locator = AsyncMock()
        cards_locator.all = AsyncMock(return_value=[card1, card2])

        # Locator for scroll container
        scroll_locator = AsyncMock()
        scroll_locator.evaluate = AsyncMock()

        def page_locator_side_effect(selector):
            if "job-card-container" in selector:
                return cards_locator
            if "jobs-search-results-list" in selector:
                return scroll_locator
            return AsyncMock()

        page.locator = MagicMock(side_effect=page_locator_side_effect)

        self.scraper._page = page
        self.scraper._pw = MagicMock()
        self.scraper._browser = MagicMock()
        self.scraper.get_job_details = AsyncMock(
            return_value=JobListing(title="", company="", location="", url="", description="", source="linkedin")
        )

        with patch("src.scrapers.linkedin_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 1
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Engineer", "Remote")

        assert len(listings) == 2
        assert listings[0].title == "Job A"
        assert listings[1].title == "Job B"

    @pytest.mark.asyncio
    @patch("src.scrapers.linkedin_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_stops_when_no_cards(self, mock_sleep):
        page = AsyncMock()
        page.goto = AsyncMock()
        # wait_for_selector raises to simulate no cards
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError("no cards"))

        self.scraper._page = page
        self.scraper._pw = MagicMock()
        self.scraper._browser = MagicMock()

        with patch("src.scrapers.linkedin_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 3
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Ghost", "Nowhere")

        assert len(listings) == 0
        # With retries (3 attempts per page) and 3 pages, goto is called
        # multiple times.  The key assertion is that no listings are returned.
        assert page.goto.call_count >= 1

    @pytest.mark.asyncio
    @patch("src.scrapers.linkedin_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_skips_unparseable_cards(self, mock_sleep):
        good_card = _make_card_locator(title="Good Job", href="/jobs/view/1/")
        bad_card = AsyncMock()
        bad_card.locator = MagicMock(side_effect=RuntimeError("broken"))

        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()

        cards_locator = AsyncMock()
        cards_locator.all = AsyncMock(return_value=[good_card, bad_card])

        scroll_locator = AsyncMock()
        scroll_locator.evaluate = AsyncMock()

        def page_locator_side_effect(selector):
            if "job-card-container" in selector:
                return cards_locator
            if "jobs-search-results-list" in selector:
                return scroll_locator
            return AsyncMock()

        page.locator = MagicMock(side_effect=page_locator_side_effect)

        self.scraper._page = page
        self.scraper._pw = MagicMock()
        self.scraper._browser = MagicMock()

        with patch("src.scrapers.linkedin_scraper.settings") as mock_settings:
            mock_settings.max_pages_per_search = 1
            mock_settings.scrape_delay_seconds = 0
            listings = await self.scraper.search("Mixed", "NYC")

        assert len(listings) == 1
        assert listings[0].title == "Good Job"


# ===================================================================
# close
# ===================================================================

class TestClose:

    @pytest.mark.asyncio
    async def test_close_shuts_down_browser_and_pw(self):
        scraper = LinkedInScraper()
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        scraper._browser = mock_browser
        scraper._pw = mock_pw
        scraper._page = AsyncMock()

        await scraper.close()

        mock_browser.close.assert_awaited_once()
        mock_pw.stop.assert_awaited_once()
        assert scraper._browser is None
        assert scraper._page is None
        assert scraper._pw is None

    @pytest.mark.asyncio
    async def test_close_noop_when_not_launched(self):
        scraper = LinkedInScraper()
        # Should not raise
        await scraper.close()
        assert scraper._browser is None
        assert scraper._page is None


# ===================================================================
# login
# ===================================================================

class TestLogin:

    @pytest.mark.asyncio
    async def test_login_fills_credentials_and_submits(self):
        scraper = LinkedInScraper()
        page = AsyncMock()

        with patch.object(scraper, "_ensure_browser", return_value=page):
            with patch("src.scrapers.linkedin_scraper.settings") as mock_settings:
                mock_settings.linkedin_email = "user@test.com"
                mock_settings.linkedin_password = "secret123"
                await scraper.login()

        page.goto.assert_awaited_once_with("https://www.linkedin.com/login")
        page.fill.assert_any_await("#username", "user@test.com")
        page.fill.assert_any_await("#password", "secret123")
        page.click.assert_awaited_once_with("[type=submit]")
        page.wait_for_url.assert_awaited_once()
