"""LinkedIn job scraper using Playwright for browser automation."""

import asyncio
import logging
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Browser, Page

from config import settings
from .base_scraper import BaseScraper, JobListing

logger = logging.getLogger("job_app_bot.scrapers.linkedin")

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

    async def _ensure_browser(self) -> Page:
        """Launch browser and return a page, reusing if already open."""
        if self._page is None:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
        return self._page

    async def login(self) -> None:
        """Authenticate with LinkedIn using credentials from settings."""
        page = await self._ensure_browser()
        await page.goto("https://www.linkedin.com/login")
        await page.fill("#username", settings.linkedin_email)
        await page.fill("#password", settings.linkedin_password)
        await page.click("[type=submit]")
        await page.wait_for_url("**/feed/**", timeout=30_000)

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
            await asyncio.sleep(0.8)

    async def search(self, query: str, location: str, **filters) -> list[JobListing]:
        """Search LinkedIn jobs with pagination.

        Args:
            query: Job title or keywords.
            location: City/state or 'remote'.
            **filters: Optional filters — experience_level, job_type, work_mode,
                       time_posted.

        Returns:
            List of JobListing results.
        """
        page = await self._ensure_browser()
        listings: list[JobListing] = []

        for page_num in range(settings.max_pages_per_search):
            url = self._build_search_url(query, location, start=page_num * 25, **filters)
            await page.goto(url, wait_until="domcontentloaded")

            # Wait for job cards to appear
            try:
                await page.wait_for_selector(
                    "div.job-card-container", timeout=10_000
                )
            except Exception:
                logger.debug("No job cards found on page %d, stopping.", page_num)
                break

            await self._scroll_job_list(page)

            cards = await page.locator("div.job-card-container").all()
            if not cards:
                break

            for card in cards:
                listing = await self._parse_card(card)
                if listing:
                    listings.append(listing)

            logger.info("Page %d: collected %d cards", page_num + 1, len(cards))
            await asyncio.sleep(settings.scrape_delay_seconds)

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
            # Fallback selector for different page layouts
            await page.wait_for_selector(
                "div.description__text, div.show-more-less-html", timeout=10_000
            )

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

    async def close(self) -> None:
        """Close the browser and Playwright instance."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
