"""End-to-end application submission orchestrator.

Combines form filling, resume upload, and status tracking into a single
workflow that submits a job application and records the result.
"""

import logging
from pathlib import Path

from src.database.db import ApplicationRepository
from .form_filler import FormFiller, FormField

logger = logging.getLogger("job_app_bot.automation.submitter")


class ApplicationSubmitter:
    """Orchestrates the full application submission flow.

    Ties together the FormFiller for browser interaction and the
    ApplicationRepository for persisting status updates.

    Usage:
        submitter = ApplicationSubmitter()
        await submitter.submit(
            application_id=1,
            url="https://example.com/apply",
            fields=[FormField(selector="#name", value="Jane Doe")],
            resume_path="output/resume.docx",
        )
        await submitter.close()
    """

    def __init__(self, headless: bool = False) -> None:
        self._filler = FormFiller(headless=headless)
        self._repo = ApplicationRepository()

    async def launch(self) -> None:
        """Launch the browser for form filling."""
        await self._filler.launch()

    async def submit(
        self,
        application_id: int,
        url: str,
        fields: list[FormField],
        resume_path: str | None = None,
        submit_selector: str = "button[type='submit']",
    ) -> bool:
        """Fill and submit a job application, then update tracking status.

        Args:
            application_id: Database ID of the Application record.
            url: URL of the job application page.
            fields: Form fields to fill in.
            resume_path: Optional path to the resume file to upload.
            submit_selector: CSS selector for the submit button.

        Returns:
            True if submission succeeded, False otherwise.
        """
        if resume_path and not Path(resume_path).exists():
            logger.error("Resume file not found: %s", resume_path)
            return False

        try:
            await self._filler.fill_application(url, fields, resume_path)
            await self._filler.submit(submit_selector)
            self._repo.update_application_status(application_id, "applied")
            logger.info("Application %d submitted successfully.", application_id)
            return True
        except Exception as exc:
            logger.error("Failed to submit application %d: %s", application_id, exc)
            return False

    async def close(self) -> None:
        """Close the browser and database connection."""
        await self._filler.close()
        self._repo.close()
