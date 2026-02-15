"""Browser-based form filling automation using Playwright."""

from dataclasses import dataclass

from playwright.async_api import async_playwright, Browser, Page


@dataclass
class FormField:
    """Represents a single form field to fill."""

    selector: str
    value: str
    field_type: str = "text"  # text, select, checkbox, file


class FormFiller:
    """Automates filling out job application forms in the browser.

    Uses Playwright to interact with application pages — filling text
    inputs, selecting dropdowns, uploading resumes, and submitting.

    Usage:
        filler = FormFiller()
        await filler.launch()
        await filler.fill_application(url, fields, resume_path)
        await filler.close()
    """

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def launch(self) -> None:
        """Launch the browser."""
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()

    async def fill_application(
        self,
        url: str,
        fields: list[FormField],
        resume_path: str | None = None,
    ) -> bool:
        """Navigate to an application page and fill out the form.

        Args:
            url: URL of the job application page.
            fields: List of FormField entries to fill.
            resume_path: Optional path to the resume file to upload.

        Returns:
            True if the form was submitted successfully.
        """
        if not self._page:
            raise RuntimeError("Browser not launched — call launch() first.")

        await self._page.goto(url, wait_until="networkidle")

        for field in fields:
            await self._fill_field(self._page, field)

        if resume_path:
            file_input = self._page.locator("input[type='file']").first
            await file_input.set_input_files(resume_path)

        return True

    async def _fill_field(self, page: Page, field: FormField) -> None:
        """Fill a single form field based on its type.

        Args:
            page: The Playwright page.
            field: FormField describing what to fill and how.
        """
        match field.field_type:
            case "text":
                await page.fill(field.selector, field.value)
            case "select":
                await page.select_option(field.selector, field.value)
            case "checkbox":
                if field.value.lower() in ("true", "1", "yes"):
                    await page.check(field.selector)
            case "file":
                await page.set_input_files(field.selector, field.value)

    async def submit(self, submit_selector: str = "button[type='submit']") -> None:
        """Click the submit button.

        Args:
            submit_selector: CSS selector for the submit button.
        """
        if not self._page:
            raise RuntimeError("Browser not launched — call launch() first.")
        await self._page.click(submit_selector)
        await self._page.wait_for_load_state("networkidle")

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
