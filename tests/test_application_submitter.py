"""Tests for the ApplicationSubmitter orchestrator."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.automation.application_submitter import ApplicationSubmitter
from src.automation.form_filler import FormField


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submitter() -> ApplicationSubmitter:
    """Create an ApplicationSubmitter with mocked filler and repo."""
    with patch("src.automation.application_submitter.ApplicationRepository") as MockRepo:
        submitter = ApplicationSubmitter(headless=True)
        submitter._filler = AsyncMock()
        submitter._repo = MockRepo.return_value
    return submitter


SAMPLE_URL = "https://example.com/apply"
SAMPLE_FIELDS = [
    FormField(selector="#name", value="Jane Doe"),
    FormField(selector="#email", value="jane@example.com"),
]


# ===================================================================
# submit — happy path
# ===================================================================

class TestSubmitSuccess:

    @pytest.mark.asyncio
    async def test_submit_fills_and_submits(self):
        submitter = _make_submitter()

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
        )

        assert result is True
        submitter._filler.fill_application.assert_awaited_once_with(
            SAMPLE_URL, SAMPLE_FIELDS, None
        )
        submitter._filler.submit.assert_awaited_once_with("button[type='submit']")

    @pytest.mark.asyncio
    async def test_submit_updates_status_to_applied(self):
        submitter = _make_submitter()

        await submitter.submit(application_id=42, url=SAMPLE_URL, fields=SAMPLE_FIELDS)

        submitter._repo.update_application_status.assert_called_once_with(42, "applied")

    @pytest.mark.asyncio
    async def test_submit_with_custom_selector(self):
        submitter = _make_submitter()

        await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
            submit_selector="#custom-submit",
        )

        submitter._filler.submit.assert_awaited_once_with("#custom-submit")

    @pytest.mark.asyncio
    async def test_submit_passes_resume_path(self, tmp_path):
        resume = tmp_path / "resume.docx"
        resume.write_text("fake resume content")

        submitter = _make_submitter()

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
            resume_path=str(resume),
        )

        assert result is True
        submitter._filler.fill_application.assert_awaited_once_with(
            SAMPLE_URL, SAMPLE_FIELDS, str(resume)
        )

    @pytest.mark.asyncio
    async def test_submit_without_resume(self):
        submitter = _make_submitter()

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
            resume_path=None,
        )

        assert result is True
        submitter._filler.fill_application.assert_awaited_once_with(
            SAMPLE_URL, SAMPLE_FIELDS, None
        )


# ===================================================================
# submit — resume file missing
# ===================================================================

class TestSubmitResumeMissing:

    @pytest.mark.asyncio
    async def test_returns_false_when_resume_not_found(self):
        submitter = _make_submitter()

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
            resume_path="/nonexistent/path/resume.pdf",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_does_not_call_filler_when_resume_missing(self):
        submitter = _make_submitter()

        await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
            resume_path="/nonexistent/path/resume.pdf",
        )

        submitter._filler.fill_application.assert_not_awaited()
        submitter._filler.submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_update_status_when_resume_missing(self):
        submitter = _make_submitter()

        await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
            resume_path="/nonexistent/path/resume.pdf",
        )

        submitter._repo.update_application_status.assert_not_called()


# ===================================================================
# submit — filler raises exception
# ===================================================================

class TestSubmitFailure:

    @pytest.mark.asyncio
    async def test_returns_false_on_fill_error(self):
        submitter = _make_submitter()
        submitter._filler.fill_application.side_effect = RuntimeError("page crashed")

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_does_not_update_status_on_fill_error(self):
        submitter = _make_submitter()
        submitter._filler.fill_application.side_effect = RuntimeError("page crashed")

        await submitter.submit(application_id=1, url=SAMPLE_URL, fields=SAMPLE_FIELDS)

        submitter._repo.update_application_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_on_submit_click_error(self):
        submitter = _make_submitter()
        submitter._filler.submit.side_effect = TimeoutError("submit button not found")

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_status_update_error(self):
        submitter = _make_submitter()
        submitter._repo.update_application_status.side_effect = ValueError("not found")

        result = await submitter.submit(
            application_id=1,
            url=SAMPLE_URL,
            fields=SAMPLE_FIELDS,
        )

        assert result is False


# ===================================================================
# launch
# ===================================================================

class TestLaunch:

    @pytest.mark.asyncio
    async def test_launch_delegates_to_filler(self):
        submitter = _make_submitter()

        await submitter.launch()

        submitter._filler.launch.assert_awaited_once()


# ===================================================================
# close
# ===================================================================

class TestClose:

    @pytest.mark.asyncio
    async def test_close_shuts_down_filler_and_repo(self):
        submitter = _make_submitter()

        await submitter.close()

        submitter._filler.close.assert_awaited_once()
        submitter._repo.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_calls_repo_even_if_filler_succeeds(self):
        submitter = _make_submitter()

        await submitter.close()

        # Both should always be called
        assert submitter._filler.close.await_count == 1
        assert submitter._repo.close.call_count == 1


# ===================================================================
# __init__
# ===================================================================

class TestInit:

    def test_headless_passed_to_filler(self):
        with patch("src.automation.application_submitter.ApplicationRepository"):
            with patch("src.automation.application_submitter.FormFiller") as MockFiller:
                ApplicationSubmitter(headless=True)
                MockFiller.assert_called_once_with(headless=True)

    def test_default_headless_is_false(self):
        with patch("src.automation.application_submitter.ApplicationRepository"):
            with patch("src.automation.application_submitter.FormFiller") as MockFiller:
                ApplicationSubmitter()
                MockFiller.assert_called_once_with(headless=False)

    def test_creates_repository(self):
        with patch("src.automation.application_submitter.ApplicationRepository") as MockRepo:
            with patch("src.automation.application_submitter.FormFiller"):
                submitter = ApplicationSubmitter()
                MockRepo.assert_called_once()
                assert submitter._repo is MockRepo.return_value
