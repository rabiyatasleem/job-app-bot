"""CLI entry point for the Job Application Automation Tool."""

import asyncio

import click
from rich.console import Console

from config import settings
from src.scrapers import IndeedScraper, LinkedInScraper
from src.ai import CoverLetterGenerator, ResumeCustomizer
from src.automation import FormFiller
from src.database import ApplicationRepository
from src.profiles import ProfileManager
from src.utils.logging import setup_logging

console = Console()
logger = setup_logging()


@click.group()
def cli():
    """Job Application Automation Tool — search, tailor, apply."""


@cli.command()
@click.option("--query", "-q", required=True, help="Job title or keywords")
@click.option("--location", "-l", default="Remote", help="Location filter")
@click.option("--source", "-s", type=click.Choice(["linkedin", "indeed", "all"]), default="all")
def search(query: str, location: str, source: str):
    """Search job boards and save results to the database."""

    async def _run():
        repo = ApplicationRepository()
        repo.create_tables()
        scrapers = []

        if source in ("linkedin", "all"):
            scrapers.append(LinkedInScraper())
        if source in ("indeed", "all"):
            scrapers.append(IndeedScraper())

        for scraper in scrapers:
            try:
                console.print(f"[bold]Searching {scraper.__class__.__name__}...[/bold]")
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
                console.print(f"  Found {len(jobs)} jobs")
            finally:
                await scraper.close()

        repo.close()

    asyncio.run(_run())


@cli.command()
@click.option("--job-id", "-j", required=True, type=int, help="Job posting ID")
@click.option("--profile", "-p", default="default", help="Profile name to use")
def tailor(job_id: int, profile: str):
    """Generate a tailored resume and cover letter for a job posting."""

    async def _run():
        pm = ProfileManager()
        user_profile = pm.load(profile)

        if not user_profile.base_resume_path:
            console.print("[red]No base resume set in profile. Run 'profile setup' first.[/red]")
            return

        repo = ApplicationRepository()
        from sqlalchemy import select
        from src.database.models import JobPosting

        posting = repo._session.get(JobPosting, job_id)
        if not posting:
            console.print(f"[red]Job posting {job_id} not found.[/red]")
            return

        from pathlib import Path

        base_resume = Path(user_profile.base_resume_path).read_text(encoding="utf-8")

        console.print("[bold]Tailoring resume...[/bold]")
        customizer = ResumeCustomizer()
        tailored_resume = await customizer.customize(base_resume, posting.description)

        console.print("[bold]Generating cover letter...[/bold]")
        generator = CoverLetterGenerator()
        cover_letter = await generator.generate(
            profile_summary=base_resume,
            job_description=posting.description,
        )

        from src.utils.file_export import save_as_docx

        out_dir = f"output/{posting.company}_{posting.id}"
        resume_path = save_as_docx(tailored_resume, f"{out_dir}/resume.docx")
        cl_path = save_as_docx(cover_letter, f"{out_dir}/cover_letter.docx")

        app = repo.create_application(posting.id)
        app.resume_path = str(resume_path)
        app.cover_letter_path = str(cl_path)
        app.status = "cover_letter_done"
        repo._session.commit()

        console.print(f"[green]Saved to {out_dir}/[/green]")
        repo.close()

    asyncio.run(_run())


@cli.command()
@click.option("--status", "-s", default=None, help="Filter by status")
def status(status: str | None):
    """Show tracked applications and their statuses."""
    repo = ApplicationRepository()
    repo.create_tables()
    apps = repo.list_applications(status=status)

    if not apps:
        console.print("[yellow]No applications found.[/yellow]")
        return

    for app in apps:
        posting = app.job_posting
        console.print(
            f"[bold]#{app.id}[/bold] {posting.title} @ {posting.company} "
            f"— [cyan]{app.status}[/cyan]"
        )

    repo.close()


@cli.command()
def profile():
    """Set up or view your candidate profile."""
    pm = ProfileManager()
    existing = pm.load("default")

    console.print("[bold]Current profile:[/bold]")
    console.print(f"  Name:  {existing.full_name or '(not set)'}")
    console.print(f"  Email: {existing.email or '(not set)'}")
    console.print(f"  Phone: {existing.phone or '(not set)'}")
    console.print(f"  Skills: {', '.join(existing.skills) or '(none)'}")
    console.print(f"  Resume: {existing.base_resume_path or '(not set)'}")


if __name__ == "__main__":
    cli()
