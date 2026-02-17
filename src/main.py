"""CLI entry point for the Job Application Automation Tool.

Provides both an interactive menu and argparse sub-commands for:
  1. Profile setup  — collect user info and save to database
  2. Job scraping   — search LinkedIn for jobs
  3. Auto-apply     — AI-customized applications via Gemini
  4. Stats          — view application statistics
"""

import argparse
import asyncio
import logging
import random
import sys
from pathlib import Path

import google.generativeai as genai
from sqlalchemy import func, select

from config import settings
from src.automation import FormFiller, fill_application_form
from src.database import ApplicationRepository, Application, JobPosting
from src.profiles import ProfileManager
from src.scrapers import LinkedInScraper
from src.utils.file_export import save_as_docx
from src.utils.logging import setup_logging

logger = setup_logging()

MAX_APPLICATIONS_PER_RUN = 5
APPLY_DELAY_MIN = 30.0
APPLY_DELAY_MAX = 60.0

_RESUME_SYSTEM_PROMPT = (
    "You are an expert resume writer. Given a candidate's base resume and a "
    "target job description, produce a tailored resume that:\n"
    "- Highlights experience and skills most relevant to the role\n"
    "- Uses keywords from the job description naturally\n"
    "- Keeps all facts truthful — never fabricate experience\n"
    "- Maintains professional tone and concise bullet points\n"
    "Return the resume in clean Markdown format."
)

