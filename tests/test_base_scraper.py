"""Tests for the base scraper interface and JobListing dataclass."""

import pytest

from src.scrapers.base_scraper import BaseScraper, JobListing


# ===================================================================
# JobListing — dataclass behavior
# ===================================================================

class TestJobListing:

    def test_required_fields(self):
        listing = JobListing(
            title="Software Engineer",
            company="Acme",
            location="Remote",
            url="https://example.com/job/1",
            description="Build stuff.",
        )
        assert listing.title == "Software Engineer"
        assert listing.company == "Acme"
        assert listing.location == "Remote"
        assert listing.url == "https://example.com/job/1"
        assert listing.description == "Build stuff."

    def test_optional_salary_default_none(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        assert listing.salary is None

    def test_optional_job_type_default_none(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        assert listing.job_type is None

    def test_optional_posted_date_default_none(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        assert listing.posted_date is None

    def test_default_source_empty(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        assert listing.source == ""

    def test_custom_salary(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
            salary="$120,000",
        )
        assert listing.salary == "$120,000"

    def test_custom_job_type(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
            job_type="full-time",
        )
        assert listing.job_type == "full-time"

    def test_custom_posted_date(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
            posted_date="3 days ago",
        )
        assert listing.posted_date == "3 days ago"

    def test_custom_source(self):
        listing = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
            source="indeed",
        )
        assert listing.source == "indeed"

    def test_all_fields_populated(self):
        listing = JobListing(
            title="ML Engineer",
            company="AI Corp",
            location="San Francisco",
            url="https://example.com/ml",
            description="Train models.",
            salary="$200k",
            job_type="full-time",
            posted_date="1 day ago",
            source="linkedin",
        )
        assert listing.title == "ML Engineer"
        assert listing.salary == "$200k"
        assert listing.source == "linkedin"

    def test_equality(self):
        a = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        b = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        assert a == b

    def test_inequality_different_title(self):
        a = JobListing(
            title="Dev", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        b = JobListing(
            title="QA", company="Co", location="NY",
            url="https://x.com", description="desc",
        )
        assert a != b

    def test_empty_strings_allowed(self):
        listing = JobListing(
            title="", company="", location="",
            url="", description="",
        )
        assert listing.title == ""


# ===================================================================
# BaseScraper — abstract base class
# ===================================================================

class TestBaseScraper:

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseScraper()

    def test_subclass_must_implement_search(self):
        class IncompleteScraper(BaseScraper):
            async def get_job_details(self, url):
                pass
            async def close(self):
                pass

        with pytest.raises(TypeError):
            IncompleteScraper()

    def test_subclass_must_implement_get_job_details(self):
        class IncompleteScraper(BaseScraper):
            async def search(self, query, location, **filters):
                return []
            async def close(self):
                pass

        with pytest.raises(TypeError):
            IncompleteScraper()

    def test_subclass_must_implement_close(self):
        class IncompleteScraper(BaseScraper):
            async def search(self, query, location, **filters):
                return []
            async def get_job_details(self, url):
                pass

        with pytest.raises(TypeError):
            IncompleteScraper()

    def test_complete_subclass_instantiates(self):
        class CompleteScraper(BaseScraper):
            async def search(self, query, location, **filters):
                return []
            async def get_job_details(self, url):
                return JobListing(
                    title="T", company="C", location="L",
                    url=url, description="D",
                )
            async def close(self):
                pass

        scraper = CompleteScraper()
        assert isinstance(scraper, BaseScraper)

    @pytest.mark.asyncio
    async def test_complete_subclass_search_returns_list(self):
        class CompleteScraper(BaseScraper):
            async def search(self, query, location, **filters):
                return [
                    JobListing(
                        title="Dev", company="Co", location=location,
                        url="https://x.com", description="desc",
                    )
                ]
            async def get_job_details(self, url):
                return JobListing(
                    title="T", company="C", location="L",
                    url=url, description="D",
                )
            async def close(self):
                pass

        scraper = CompleteScraper()
        results = await scraper.search("python", "remote")
        assert len(results) == 1
        assert results[0].title == "Dev"

    @pytest.mark.asyncio
    async def test_complete_subclass_get_job_details(self):
        class CompleteScraper(BaseScraper):
            async def search(self, query, location, **filters):
                return []
            async def get_job_details(self, url):
                return JobListing(
                    title="Detail", company="Co", location="NY",
                    url=url, description="Full description",
                )
            async def close(self):
                pass

        scraper = CompleteScraper()
        detail = await scraper.get_job_details("https://example.com/job/1")
        assert detail.description == "Full description"
        assert detail.url == "https://example.com/job/1"

    @pytest.mark.asyncio
    async def test_complete_subclass_close(self):
        closed = False

        class CompleteScraper(BaseScraper):
            async def search(self, query, location, **filters):
                return []
            async def get_job_details(self, url):
                return JobListing(
                    title="T", company="C", location="L",
                    url=url, description="D",
                )
            async def close(self):
                nonlocal closed
                closed = True

        scraper = CompleteScraper()
        await scraper.close()
        assert closed is True
