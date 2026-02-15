"""Tests for database models and the ApplicationRepository."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from src.database.models import Application, Base, JobPosting
from src.database.db import ApplicationRepository


# ---------------------------------------------------------------------------
# Fixtures — every test gets a fresh in-memory SQLite database
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as sess:
        yield sess


@pytest.fixture()
def repo():
    repository = ApplicationRepository(db_url="sqlite:///:memory:")
    repository.create_tables()
    yield repository
    repository.close()


def _make_posting(repo: ApplicationRepository, **overrides) -> JobPosting:
    """Helper to insert a job posting with sensible defaults."""
    defaults = {
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "url": "https://example.com/jobs/1",
        "description": "Build things.",
        "source": "indeed",
    }
    defaults.update(overrides)
    return repo.save_job_posting(**defaults)


# ===================================================================
# Models — schema
# ===================================================================

class TestSchema:

    def test_tables_created(self, engine):
        tables = inspect(engine).get_table_names()
        assert "job_postings" in tables
        assert "applications" in tables

    def test_job_posting_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("job_postings")}
        expected = {
            "id", "title", "company", "location", "url",
            "description", "salary", "job_type", "source", "scraped_at",
        }
        assert expected.issubset(cols)

    def test_application_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("applications")}
        expected = {
            "id", "job_posting_id", "status", "resume_path",
            "cover_letter_path", "match_score", "notes",
            "applied_at", "created_at", "updated_at",
        }
        assert expected.issubset(cols)


# ===================================================================
# Models — defaults and relationships
# ===================================================================

class TestModelDefaults:

    def test_job_posting_scraped_at_auto(self, session):
        posting = JobPosting(
            title="Dev", company="Co", url="https://x.com/1", description=""
        )
        session.add(posting)
        session.commit()
        session.refresh(posting)

        assert posting.scraped_at is not None
        assert isinstance(posting.scraped_at, datetime)

    def test_application_default_status(self, session):
        posting = JobPosting(
            title="Dev", company="Co", url="https://x.com/2", description=""
        )
        session.add(posting)
        session.commit()

        app = Application(job_posting_id=posting.id)
        session.add(app)
        session.commit()
        session.refresh(app)

        assert app.status == "saved"

    def test_application_created_at_auto(self, session):
        posting = JobPosting(
            title="Dev", company="Co", url="https://x.com/3", description=""
        )
        session.add(posting)
        session.commit()

        app = Application(job_posting_id=posting.id)
        session.add(app)
        session.commit()
        session.refresh(app)

        assert app.created_at is not None
        assert isinstance(app.created_at, datetime)

    def test_relationship_posting_to_applications(self, session):
        posting = JobPosting(
            title="Dev", company="Co", url="https://x.com/4", description=""
        )
        session.add(posting)
        session.commit()

        app = Application(job_posting_id=posting.id)
        session.add(app)
        session.commit()
        session.refresh(posting)

        assert len(posting.applications) == 1
        assert posting.applications[0].id == app.id

    def test_relationship_application_to_posting(self, session):
        posting = JobPosting(
            title="Dev", company="Co", url="https://x.com/5", description=""
        )
        session.add(posting)
        session.commit()

        app = Application(job_posting_id=posting.id)
        session.add(app)
        session.commit()
        session.refresh(app)

        assert app.job_posting.id == posting.id
        assert app.job_posting.title == "Dev"


# ===================================================================
# Repository — create_tables
# ===================================================================

class TestCreateTables:

    def test_create_tables_idempotent(self):
        repo = ApplicationRepository(db_url="sqlite:///:memory:")
        repo.create_tables()
        repo.create_tables()  # should not raise
        repo.close()


# ===================================================================
# Repository — save_job_posting
# ===================================================================

class TestSaveJobPosting:

    def test_insert_new_posting(self, repo):
        posting = _make_posting(repo)

        assert posting.id is not None
        assert posting.title == "Software Engineer"
        assert posting.company == "Acme Corp"
        assert posting.url == "https://example.com/jobs/1"
        assert posting.source == "indeed"

    def test_insert_with_all_fields(self, repo):
        posting = _make_posting(
            repo,
            salary="$120k",
            job_type="full-time",
            url="https://example.com/jobs/full",
        )

        assert posting.salary == "$120k"
        assert posting.job_type == "full-time"

    def test_upsert_updates_existing_by_url(self, repo):
        url = "https://example.com/jobs/upsert"
        posting1 = _make_posting(repo, url=url, title="V1")
        posting2 = _make_posting(repo, url=url, title="V2", company="NewCo")

        assert posting1.id == posting2.id
        assert posting2.title == "V2"
        assert posting2.company == "NewCo"

    def test_different_urls_create_separate_postings(self, repo):
        p1 = _make_posting(repo, url="https://a.com/1")
        p2 = _make_posting(repo, url="https://a.com/2")

        assert p1.id != p2.id

    def test_scraped_at_populated(self, repo):
        posting = _make_posting(repo)

        assert posting.scraped_at is not None


# ===================================================================
# Repository — create_application
# ===================================================================

class TestCreateApplication:

    def test_create_application(self, repo):
        posting = _make_posting(repo)
        app = repo.create_application(posting.id)

        assert app.id is not None
        assert app.job_posting_id == posting.id
        assert app.status == "saved"

    def test_multiple_applications_for_same_posting(self, repo):
        posting = _make_posting(repo)
        app1 = repo.create_application(posting.id)
        app2 = repo.create_application(posting.id)

        assert app1.id != app2.id
        assert app1.job_posting_id == app2.job_posting_id


# ===================================================================
# Repository — update_application_status
# ===================================================================

class TestUpdateApplicationStatus:

    def test_update_to_applied(self, repo):
        posting = _make_posting(repo)
        app = repo.create_application(posting.id)

        updated = repo.update_application_status(app.id, "applied")

        assert updated.status == "applied"
        assert updated.applied_at is not None
        assert isinstance(updated.applied_at, datetime)

    def test_update_to_interviewing(self, repo):
        posting = _make_posting(repo)
        app = repo.create_application(posting.id)

        updated = repo.update_application_status(app.id, "interviewing")

        assert updated.status == "interviewing"
        assert updated.applied_at is None  # only set for "applied"

    def test_update_to_rejected(self, repo):
        posting = _make_posting(repo)
        app = repo.create_application(posting.id)

        updated = repo.update_application_status(app.id, "rejected")

        assert updated.status == "rejected"

    def test_update_to_offered(self, repo):
        posting = _make_posting(repo)
        app = repo.create_application(posting.id)

        updated = repo.update_application_status(app.id, "offered")

        assert updated.status == "offered"

    def test_sequential_status_updates(self, repo):
        posting = _make_posting(repo)
        app = repo.create_application(posting.id)

        repo.update_application_status(app.id, "resume_tailored")
        repo.update_application_status(app.id, "cover_letter_done")
        updated = repo.update_application_status(app.id, "applied")

        assert updated.status == "applied"
        assert updated.applied_at is not None

    def test_raises_for_nonexistent_application(self, repo):
        with pytest.raises(ValueError, match="not found"):
            repo.update_application_status(9999, "applied")


# ===================================================================
# Repository — list_applications
# ===================================================================

class TestListApplications:

    def test_list_all(self, repo):
        p1 = _make_posting(repo, url="https://a.com/1")
        p2 = _make_posting(repo, url="https://a.com/2")
        repo.create_application(p1.id)
        repo.create_application(p2.id)

        apps = repo.list_applications()

        assert len(apps) == 2

    def test_list_empty(self, repo):
        apps = repo.list_applications()
        assert apps == []

    def test_filter_by_status(self, repo):
        p1 = _make_posting(repo, url="https://a.com/1")
        p2 = _make_posting(repo, url="https://a.com/2")
        app1 = repo.create_application(p1.id)
        repo.create_application(p2.id)

        repo.update_application_status(app1.id, "applied")

        applied = repo.list_applications(status="applied")
        saved = repo.list_applications(status="saved")

        assert len(applied) == 1
        assert applied[0].id == app1.id
        assert len(saved) == 1

    def test_filter_returns_empty_for_no_match(self, repo):
        posting = _make_posting(repo)
        repo.create_application(posting.id)

        apps = repo.list_applications(status="offered")

        assert apps == []

    def test_filter_none_returns_all(self, repo):
        posting = _make_posting(repo)
        repo.create_application(posting.id)

        apps = repo.list_applications(status=None)

        assert len(apps) == 1


# ===================================================================
# Repository — close
# ===================================================================

class TestClose:

    def test_close_does_not_raise(self, repo):
        repo.close()
        # calling close via fixture teardown again is fine too

    def test_close_on_fresh_repo(self):
        r = ApplicationRepository(db_url="sqlite:///:memory:")
        r.close()  # should not raise
