"""AI-powered resume customization using the Anthropic API."""

import asyncio
import logging

import anthropic

from config import settings

logger = logging.getLogger("job_app_bot.ai.resume_customizer")

_CUSTOMIZE_SYSTEM_PROMPT = (
    "You are an expert resume writer. Customize the given resume for the job "
    "description while keeping all information truthful. Highlight relevant "
    "experience and skills. Use ATS-friendly formatting."
)


class ResumeCustomizer:
    """Tailors a base resume to match a specific job description.

    Uses Claude to rewrite bullet points, reorder sections, and
    highlight the most relevant skills for each application.

    Usage:
        customizer = ResumeCustomizer()
        tailored = await customizer.customize(base_resume, job_description)
    """

    SYSTEM_PROMPT = (
        "You are an expert resume writer. Given a candidate's base resume and a "
        "target job description, produce a tailored resume that:\n"
        "- Highlights experience and skills most relevant to the role\n"
        "- Uses keywords from the job description naturally\n"
        "- Keeps all facts truthful — never fabricate experience\n"
        "- Maintains professional tone and concise bullet points\n"
        "Return the resume in clean Markdown format."
    )

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def customize(self, base_resume: str, job_description: str) -> str:
        """Generate a tailored resume for a specific job posting.

        Args:
            base_resume: The candidate's master resume (Markdown or plain text).
            job_description: Full text of the target job posting.

        Returns:
            Tailored resume as a Markdown string.
        """
        message = await self._client.messages.create(
            model=settings.model_name,
            max_tokens=settings.max_tokens,
            system=self.SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"## Base Resume\n\n{base_resume}\n\n"
                        f"## Job Description\n\n{job_description}\n\n"
                        "Please produce the tailored resume."
                    ),
                }
            ],
        )
        return message.content[0].text

    async def suggest_skills(self, job_description: str, current_skills: list[str]) -> list[str]:
        """Identify skills from the job description the candidate should emphasize.

        Args:
            job_description: Full text of the target job posting.
            current_skills: Skills already listed on the candidate's resume.

        Returns:
            Ordered list of skills to highlight, most important first.
        """
        message = await self._client.messages.create(
            model=settings.model_name,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Job description:\n{job_description}\n\n"
                        f"Candidate skills: {', '.join(current_skills)}\n\n"
                        "List the top skills from the candidate's list that best match "
                        "this job, in order of relevance. One per line, no numbering."
                    ),
                }
            ],
        )
        return [line.strip() for line in message.content[0].text.splitlines() if line.strip()]


async def customize_resume(
    base_resume: str, job_description: str, *, retries: int = 3
) -> str:
    """Customize a resume for a job description using Claude.

    Analyzes the job requirements and tailors the resume to highlight
    relevant skills and experience. All information is kept truthful
    and the output is optimized for ATS systems.

    Args:
        base_resume: The candidate's original resume text.
        job_description: Full text of the target job posting.
        retries: Number of retry attempts on API failure.

    Returns:
        Customized resume text.

    Raises:
        anthropic.APIError: If all retry attempts are exhausted.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_content = (
        f"## Base Resume\n\n{base_resume}\n\n"
        f"## Job Description\n\n{job_description}\n\n"
        "Customize this resume for the job description. "
        "Keep all information truthful. Optimize formatting for ATS systems. "
        "Return only the customized resume text."
    )

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            logger.info("Calling Claude API (attempt %d/%d)...", attempt, retries)
            message = await client.messages.create(
                model=settings.model_name,
                max_tokens=settings.max_tokens,
                system=_CUSTOMIZE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            result = message.content[0].text
            logger.info(
                "Resume customized successfully (%d characters).", len(result)
            )
            return result
        except anthropic.APIError as exc:
            last_exc = exc
            wait = 2 ** attempt
            logger.warning(
                "API call failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, retries, exc, wait,
            )
            await asyncio.sleep(wait)

    logger.error("All %d retry attempts exhausted.", retries)
    raise last_exc  # type: ignore[misc]


async def main() -> None:
    """Example usage of customize_resume."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    base_resume = (
        "John Doe\n"
        "Software Engineer | john@example.com\n\n"
        "EXPERIENCE\n"
        "Senior Developer, Acme Corp (2020-Present)\n"
        "- Built REST APIs using Python/FastAPI serving 1M+ requests/day\n"
        "- Led migration from monolith to microservices architecture\n"
        "- Implemented CI/CD pipelines with GitHub Actions\n"
        "- Mentored 3 junior developers\n\n"
        "Developer, StartupXYZ (2017-2020)\n"
        "- Developed full-stack web apps with React and Django\n"
        "- Managed PostgreSQL databases and Redis caching\n"
        "- Wrote unit and integration tests (95% coverage)\n\n"
        "SKILLS\n"
        "Python, JavaScript, TypeScript, FastAPI, Django, React, PostgreSQL, "
        "Redis, Docker, Kubernetes, AWS, CI/CD, Git\n\n"
        "EDUCATION\n"
        "B.S. Computer Science, State University (2017)"
    )

    job_description = (
        "Senior Python Developer - Remote\n\n"
        "We're looking for a Senior Python Developer to join our backend team.\n\n"
        "Requirements:\n"
        "- 5+ years Python experience\n"
        "- Experience with FastAPI or Django\n"
        "- Strong knowledge of PostgreSQL\n"
        "- Experience with Docker and Kubernetes\n"
        "- CI/CD pipeline experience\n"
        "- Excellent communication skills\n\n"
        "Nice to have:\n"
        "- AWS experience\n"
        "- Microservices architecture\n"
        "- Team lead experience"
    )

    customized = await customize_resume(base_resume, job_description)
    print("=" * 60)
    print("CUSTOMIZED RESUME")
    print("=" * 60)
    print(customized)


if __name__ == "__main__":
    asyncio.run(main())
