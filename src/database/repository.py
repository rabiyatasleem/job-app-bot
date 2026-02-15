"""Repository layer for querying and persisting application data."""

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from config import settings
from .models import Application, Base, JobPosting


class ApplicationRepository:
    """CRUD operations for job postings and applications.

    Wraps SQLAlchemy to provide a clean interface for the rest of the app.

    Usage:
        repo = ApplicationRepository()
        repo.create_tables()
        posting = repo.save_job_posting(title=..., company=..., url=..., ...)
        app = repo.create_application(posting.id)
    """

    def __init__(self, db_url: str | None = None) -> None:
        self._engine = create_engine(db_url or settings.database_url)
        self._session = Session(self._engine)

    def create_tables(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self._engine)

    def save_job_posting(self, **kwargs) -> JobPosting:
        """Insert or update a job posting (upsert by URL).

        Args:
            **kwargs: Fields matching JobPosting columns.

        Returns:
            The persisted JobPosting instance.
        """
        existing = self._session.execute(
            select(JobPosting).where(JobPosting.url == kwargs.get("url"))
        ).scalar_one_or_none()

        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            posting = existing
        else:
            posting = JobPosting(**kwargs)
            self._session.add(posting)

        self._session.commit()
        self._session.refresh(posting)
        return posting

    def create_application(self, job_posting_id: int) -> Application:
        """Create a new application entry for a job posting.

        Args:
            job_posting_id: ID of the associated JobPosting.

        Returns:
            The new Application instance.
        """
        app = Application(job_posting_id=job_posting_id)
        self._session.add(app)
        self._session.commit()
        self._session.refresh(app)
        return app

    def update_application_status(self, application_id: int, status: str) -> Application:
        """Update the status of an existing application.

        Args:
            application_id: ID of the Application to update.
            status: New status value.

        Returns:
            The updated Application instance.
        """
        app = self._session.get(Application, application_id)
        if not app:
            raise ValueError(f"Application {application_id} not found")
        app.status = status
        if status == "applied":
            app.applied_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(app)
        return app

    def list_applications(self, status: str | None = None) -> list[Application]:
        """List applications, optionally filtered by status.

        Args:
            status: If provided, only return applications with this status.

        Returns:
            List of Application instances.
        """
        stmt = select(Application)
        if status:
            stmt = stmt.where(Application.status == status)
        return list(self._session.scalars(stmt).all())

    def close(self) -> None:
        """Close the database session."""
        self._session.close()
