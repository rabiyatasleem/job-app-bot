"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    database_url: str = "sqlite:///data/applications.db"

    linkedin_email: str = ""
    linkedin_password: str = ""
    indeed_email: str = ""
    indeed_password: str = ""

    # Anthropic model config
    model_name: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096

    # Gemini model config
    gemini_model: str = "gemini-1.5-flash"

    # Scraping config
    scrape_delay_seconds: float = 2.0
    max_pages_per_search: int = 5

    model_config = {"env_file": ".env"}


settings = Settings()
