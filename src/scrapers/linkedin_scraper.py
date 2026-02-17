"""LinkedIn job scraper using Playwright for browser automation."""

import asyncio
import logging
import random
from typing import Callable, TypeVar
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

from config import settings
from .base_scraper import BaseScraper, JobListing

logger = logging.getLogger("job_app_bot.scrapers.linkedin")

T = TypeVar("T")

# LinkedIn filter codes
_EXPERIENCE_LEVELS = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}

_JOB_TYPES = {
    "full-time": "F",
    "part-time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "volunteer": "V",
}

_WORK_MODES = {
    "onsite": "1",
    "remote": "2",
    "hybrid": "3",
}


class LinkedInScraper(BaseScraper):
    """Scrapes job listings from LinkedIn.

    Uses Playwright to handle LinkedIn's dynamic content and
    authentication requirements.

    Usage:
        scraper = LinkedInScraper()
        await scraper.login()
        jobs = await scraper.search("Software Engineer", "Remote")
        await scraper.close()
    """

    JOBS_SEARCH_URL = "https://www.linkedin.com/jobs/search/"

    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._pw = None

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

    async def _ensure_browser(self) -> Page:
        """Launch browser and return a page, reusing if already open."""
        if self._page is None:
            try:
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(headless=True)
                self._page = await self._browser.new_page()
            except Exception as exc:
                logger.error("Failed to launch browser: %s", exc)
                # Clean up partial state
                if self._pw:
                    try:
                        await self._pw.stop()
                    except Exception:
                        pass
                self._pw = None
                self._browser = None
                self._page = None
                raise
        return self._page

    async def login(self) -> None:
        """Authenticate with LinkedIn using credentials from settings."""
        page = await self._ensure_browser()
        await page.goto("https://www.linkedin.com/login")
        await page.fill("#username", settings.linkedin_email)
        await page.fill("#password", settings.linkedin_password)
        await page.click("[type=submit]")
        try:
            await page.wait_for_url("**/feed/**", timeout=30_000)
        except PlaywrightTimeout:
            raise TimeoutError(
                "LinkedIn login timed out — check credentials or for a CAPTCHA challenge."
            ) from None

    def _build_search_url(self, query: str, location: str, start: int = 0, **filters) -> str:
        """Build a LinkedIn jobs search URL with query params and filters.

        Args:
            query: Job title or keywords.
            location: City/state or 'remote'.
            start: Pagination offset (increments of 25).
            **filters: Optional — experience_level, job_type, work_mode, time_posted.

        Returns:
            Full search URL string.
        """
        params = {
            "keywords": query,
            "location": location,
            "start": str(start),
        }

        experience = filters.get("experience_level", "")
        if experience and experience.lower() in _EXPERIENCE_LEVELS:
            params["f_E"] = _EXPERIENCE_LEVELS[experience.lower()]

        job_type = filters.get("job_type", "")
        if job_type and job_type.lower() in _JOB_TYPES:
            params["f_JT"] = _JOB_TYPES[job_type.lower()]

        work_mode = filters.get("work_mode", "")
        if work_mode and work_mode.lower() in _WORK_MODES:
            params["f_WT"] = _WORK_MODES[work_mode.lower()]

        time_posted = filters.get("time_posted", "")
        time_codes = {"day": "r86400", "week": "r604800", "month": "r2592000"}
        if time_posted and time_posted.lower() in time_codes:
            params["f_TPR"] = time_codes[time_posted.lower()]

        return f"{self.JOBS_SEARCH_URL}?{urlencode(params)}"

    async def _scroll_job_list(self, page: Page) -> None:
        """Scroll the job results panel to trigger lazy-loaded cards."""
        jobs_container = page.locator("div.jobs-search-results-list")
        for _ in range(3):
            await jobs_container.evaluate("el => el.scrollTop = el.scrollHeight")
            await asyncio.sleep(random.uniform(0.5, 1.2))

    async def _fetch_page(self, page: Page, url: str) -> list[JobListing]:
        """Navigate to a search results page and extract job cards.

        Args:
            page: Playwright Page instance.
            url: Search results URL to navigate to.

        Returns:
            List of JobListing objects parsed from the page.
        """
        await page.goto(url, wait_until="domcontentloaded")

        await page.wait_for_selector("div.job-card-container", timeout=10_000)

        await self._scroll_job_list(page)

        cards = await page.locator("div.job-card-container").all()
        results: list[JobListing] = []
        for card in cards:
            listing = await self._parse_card(card)
            if listing:
                results.append(listing)
        return results

    async def search(
        self, query: str, location: str, *, max_results: int = 0, **filters
    ) -> list[JobListing]:
        """Search LinkedIn jobs with pagination.

        Args:
            query: Job title or keywords.
            location: City/state or 'remote'.
            max_results: Stop after collecting this many listings. 0 means
                use settings.max_pages_per_search pages.
            **filters: Optional filters — experience_level, job_type, work_mode,
                       time_posted.

        Returns:
            List of JobListing results.
        """
        page = await self._ensure_browser()
        listings: list[JobListing] = []
        num_pages = settings.max_pages_per_search

        for page_num in range(num_pages):
            url = self._build_search_url(query, location, start=page_num * 25, **filters)

            try:
                page_listings = await self._retry(self._fetch_page, page, url)
            except Exception as exc:
                logger.warning("Page %d failed after retries: %s. Continuing.", page_num + 1, exc)
                continue

            if not page_listings:
                logger.debug("No cards on page %d, stopping pagination.", page_num + 1)
                break

            listings.extend(page_listings)
            logger.info(
                "Page %d: collected %d cards (total: %d)",
                page_num + 1, len(page_listings), len(listings),
            )

            if max_results and len(listings) >= max_results:
                listings = listings[:max_results]
                logger.info("Reached max_results=%d, stopping.", max_results)
                break

            await asyncio.sleep(random.uniform(2.0, 5.0))

        # Fetch full descriptions for each listing
        for i, listing in enumerate(listings):
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

    async def _parse_card(self, card) -> JobListing | None:
        """Extract job data from a LinkedIn job card element.

        Args:
            card: Playwright Locator for a single job card.

        Returns:
            JobListing or None if required fields are missing.
        """
        try:
            # Title and URL
            title_el = card.locator("a.job-card-container__link")
            title = (await title_el.inner_text()).strip()
            href = await title_el.get_attribute("href") or ""
            job_url = f"https://www.linkedin.com{href.split('?')[0]}" if href.startswith("/") else href

            # Company
            company_el = card.locator("span.job-card-container__primary-description")
            company = (await company_el.inner_text()).strip() if await company_el.count() else "Unknown"

            # Location
            location_el = card.locator("li.job-card-container__metadata-item")
            location = (await location_el.first.inner_text()).strip() if await location_el.count() else ""

            if not title or not job_url:
                return None

            return JobListing(
                title=title,
                company=company,
                location=location,
                url=job_url,
                description="",  # populated by get_job_details
                source="linkedin",
            )
        except Exception as exc:
            logger.debug("Failed to parse LinkedIn card: %s", exc)
            return None

    async def get_job_details(self, url: str) -> JobListing:
        """Fetch full job details from a LinkedIn posting URL.

        Args:
            url: Direct URL to the LinkedIn job posting.

        Returns:
            JobListing with the complete description populated.
        """
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("div.jobs-description", timeout=10_000)
        except Exception:
            try:
                await page.wait_for_selector(
                    "div.description__text, div.show-more-less-html", timeout=10_000
                )
            except Exception:
                logger.warning("No description selector matched for %s", url)

        # Title
        title = ""
        for sel in ["h1.job-details-jobs-unified-top-card__job-title", "h1.top-card-layout__title", "h2.top-card-layout__title"]:
            el = page.locator(sel)
            if await el.count():
                title = (await el.first.inner_text()).strip()
                break

        # Company
        company = ""
        for sel in [
            "div.job-details-jobs-unified-top-card__company-name a",
            "a.topcard__org-name-link",
            "span.topcard__flavor",
        ]:
            el = page.locator(sel)
            if await el.count():
                company = (await el.first.inner_text()).strip()
                break

        # Location
        location = ""
        for sel in [
            "span.job-details-jobs-unified-top-card__bullet",
            "span.topcard__flavor--bullet",
        ]:
            el = page.locator(sel)
            if await el.count():
                location = (await el.first.inner_text()).strip()
                break

        # Full description
        description = ""
        for sel in [
            "div.jobs-description__content",
            "div.description__text",
            "div.show-more-less-html__markup",
        ]:
            el = page.locator(sel)
            if await el.count():
                description = (await el.first.inner_text()).strip()
                break

        # Salary (if shown)
        salary = None
        salary_el = page.locator("div.salary, span.salary")
        if await salary_el.count():
            salary = (await salary_el.first.inner_text()).strip()

        # Job type metadata
        job_type = None
        metadata_items = await page.locator(
            "li.job-details-jobs-unified-top-card__job-insight span"
        ).all()
        for item in metadata_items:
            text = (await item.inner_text()).strip().lower()
            if any(t in text for t in ["full-time", "part-time", "contract", "temporary", "internship"]):
                job_type = text
                break

        return JobListing(
            title=title or "Unknown Title",
            company=company or "Unknown Company",
            location=location,
            url=url,
            description=description,
            salary=salary,
            job_type=job_type,
            source="linkedin",
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
        """Close the browser and Playwright instance."""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
                self._page = None
            if self._pw:
                await self._pw.stop()
                self._pw = None
        except Exception as exc:
            logger.debug("Error during cleanup: %s", exc)
            self._browser = None
            self._page = None
            self._pw = None


async def main() -> None:
    """Standalone test: search LinkedIn and save results."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    scraper = LinkedInScraper()
    try:
        await scraper.login()
        logger.info("Login successful.")

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
