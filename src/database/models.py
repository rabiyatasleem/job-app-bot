"""SQLAlchemy models for tracking job applications."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class JobPosting(Base):
    """A scraped job posting."""

    __tablename__ = "job_postings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    company = Column(String(256), nullable=False)
    location = Column(String(256))
    url = Column(String(2048), unique=True, nullable=False)
    description = Column(Text)
    salary = Column(String(128))
    job_type = Column(String(64))
    source = Column(String(64))  # linkedin, indeed
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    applications = relationship("Application", back_populates="job_posting")


class Application(Base):
    """A job application the user has submitted or plans to submit."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_posting_id = Column(Integer, ForeignKey("job_postings.id"), nullable=False)
    status = Column(
        Enum(
            "saved",
            "resume_tailored",
            "cover_letter_done",
            "applied",
            "interviewing",
            "offered",
            "rejected",
            "withdrawn",
            name="application_status",
        ),
        default="saved",
    )
    resume_path = Column(String(512))
    cover_letter_path = Column(String(512))
    match_score = Column(Float)
    notes = Column(Text)
    applied_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    job_posting = relationship("JobPosting", back_populates="applications")
