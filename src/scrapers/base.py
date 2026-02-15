"""Base scraper interface that all job board scrapers implement."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class JobListing:
    """Normalized job listing returned by all scrapers."""

    title: str
    company: str
    location: str
    url: str
    description: str
    salary: str | None = None
    job_type: str | None = None  # full-time, part-time, contract
    posted_date: str | None = None
    source: str = ""  # linkedin, indeed, etc.


class BaseScraper(ABC):
    """Abstract base class for job board scrapers."""

    @abstractmethod
    async def search(self, query: str, location: str, **filters) -> list[JobListing]:
        """Search for jobs matching the given criteria.

        Args:
            query: Job title or keywords.
            location: City, state, or 'remote'.
            **filters: Board-specific filters (experience level, job type, etc.).

        Returns:
            List of normalized JobListing results.
        """

    @abstractmethod
    async def get_job_details(self, url: str) -> JobListing:
        """Fetch full details for a single job posting.

        Args:
            url: Direct URL to the job posting.

        Returns:
            JobListing with the complete description populated.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any resources (browser pages, HTTP clients, etc.)."""
