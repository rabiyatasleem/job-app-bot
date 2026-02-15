# Job Application Automation Tool

A Python-powered CLI tool that automates the job application pipeline — from scraping listings on LinkedIn and Indeed, to tailoring resumes and cover letters with AI, to filling out application forms in the browser.

## Features

- **Job Scraping** — Search LinkedIn (via Playwright) and Indeed (via httpx + BeautifulSoup) with filters for job type, experience level, location, salary, and recency
- **AI Resume Tailoring** — Uses the Anthropic API to rewrite your base resume for each job, highlighting relevant skills and matching keywords
- **Cover Letter Generation** — Generates compelling, role-specific cover letters with configurable tone
- **Form Filling** — Automates browser-based application forms using Playwright (text inputs, dropdowns, checkboxes, file uploads)
- **Application Tracking** — SQLite database tracks every application through stages: saved → resume tailored → cover letter done → applied → interviewing → offered/rejected
- **Profile Management** — Store candidate info (contact, skills, work history, education) as JSON profiles

## Project Structure

```
job-app-bot/
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py                    # Pydantic settings from .env
├── src/
│   ├── main.py                        # CLI entry point
│   ├── scrapers/
│   │   ├── base_scraper.py            # BaseScraper ABC + JobListing dataclass
│   │   ├── linkedin_scraper.py        # Playwright-based LinkedIn scraper
│   │   └── indeed_scraper.py          # httpx + BeautifulSoup Indeed scraper
│   ├── ai/
│   │   ├── resume_customizer.py       # Anthropic-powered resume tailoring
│   │   └── cover_letter_generator.py  # Anthropic-powered cover letters
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
│   ├── user_resume.pdf                # Your base resume (add your own)
│   └── applications.db                # SQLite DB (created at runtime)
└── tests/
    ├── conftest.py                    # Shared fixtures and HTML samples
    ├── test_indeed_scraper.py         # 30 tests
    └── test_linkedin_scraper.py       # 30 tests
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

Edit `.env` with your keys:

```
ANTHROPIC_API_KEY=sk-ant-...
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
```

### 3. Set up your profile

Create `config/profiles/default.json`:

```json
{
  "full_name": "Jane Doe",
  "email": "jane@example.com",
  "phone": "+1-555-0100",
  "location": "New York, NY",
  "skills": ["Python", "SQL", "Machine Learning", "AWS"],
  "experience_years": 5,
  "base_resume_path": "path/to/your/resume.md"
}
```

## Usage

### Search for jobs

```bash
# Search all boards
python src/main.py search -q "Software Engineer" -l "Remote"

# Search specific board with filters
python src/main.py search -q "Data Analyst" -l "New York, NY" -s indeed
```

### Tailor resume and generate cover letter

```bash
# Generate tailored documents for a specific job posting
python src/main.py tailor -j 1 -p default
```

This creates a `output/<company>_<id>/` folder with `resume.docx` and `cover_letter.docx`.

### Track applications

```bash
# View all applications
python src/main.py status

# Filter by status
python src/main.py status -s applied
```

### View your profile

```bash
python src/main.py profile
```

## Running Tests

```bash
python -m pytest tests/ -v
```

All 60 tests run without network access — scrapers are tested against HTML fixtures and mocked HTTP/Playwright responses.

## Tech Stack

| Component | Library |
|-----------|---------|
| Scraping (LinkedIn) | Playwright |
| Scraping (Indeed) | httpx, BeautifulSoup, lxml |
| AI | Anthropic API (Claude) |
| Database | SQLAlchemy + SQLite |
| Document export | python-docx |
| CLI | Click + Rich |
| Config | Pydantic Settings + python-dotenv |
| Testing | pytest + pytest-asyncio |

## License

MIT