_COVER_LETTER_SYSTEM_PROMPT = (
    "You are an expert career coach writing a cover letter. "
    "Write a concise, compelling cover letter that:\n"
    "- Opens with a strong hook — not 'I am writing to apply'\n"
    "- Connects the candidate's specific experience to the role's needs\n"
    "- Shows enthusiasm for the company and position\n"
    "- Closes with a clear call to action\n"
    "- Stays under 400 words\n"
    "- Never fabricates experience or credentials\n"
    "Return plain text with paragraph breaks."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _input(prompt: str, default: str = "") -> str:
    """Read a line from stdin with an optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _input_multiline(prompt: str) -> str:
    """Read multiple lines until user enters a blank line."""
    print(f"{prompt} (paste text, then press Enter twice to finish):")
    lines = []
    while True:
        line = input()
        if line == "":
            if lines:
                break
            continue
        lines.append(line)
    return "\n".join(lines)


def _confirm(prompt: str) -> bool:
    """Ask user yes/no and return True for 'y'."""
    return input(f"{prompt} (y/n): ").strip().lower() == "y"


def _get_gemini_model() -> genai.GenerativeModel:
    """Configure and return a Gemini GenerativeModel."""
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_model)


async def _gemini_generate(model: genai.GenerativeModel, prompt: str) -> str:
    """Call Gemini API asynchronously with retry logic.

    Args:
        model: Configured GenerativeModel instance.
        prompt: Full prompt text to send.

    Returns:
        Generated text response.
    """
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                model.generate_content, prompt
            )
            return response.text
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt + random.uniform(0, 1)
            logger.warning(
                "Gemini attempt %d/3 failed: %s. Retrying in %.1fs...",
                attempt + 1, exc, wait,
            )
            await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 1. Setup — collect user profile interactively
# ---------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace) -> None:
    """Collect user information and save to profile + database."""
    profile_name = getattr(args, "profile", "default")
    pm = ProfileManager()
    profile = pm.load(profile_name)

    print("\n=== Profile Setup ===\n")

    # Personal info
    profile.full_name = _input("Full name", profile.full_name)
    profile.email = _input("Email", profile.email)
    profile.phone = _input("Phone", profile.phone)

    # Skills
    skills_str = _input(
        "Skills (comma-separated)",
        ", ".join(profile.skills) if profile.skills else "",
    )
    if skills_str:
        profile.skills = [s.strip() for s in skills_str.split(",") if s.strip()]

    # Experience
    exp = _input("Years of experience", str(profile.experience_years or ""))
    if exp.isdigit():
        profile.experience_years = int(exp)

    profile.summary = _input("Professional summary", profile.summary)

    # Education
    print("\nEducation (leave blank to skip):")
    edu_text = _input("  Degree and school (e.g. 'B.S. CS, MIT 2020')")
    if edu_text:
        profile.education = [{"description": edu_text}]

    # Resume text
    print()
    if _confirm("Paste your resume text?"):
        resume_text = _input_multiline("Resume text")
        if resume_text:
            resume_path = Path("data/base_resume.txt")
            resume_path.parent.mkdir(parents=True, exist_ok=True)
            resume_path.write_text(resume_text, encoding="utf-8")
            profile.base_resume_path = str(resume_path)
            print(f"  Resume saved to {resume_path}")
    else:
        resume_path_str = _input("Path to resume file", profile.base_resume_path)
        if resume_path_str and Path(resume_path_str).exists():
            profile.base_resume_path = resume_path_str
        elif resume_path_str:
            logger.warning("Resume file not found: %s", resume_path_str)

    # Job preferences
    print("\n--- Job Preferences ---")
    profile.location = _input("Preferred location", profile.location or "Remote")
    keywords = _input("Job search keywords", profile.summary[:50] if profile.summary else "")
    profile.linkedin_url = _input("LinkedIn URL", profile.linkedin_url)

    # Save profile to JSON
    path = pm.save(profile, profile_name)
    print(f"\nProfile saved to {path}")

    # Also save to database (create tables + store a job-preferences marker)
    repo = ApplicationRepository()
    repo.create_tables()
    repo.close()

    logger.info("Profile '%s' setup complete.", profile_name)
    print("Setup complete!")


# ---------------------------------------------------------------------------
# 2. Scrape — run LinkedIn scraper
# ---------------------------------------------------------------------------

def cmd_scrape(args: argparse.Namespace) -> None:
    """Search LinkedIn for jobs and save results to the database."""
    query = getattr(args, "query", "") or ""
    location = getattr(args, "location", "Remote")

    if not query:
        query = _input("Job search keywords (e.g. 'Python Developer')")
        if not query:
            print("Search query is required.")
            return
        location = _input("Location", "Remote")

    async def _run() -> None:
        repo = ApplicationRepository()
        repo.create_tables()

        scraper = LinkedInScraper()
        try:
            print(f"\nSearching LinkedIn for '{query}' in '{location}'...")
            logger.info("Starting LinkedIn search: query=%s location=%s", query, location)

            await scraper.login()
            jobs = await scraper.search(query, location)

            for job in jobs:
                repo.save_job_posting(
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    url=job.url,
                    description=job.description,
                    salary=job.salary,
                    job_type=job.job_type,
                    source=job.source,
                )

            print(f"\nFound {len(jobs)} jobs from LinkedIn.")
            logger.info("LinkedIn returned %d jobs.", len(jobs))
        except Exception as exc:
            logger.error("LinkedIn scraper failed: %s", exc)
            print(f"Error: {exc}")
        finally:
            await scraper.close()
            repo.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. Apply — auto-apply workflow with Gemini AI
# ---------------------------------------------------------------------------

def cmd_apply(args: argparse.Namespace) -> None:
    """Apply to jobs with Gemini-customized resumes and cover letters."""
    profile_name = getattr(args, "profile", "default")
    max_apps = min(getattr(args, "max", MAX_APPLICATIONS_PER_RUN), MAX_APPLICATIONS_PER_RUN)

    async def _run() -> None:
        # Load profile
        pm = ProfileManager()
        user_profile = pm.load(profile_name)

        if not user_profile.base_resume_path:
            print("Error: No base resume in profile. Run 'setup' first.")
            return

        resume_file = Path(user_profile.base_resume_path)
        if not resume_file.exists():
            print(f"Error: Resume file not found: {resume_file}")
            return

        base_resume = resume_file.read_text(encoding="utf-8")

        if not settings.gemini_api_key:
            print("Error: GEMINI_API_KEY not set in .env file.")
            return

        # Get unapplied jobs from database
        repo = ApplicationRepository()
        repo.create_tables()

        applied_subq = select(Application.job_posting_id)
        stmt = (
            select(JobPosting)
            .where(JobPosting.id.not_in(applied_subq))
            .limit(max_apps)
        )
        postings = list(repo._session.scalars(stmt).all())

        if not postings:
            print("No unapplied jobs found. Run 'scrape' first.")
            repo.close()
            return

        print(f"\nFound {len(postings)} unapplied jobs (max {max_apps} per run).\n")

        # Set up Gemini
        gemini = _get_gemini_model()
        filler = FormFiller(headless=False)
        applied_count = 0

        try:
            await filler.launch()

            for i, posting in enumerate(postings, 1):
                print(f"\n--- [{i}/{len(postings)}] {posting.title} @ {posting.company} ---")
                print(f"  URL: {posting.url}")

                try:
                    # Customize resume with Gemini
                    print("  Customizing resume with Gemini...")
                    resume_prompt = (
                        f"{_RESUME_SYSTEM_PROMPT}\n\n"
                        f"## Base Resume\n\n{base_resume}\n\n"
                        f"## Job Description\n\n{posting.description or 'No description available'}\n\n"
                        "Please produce the tailored resume."
                    )
                    tailored_resume = await _gemini_generate(gemini, resume_prompt)
                    logger.info("Resume customized for posting %d.", posting.id)

                    # Generate cover letter with Gemini
                    print("  Generating cover letter with Gemini...")
                    cover_prompt = (
                        f"{_COVER_LETTER_SYSTEM_PROMPT}\n\n"
                        f"## Candidate Profile\n\n{base_resume}\n\n"
                        f"## Job Description\n\n{posting.description or 'No description available'}\n\n"
                        f"## Company: {posting.company}\n\n"
                        "Tone: professional\n\nPlease write the cover letter."
                    )
                    cover_letter = await _gemini_generate(gemini, cover_prompt)
                    logger.info("Cover letter generated for posting %d.", posting.id)

                    # Save documents
                    safe_company = posting.company.replace(" ", "_")[:30]
                    out_dir = f"output/{safe_company}_{posting.id}"
                    resume_path = save_as_docx(tailored_resume, f"{out_dir}/resume.docx")
                    cl_path = save_as_docx(cover_letter, f"{out_dir}/cover_letter.docx")
                    print(f"  Documents saved to {out_dir}/")

                    # Create application record
                    app = repo.create_application(posting.id)
                    repo.update_application_status(app.id, "resume_tailored")

                    # Open job URL in browser and fill form
                    print(f"  Opening application page...")
                    if filler._page:
                        await filler._page.goto(posting.url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)

                        result = await fill_application_form(
                            filler._page,
                            user_profile,
                            resume_path=str(resume_path),
                            cover_letter_path=str(cl_path),
                            screenshot_dir=out_dir,
                        )
                        print(
                            f"  Form fill: {result.fields_filled}/{result.fields_total} fields"
                        )

                        # Take screenshot
                        if result.screenshot_path:
                            print(f"  Screenshot: {result.screenshot_path}")
                        if result.errors:
                            for err in result.errors:
                                logger.warning("  Fill error: %s", err)

                    # Ask user for confirmation
                    if _confirm("  Submit this application?"):
                        try:
                            await filler.submit()
                            repo.update_application_status(app.id, "applied")
                            applied_count += 1
                            print("  Submitted!")
                            logger.info(
                                "Application %d submitted for posting %d.",
                                app.id, posting.id,
                            )
                        except Exception as exc:
                            logger.error("Submit failed for posting %d: %s", posting.id, exc)
                            print(f"  Submit failed: {exc}")
                    else:
                        repo.update_application_status(app.id, "saved")
                        print("  Skipped.")

                except Exception as exc:
                    logger.error("Failed to process posting %d: %s", posting.id, exc)
                    print(f"  Error: {exc}")
                    continue

                # Random delay between applications (30-60s)
                if i < len(postings):
                    delay = random.uniform(APPLY_DELAY_MIN, APPLY_DELAY_MAX)
                    print(f"  Waiting {delay:.0f}s before next application...")
                    await asyncio.sleep(delay)

        finally:
            await filler.close()
            repo.close()

        print(f"\nDone! Applied to {applied_count}/{len(postings)} jobs.")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. Stats — show application statistics
# ---------------------------------------------------------------------------

def cmd_stats(args: argparse.Namespace) -> None:
    """Display job and application statistics."""
    repo = ApplicationRepository()
    repo.create_tables()

    # Total jobs in database
    total_jobs = repo._session.scalar(select(func.count(JobPosting.id))) or 0

    # Jobs by source
    source_rows = repo._session.execute(
        select(JobPosting.source, func.count(JobPosting.id))
        .group_by(JobPosting.source)
    ).all()

    # Total applications
    total_apps = repo._session.scalar(select(func.count(Application.id))) or 0

    # Applications by status
    status_rows = repo._session.execute(
        select(Application.status, func.count(Application.id))
        .group_by(Application.status)
    ).all()

    repo.close()

    print("\n=== Job Application Stats ===\n")
    print(f"  Total jobs scraped:      {total_jobs}")
    if source_rows:
        for source, count in source_rows:
            print(f"    - {source or 'unknown':15s} {count}")

    print(f"\n  Total applications:      {total_apps}")
    if status_rows:
        for status, count in status_rows:
            print(f"    - {status:20s} {count}")
    else:
        print("    (no applications yet)")

    print()


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def interactive_menu() -> None:
    """Run the interactive menu loop."""
    print("\n====================================")
    print("  Job Application Automation Tool")
    print("      Powered by Google Gemini")
    print("====================================\n")

    menu_items = {
        "1": ("Setup profile", cmd_setup),
        "2": ("Scrape jobs (LinkedIn)", cmd_scrape),
        "3": ("Auto-apply", cmd_apply),
        "4": ("Stats", cmd_stats),
        "q": ("Quit", None),
    }

    while True:
        print("\nMenu:")
        for key, (label, _) in menu_items.items():
            print(f"  {key}. {label}")

        choice = input("\nSelect option: ").strip().lower()

        if choice == "q":
            print("Goodbye!")
            break

        if choice not in menu_items or menu_items[choice][1] is None:
            print("Invalid option. Try again.")
            continue

        _, handler = menu_items[choice]
        try:
            ns = argparse.Namespace(
                profile="default",
                query="",
                location="Remote",
                max=MAX_APPLICATIONS_PER_RUN,
                status=None,
            )

            if choice == "2":
                ns.query = _input("Search query (e.g. 'Python Developer')")
                if not ns.query:
                    print("Query is required.")
                    continue
                ns.location = _input("Location", "Remote")

            handler(ns)  # type: ignore[misc]
        except KeyboardInterrupt:
            print("\n  Interrupted.")
        except Exception as exc:
            logger.error("Command failed: %s", exc)
            print(f"Error: {exc}")


# ---------------------------------------------------------------------------
# Argparse CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with sub-commands."""
    parser = argparse.ArgumentParser(
        prog="job-app-bot",
        description="Job Application Automation Tool — search, tailor, apply with Gemini AI.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command")

    # setup
    sp_setup = sub.add_parser("setup", help="Set up your candidate profile")
    sp_setup.add_argument("--profile", "-p", default="default", help="Profile name")

    # scrape
    sp_scrape = sub.add_parser("scrape", help="Scrape LinkedIn for jobs")
    sp_scrape.add_argument("query", nargs="?", default="", help="Job title or keywords")
    sp_scrape.add_argument("--location", "-l", default="Remote", help="Location filter")

    # apply
    sp_apply = sub.add_parser("apply", help="Auto-apply to unapplied jobs")
    sp_apply.add_argument("--profile", "-p", default="default", help="Profile name")
    sp_apply.add_argument(
        "--max", "-m", type=int, default=MAX_APPLICATIONS_PER_RUN,
        help="Max applications per run (cap: 5)",
    )

    # stats
    sub.add_parser("stats", help="Show job and application statistics")

    # menu
    sub.add_parser("menu", help="Launch interactive menu")

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        setup_logging(logging.DEBUG)
        logger.debug("Debug logging enabled.")

    commands = {
        "setup": cmd_setup,
        "scrape": cmd_scrape,
        "apply": cmd_apply,
        "stats": cmd_stats,
        "menu": lambda _: interactive_menu(),
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
