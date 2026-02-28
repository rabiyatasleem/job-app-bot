# Job Application Automation Tool

A Python-powered CLI tool that automates the job application pipeline — from scraping listings on LinkedIn and Indeed, to tailoring resumes and cover letters with Gemini AI, to filling out application forms in the browser.

## Features

- **Job Scraping** — Search LinkedIn (via Playwright) and Indeed (via httpx + BeautifulSoup) with filters for job type, experience level, location, salary, and recency
- **AI Resume Tailoring** — Uses Google Gemini to rewrite your base resume for each job, highlighting relevant skills and matching keywords
- **Cover Letter Generation** — Generates compelling, role-specific cover letters using Gemini AI
- **Form Filling** — Automates browser-based application forms using Playwright (text inputs, dropdowns, checkboxes, file uploads)
- **Application Tracking** — SQLite database tracks every application through stages: saved → resume tailored → applied → interviewing → offered/rejected
- **Profile Management** — Store candidate info (contact, skills, work history, education) as JSON profiles

## Project Structure

```
job-app-bot/
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py                    # Pydantic settings from .env
├── src/
│   ├── main.py                        # CLI entry point (argparse)
│   ├── scrapers/
│   │   ├── base_scraper.py            # BaseScraper ABC + JobListing dataclass
│   │   ├── linkedin_scraper.py        # Playwright-based LinkedIn scraper
│   │   └── indeed_scraper.py          # httpx + BeautifulSoup Indeed scraper
│   ├── ai/
│   │   ├── resume_customizer.py       # AI-powered resume tailoring
│   │   └── cover_letter_generator.py  # AI-powered cover letters
│   ├── automation/
│   │   ├── form_filler.py             # Playwright form filling
│   │   └── application_submitter.py   # End-to-end submission orchestrator
│   ├── database/
│   │   ├── models.py                  # SQLAlchemy models
│   │   └── db.py                      # CRUD operations
│   ├── profiles/
│   │   └── manager.py                 # JSON profile storage
│   └── utils/
│       ├── logging.py                 # Centralized logger
│       └── file_export.py             # Export to .docx / .txt
├── data/
│   └── applications.db                # SQLite DB (created at runtime)
└── tests/
    ├── conftest.py                    # Shared fixtures and HTML samples
    ├── test_ai.py
    ├── test_application_submitter.py
    ├── test_base_scraper.py
    ├── test_database.py
    ├── test_file_export.py
    ├── test_form_filler.py
    ├── test_indeed_scraper.py
    ├── test_linkedin_scraper.py
    ├── test_logging.py
    ├── test_main.py
    ├── test_profiles.py
    └── test_settings.py
```

## Setup

### 1. Clone and install

```bash
git clone https://github.com/rabiyatasleem/job-app-bot.git
cd job-app-bot
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
GEMINI_API_KEY=your-gemini-api-key
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
```

### 3. Set up your profile

Run the interactive setup command to enter your details and save your base resume:

```bash
python src/main.py setup
```

Or pass a profile name:

```bash
python src/main.py setup --profile work
```

## Usage

### Interactive menu

```bash
python src/main.py
```

Launches a numbered menu to walk through all steps.

### Scrape jobs from LinkedIn

```bash
python src/main.py scrape "Software Engineer" --location "Remote"
```

Results are saved to the SQLite database.

### Auto-apply with Gemini AI

```bash
python src/main.py apply
```

For each unapplied job in the database, this will:
1. Tailor your resume to the job description using Gemini
2. Generate a cover letter using Gemini
3. Save `resume.docx` and `cover_letter.docx` to `output/<company>_<id>/`
4. Open the application page in a browser and fill the form
5. Ask for your confirmation before submitting

Options:

```bash
python src/main.py apply --profile work --max 3
```

### View statistics

```bash
python src/main.py stats
```

Shows total jobs scraped by source and applications by status.

### All commands

```
python src/main.py setup    # Set up candidate profile
python src/main.py scrape   # Scrape LinkedIn for jobs
python src/main.py apply    # Auto-apply to unapplied jobs
python src/main.py stats    # Show job and application statistics
python src/main.py menu     # Launch interactive menu
```

Use `-v` / `--verbose` with any command to enable debug logging.

## Running Tests

```bash
python -m pytest tests/ -v
```

All 462 tests run without network access — scrapers are tested against HTML fixtures and mocked HTTP/Playwright responses.

## Tech Stack

| Component | Library |
|-----------|---------|
| Scraping (LinkedIn) | Playwright |
| Scraping (Indeed) | httpx, BeautifulSoup, lxml |
| AI | Google Gemini (google-genai) |
| Database | SQLAlchemy + SQLite |
| Document export | python-docx |
| CLI | argparse + Rich |
| Config | Pydantic Settings + python-dotenv |
| Testing | pytest + pytest-asyncio |

## License

MIT
