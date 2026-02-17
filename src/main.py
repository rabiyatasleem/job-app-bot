"""CLI entry point for the Job Application Automation Tool.

Provides both an interactive menu and argparse sub-commands for:
  1. Profile setup
  2. Job search
  3. Auto-apply
  4. Application status
  5. Settings management
"""

import argparse
import asyncio
import logging
import random
import sys
from pathlib import Path

from config import settings
from src.ai import CoverLetterGenerator, ResumeCustomizer
from src.automation import FormFiller, fill_application_form
from src.database import ApplicationRepository, JobPosting
from src.profiles import ProfileManager
from src.scrapers import IndeedScraper, LinkedInScraper
from src.utils.file_export import save_as_docx
from src.utils.logging import setup_logging

logger = setup_logging()

MAX_APPLICATIONS_PER_RUN = 10
APPLY_DELAY_MIN = 30.0
APPLY_DELAY_MAX = 60.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _input(prompt: str, default: str = "") -> str:
    """Read a line from stdin with an optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _confirm(prompt: str) -> bool:
    """Ask user yes/no and return True for 'y'."""
    return input(f"{prompt} (y/n): ").strip().lower() == "y"


# ---------------------------------------------------------------------------
# 1. Profile setup
# ---------------------------------------------------------------------------

def cmd_setup_profile(args: argparse.Namespace) -> None:
    """Collect user information and save to a profile."""
    profile_name = getattr(args, "profile", "default")
    pm = ProfileManager()
    profile = pm.load(profile_name)

    print("\n=== Profile Setup ===\n")

    profile.full_name = _input("Full name", profile.full_name)
    profile.email = _input("Email", profile.email)
    profile.phone = _input("Phone", profile.phone)
    profile.location = _input("Location", profile.location)
    profile.linkedin_url = _input("LinkedIn URL", profile.linkedin_url)
    profile.github_url = _input("GitHub URL", profile.github_url)
    profile.portfolio_url = _input("Portfolio URL", profile.portfolio_url)
    profile.summary = _input("Professional summary", profile.summary)

    skills_str = _input(
        "Skills (comma-separated)",
        ", ".join(profile.skills) if profile.skills else "",
    )
    if skills_str:
        profile.skills = [s.strip() for s in skills_str.split(",") if s.strip()]

    exp = _input("Years of experience", str(profile.experience_years or ""))
    if exp.isdigit():
        profile.experience_years = int(exp)

    resume_path = _input("Path to base resume", profile.base_resume_path)
    if resume_path and Path(resume_path).exists():
        profile.base_resume_path = resume_path
    elif resume_path:
        logger.warning("Resume file not found: %s", resume_path)

    path = pm.save(profile, profile_name)
    print(f"\nProfile saved to {path}")
    logger.info("Profile '%s' saved.", profile_name)


# ---------------------------------------------------------------------------
# 2. Find jobs
# ---------------------------------------------------------------------------

def cmd_find_jobs(args: argparse.Namespace) -> None:
    """Search job boards and save results to the database."""
    query = args.query
    location = getattr(args, "location", "Remote")
    source = getattr(args, "source", "all")

    async def _run() -> None:
        repo = ApplicationRepository()
        repo.create_tables()

        scrapers = []
        if source in ("linkedin", "all"):
            scrapers.append(("LinkedIn", LinkedInScraper()))
        if source in ("indeed", "all"):
            scrapers.append(("Indeed", IndeedScraper()))

        total = 0
        for name, scraper in scrapers:
            try:
                print(f"\nSearching {name} for '{query}' in '{location}'...")
                logger.info("Starting %s search: query=%s location=%s", name, query, location)
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
                total += len(jobs)
                print(f"  Found {len(jobs)} jobs from {name}")
                logger.info("%s returned %d jobs.", name, len(jobs))
            except Exception as exc:
                logger.error("%s scraper failed: %s", name, exc)
                print(f"  Error with {name}: {exc}")
            finally:
                await scraper.close()

        repo.close()
        print(f"\nTotal: {total} jobs saved to database.")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. Auto-apply
# ---------------------------------------------------------------------------

def cmd_auto_apply(args: argparse.Namespace) -> None:
    """Apply to jobs with AI-customized resumes and cover letters."""
    profile_name = getattr(args, "profile", "default")
    max_apps = getattr(args, "max", MAX_APPLICATIONS_PER_RUN)

    async def _run() -> None:
        pm = ProfileManager()
        user_profile = pm.load(profile_name)

        if not user_profile.base_resume_path:
            print("Error: No base resume in profile. Run 'setup' first.")
            logger.error("Auto-apply aborted: no base resume path in profile.")
            return

        resume_file = Path(user_profile.base_resume_path)
        if not resume_file.exists():
            print(f"Error: Resume file not found: {resume_file}")
            logger.error("Auto-apply aborted: resume file missing: %s", resume_file)
            return

        base_resume = resume_file.read_text(encoding="utf-8")

        repo = ApplicationRepository()
        repo.create_tables()

        # Find jobs without applications
        from sqlalchemy import select
        from src.database.models import Application

        applied_subq = select(Application.job_posting_id)
        stmt = select(JobPosting).where(JobPosting.id.not_in(applied_subq)).limit(max_apps)
        postings = list(repo._session.scalars(stmt).all())

        if not postings:
            print("No unapplied jobs found. Run 'find' first.")
            logger.info("No unapplied jobs to process.")
            repo.close()
            return

        print(f"\nFound {len(postings)} unapplied jobs (max {max_apps} per run).\n")
        logger.info("Starting auto-apply for %d postings.", len(postings))

        customizer = ResumeCustomizer()
        cover_gen = CoverLetterGenerator()
        filler = FormFiller(headless=False)

        applied_count = 0

        try:
            await filler.launch()

            for i, posting in enumerate(postings[:max_apps], 1):
                print(f"--- [{i}/{min(len(postings), max_apps)}] {posting.title} @ {posting.company} ---")
                logger.info(
                    "Processing posting %d: %s at %s", posting.id, posting.title, posting.company
                )

                try:
                    # Customize resume
                    print("  Customizing resume...")
                    tailored_resume = await customizer.customize(
                        base_resume, posting.description or ""
                    )
                    logger.info("Resume customized for posting %d.", posting.id)

                    # Generate cover letter
                    print("  Generating cover letter...")
                    cover_letter = await cover_gen.generate(
                        profile_summary=base_resume,
                        job_description=posting.description or "",
                    )
                    logger.info("Cover letter generated for posting %d.", posting.id)

                    # Save documents
                    safe_company = posting.company.replace(" ", "_")[:30]
                    out_dir = f"output/{safe_company}_{posting.id}"
                    resume_path = save_as_docx(tailored_resume, f"{out_dir}/resume.docx")
                    cl_path = save_as_docx(cover_letter, f"{out_dir}/cover_letter.docx")
                    print(f"  Saved to {out_dir}/")

                    # Create application record
                    app = repo.create_application(posting.id)
                    repo.update_application_status(app.id, "resume_tailored")

                    # Open application page and fill form
                    print(f"  Opening {posting.url}")
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
                        if result.screenshot_path:
                            print(f"  Screenshot: {result.screenshot_path}")
                        if result.errors:
                            for err in result.errors:
                                logger.warning("  Fill error: %s", err)

                    # Ask for confirmation
                    if _confirm("  Submit this application?"):
                        try:
                            await filler.submit()
                            repo.update_application_status(app.id, "applied")
                            applied_count += 1
                            print("  Submitted!")
                            logger.info("Application %d submitted for posting %d.", app.id, posting.id)
                        except Exception as exc:
                            logger.error("Submit failed for posting %d: %s", posting.id, exc)
                            print(f"  Submit failed: {exc}")
                    else:
                        repo.update_application_status(app.id, "saved")
                        print("  Skipped.")
                        logger.info("User skipped posting %d.", posting.id)

                except Exception as exc:
                    logger.error("Failed to process posting %d: %s", posting.id, exc)
                    print(f"  Error: {exc}")
                    continue

                # Random delay between applications
                if i < min(len(postings), max_apps):
                    delay = random.uniform(APPLY_DELAY_MIN, APPLY_DELAY_MAX)
                    print(f"  Waiting {delay:.0f}s before next application...")
                    await asyncio.sleep(delay)

        finally:
            await filler.close()
            repo.close()

        print(f"\nDone! Applied to {applied_count}/{len(postings[:max_apps])} jobs.")
        logger.info("Auto-apply complete: %d/%d applications submitted.", applied_count, len(postings[:max_apps]))

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. View applications
# ---------------------------------------------------------------------------

def cmd_view_applications(args: argparse.Namespace) -> None:
    """Display application history and statistics."""
    status_filter = getattr(args, "status", None)

    repo = ApplicationRepository()
    repo.create_tables()
    apps = repo.list_applications(status=status_filter)

    if not apps:
        print("No applications found.")
        repo.close()
        return

    # Stats
    statuses: dict[str, int] = {}
    for app in apps:
        statuses[app.status] = statuses.get(app.status, 0) + 1

    print(f"\n=== Applications ({len(apps)} total) ===\n")

    print("Status breakdown:")
    for s, count in sorted(statuses.items()):
        print(f"  {s}: {count}")

    print(f"\n{'ID':<5} {'Status':<18} {'Title':<35} {'Company':<25} {'Date'}")
    print("-" * 100)

    for app in apps:
        posting = app.job_posting
        date_str = app.created_at.strftime("%Y-%m-%d") if app.created_at else "N/A"
        title = (posting.title or "")[:33]
        company = (posting.company or "")[:23]
        print(f"{app.id:<5} {app.status:<18} {title:<35} {company:<25} {date_str}")

    repo.close()


# ---------------------------------------------------------------------------
# 5. Settings
# ---------------------------------------------------------------------------

def cmd_settings(args: argparse.Namespace) -> None:
    """Show or update configuration settings."""
    print("\n=== Current Settings ===\n")
    print(f"  Database URL:          {settings.database_url}")
    print(f"  Model:                 {settings.model_name}")
    print(f"  Max tokens:            {settings.max_tokens}")
    print(f"  Scrape delay:          {settings.scrape_delay_seconds}s")
    print(f"  Max pages per search:  {settings.max_pages_per_search}")
    print(f"  LinkedIn email:        {'(set)' if settings.linkedin_email else '(not set)'}")
    print(f"  Indeed email:          {'(set)' if settings.indeed_email else '(not set)'}")
    print(f"\n  Max apps per run:      {MAX_APPLICATIONS_PER_RUN}")
    print(f"  Apply delay:           {APPLY_DELAY_MIN}-{APPLY_DELAY_MAX}s")
    print("\nEdit the .env file to change settings.")


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def interactive_menu() -> None:
    """Run the interactive menu loop."""
    print("\n====================================")
    print("  Job Application Automation Tool")
    print("====================================\n")

    menu_items = {
        "1": ("Setup profile", cmd_setup_profile),
        "2": ("Find jobs", cmd_find_jobs),
        "3": ("Auto-apply", cmd_auto_apply),
        "4": ("View applications", cmd_view_applications),
        "5": ("Settings", cmd_settings),
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
            # Build a minimal namespace for menu-driven commands
            ns = argparse.Namespace(
                profile="default",
                query="",
                location="Remote",
                source="all",
                max=MAX_APPLICATIONS_PER_RUN,
                status=None,
            )

            if choice == "2":
                ns.query = _input("Search query (e.g. 'Python Developer')")
                if not ns.query:
                    print("Query is required.")
                    continue
                ns.location = _input("Location", "Remote")
                ns.source = _input("Source (linkedin/indeed/all)", "all")

            if choice == "4":
                status_val = _input("Filter by status (leave blank for all)", "")
                ns.status = status_val or None

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
        description="Job Application Automation Tool — search, tailor, apply.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command")

    # setup
    sp_setup = sub.add_parser("setup", help="Set up your candidate profile")
    sp_setup.add_argument("--profile", "-p", default="default", help="Profile name")

    # find
    sp_find = sub.add_parser("find", help="Search for jobs")
    sp_find.add_argument("query", help="Job title or keywords")
    sp_find.add_argument("--location", "-l", default="Remote", help="Location filter")
    sp_find.add_argument(
        "--source", "-s", choices=["linkedin", "indeed", "all"], default="all",
    )

    # apply
    sp_apply = sub.add_parser("apply", help="Auto-apply to unapplied jobs")
    sp_apply.add_argument("--profile", "-p", default="default", help="Profile name")
    sp_apply.add_argument(
        "--max", "-m", type=int, default=MAX_APPLICATIONS_PER_RUN,
        help="Max applications per run",
    )

    # status
    sp_status = sub.add_parser("status", help="View application history")
    sp_status.add_argument("--status", "-s", default=None, help="Filter by status")

    # settings
    sub.add_parser("settings", help="View current settings")

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
        "setup": cmd_setup_profile,
        "find": cmd_find_jobs,
        "apply": cmd_auto_apply,
        "status": cmd_view_applications,
        "settings": cmd_settings,
        "menu": lambda _: interactive_menu(),
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
