"""AI-powered cover letter generation using the Anthropic API."""

import anthropic

from config import settings


class CoverLetterGenerator:
    """Generates tailored cover letters for job applications.

    Uses Claude to write compelling, personalized cover letters
    that connect the candidate's experience to the role.

    Usage:
        generator = CoverLetterGenerator()
        letter = await generator.generate(profile, job_description)
    """

    SYSTEM_PROMPT = (
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

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(
        self,
        profile_summary: str,
        job_description: str,
        company_info: str = "",
        tone: str = "professional",
    ) -> str:
        """Generate a tailored cover letter.

        Args:
            profile_summary: Candidate's background summary / resume highlights.
            job_description: Full text of the target job posting.
            company_info: Optional extra context about the company.
            tone: Writing tone — 'professional', 'conversational', or 'enthusiastic'.

        Returns:
            Cover letter as plain text.
        """
        user_content = (
            f"## Candidate Profile\n\n{profile_summary}\n\n"
            f"## Job Description\n\n{job_description}\n\n"
        )
        if company_info:
            user_content += f"## Company Info\n\n{company_info}\n\n"
        user_content += f"Tone: {tone}\n\nPlease write the cover letter."

        message = await self._client.messages.create(
            model=settings.model_name,
            max_tokens=settings.max_tokens,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return message.content[0].text
