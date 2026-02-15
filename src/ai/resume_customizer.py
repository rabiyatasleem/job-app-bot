"""AI-powered resume customization using the Anthropic API."""

import anthropic

from config import settings


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
