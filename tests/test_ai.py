"""Tests for the AI modules — ResumeCustomizer, customize_resume, and CoverLetterGenerator."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from src.ai.resume_customizer import (
    ResumeCustomizer,
    customize_resume,
    _CUSTOMIZE_SYSTEM_PROMPT,
)
from src.ai.cover_letter_generator import CoverLetterGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_message(text: str):
    """Build a fake Anthropic Message response with the given text."""
    block = MagicMock()
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


SAMPLE_RESUME = "# Jane Doe\n\n- 5 years Python\n- Built REST APIs"
SAMPLE_JOB = "We need a senior Python developer with REST API experience."
SAMPLE_COMPANY = "Acme Corp is a fast-growing SaaS startup."


# ===================================================================
# ResumeCustomizer — __init__
# ===================================================================

class TestResumeCustomizerInit:

    def test_creates_async_client(self):
        with patch("src.ai.resume_customizer.anthropic.AsyncAnthropic") as MockClient:
            customizer = ResumeCustomizer()
            MockClient.assert_called_once_with(api_key="test-key-not-real")
            assert customizer._client is MockClient.return_value

    def test_system_prompt_defined(self):
        assert "expert resume writer" in ResumeCustomizer.SYSTEM_PROMPT


# ===================================================================
# ResumeCustomizer — customize
# ===================================================================

class TestCustomize:

    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("src.ai.resume_customizer.anthropic.AsyncAnthropic"):
            self.customizer = ResumeCustomizer()
            self.customizer._client = AsyncMock()
        yield

    @pytest.mark.asyncio
    async def test_returns_tailored_resume_text(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("# Tailored Resume\n\n- Expert Python dev")
        )

        result = await self.customizer.customize(SAMPLE_RESUME, SAMPLE_JOB)

        assert result == "# Tailored Resume\n\n- Expert Python dev"

    @pytest.mark.asyncio
    async def test_passes_system_prompt(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await self.customizer.customize(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.customizer._client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == ResumeCustomizer.SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_passes_model_and_max_tokens(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await self.customizer.customize(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.customizer._client.messages.create.call_args.kwargs
        assert call_kwargs["model"] is not None
        assert isinstance(call_kwargs["max_tokens"], int)

    @pytest.mark.asyncio
    async def test_user_message_contains_resume_and_job(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await self.customizer.customize(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.customizer._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert SAMPLE_RESUME in user_content
        assert SAMPLE_JOB in user_content
        assert "## Base Resume" in user_content
        assert "## Job Description" in user_content

    @pytest.mark.asyncio
    async def test_user_message_role_is_user(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await self.customizer.customize(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.customizer._client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_api_error_propagates(self):
        self.customizer._client.messages.create = AsyncMock(
            side_effect=Exception("API rate limited")
        )

        with pytest.raises(Exception, match="API rate limited"):
            await self.customizer.customize(SAMPLE_RESUME, SAMPLE_JOB)


# ===================================================================
# ResumeCustomizer — suggest_skills
# ===================================================================

class TestSuggestSkills:

    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("src.ai.resume_customizer.anthropic.AsyncAnthropic"):
            self.customizer = ResumeCustomizer()
            self.customizer._client = AsyncMock()
        yield

    @pytest.mark.asyncio
    async def test_returns_list_of_skills(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("Python\nREST APIs\nSQL")
        )

        result = await self.customizer.suggest_skills(
            SAMPLE_JOB, ["Python", "SQL", "REST APIs", "Go"]
        )

        assert result == ["Python", "REST APIs", "SQL"]

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_skills(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("  Python  \n  SQL  \n")
        )

        result = await self.customizer.suggest_skills(SAMPLE_JOB, ["Python", "SQL"])

        assert result == ["Python", "SQL"]

    @pytest.mark.asyncio
    async def test_skips_empty_lines(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("Python\n\n\nSQL\n\n")
        )

        result = await self.customizer.suggest_skills(SAMPLE_JOB, ["Python", "SQL"])

        assert result == ["Python", "SQL"]

    @pytest.mark.asyncio
    async def test_user_message_contains_job_and_skills(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("Python")
        )

        await self.customizer.suggest_skills(SAMPLE_JOB, ["Python", "Go"])

        call_kwargs = self.customizer._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert SAMPLE_JOB in user_content
        assert "Python, Go" in user_content

    @pytest.mark.asyncio
    async def test_max_tokens_is_1024(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("Python")
        )

        await self.customizer.suggest_skills(SAMPLE_JOB, ["Python"])

        call_kwargs = self.customizer._client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self):
        self.customizer._client.messages.create = AsyncMock(
            return_value=_mock_message("")
        )

        result = await self.customizer.suggest_skills(SAMPLE_JOB, ["Python"])

        assert result == []


# ===================================================================
# CoverLetterGenerator — __init__
# ===================================================================

class TestCoverLetterGeneratorInit:

    def test_creates_async_client(self):
        with patch("src.ai.cover_letter_generator.anthropic.AsyncAnthropic") as MockClient:
            generator = CoverLetterGenerator()
            MockClient.assert_called_once_with(api_key="test-key-not-real")
            assert generator._client is MockClient.return_value

    def test_system_prompt_defined(self):
        assert "cover letter" in CoverLetterGenerator.SYSTEM_PROMPT.lower()


# ===================================================================
# CoverLetterGenerator — generate
# ===================================================================

class TestGenerate:

    @pytest.fixture(autouse=True)
    def setup(self):
        with patch("src.ai.cover_letter_generator.anthropic.AsyncAnthropic"):
            self.generator = CoverLetterGenerator()
            self.generator._client = AsyncMock()
        yield

    @pytest.mark.asyncio
    async def test_returns_cover_letter_text(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("Dear Hiring Manager,\n\nI am excited...")
        )

        result = await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB)

        assert result == "Dear Hiring Manager,\n\nI am excited..."

    @pytest.mark.asyncio
    async def test_passes_system_prompt(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == CoverLetterGenerator.SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_user_message_contains_profile_and_job(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert SAMPLE_RESUME in user_content
        assert SAMPLE_JOB in user_content
        assert "## Candidate Profile" in user_content
        assert "## Job Description" in user_content

    @pytest.mark.asyncio
    async def test_default_tone_is_professional(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Tone: professional" in user_content

    @pytest.mark.asyncio
    async def test_custom_tone(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB, tone="enthusiastic")

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "Tone: enthusiastic" in user_content

    @pytest.mark.asyncio
    async def test_company_info_included_when_provided(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(
            SAMPLE_RESUME, SAMPLE_JOB, company_info=SAMPLE_COMPANY
        )

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "## Company Info" in user_content
        assert SAMPLE_COMPANY in user_content

    @pytest.mark.asyncio
    async def test_company_info_omitted_when_empty(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB, company_info="")

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "## Company Info" not in user_content

    @pytest.mark.asyncio
    async def test_passes_model_and_max_tokens(self):
        self.generator._client.messages.create = AsyncMock(
            return_value=_mock_message("letter")
        )

        await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.generator._client.messages.create.call_args.kwargs
        assert call_kwargs["model"] is not None
        assert isinstance(call_kwargs["max_tokens"], int)

    @pytest.mark.asyncio
    async def test_api_error_propagates(self):
        self.generator._client.messages.create = AsyncMock(
            side_effect=Exception("service unavailable")
        )

        with pytest.raises(Exception, match="service unavailable"):
            await self.generator.generate(SAMPLE_RESUME, SAMPLE_JOB)


# ===================================================================
# customize_resume (standalone function)
# ===================================================================

class TestCustomizeResume:
    """Tests for the standalone customize_resume function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_client = AsyncMock()
        self.patcher = patch(
            "src.ai.resume_customizer.anthropic.AsyncAnthropic",
            return_value=self.mock_client,
        )
        self.MockAnthropic = self.patcher.start()
        yield
        self.patcher.stop()

    # --- Success path ---

    @pytest.mark.asyncio
    async def test_returns_customized_text(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("Tailored resume content")
        )

        result = await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        assert result == "Tailored resume content"

    @pytest.mark.asyncio
    async def test_creates_client_with_api_key(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        self.MockAnthropic.assert_called_once_with(api_key="test-key-not-real")

    @pytest.mark.asyncio
    async def test_passes_system_prompt(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == _CUSTOMIZE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_system_prompt_mentions_ats(self):
        assert "ATS" in _CUSTOMIZE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_system_prompt_mentions_truthful(self):
        assert "truthful" in _CUSTOMIZE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_user_message_contains_resume_and_job(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert SAMPLE_RESUME in user_content
        assert SAMPLE_JOB in user_content

    @pytest.mark.asyncio
    async def test_user_message_has_section_headers(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "## Base Resume" in user_content
        assert "## Job Description" in user_content

    @pytest.mark.asyncio
    async def test_user_message_role_is_user(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_passes_model_from_settings(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] is not None

    @pytest.mark.asyncio
    async def test_passes_max_tokens_from_settings(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        call_kwargs = self.mock_client.messages.create.call_args.kwargs
        assert isinstance(call_kwargs["max_tokens"], int)

    @pytest.mark.asyncio
    async def test_calls_api_once_on_success(self):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("resume")
        )

        await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        assert self.mock_client.messages.create.call_count == 1

    # --- Retry behavior ---

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_api_error(self, mock_sleep):
        self.mock_client.messages.create = AsyncMock(
            side_effect=[
                anthropic.APIError(
                    message="rate limited",
                    request=MagicMock(),
                    body=None,
                ),
                _mock_message("recovered resume"),
            ]
        )

        result = await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        assert result == "recovered resume"
        assert self.mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_up_to_max_then_raises(self, mock_sleep):
        api_error = anthropic.APIError(
            message="server error",
            request=MagicMock(),
            body=None,
        )
        self.mock_client.messages.create = AsyncMock(side_effect=api_error)

        with pytest.raises(anthropic.APIError):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB, retries=3)

        assert self.mock_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_custom_retries_count(self, mock_sleep):
        api_error = anthropic.APIError(
            message="error",
            request=MagicMock(),
            body=None,
        )
        self.mock_client.messages.create = AsyncMock(side_effect=api_error)

        with pytest.raises(anthropic.APIError):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB, retries=2)

        assert self.mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_exponential_backoff_delays(self, mock_sleep):
        api_error = anthropic.APIError(
            message="error",
            request=MagicMock(),
            body=None,
        )
        self.mock_client.messages.create = AsyncMock(side_effect=api_error)

        with pytest.raises(anthropic.APIError):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB, retries=3)

        sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_args == [2, 4, 8]

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_succeeds_on_third_attempt(self, mock_sleep):
        api_error = anthropic.APIError(
            message="error",
            request=MagicMock(),
            body=None,
        )
        self.mock_client.messages.create = AsyncMock(
            side_effect=[api_error, api_error, _mock_message("third time")]
        )

        result = await customize_resume(SAMPLE_RESUME, SAMPLE_JOB, retries=3)

        assert result == "third time"
        assert self.mock_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_non_api_error_not_retried(self):
        self.mock_client.messages.create = AsyncMock(
            side_effect=ValueError("bad input")
        )

        with pytest.raises(ValueError, match="bad input"):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        assert self.mock_client.messages.create.call_count == 1

    # --- Logging ---

    @pytest.mark.asyncio
    async def test_logs_info_on_success(self, caplog):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("customized")
        )

        with caplog.at_level(logging.INFO, logger="job_app_bot.ai.resume_customizer"):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        messages = [r.message for r in caplog.records]
        assert any("attempt 1/3" in m for m in messages)
        assert any("successfully" in m for m in messages)

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_logs_warning_on_retry(self, mock_sleep, caplog):
        api_error = anthropic.APIError(
            message="rate limited",
            request=MagicMock(),
            body=None,
        )
        self.mock_client.messages.create = AsyncMock(
            side_effect=[api_error, _mock_message("ok")]
        )

        with caplog.at_level(logging.WARNING, logger="job_app_bot.ai.resume_customizer"):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("attempt 1/3" in w for w in warnings)

    @pytest.mark.asyncio
    @patch("src.ai.resume_customizer.asyncio.sleep", new_callable=AsyncMock)
    async def test_logs_error_when_exhausted(self, mock_sleep, caplog):
        api_error = anthropic.APIError(
            message="error",
            request=MagicMock(),
            body=None,
        )
        self.mock_client.messages.create = AsyncMock(side_effect=api_error)

        with caplog.at_level(logging.ERROR, logger="job_app_bot.ai.resume_customizer"):
            with pytest.raises(anthropic.APIError):
                await customize_resume(SAMPLE_RESUME, SAMPLE_JOB, retries=2)

        errors = [r.message for r in caplog.records if r.levelno == logging.ERROR]
        assert any("exhausted" in e for e in errors)

    @pytest.mark.asyncio
    async def test_logs_character_count_on_success(self, caplog):
        self.mock_client.messages.create = AsyncMock(
            return_value=_mock_message("x" * 42)
        )

        with caplog.at_level(logging.INFO, logger="job_app_bot.ai.resume_customizer"):
            await customize_resume(SAMPLE_RESUME, SAMPLE_JOB)

        messages = [r.message for r in caplog.records]
        assert any("42 characters" in m for m in messages)
