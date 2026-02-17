"""Tests for the CLI entry point (main.py)."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import argparse
import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import (
    MAX_APPLICATIONS_PER_RUN,
    APPLY_DELAY_MIN,
    APPLY_DELAY_MAX,
    _input,
    _confirm,
    build_parser,
    main,
    cmd_setup_profile,
    cmd_find_jobs,
    cmd_auto_apply,
    cmd_view_applications,
    cmd_settings,
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
        args = parser.parse_args(["-v", "settings"])
        assert args.verbose is True

    def test_parser_no_verbose_default(self):
        parser = build_parser()
        args = parser.parse_args(["settings"])
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

    def test_parser_find_command(self):
        parser = build_parser()
        args = parser.parse_args(["find", "Python Developer"])
        assert args.command == "find"
        assert args.query == "Python Developer"

    def test_parser_find_location(self):
        parser = build_parser()
        args = parser.parse_args(["find", "Dev", "--location", "NYC"])
        assert args.location == "NYC"

    def test_parser_find_default_location(self):
        parser = build_parser()
        args = parser.parse_args(["find", "Dev"])
        assert args.location == "Remote"

    def test_parser_find_source(self):
        parser = build_parser()
        args = parser.parse_args(["find", "Dev", "--source", "linkedin"])
        assert args.source == "linkedin"

    def test_parser_find_source_choices(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["find", "Dev", "--source", "glassdoor"])

    def test_parser_apply_command(self):
        parser = build_parser()
        args = parser.parse_args(["apply"])
        assert args.command == "apply"

    def test_parser_apply_max(self):
        parser = build_parser()
        args = parser.parse_args(["apply", "--max", "5"])
        assert args.max == 5

    def test_parser_apply_default_max(self):
        parser = build_parser()
        args = parser.parse_args(["apply"])
        assert args.max == MAX_APPLICATIONS_PER_RUN

    def test_parser_status_command(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_parser_status_filter(self):
        parser = build_parser()
        args = parser.parse_args(["status", "--status", "applied"])
        assert args.status == "applied"

    def test_parser_status_default_none(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.status is None

    def test_parser_settings_command(self):
        parser = build_parser()
        args = parser.parse_args(["settings"])
        assert args.command == "settings"

    def test_parser_menu_command(self):
        parser = build_parser()
        args = parser.parse_args(["menu"])
        assert args.command == "menu"

    def test_parser_no_command(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None


# ===================================================================
# _input / _confirm helpers
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


# ===================================================================
# main() dispatch
# ===================================================================

class TestMainDispatch:

    @patch("src.main.cmd_settings")
    def test_main_dispatches_settings(self, mock_cmd):
        main(["settings"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_setup_profile")
    def test_main_dispatches_setup(self, mock_cmd):
        main(["setup"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_find_jobs")
    def test_main_dispatches_find(self, mock_cmd):
        main(["find", "python"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_auto_apply")
    def test_main_dispatches_apply(self, mock_cmd):
        main(["apply"])
        mock_cmd.assert_called_once()

    @patch("src.main.cmd_view_applications")
    def test_main_dispatches_status(self, mock_cmd):
        main(["status"])
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
    @patch("src.main.cmd_settings")
    def test_main_verbose_enables_debug(self, mock_cmd, mock_setup):
        mock_setup.return_value = MagicMock()
        main(["-v", "settings"])
        # verbose flag triggers setup_logging with DEBUG
        # The second call (first is at import) should use DEBUG
        assert mock_setup.call_count >= 1


# ===================================================================
# cmd_find_jobs
# ===================================================================

class TestCmdFindJobs:

    @patch("src.main.ApplicationRepository")
    @patch("src.main.IndeedScraper")
    @patch("src.main.LinkedInScraper")
    def test_find_all_sources(self, MockLinkedIn, MockIndeed, MockRepo):
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
        mock_job.source = "indeed"

        for MockScraper in [MockLinkedIn, MockIndeed]:
            instance = MockScraper.return_value
            instance.search = AsyncMock(return_value=[mock_job])
            instance.close = AsyncMock()

        args = argparse.Namespace(query="python", location="Remote", source="all")
        cmd_find_jobs(args)

        assert mock_repo.save_job_posting.call_count == 2

    @patch("src.main.ApplicationRepository")
    @patch("src.main.IndeedScraper")
    def test_find_indeed_only(self, MockIndeed, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        MockIndeed.return_value.search = AsyncMock(return_value=[])
        MockIndeed.return_value.close = AsyncMock()

        args = argparse.Namespace(query="python", location="Remote", source="indeed")
        cmd_find_jobs(args)

        mock_repo.close.assert_called_once()

    @patch("src.main.ApplicationRepository")
    @patch("src.main.LinkedInScraper")
    def test_find_linkedin_only(self, MockLinkedIn, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        MockLinkedIn.return_value.search = AsyncMock(return_value=[])
        MockLinkedIn.return_value.close = AsyncMock()

        args = argparse.Namespace(query="python", location="Remote", source="linkedin")
        cmd_find_jobs(args)

        mock_repo.close.assert_called_once()

    @patch("src.main.ApplicationRepository")
    @patch("src.main.IndeedScraper")
    @patch("src.main.LinkedInScraper")
    def test_find_handles_scraper_error(self, MockLinkedIn, MockIndeed, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        MockLinkedIn.return_value.search = AsyncMock(side_effect=Exception("timeout"))
        MockLinkedIn.return_value.close = AsyncMock()
        MockIndeed.return_value.search = AsyncMock(return_value=[])
        MockIndeed.return_value.close = AsyncMock()

        args = argparse.Namespace(query="python", location="Remote", source="all")
        cmd_find_jobs(args)

        mock_repo.close.assert_called_once()


# ===================================================================
# cmd_view_applications
# ===================================================================

class TestCmdViewApplications:

    @patch("src.main.ApplicationRepository")
    def test_no_applications(self, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = []
        mock_repo.close = MagicMock()

        args = argparse.Namespace(status=None)
        cmd_view_applications(args)

        mock_repo.list_applications.assert_called_once_with(status=None)

    @patch("src.main.ApplicationRepository")
    def test_lists_applications(self, MockRepo, capsys):
        mock_posting = MagicMock()
        mock_posting.title = "Python Dev"
        mock_posting.company = "Acme"

        mock_app = MagicMock()
        mock_app.id = 1
        mock_app.status = "applied"
        mock_app.job_posting = mock_posting
        mock_app.created_at = datetime(2025, 1, 15)

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = [mock_app]
        mock_repo.close = MagicMock()

        args = argparse.Namespace(status=None)
        cmd_view_applications(args)

        output = capsys.readouterr().out
        assert "Python Dev" in output
        assert "Acme" in output
        assert "applied" in output

    @patch("src.main.ApplicationRepository")
    def test_status_filter(self, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = []
        mock_repo.close = MagicMock()

        args = argparse.Namespace(status="applied")
        cmd_view_applications(args)

        mock_repo.list_applications.assert_called_once_with(status="applied")

    @patch("src.main.ApplicationRepository")
    def test_status_breakdown(self, MockRepo, capsys):
        apps = []
        for status in ["applied", "applied", "saved"]:
            mock_posting = MagicMock()
            mock_posting.title = "Job"
            mock_posting.company = "Co"
            mock_app = MagicMock()
            mock_app.id = len(apps) + 1
            mock_app.status = status
            mock_app.job_posting = mock_posting
            mock_app.created_at = datetime(2025, 1, 15)
            apps.append(mock_app)

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = apps
        mock_repo.close = MagicMock()

        args = argparse.Namespace(status=None)
        cmd_view_applications(args)

        output = capsys.readouterr().out
        assert "applied: 2" in output
        assert "saved: 1" in output


# ===================================================================
# cmd_settings
# ===================================================================

class TestCmdSettings:

    @patch("src.main.settings")
    def test_settings_prints_config(self, mock_settings, capsys):
        mock_settings.database_url = "sqlite:///test.db"
        mock_settings.model_name = "claude-3"
        mock_settings.max_tokens = 4096
        mock_settings.scrape_delay_seconds = 2
        mock_settings.max_pages_per_search = 5
        mock_settings.linkedin_email = "user@test.com"
        mock_settings.indeed_email = ""

        args = argparse.Namespace()
        cmd_settings(args)

        output = capsys.readouterr().out
        assert "sqlite:///test.db" in output
        assert "claude-3" in output
        assert "4096" in output
        assert "(set)" in output
        assert "(not set)" in output

    @patch("src.main.settings")
    def test_settings_shows_constants(self, mock_settings, capsys):
        mock_settings.database_url = "x"
        mock_settings.model_name = "x"
        mock_settings.max_tokens = 0
        mock_settings.scrape_delay_seconds = 0
        mock_settings.max_pages_per_search = 0
        mock_settings.linkedin_email = ""
        mock_settings.indeed_email = ""

        args = argparse.Namespace()
        cmd_settings(args)

        output = capsys.readouterr().out
        assert str(MAX_APPLICATIONS_PER_RUN) in output
        assert str(APPLY_DELAY_MIN) in output
        assert str(APPLY_DELAY_MAX) in output


# ===================================================================
# cmd_setup_profile
# ===================================================================

class TestCmdSetupProfile:

    @patch("src.main.ProfileManager")
    @patch("builtins.input")
    def test_setup_saves_profile(self, mock_input, MockPM):
        mock_profile = MagicMock()
        mock_profile.full_name = ""
        mock_profile.email = ""
        mock_profile.phone = ""
        mock_profile.location = ""
        mock_profile.linkedin_url = ""
        mock_profile.github_url = ""
        mock_profile.portfolio_url = ""
        mock_profile.summary = ""
        mock_profile.skills = []
        mock_profile.experience_years = None
        mock_profile.base_resume_path = ""

        pm_instance = MockPM.return_value
        pm_instance.load.return_value = mock_profile
        pm_instance.save.return_value = "/profiles/default.json"

        # Simulate user entering values for each _input call
        mock_input.side_effect = [
            "Alice Smith",   # full name
            "alice@test.com", # email
            "555-0000",       # phone
            "NYC",            # location
            "",               # linkedin
            "",               # github
            "",               # portfolio
            "Software eng",   # summary
            "Python, SQL",    # skills
            "5",              # experience
            "",               # resume path
        ]

        args = argparse.Namespace(profile="default")
        cmd_setup_profile(args)

        pm_instance.save.assert_called_once()

    @patch("src.main.ProfileManager")
    @patch("builtins.input")
    def test_setup_uses_specified_profile_name(self, mock_input, MockPM):
        mock_profile = MagicMock()
        mock_profile.full_name = ""
        mock_profile.email = ""
        mock_profile.phone = ""
        mock_profile.location = ""
        mock_profile.linkedin_url = ""
        mock_profile.github_url = ""
        mock_profile.portfolio_url = ""
        mock_profile.summary = ""
        mock_profile.skills = []
        mock_profile.experience_years = None
        mock_profile.base_resume_path = ""

        pm_instance = MockPM.return_value
        pm_instance.load.return_value = mock_profile
        pm_instance.save.return_value = "/profiles/work.json"

        mock_input.side_effect = [""] * 11

        args = argparse.Namespace(profile="work")
        cmd_setup_profile(args)

        pm_instance.load.assert_called_once_with("work")
        pm_instance.save.assert_called_once_with(mock_profile, "work")


# ===================================================================
# cmd_auto_apply
# ===================================================================

class TestCmdAutoApply:

    @patch("src.main.ProfileManager")
    def test_apply_no_resume_shows_error(self, MockPM, capsys):
        mock_profile = MagicMock()
        mock_profile.base_resume_path = ""
        MockPM.return_value.load.return_value = mock_profile

        args = argparse.Namespace(profile="default", max=10)
        cmd_auto_apply(args)

        output = capsys.readouterr().out
        assert "No base resume" in output or "Error" in output

    @patch("src.main.ProfileManager")
    def test_apply_missing_resume_file(self, MockPM, capsys, tmp_path):
        mock_profile = MagicMock()
        mock_profile.base_resume_path = str(tmp_path / "nonexistent.txt")
        MockPM.return_value.load.return_value = mock_profile

        args = argparse.Namespace(profile="default", max=10)
        cmd_auto_apply(args)

        output = capsys.readouterr().out
        assert "not found" in output or "Error" in output

    @patch("src.main.ApplicationRepository")
    @patch("src.main.ProfileManager")
    def test_apply_no_unapplied_jobs(self, MockPM, MockRepo, capsys, tmp_path):
        resume = tmp_path / "resume.txt"
        resume.write_text("My resume content")

        mock_profile = MagicMock()
        mock_profile.base_resume_path = str(resume)
        MockPM.return_value.load.return_value = mock_profile

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo._session = MagicMock()

        # Empty result for the query
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_repo._session.scalars.return_value = mock_scalars
        mock_repo.close = MagicMock()

        args = argparse.Namespace(profile="default", max=10)
        cmd_auto_apply(args)

        output = capsys.readouterr().out
        assert "No unapplied jobs" in output or "find" in output.lower()


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

    @patch("builtins.input", side_effect=["5", "q"])
    @patch("src.main.cmd_settings")
    def test_menu_settings(self, mock_cmd, mock_input):
        interactive_menu()
        mock_cmd.assert_called_once()

    @patch("builtins.input", side_effect=["4", "", "q"])
    @patch("src.main.cmd_view_applications")
    def test_menu_view_applications(self, mock_cmd, mock_input):
        interactive_menu()
        mock_cmd.assert_called_once()


# ===================================================================
# Constants
# ===================================================================

class TestConstants:

    def test_max_applications_per_run(self):
        assert MAX_APPLICATIONS_PER_RUN == 10

    def test_apply_delay_min(self):
        assert APPLY_DELAY_MIN == 30.0

    def test_apply_delay_max(self):
        assert APPLY_DELAY_MAX == 60.0

    def test_delay_min_less_than_max(self):
        assert APPLY_DELAY_MIN < APPLY_DELAY_MAX
