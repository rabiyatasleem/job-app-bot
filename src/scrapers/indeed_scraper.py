"""Indeed job scraper using httpx + BeautifulSoup."""

import asyncio
import logging
import random
import re
from typing import Callable, TypeVar
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from config import settings
from .base_scraper import BaseScraper, JobListing

logger = logging.getLogger("job_app_bot.scrapers.indeed")

T = TypeVar("T")

# Indeed filter param values
_JOB_TYPES = {
    "full-time": "fulltime",
    "part-time": "parttime",
    "contract": "contract",
    "temporary": "temporary",
    "internship": "internship",
}

_EXPERIENCE_LEVELS = {
    "entry": "entry_level",
    "mid": "mid_level",
    "senior": "senior_level",
}


class IndeedScraper(BaseScraper):
    """Scrapes job listings from Indeed.

    Uses httpx for HTTP requests and BeautifulSoup for HTML parsing.
    Respects rate limits via configurable delay between requests.

    Usage:
        scraper = IndeedScraper()
        jobs = await scraper.search("Data Analyst", "New York, NY")
        await scraper.close()
    """

    BASE_URL = "https://www.indeed.com"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=30.0,
        )

    async def _retry(self, fn: Callable[..., T], *args, retries: int = 3, **kwargs) -> T:
        """Retry an async callable with exponential backoff.

        Args:
            fn: Async function to call.
            *args: Positional arguments for fn.
            retries: Maximum number of attempts.
            **kwargs: Keyword arguments for fn.

        Returns:
            Result of the async callable.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt + random.uniform(0, 1)
                logger.warning(
                    "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1, retries, exc, wait,
                )
                await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def _fetch_page(self, url: str, **kwargs) -> httpx.Response:
        """Fetch a page with raise_for_status.

        Args:
            url: URL to fetch.
            **kwargs: Additional arguments for httpx.get.

        Returns:
            httpx.Response object.
        """
        resp = await self._client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def _build_search_params(
        self, query: str, location: str, start: int = 0, **filters
    ) -> dict:
        """Build query parameters for an Indeed search request.

        Args:
            query: Job title or keywords.
            location: City/state or 'remote'.
            start: Pagination offset (increments of 10).
            **filters: Optional — job_type, salary_min, experience_level,
                       days_ago (1, 3, 7, 14).

        Returns:
            Dict of query params.
        """
        params: dict[str, str] = {
            "q": query,
            "l": location,
            "start": str(start),
        }

        job_type = filters.get("job_type", "")
        if job_type and job_type.lower() in _JOB_TYPES:
            params["jt"] = _JOB_TYPES[job_type.lower()]

        salary_min = filters.get("salary_min")
        if salary_min:
            params["salary"] = str(salary_min)

        experience = filters.get("experience_level", "")
        if experience and experience.lower() in _EXPERIENCE_LEVELS:
            params["explvl"] = _EXPERIENCE_LEVELS[experience.lower()]

        days_ago = filters.get("days_ago")
        if days_ago:
            params["fromage"] = str(days_ago)

        return params

    async def search(self, query: str, location: str, **filters) -> list[JobListing]:
        """Search Indeed for jobs with pagination.

        Args:
            query: Job title or keywords.
            location: City/state or 'remote'.
            **filters: Optional — job_type, salary_min, experience_level, days_ago.

        Returns:
            List of JobListing results.
        """
        listings: list[JobListing] = []
        seen_urls: set[str] = set()

        for page_num in range(settings.max_pages_per_search):
            params = self._build_search_params(
                query, location, start=page_num * 10, **filters
            )
            resp = await self._retry(
                self._fetch_page, f"{self.BASE_URL}/jobs", params=params
            )

            soup = BeautifulSoup(resp.text, "lxml")

            # Indeed uses multiple card container selectors across A/B tests
            cards = soup.select("div.job_seen_beacon")
            if not cards:
                cards = soup.select("div.jobsearch-ResultsList > div[data-jk]")
            if not cards:
                cards = soup.select("td.resultContent")

            if not cards:
                logger.debug("No cards found on page %d, stopping.", page_num)
                break

            page_count = 0
            for card in cards:
                listing = self._parse_card(card)
                if listing and listing.url not in seen_urls:
                    seen_urls.add(listing.url)
                    listings.append(listing)
                    page_count += 1

            logger.info("Page %d: collected %d new listings", page_num + 1, page_count)

            if page_count == 0:
                break

            await asyncio.sleep(random.uniform(2.0, 5.0))

        # Fetch full descriptions for each listing
        for listing in listings:
            if listing.url:
                try:
                    details = await self._retry(self.get_job_details, listing.url)
                    listing.description = details.description
                    listing.salary = details.salary or listing.salary
                    listing.job_type = details.job_type or listing.job_type
                except Exception as exc:
                    logger.warning("Failed to fetch details for %s: %s", listing.url, exc)
                await asyncio.sleep(random.uniform(2.0, 5.0))

        logger.info("Search complete: %d total listings collected.", len(listings))
        return listings

    def _parse_card(self, card: Tag) -> JobListing | None:
        """Extract job data from an Indeed search result card.

        Args:
            card: BeautifulSoup element for one job card.

        Returns:
            JobListing or None if parsing fails.
        """
        try:
            # --- Title and URL ---
            title_el = (
                card.select_one("h2.jobTitle a")
                or card.select_one("a[data-jk]")
                or card.select_one("h2 a")
            )
            if not title_el:
                return None

            title_span = title_el.select_one("span")
            title = title_span.get_text(strip=True) if title_span else title_el.get_text(strip=True)

            href = title_el.get("href", "")
            if href.startswith("/"):
                job_url = urljoin(self.BASE_URL, href)
            elif href.startswith("http"):
                job_url = href
            else:
                # Build URL from data-jk attribute (Indeed job key)
                jk = title_el.get("data-jk") or card.get("data-jk", "")
                if jk:
                    job_url = f"{self.BASE_URL}/viewjob?jk={jk}"
                else:
                    return None

            if not title:
                return None

            # --- Company ---
            company_el = (
                card.select_one("[data-testid='company-name']")
                or card.select_one("span.companyName")
                or card.select_one("span.company")
            )
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            # --- Location ---
            location_el = (
                card.select_one("[data-testid='text-location']")
                or card.select_one("div.companyLocation")
                or card.select_one("span.companyLocation")
            )
            location = location_el.get_text(strip=True) if location_el else ""

            # --- Salary ---
            salary = None
            salary_el = (
                card.select_one("div.salary-snippet-container")
                or card.select_one("[data-testid='attribute_snippet_testid']")
                or card.select_one("span.estimated-salary")
                or card.select_one("div.metadata.salary-snippet-container")
            )
            if salary_el:
                salary_text = salary_el.get_text(strip=True)
                # Only keep if it looks like a salary (contains $ or "year"/"hour")
                if re.search(r"(\$|year|hour|annually)", salary_text, re.IGNORECASE):
                    salary = salary_text

            # --- Job type ---
            job_type = None
            metadata_els = card.select("div.metadata div.attribute_snippet")
            for el in metadata_els:
                text = el.get_text(strip=True).lower()
                if any(t in text for t in ["full-time", "part-time", "contract", "temporary", "internship"]):
                    job_type = text
                    break

            # --- Description snippet ---
            desc_el = card.select_one("div.job-snippet") or card.select_one(
                "table.jobCardShelfContainer"
            )
            description_snippet = desc_el.get_text(" ", strip=True) if desc_el else ""

            # --- Posted date ---
            date_el = card.select_one("span.date") or card.select_one(
                "[data-testid='myJobsStateDate']"
            )
            posted_date = date_el.get_text(strip=True) if date_el else None

            return JobListing(
                title=title,
                company=company,
                location=location,
                url=job_url,
                description=description_snippet,
                salary=salary,
                job_type=job_type,
                posted_date=posted_date,
                source="indeed",
            )
        except Exception as exc:
            logger.debug("Failed to parse Indeed card: %s", exc)
            return None

    async def get_job_details(self, url: str) -> JobListing:
        """Fetch full job details from an Indeed posting URL.

        Args:
            url: Direct URL to the Indeed job posting.

        Returns:
            JobListing with the complete description populated.
        """
        resp = await self._retry(self._fetch_page, url)
        soup = BeautifulSoup(resp.text, "lxml")

        # --- Title ---
        title_el = (
            soup.select_one("h1.jobsearch-JobInfoHeader-title")
            or soup.select_one("h1[data-testid='jobsearch-JobInfoHeader-title']")
            or soup.select_one("h1")
        )
        title = title_el.get_text(strip=True) if title_el else "Unknown Title"

        # --- Company ---
        company_el = (
            soup.select_one("[data-testid='inlineHeader-companyName'] a")
            or soup.select_one("div.jobsearch-InlineCompanyRating a")
            or soup.select_one("div.jobsearch-CompanyInfoWithoutHeaderImage a")
        )
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"

        # --- Location ---
        location_el = (
            soup.select_one("[data-testid='inlineHeader-companyLocation']")
            or soup.select_one("div.jobsearch-JobInfoHeader-subtitle > div:nth-child(2)")
        )
        location = location_el.get_text(strip=True) if location_el else ""
        # Clean up the "- " prefix Indeed sometimes adds
        location = re.sub(r"^[\s\-]+", "", location)

        # --- Full description ---
        desc_el = (
            soup.select_one("div#jobDescriptionText")
            or soup.select_one("div.jobsearch-jobDescriptionText")
            or soup.select_one("div.jobsearch-JobComponent-description")
        )
        description = desc_el.get_text("\n", strip=True) if desc_el else ""

        # --- Salary ---
        salary = None
        salary_el = (
            soup.select_one("div#salaryInfoAndJobType span.css-2iqe2o")
            or soup.select_one("[data-testid='attribute_snippet_testid']")
        )
        if salary_el:
            salary_text = salary_el.get_text(strip=True)
            if re.search(r"(\$|year|hour|annually)", salary_text, re.IGNORECASE):
                salary = salary_text

        # --- Job type ---
        job_type = None
        type_el = soup.select_one("div#salaryInfoAndJobType span:last-child")
        if type_el:
            text = type_el.get_text(strip=True).lower().strip("- ")
            if any(t in text for t in ["full-time", "part-time", "contract", "temporary", "internship"]):
                job_type = text

        return JobListing(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            salary=salary,
            job_type=job_type,
            source="indeed",
        )

    def save_to_database(self, listings: list[JobListing]) -> int:
        """Save job listings to the database.

        Args:
            listings: List of JobListing objects to persist.

        Returns:
            Number of listings saved.
        """
        from src.database.db import ApplicationRepository

        repo = ApplicationRepository()
        repo.create_tables()
        saved = 0
        for listing in listings:
            try:
                repo.save_job_posting(
                    title=listing.title,
                    company=listing.company,
                    location=listing.location,
                    url=listing.url,
                    description=listing.description,
                    salary=listing.salary,
                    job_type=listing.job_type,
                    source=listing.source,
                )
                saved += 1
            except Exception as exc:
                logger.warning("Failed to save listing %s: %s", listing.url, exc)
        repo.close()
        logger.info("Saved %d/%d listings to database.", saved, len(listings))
        return saved

    async def close(self) -> None:
        """Close the HTTP client."""
        try:
            await self._client.aclose()
        except Exception as exc:
            logger.debug("Error during cleanup: %s", exc)


async def main() -> None:
    """Standalone test: search Indeed and save results."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    scraper = IndeedScraper()
    try:
        listings = await scraper.search("Python Developer", "Remote")
        logger.info("Found %d listings.", len(listings))

        for listing in listings[:5]:
            print(f"  {listing.title} @ {listing.company} — {listing.location}")

        saved = scraper.save_to_database(listings)
        print(f"\nSaved {saved} listings to database.")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
