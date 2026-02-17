"""Browser-based form filling automation using Playwright."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page, Locator

logger = logging.getLogger("job_app_bot.automation.form_filler")


@dataclass
class FormField:
    """Represents a single form field to fill."""

    selector: str
    value: str
    field_type: str = "text"  # text, select, checkbox, file


# ---------------------------------------------------------------------------
# Field-mapping keyword tables
# ---------------------------------------------------------------------------

_FIELD_KEYWORDS: dict[str, list[str]] = {
    "full_name": [
        "full name", "fullname", "your name", "candidate name", "applicant name",
        "name",
    ],
    "first_name": ["first name", "firstname", "given name", "fname"],
    "last_name": ["last name", "lastname", "surname", "family name", "lname"],
    "email": ["email", "e-mail", "email address"],
    "phone": [
        "phone", "telephone", "mobile", "cell", "phone number", "contact number",
    ],
    "location": [
        "location", "city", "address", "where are you located",
        "current location",
    ],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "github_url": ["github", "github url", "github profile"],
    "portfolio_url": ["portfolio", "website", "personal site", "portfolio url"],
    "summary": [
        "summary", "about you", "tell us about yourself", "cover letter",
        "additional information", "about",
    ],
    "experience_years": [
        "years of experience", "experience", "total experience",
        "years experience", "work experience",
    ],
    "education": [
        "education", "degree", "university", "school", "highest education",
        "qualification",
    ],
}

_RESUME_KEYWORDS = [
    "resume", "cv", "curriculum vitae", "upload resume", "attach resume",
    "upload cv", "attach cv",
]
_COVER_LETTER_KEYWORDS = [
    "cover letter", "covering letter", "upload cover letter",
    "attach cover letter",
]
_AGREEMENT_KEYWORDS = [
    "agree", "terms", "consent", "acknowledge", "i confirm",
    "privacy policy", "i accept", "authorization",
]

# Platform-specific selectors for common ATS systems
_ATS_SELECTORS: dict[str, dict[str, str]] = {
    "greenhouse": {
        "first_name": "#first_name",
        "last_name": "#last_name",
        "email": "#email",
        "phone": "#phone",
        "resume": "input[type='file'][name*='resume'], input[data-field='resume']",
        "cover_letter": "input[type='file'][name*='cover_letter']",
        "linkedin": "#job_application_answers_attributes_0_text_value, input[name*='linkedin']",
    },
    "lever": {
        "full_name": "input[name='name']",
        "email": "input[name='email']",
        "phone": "input[name='phone']",
        "resume": "input[type='file'][name='resume']",
        "linkedin": "input[name='urls[LinkedIn]']",
        "github": "input[name='urls[GitHub]']",
        "portfolio": "input[name='urls[Portfolio]']",
        "summary": "textarea[name='comments']",
    },
    "workday": {
        "resume": "input[data-automation-id='file-upload-input-ref']",
        "first_name": "input[data-automation-id='legalNameSection_firstName']",
        "last_name": "input[data-automation-id='legalNameSection_lastName']",
        "email": "input[data-automation-id='email']",
        "phone": "input[data-automation-id='phone-number']",
        "location": "input[data-automation-id='addressSection_city']",
    },
}


@dataclass
class DetectedField:
    """A form field detected on the page with its matching profile key."""

    locator: Locator
    tag: str  # input, select, textarea
    input_type: str  # text, email, file, checkbox, etc.
    label_text: str
    profile_key: str  # matched key from UserProfile, or ""
    confidence: float = 0.0


@dataclass
class FillResult:
    """Outcome of a fill_application_form call."""

    success: bool
    fields_filled: int = 0
    fields_total: int = 0
    screenshot_path: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip, and collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _fuzzy_score(haystack: str, needle: str) -> float:
    """Return a 0-1 similarity score between *haystack* and *needle*.

    Uses substring matching plus a bonus for exact containment.
    """
    h = _normalize(haystack)
    n = _normalize(needle)
    if not h or not n:
        return 0.0
    if n == h:
        return 1.0
    if n in h:
        return 0.8 + 0.2 * (len(n) / len(h))
    # Token overlap
    h_tokens = set(h.split())
    n_tokens = set(n.split())
    if not n_tokens:
        return 0.0
    overlap = len(h_tokens & n_tokens) / len(n_tokens)
    return overlap * 0.7


def _match_profile_key(label: str) -> tuple[str, float]:
    """Find the best matching UserProfile key for a label string.

    Returns:
        (profile_key, confidence) — key is "" if no match found above threshold.
    """
    best_key = ""
    best_score = 0.0
    for key, keywords in _FIELD_KEYWORDS.items():
        for kw in keywords:
            score = _fuzzy_score(label, kw)
            if score > best_score:
                best_score = score
                best_key = key
    if best_score < 0.4:
        return ("", 0.0)
    return (best_key, best_score)


def _is_resume_field(label: str) -> bool:
    norm = _normalize(label)
    return any(kw in norm for kw in _RESUME_KEYWORDS)


def _is_cover_letter_field(label: str) -> bool:
    norm = _normalize(label)
    return any(kw in norm for kw in _COVER_LETTER_KEYWORDS)


def _is_agreement_field(label: str) -> bool:
    norm = _normalize(label)
    return any(kw in norm for kw in _AGREEMENT_KEYWORDS)


# ---------------------------------------------------------------------------
# Core: FormFiller class
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Intelligent form filling
# ---------------------------------------------------------------------------

def _detect_ats_platform(url: str) -> str:
    """Detect the ATS platform from the URL.

    Returns:
        Platform name ("greenhouse", "lever", "workday") or "" if unknown.
    """
    url_lower = url.lower()
    if "greenhouse.io" in url_lower or "boards.greenhouse" in url_lower:
        return "greenhouse"
    if "lever.co" in url_lower or "jobs.lever" in url_lower:
        return "lever"
    if "myworkday" in url_lower or "workday.com" in url_lower:
        return "workday"
    return ""


async def _get_field_label(page: Page, element: Locator) -> str:
    """Extract the best label text for a form element.

    Checks (in order): associated <label>, aria-label, placeholder,
    name attribute, id attribute.
    """
    # aria-label
    aria = await element.get_attribute("aria-label") or ""
    if aria.strip():
        return aria.strip()

    # Associated <label> via id
    el_id = await element.get_attribute("id") or ""
    if el_id:
        label_loc = page.locator(f"label[for='{el_id}']")
        if await label_loc.count():
            text = (await label_loc.first.inner_text()).strip()
            if text:
                return text

    # Placeholder
    placeholder = await element.get_attribute("placeholder") or ""
    if placeholder.strip():
        return placeholder.strip()

    # name attribute
    name = await element.get_attribute("name") or ""
    if name.strip():
        # Convert name_with_underscores to readable text
        return name.replace("_", " ").replace("-", " ").replace("[", " ").replace("]", "").strip()

    return el_id.replace("_", " ").replace("-", " ").strip()


async def _detect_form_fields(page: Page) -> list[DetectedField]:
    """Scan the page for all fillable form fields.

    Returns:
        List of DetectedField with label text and matched profile keys.
    """
    detected: list[DetectedField] = []

    # Text-like inputs
    input_types = "input:not([type='hidden']):not([type='submit']):not([type='button'])"
    inputs = await page.locator(input_types).all()
    for inp in inputs:
        inp_type = (await inp.get_attribute("type") or "text").lower()
        label = await _get_field_label(page, inp)
        profile_key, confidence = _match_profile_key(label)
        detected.append(DetectedField(
            locator=inp,
            tag="input",
            input_type=inp_type,
            label_text=label,
            profile_key=profile_key,
            confidence=confidence,
        ))

    # Selects
    selects = await page.locator("select").all()
    for sel in selects:
        label = await _get_field_label(page, sel)
        profile_key, confidence = _match_profile_key(label)
        detected.append(DetectedField(
            locator=sel,
            tag="select",
            input_type="select",
            label_text=label,
            profile_key=profile_key,
            confidence=confidence,
        ))

    # Textareas
    textareas = await page.locator("textarea").all()
    for ta in textareas:
        label = await _get_field_label(page, ta)
        profile_key, confidence = _match_profile_key(label)
        detected.append(DetectedField(
            locator=ta,
            tag="textarea",
            input_type="textarea",
            label_text=label,
            profile_key=profile_key,
            confidence=confidence,
        ))

    return detected


def _get_profile_value(profile, key: str) -> str:
    """Safely extract a string value from the user profile for a given key.

    Handles compound keys like first_name / last_name by splitting full_name.
    """
    if key == "first_name":
        parts = (getattr(profile, "full_name", "") or "").split()
        return parts[0] if parts else ""
    if key == "last_name":
        parts = (getattr(profile, "full_name", "") or "").split()
        return " ".join(parts[1:]) if len(parts) > 1 else ""
    if key == "experience_years":
        val = getattr(profile, key, 0)
        return str(val) if val else ""
    if key == "education":
        edu_list = getattr(profile, key, [])
        if edu_list and isinstance(edu_list, list) and isinstance(edu_list[0], dict):
            entry = edu_list[0]
            return entry.get("degree", "")
        return str(edu_list) if edu_list else ""

    val = getattr(profile, key, "")
    return str(val) if val else ""


async def _fill_with_ats_selectors(
    page: Page, platform: str, profile, resume_path: str, cover_letter_path: str,
) -> int:
    """Try to fill fields using known ATS-specific selectors.

    Returns:
        Number of fields successfully filled.
    """
    selectors = _ATS_SELECTORS.get(platform, {})
    filled = 0
    for field_key, selector in selectors.items():
        loc = page.locator(selector)
        if not await loc.count():
            continue

        if field_key == "resume" and resume_path:
            try:
                await loc.first.set_input_files(resume_path)
                filled += 1
                logger.debug("ATS filled resume via %s", selector)
            except Exception as exc:
                logger.debug("ATS resume upload failed: %s", exc)
        elif field_key == "cover_letter" and cover_letter_path:
            try:
                await loc.first.set_input_files(cover_letter_path)
                filled += 1
                logger.debug("ATS filled cover_letter via %s", selector)
            except Exception as exc:
                logger.debug("ATS cover letter upload failed: %s", exc)
        elif field_key in ("resume", "cover_letter"):
            continue
        else:
            # Map ATS key to profile key
            profile_map = {
                "first_name": "first_name",
                "last_name": "last_name",
                "full_name": "full_name",
                "email": "email",
                "phone": "phone",
                "location": "location",
                "linkedin": "linkedin_url",
                "github": "github_url",
                "portfolio": "portfolio_url",
                "summary": "summary",
            }
            pk = profile_map.get(field_key, "")
            val = _get_profile_value(profile, pk) if pk else ""
            if val:
                try:
                    await loc.first.fill(val)
                    filled += 1
                    logger.debug("ATS filled %s = %s", field_key, val[:30])
                except Exception as exc:
                    logger.debug("ATS fill failed for %s: %s", field_key, exc)

    return filled


async def fill_application_form(
    page: Page,
    user_profile,
    resume_path: str = "",
    cover_letter_path: str = "",
    screenshot_dir: str = "output/screenshots",
) -> FillResult:
    """Intelligently detect and fill all form fields on a job application page.

    Detects the ATS platform, scans for form fields, maps them to profile
    data using fuzzy matching, uploads files, checks agreement boxes, and
    takes a screenshot before submission.

    Args:
        page: An active Playwright Page already navigated to the form.
        user_profile: A UserProfile (or compatible object) with candidate data.
        resume_path: Path to the resume file for upload.
        cover_letter_path: Path to the cover letter file for upload.
        screenshot_dir: Directory to save pre-submission screenshots.

    Returns:
        FillResult with success status, counts, and any errors.
    """
    result = FillResult(success=False)
    url = page.url
    logger.info("Starting intelligent form fill on %s", url)

    # 1. Detect ATS platform and try platform-specific selectors first
    platform = _detect_ats_platform(url)
    ats_filled = 0
    if platform:
        logger.info("Detected ATS platform: %s", platform)
        ats_filled = await _fill_with_ats_selectors(
            page, platform, user_profile, resume_path, cover_letter_path,
        )
        logger.info("ATS-specific selectors filled %d fields.", ats_filled)

    # 2. Detect all form fields on the page
    detected = await _detect_form_fields(page)
    result.fields_total = len(detected)
    logger.info("Detected %d form fields on page.", len(detected))

    # 3. Fill each field
    filled_keys: set[str] = set()

    for df in detected:
        try:
            # --- File uploads ---
            if df.input_type == "file":
                if _is_resume_field(df.label_text) and resume_path:
                    await df.locator.set_input_files(resume_path)
                    result.fields_filled += 1
                    logger.debug("Uploaded resume to '%s'", df.label_text)
                elif _is_cover_letter_field(df.label_text) and cover_letter_path:
                    await df.locator.set_input_files(cover_letter_path)
                    result.fields_filled += 1
                    logger.debug("Uploaded cover letter to '%s'", df.label_text)
                elif resume_path:
                    # Generic file input — default to resume
                    await df.locator.set_input_files(resume_path)
                    result.fields_filled += 1
                    logger.debug("Uploaded resume to generic file input")
                continue

            # --- Checkboxes ---
            if df.input_type == "checkbox":
                if _is_agreement_field(df.label_text):
                    is_checked = await df.locator.is_checked()
                    if not is_checked:
                        await df.locator.check()
                        result.fields_filled += 1
                        logger.debug("Checked agreement: '%s'", df.label_text)
                continue

            # --- Radio buttons (skip — need context) ---
            if df.input_type == "radio":
                continue

            # --- Matched profile fields ---
            if df.profile_key and df.profile_key not in filled_keys:
                value = _get_profile_value(user_profile, df.profile_key)
                if value:
                    if df.tag == "select":
                        await _fill_select(df.locator, value)
                    else:
                        await df.locator.fill(value)
                    result.fields_filled += 1
                    filled_keys.add(df.profile_key)
                    logger.debug(
                        "Filled '%s' (%s) = '%s'",
                        df.label_text, df.profile_key, value[:50],
                    )

        except Exception as exc:
            error_msg = f"Error filling '{df.label_text}': {exc}"
            result.errors.append(error_msg)
            logger.warning(error_msg)

    result.fields_filled += ats_filled

    # 4. Take screenshot before submission
    try:
        ss_dir = Path(screenshot_dir)
        ss_dir.mkdir(parents=True, exist_ok=True)
        # Use sanitized URL fragment as filename
        safe_name = re.sub(r"[^\w]", "_", url.split("//")[-1][:60])
        ss_path = ss_dir / f"pre_submit_{safe_name}.png"
        await page.screenshot(path=str(ss_path), full_page=True)
        result.screenshot_path = str(ss_path)
        logger.info("Screenshot saved: %s", ss_path)
    except Exception as exc:
        logger.warning("Failed to take screenshot: %s", exc)

    result.success = result.fields_filled > 0
    logger.info(
        "Form fill complete: %d/%d fields filled, success=%s",
        result.fields_filled, result.fields_total, result.success,
    )
    return result


async def _fill_select(locator: Locator, value: str) -> None:
    """Try to select an option by value, then label, then fuzzy match."""
    try:
        await locator.select_option(value=value)
        return
    except Exception:
        pass

    try:
        await locator.select_option(label=value)
        return
    except Exception:
        pass

    # Fuzzy: find best-matching option text
    options = await locator.locator("option").all()
    best_option = None
    best_score = 0.0
    for opt in options:
        text = (await opt.inner_text()).strip()
        score = _fuzzy_score(text, value)
        if score > best_score:
            best_score = score
            best_option = text
    if best_option and best_score >= 0.4:
        await locator.select_option(label=best_option)
    else:
        raise ValueError(f"No matching option for '{value}'")
