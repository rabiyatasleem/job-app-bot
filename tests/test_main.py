"""Tests for the CLI entry point (main.py)."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-not-real")

import argparse
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import (
    MAX_APPLICATIONS_PER_RUN,
    APPLY_DELAY_MIN,
    APPLY_DELAY_MAX,
    _RESUME_SYSTEM_PROMPT,
    _COVER_LETTER_SYSTEM_PROMPT,
    _input,
    _confirm,
    _input_multiline,
    _get_gemini_model,
    _gemini_generate,
    build_parser,
    main,
    cmd_setup,
    cmd_scrape,
    cmd_apply,
    cmd_stats,
    interactive_menu,
)


# ===================================================================
# build_parser / argparse
# ===================================================================

class TestBuildParser:

    def test_parser_returns_argparse_parser(self):
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parser_prog_name(self):
        parser = build_parser()
        assert parser.prog == "job-app-bot"

    def test_parser_verbose_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-v", "stats"])
        assert args.verbose is True

    def test_parser_no_verbose_default(self):
        parser = build_parser()
        args = parser.parse_args(["stats"])
        assert args.verbose is False

    def test_parser_setup_command(self):
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.command == "setup"

    def test_parser_setup_profile_option(self):
        parser = build_parser()
        args = parser.parse_args(["setup", "--profile", "work"])
        assert args.profile == "work"

    def test_parser_setup_default_profile(self):
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.profile == "default"

    def test_parser_scrape_command(self):
        parser = build_parser()
        args = parser.parse_args(["scrape", "Python Developer"])
        assert args.command == "scrape"
        assert args.query == "Python Developer"

    def test_parser_scrape_optional_query(self):
        parser = build_parser()
        args = parser.parse_args(["scrape"])
        assert args.command == "scrape"
        assert args.query == ""

    def test_parser_scrape_location(self):
        parser = build_parser()
        args = parser.parse_args(["scrape", "Dev", "--location", "NYC"])
        assert args.location == "NYC"

    def test_parser_scrape_default_location(self):
        parser = build_parser()
        args = parser.parse_args(["scrape", "Dev"])
        assert args.location == "Remote"

    def test_parser_apply_command(self):
        parser = build_parser()
        args = parser.parse_args(["apply"])
        assert args.command == "apply"

    def test_parser_apply_max(self):
        parser = build_parser()
        args = parser.parse_args(["apply", "--max", "3"])
        assert args.max == 3

    def test_parser_apply_default_max(self):
        parser = build_parser()
        args = parser.parse_args(["apply"])
        assert args.max == MAX_APPLICATIONS_PER_RUN

    def test_parser_stats_command(self):
        parser = build_parser()
        args = parser.parse_args(["stats"])
        assert args.command == "stats"

    def test_parser_menu_command(self):
        parser = build_parser()
        args = parser.parse_args(["menu"])
        assert args.command == "menu"

    def test_parser_no_command(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None


# ===================================================================
# _input / _confirm / _input_multiline helpers
# ===================================================================

class TestHelpers:

    @patch("builtins.input", return_value="Alice")
    def test_input_returns_value(self, mock_in):
        assert _input("Name") == "Alice"

    @patch("builtins.input", return_value="")
    def test_input_returns_default(self, mock_in):
        assert _input("Name", "Bob") == "Bob"

    @patch("builtins.input", return_value="  Carol  ")
    def test_input_strips_whitespace(self, mock_in):
        assert _input("Name") == "Carol"

    @patch("builtins.input", return_value="y")
    def test_confirm_yes(self, mock_in):
        assert _confirm("OK?") is True

    @patch("builtins.input", return_value="n")
    def test_confirm_no(self, mock_in):
        assert _confirm("OK?") is False

    @patch("builtins.input", return_value="Y")
    def test_confirm_uppercase_yes(self, mock_in):
        assert _confirm("OK?") is True

    @patch("builtins.input", return_value="")
    def test_confirm_empty_is_no(self, mock_in):
        assert _confirm("OK?") is False

    @patch("builtins.input", side_effect=["line one", "line two", ""])
    def test_input_multiline_collects_lines(self, mock_in):
        result = _input_multiline("Paste text")
        assert result == "line one\nline two"

    @patch("builtins.input", side_effect=["", "first line", ""])
    def test_input_multiline_skips_leading_blank(self, mock_in):
        result = _input_multiline("Paste text")
        assert result == "first line"


# ===================================================================
# main() dispatch
# ===================================================================

class TestMainDispatch:

    @patch("src.main.cmd_stats")
    def test_main_dispatches_stats(self, mock_cmd):
        main(["stats"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_setup")
    def test_main_dispatches_setup(self, mock_cmd):
        main(["setup"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_scrape")
    def test_main_dispatches_scrape(self, mock_cmd):
        main(["scrape", "python"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_apply")
    def test_main_dispatches_apply(self, mock_cmd):
        main(["apply"])
        mock_cmd.assert_called_once()

    @patch("src.main.interactive_menu")
    def test_main_no_command_runs_menu(self, mock_menu):
        main([])
        mock_menu.assert_called_once()

    @patch("src.main.interactive_menu")
    def test_main_menu_command(self, mock_menu):
        main(["menu"])
        mock_menu.assert_called_once()

    @patch("src.main.setup_logging")
    @patch("src.main.cmd_stats")
    def test_main_verbose_enables_debug(self, mock_cmd, mock_setup):
        mock_setup.return_value = MagicMock()
        main(["-v", "stats"])
        assert mock_setup.call_count >= 1


# ===================================================================
# cmd_scrape
# ===================================================================

class TestCmdScrape:

    @patch("src.main.ApplicationRepository")
    @patch("src.main.LinkedInScraper")
    def test_scrape_saves_jobs(self, MockLinkedIn, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        mock_job = MagicMock()
        mock_job.title = "Dev"
        mock_job.company = "Co"
        mock_job.location = "Remote"
        mock_job.url = "https://x.com"
        mock_job.description = "desc"
        mock_job.salary = None
        mock_job.job_type = None
        mock_job.source = "linkedin"

        instance = MockLinkedIn.return_value
        instance.login = AsyncMock()
        instance.search = AsyncMock(return_value=[mock_job])
        instance.close = AsyncMock()

        args = argparse.Namespace(query="python", location="Remote")
        cmd_scrape(args)

        mock_repo.save_job_posting.assert_called_once()
        mock_repo.close.assert_called_once()

    @patch("src.main.ApplicationRepository")
    @patch("src.main.LinkedInScraper")
    def test_scrape_handles_error(self, MockLinkedIn, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        instance = MockLinkedIn.return_value
        instance.login = AsyncMock()
        instance.search = AsyncMock(side_effect=Exception("timeout"))
        instance.close = AsyncMock()

        args = argparse.Namespace(query="python", location="Remote")
        cmd_scrape(args)

        mock_repo.close.assert_called_once()

    @patch("builtins.input", side_effect=["", ""])
    def test_scrape_no_query_shows_error(self, mock_input, capsys):
        args = argparse.Namespace(query="", location="Remote")
        cmd_scrape(args)

        output = capsys.readouterr().out
        assert "required" in output.lower()


# ===================================================================
# cmd_stats
# ===================================================================

class TestCmdStats:

    @patch("src.main.ApplicationRepository")
    def test_stats_shows_totals(self, MockRepo, capsys):
        mock_session = MagicMock()
        mock_session.scalar.side_effect = [10, 3]  # total jobs, total apps
        mock_session.execute.side_effect = [
            MagicMock(all=MagicMock(return_value=[("linkedin", 7), ("indeed", 3)])),
            MagicMock(all=MagicMock(return_value=[("applied", 2), ("saved", 1)])),
        ]

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo._session = mock_session
        mock_repo.close = MagicMock()

        args = argparse.Namespace()
        cmd_stats(args)

        output = capsys.readouterr().out
        assert "10" in output
        assert "3" in output
        assert "linkedin" in output
        assert "applied" in output

    @patch("src.main.ApplicationRepository")
    def test_stats_no_applications(self, MockRepo, capsys):
        mock_session = MagicMock()
        mock_session.scalar.side_effect = [0, 0]
        mock_session.execute.side_effect = [
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo._session = mock_session
        mock_repo.close = MagicMock()

        args = argparse.Namespace()
        cmd_stats(args)

        output = capsys.readouterr().out
        assert "0" in output
        assert "no applications yet" in output


# ===================================================================
# cmd_setup
# ===================================================================

class TestCmdSetup:

    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    @patch("builtins.input")
    def test_setup_saves_profile(self, mock_input, MockPM, MockRepo):
        mock_profile = MagicMock()
        mock_profile.full_name = ""
        mock_profile.email = ""
        mock_profile.phone = ""
        mock_profile.location = ""
        mock_profile.linkedin_url = ""
        mock_profile.summary = ""
        mock_profile.skills = []
        mock_profile.experience_years = None
        mock_profile.base_resume_path = ""

        pm_instance = MockPM.return_value
        pm_instance.load.return_value = mock_profile
        pm_instance.save.return_value = "/profiles/default.json"

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.close = MagicMock()

        # Simulate user entering values for each _input / _confirm call
        mock_input.side_effect = [
            "Alice Smith",    # full name
            "alice@test.com", # email
            "555-0000",       # phone
            "Python, SQL",    # skills
            "5",              # experience
            "Software eng",   # summary
            "",               # education
            "n",              # paste resume? -> no
            "",               # resume path
            "Remote",         # preferred location
            "python dev",     # keywords
            "",               # linkedin url
        ]

        args = argparse.Namespace(profile="default")
        cmd_setup(args)

        pm_instance.save.assert_called_once()

    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    @patch("builtins.input")
    def test_setup_uses_specified_profile_name(self, mock_input, MockPM, MockRepo):
        mock_profile = MagicMock()
        mock_profile.full_name = ""
        mock_profile.email = ""
        mock_profile.phone = ""
        mock_profile.location = ""
        mock_profile.linkedin_url = ""
        mock_profile.summary = ""
        mock_profile.skills = []
        mock_profile.experience_years = None
        mock_profile.base_resume_path = ""

        pm_instance = MockPM.return_value
        pm_instance.load.return_value = mock_profile
        pm_instance.save.return_value = "/profiles/work.json"

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.close = MagicMock()

        mock_input.side_effect = [""] * 12

        args = argparse.Namespace(profile="work")
        cmd_setup(args)

        pm_instance.load.assert_called_once_with("work")
        pm_instance.save.assert_called_once_with(mock_profile, "work")


# ===================================================================
# cmd_apply
# ===================================================================

class TestCmdApply:

    @patch("src.main.ProfileManager")
    def test_apply_no_resume_shows_error(self, MockPM, capsys):
        mock_profile = MagicMock()
        mock_profile.base_resume_path = ""
        MockPM.return_value.load.return_value = mock_profile

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        output = capsys.readouterr().out
        assert "No base resume" in output or "Error" in output

    @patch("src.main.ProfileManager")
    def test_apply_missing_resume_file(self, MockPM, capsys, tmp_path):
        mock_profile = MagicMock()
        mock_profile.base_resume_path = str(tmp_path / "nonexistent.txt")
        MockPM.return_value.load.return_value = mock_profile

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        output = capsys.readouterr().out
        assert "not found" in output or "Error" in output

    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_no_unapplied_jobs(self, MockPM, MockRepo, mock_settings, capsys, tmp_path):
        resume = tmp_path / "resume.txt"
        resume.write_text("My resume content")

        mock_profile = MagicMock()
        mock_profile.base_resume_path = str(resume)
        MockPM.return_value.load.return_value = mock_profile

        mock_settings.gemini_api_key = "test-key"

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo._session = MagicMock()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_repo._session.scalars.return_value = mock_scalars
        mock_repo.close = MagicMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        output = capsys.readouterr().out
        assert "No unapplied jobs" in output or "scrape" in output.lower()

    @patch("src.main.settings")
    @patch("src.main.ProfileManager")
    def test_apply_no_gemini_key(self, MockPM, mock_settings, capsys, tmp_path):
        resume = tmp_path / "resume.txt"
        resume.write_text("My resume content")

        mock_profile = MagicMock()
        mock_profile.base_resume_path = str(resume)
        MockPM.return_value.load.return_value = mock_profile

        mock_settings.gemini_api_key = ""

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        output = capsys.readouterr().out
        assert "GEMINI_API_KEY" in output


# ===================================================================
# interactive_menu
# ===================================================================

class TestInteractiveMenu:

    @patch("builtins.input", return_value="q")
    def test_menu_quit(self, mock_input, capsys):
        interactive_menu()
        output = capsys.readouterr().out
        assert "Goodbye" in output

    @patch("builtins.input", side_effect=["x", "q"])
    def test_menu_invalid_option(self, mock_input, capsys):
        interactive_menu()
        output = capsys.readouterr().out
        assert "Invalid" in output

    @patch("builtins.input", side_effect=["4", "q"])
    @patch("src.main.cmd_stats")
    def test_menu_stats(self, mock_cmd, mock_input):
        interactive_menu()
        mock_cmd.assert_called_once()

    @patch("builtins.input", side_effect=["1", "q"])
    @patch("src.main.cmd_setup")
    def test_menu_setup(self, mock_cmd, mock_input):
        interactive_menu()
        mock_cmd.assert_called_once()


# ===================================================================
# _get_gemini_model
# ===================================================================

class TestGetGeminiModel:

    @patch("src.main.genai")
    @patch("src.main.settings")
    def test_configures_api_key(self, mock_settings, mock_genai):
        mock_settings.gemini_api_key = "test-key-123"
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        _get_gemini_model()

        mock_genai.Client.assert_called_once_with(api_key="test-key-123")

    @patch("src.main.genai")
    @patch("src.main.settings")
    def test_returns_client(self, mock_settings, mock_genai):
        mock_settings.gemini_api_key = "key"
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        result = _get_gemini_model()

        mock_genai.Client.assert_called_once_with(api_key="key")
        assert result is mock_client

    @patch("src.main.genai")
    @patch("src.main.settings")
    def test_uses_configured_api_key(self, mock_settings, mock_genai):
        mock_settings.gemini_api_key = "another-key-xyz"

        _get_gemini_model()

        mock_genai.Client.assert_called_once_with(api_key="another-key-xyz")


# ===================================================================
# _gemini_generate
# ===================================================================

class TestGeminiGenerate:

    @pytest.mark.asyncio
    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.settings")
    async def test_returns_text_on_success(self, mock_settings, mock_sleep):
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Generated resume text"
        mock_client.models.generate_content.return_value = mock_response

        result = await _gemini_generate(mock_client, "test prompt")

        assert result == "Generated resume text"
        mock_client.models.generate_content.assert_called_once_with(
            model="gemini-2.0-flash", contents="test prompt"
        )
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.settings")
    async def test_retries_on_failure_then_succeeds(self, mock_settings, mock_sleep):
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Success on retry"
        mock_client.models.generate_content.side_effect = [
            Exception("API error"),
            mock_response,
        ]

        result = await _gemini_generate(mock_client, "prompt")

        assert result == "Success on retry"
        assert mock_client.models.generate_content.call_count == 2
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.settings")
    async def test_raises_after_all_retries_exhausted(self, mock_settings, mock_sleep):
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("persistent failure")

        with pytest.raises(Exception, match="persistent failure"):
            await _gemini_generate(mock_client, "prompt")

        assert mock_client.models.generate_content.call_count == 3
        assert mock_sleep.await_count == 3

    @pytest.mark.asyncio
    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.settings")
    async def test_retries_twice_then_succeeds(self, mock_settings, mock_sleep):
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Third attempt"
        mock_client.models.generate_content.side_effect = [
            Exception("fail 1"),
            Exception("fail 2"),
            mock_response,
        ]

        result = await _gemini_generate(mock_client, "prompt")

        assert result == "Third attempt"
        assert mock_client.models.generate_content.call_count == 3
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.settings")
    async def test_passes_prompt_to_model(self, mock_settings, mock_sleep):
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_client.models.generate_content.return_value = mock_response

        await _gemini_generate(mock_client, "Customize this resume for a Python role")

        mock_client.models.generate_content.assert_called_once_with(
            model="gemini-2.0-flash",
            contents="Customize this resume for a Python role",
        )


# ===================================================================
# cmd_apply — full Gemini workflow
# ===================================================================

class TestCmdApplyGeminiWorkflow:
    """Tests for the apply command's Gemini-powered resume/cover letter flow."""

    def _setup_apply_mocks(self, tmp_path, MockPM, MockRepo, mock_settings):
        """Helper to wire up common mocks for cmd_apply tests."""
        resume = tmp_path / "resume.txt"
        resume.write_text("Base resume content")

        mock_profile = MagicMock()
        mock_profile.base_resume_path = str(resume)
        mock_profile.full_name = "Test User"
        MockPM.return_value.load.return_value = mock_profile

        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-1.5-flash"

        mock_posting = MagicMock()
        mock_posting.id = 1
        mock_posting.title = "Python Developer"
        mock_posting.company = "TestCorp"
        mock_posting.url = "https://example.com/job/1"
        mock_posting.description = "Build Python apps"

        mock_app = MagicMock()
        mock_app.id = 10

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo._session = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_posting]
        mock_repo._session.scalars.return_value = mock_scalars
        mock_repo.create_application.return_value = mock_app
        mock_repo.update_application_status = MagicMock()
        mock_repo.close = MagicMock()

        return mock_profile, mock_posting, mock_app, mock_repo

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=True)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_calls_gemini_for_resume_and_cover_letter(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_model = MagicMock()
        mock_get_model.return_value = mock_model
        mock_generate.side_effect = ["Tailored resume text", "Cover letter text"]
        mock_save_docx.return_value = tmp_path / "resume.docx"

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None  # Skip browser interaction
        filler.submit = AsyncMock()
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        # Gemini should be called twice: once for resume, once for cover letter
        assert mock_generate.await_count == 2
        resume_call_prompt = mock_generate.call_args_list[0][0][1]
        cover_call_prompt = mock_generate.call_args_list[1][0][1]
        assert "Base resume content" in resume_call_prompt
        assert "Build Python apps" in resume_call_prompt
        assert "Base resume content" in cover_call_prompt
        assert "TestCorp" in cover_call_prompt

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=True)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_submit_updates_status_to_applied(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = ["Resume", "Cover letter"]
        mock_save_docx.return_value = tmp_path / "out.docx"

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None
        filler.submit = AsyncMock()
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        # Should have updated status to "applied"
        status_calls = [
            c[0] for c in mock_repo.update_application_status.call_args_list
        ]
        assert (mock_app.id, "resume_tailored") in status_calls
        assert (mock_app.id, "applied") in status_calls

        output = capsys.readouterr().out
        assert "Submitted!" in output

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=False)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_skip_updates_status_to_saved(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = ["Resume", "Cover letter"]
        mock_save_docx.return_value = tmp_path / "out.docx"

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        # Should have updated status to "saved" (user skipped)
        status_calls = [
            c[0] for c in mock_repo.update_application_status.call_args_list
        ]
        assert (mock_app.id, "saved") in status_calls

        output = capsys.readouterr().out
        assert "Skipped" in output

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_gemini_failure_continues_to_next_job(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = Exception("Gemini API down")

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        output = capsys.readouterr().out
        assert "Error" in output or "Gemini API down" in output
        # Filler and repo should still be cleaned up
        filler.close.assert_awaited_once()
        mock_repo.close.assert_called_once()

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=True)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_saves_documents_as_docx(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = ["Custom resume markdown", "Dear Hiring Manager..."]
        mock_save_docx.return_value = tmp_path / "out.docx"

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None
        filler.submit = AsyncMock()
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        # save_as_docx called twice: resume + cover letter
        assert mock_save_docx.call_count == 2
        resume_call = mock_save_docx.call_args_list[0]
        cover_call = mock_save_docx.call_args_list[1]
        assert resume_call[0][0] == "Custom resume markdown"
        assert "resume.docx" in resume_call[0][1]
        assert cover_call[0][0] == "Dear Hiring Manager..."
        assert "cover_letter.docx" in cover_call[0][1]

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=True)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.fill_application_form")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_fills_form_and_takes_screenshot(
        self, MockPM, MockRepo, mock_settings, MockFillForm, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = ["Resume", "Cover letter"]
        mock_save_docx.return_value = tmp_path / "out.docx"

        mock_page = AsyncMock()
        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = mock_page
        filler.submit = AsyncMock()
        filler.close = AsyncMock()

        fill_result = MagicMock()
        fill_result.fields_filled = 5
        fill_result.fields_total = 8
        fill_result.screenshot_path = "/tmp/screenshot.png"
        fill_result.errors = []
        MockFillForm.return_value = fill_result

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        # Should have navigated to job URL
        mock_page.goto.assert_awaited_once_with(
            posting.url, wait_until="domcontentloaded"
        )
        # Should have called fill_application_form
        MockFillForm.assert_awaited_once()

        output = capsys.readouterr().out
        assert "5/8 fields" in output
        assert "screenshot.png" in output

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=True)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_submit_failure_does_not_crash(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = ["Resume", "Cover letter"]
        mock_save_docx.return_value = tmp_path / "out.docx"

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None
        filler.submit = AsyncMock(side_effect=Exception("Browser crash"))
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        output = capsys.readouterr().out
        assert "Submit failed" in output
        # Should still complete and print summary
        assert "Done!" in output

    @patch("src.main.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.main.save_as_docx")
    @patch("src.main._confirm", return_value=True)
    @patch("src.main._gemini_generate", new_callable=AsyncMock)
    @patch("src.main._get_gemini_model")
    @patch("src.main.FormFiller")
    @patch("src.main.settings")
    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_uses_resume_system_prompt(
        self, MockPM, MockRepo, mock_settings, MockFiller,
        mock_get_model, mock_generate, mock_confirm, mock_save_docx,
        mock_sleep, capsys, tmp_path,
    ):
        mock_profile, posting, mock_app, mock_repo = self._setup_apply_mocks(
            tmp_path, MockPM, MockRepo, mock_settings
        )

        mock_get_model.return_value = MagicMock()
        mock_generate.side_effect = ["Resume", "Cover letter"]
        mock_save_docx.return_value = tmp_path / "out.docx"

        filler = MockFiller.return_value
        filler.launch = AsyncMock()
        filler._page = None
        filler.submit = AsyncMock()
        filler.close = AsyncMock()

        args = argparse.Namespace(profile="default", max=5)
        cmd_apply(args)

        resume_prompt = mock_generate.call_args_list[0][0][1]
        cover_prompt = mock_generate.call_args_list[1][0][1]
        assert "expert resume writer" in resume_prompt
        assert "expert career coach" in cover_prompt


# ===================================================================
# Prompt constants
# ===================================================================

class TestPromptConstants:

    def test_resume_prompt_mentions_markdown(self):
        assert "Markdown" in _RESUME_SYSTEM_PROMPT

    def test_resume_prompt_mentions_truthful(self):
        assert "truthful" in _RESUME_SYSTEM_PROMPT

    def test_cover_letter_prompt_word_limit(self):
        assert "400 words" in _COVER_LETTER_SYSTEM_PROMPT

    def test_cover_letter_prompt_no_generic_opener(self):
        assert "I am writing to apply" in _COVER_LETTER_SYSTEM_PROMPT


# ===================================================================
# Constants
# ===================================================================

class TestConstants:

    def test_max_applications_per_run(self):
        assert MAX_APPLICATIONS_PER_RUN == 5

    def test_apply_delay_min(self):
        assert APPLY_DELAY_MIN == 30.0

    def test_apply_delay_max(self):
        assert APPLY_DELAY_MAX == 60.0

    def test_delay_min_less_than_max(self):
        assert APPLY_DELAY_MIN < APPLY_DELAY_MAX
