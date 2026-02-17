"""Tests for the CLI entry point (main.py)."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from click.testing import CliRunner

from src.main import cli


# ===================================================================
# CLI group
# ===================================================================

class TestCLIGroup:

    def test_cli_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Job Application Automation Tool" in result.output

    def test_cli_lists_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "search" in result.output
        assert "tailor" in result.output
        assert "status" in result.output
        assert "profile" in result.output


# ===================================================================
# search command
# ===================================================================

class TestSearchCommand:

    def test_search_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "--query" in result.output
        assert "--location" in result.output
        assert "--source" in result.output

    def test_search_requires_query(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["search"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower() or "Error" in result.output

    @patch("src.main.ApplicationRepository")
    @patch("src.main.IndeedScraper")
    @patch("src.main.LinkedInScraper")
    def test_search_all_sources(self, MockLinkedIn, MockIndeed, MockRepo):
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

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "-q", "python", "-s", "all"])

        assert result.exit_code == 0

    @patch("src.main.ApplicationRepository")
    @patch("src.main.IndeedScraper")
    def test_search_indeed_only(self, MockIndeed, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        MockIndeed.return_value.search = AsyncMock(return_value=[])
        MockIndeed.return_value.close = AsyncMock()

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "-q", "python", "-s", "indeed"])

        assert result.exit_code == 0

    @patch("src.main.ApplicationRepository")
    @patch("src.main.LinkedInScraper")
    def test_search_linkedin_only(self, MockLinkedIn, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        MockLinkedIn.return_value.search = AsyncMock(return_value=[])
        MockLinkedIn.return_value.close = AsyncMock()

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "-q", "python", "-s", "linkedin"])

        assert result.exit_code == 0

    def test_search_invalid_source(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "-q", "python", "-s", "glassdoor"])
        assert result.exit_code != 0

    @patch("src.main.ApplicationRepository")
    @patch("src.main.IndeedScraper")
    @patch("src.main.LinkedInScraper")
    def test_search_default_location_remote(self, MockLinkedIn, MockIndeed, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.save_job_posting = MagicMock()
        mock_repo.close = MagicMock()
        mock_repo.create_tables = MagicMock()

        for MockScraper in [MockLinkedIn, MockIndeed]:
            instance = MockScraper.return_value
            instance.search = AsyncMock(return_value=[])
            instance.close = AsyncMock()

        runner = CliRunner()
        result = runner.invoke(cli, ["search", "-q", "python"])

        assert result.exit_code == 0


# ===================================================================
# tailor command
# ===================================================================

class TestTailorCommand:

    def test_tailor_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tailor", "--help"])
        assert result.exit_code == 0
        assert "--job-id" in result.output
        assert "--profile" in result.output

    def test_tailor_requires_job_id(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tailor"])
        assert result.exit_code != 0

    @patch("src.main.ProfileManager")
    def test_tailor_no_resume_shows_error(self, MockPM):
        mock_profile = MagicMock()
        mock_profile.base_resume_path = ""
        MockPM.return_value.load.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(cli, ["tailor", "-j", "1"])

        assert result.exit_code == 0
        assert "No base resume" in result.output or "not set" in result.output.lower()

    @patch("src.main.ProfileManager")
    @patch("src.main.ApplicationRepository")
    def test_tailor_job_not_found(self, MockRepo, MockPM):
        mock_profile = MagicMock()
        mock_profile.base_resume_path = "/tmp/resume.txt"
        MockPM.return_value.load.return_value = mock_profile

        mock_repo = MockRepo.return_value
        mock_repo._session = MagicMock()
        mock_repo._session.get.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["tailor", "-j", "999"])

        assert result.exit_code == 0
        assert "not found" in result.output


# ===================================================================
# status command
# ===================================================================

class TestStatusCommand:

    def test_status_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.output

    @patch("src.main.ApplicationRepository")
    def test_status_no_applications(self, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = []
        mock_repo.close = MagicMock()

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "No applications found" in result.output

    @patch("src.main.ApplicationRepository")
    def test_status_lists_applications(self, MockRepo):
        mock_posting = MagicMock()
        mock_posting.title = "Python Dev"
        mock_posting.company = "Acme"

        mock_app = MagicMock()
        mock_app.id = 1
        mock_app.status = "applied"
        mock_app.job_posting = mock_posting

        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = [mock_app]
        mock_repo.close = MagicMock()

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Python Dev" in result.output
        assert "Acme" in result.output

    @patch("src.main.ApplicationRepository")
    def test_status_filter_param(self, MockRepo):
        mock_repo = MockRepo.return_value
        mock_repo.create_tables = MagicMock()
        mock_repo.list_applications.return_value = []
        mock_repo.close = MagicMock()

        runner = CliRunner()
        result = runner.invoke(cli, ["status", "-s", "applied"])

        assert result.exit_code == 0
        mock_repo.list_applications.assert_called_once_with(status="applied")


# ===================================================================
# profile command
# ===================================================================

class TestProfileCommand:

    def test_profile_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["profile", "--help"])
        assert result.exit_code == 0

    @patch("src.main.ProfileManager")
    def test_profile_shows_current(self, MockPM):
        mock_profile = MagicMock()
        mock_profile.full_name = "Jane Doe"
        mock_profile.email = "jane@example.com"
        mock_profile.phone = "555-1234"
        mock_profile.skills = ["Python", "SQL"]
        mock_profile.base_resume_path = "/resumes/base.txt"
        MockPM.return_value.load.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(cli, ["profile"])

        assert result.exit_code == 0
        assert "Jane Doe" in result.output
        assert "jane@example.com" in result.output
        assert "555-1234" in result.output

    @patch("src.main.ProfileManager")
    def test_profile_empty_fields_show_not_set(self, MockPM):
        mock_profile = MagicMock()
        mock_profile.full_name = None
        mock_profile.email = None
        mock_profile.phone = None
        mock_profile.skills = []
        mock_profile.base_resume_path = None
        MockPM.return_value.load.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(cli, ["profile"])

        assert result.exit_code == 0
        assert "not set" in result.output
