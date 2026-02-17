"""Tests for the application settings module."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from config.settings import Settings


# ===================================================================
# Settings — defaults
# ===================================================================

class TestSettingsDefaults:

    def test_database_url_default(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.database_url == "sqlite:///data/applications.db"

    def test_linkedin_email_default_empty(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.linkedin_email == ""

    def test_linkedin_password_default_empty(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.linkedin_password == ""

    def test_indeed_email_default_empty(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.indeed_email == ""

    def test_indeed_password_default_empty(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.indeed_password == ""

    def test_model_name_default(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.model_name == "claude-sonnet-4-5-20250929"

    def test_max_tokens_default(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.max_tokens == 4096

    def test_scrape_delay_seconds_default(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.scrape_delay_seconds == 2.0

    def test_max_pages_per_search_default(self):
        s = Settings(anthropic_api_key="test-key")
        assert s.max_pages_per_search == 5


# ===================================================================
# Settings — custom values
# ===================================================================

class TestSettingsCustom:

    def test_custom_database_url(self):
        s = Settings(
            anthropic_api_key="test-key",
            database_url="sqlite:///custom.db",
        )
        assert s.database_url == "sqlite:///custom.db"

    def test_custom_linkedin_credentials(self):
        s = Settings(
            anthropic_api_key="test-key",
            linkedin_email="user@example.com",
            linkedin_password="secret",
        )
        assert s.linkedin_email == "user@example.com"
        assert s.linkedin_password == "secret"

    def test_custom_indeed_credentials(self):
        s = Settings(
            anthropic_api_key="test-key",
            indeed_email="user@indeed.com",
            indeed_password="pass123",
        )
        assert s.indeed_email == "user@indeed.com"
        assert s.indeed_password == "pass123"

    def test_custom_model_name(self):
        s = Settings(
            anthropic_api_key="test-key",
            model_name="claude-opus-4-6",
        )
        assert s.model_name == "claude-opus-4-6"

    def test_custom_max_tokens(self):
        s = Settings(anthropic_api_key="test-key", max_tokens=8192)
        assert s.max_tokens == 8192

    def test_custom_scrape_delay(self):
        s = Settings(anthropic_api_key="test-key", scrape_delay_seconds=5.0)
        assert s.scrape_delay_seconds == 5.0

    def test_custom_max_pages(self):
        s = Settings(anthropic_api_key="test-key", max_pages_per_search=10)
        assert s.max_pages_per_search == 10


# ===================================================================
# Settings — anthropic_api_key required
# ===================================================================

class TestSettingsRequired:

    def test_api_key_is_stored(self):
        s = Settings(anthropic_api_key="my-api-key-123")
        assert s.anthropic_api_key == "my-api-key-123"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-456")
        s = Settings()
        assert s.anthropic_api_key == "env-key-456"


# ===================================================================
# Settings — singleton from config package
# ===================================================================

class TestSettingsSingleton:

    def test_settings_import(self):
        from config import settings
        assert hasattr(settings, "anthropic_api_key")
        assert hasattr(settings, "database_url")
        assert hasattr(settings, "model_name")
