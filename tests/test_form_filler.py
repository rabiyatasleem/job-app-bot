"""Tests for the FormFiller browser automation and intelligent form filling."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.automation.form_filler import (
    FormFiller,
    FormField,
    FillResult,
    DetectedField,
    fill_application_form,
    _normalize,
    _fuzzy_score,
    _match_profile_key,
    _is_resume_field,
    _is_cover_letter_field,
    _is_agreement_field,
    _detect_ats_platform,
    _get_field_label,
    _detect_form_fields,
    _get_profile_value,
    _fill_with_ats_selectors,
    _fill_select,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_filler_with_page() -> tuple[FormFiller, AsyncMock]:
    """Return a FormFiller with a mocked Playwright page already attached."""
    filler = FormFiller(headless=True)
    page = AsyncMock()

    # .locator(...).first returns an AsyncMock we can inspect
    file_input = AsyncMock()
    locator_mock = MagicMock()
    locator_mock.first = file_input
    page.locator = MagicMock(return_value=locator_mock)

    filler._page = page
    filler._browser = AsyncMock()
    return filler, page


# ===================================================================
# FormField dataclass
# ===================================================================

class TestFormField:

    def test_defaults(self):
        field = FormField(selector="#name", value="Alice")
        assert field.selector == "#name"
        assert field.value == "Alice"
        assert field.field_type == "text"

    def test_custom_type(self):
        field = FormField(selector="#role", value="engineer", field_type="select")
        assert field.field_type == "select"


# ===================================================================
# __init__
# ===================================================================

class TestInit:

    def test_default_headless_false(self):
        filler = FormFiller()
        assert filler._headless is False
        assert filler._browser is None
        assert filler._page is None

    def test_headless_true(self):
        filler = FormFiller(headless=True)
        assert filler._headless is True


# ===================================================================
# launch
# ===================================================================

class TestLaunch:

    @pytest.mark.asyncio
    async def test_launch_creates_browser_and_page(self):
        mock_page = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("src.automation.form_filler.async_playwright") as mock_pw:
            mock_pw.return_value.start = AsyncMock(return_value=mock_pw_instance)

            filler = FormFiller(headless=True)
            await filler.launch()

        mock_pw_instance.chromium.launch.assert_awaited_once_with(headless=True)
        mock_browser.new_page.assert_awaited_once()
        assert filler._browser is mock_browser
        assert filler._page is mock_page


# ===================================================================
# fill_application
# ===================================================================

class TestFillApplication:

    @pytest.mark.asyncio
    async def test_raises_if_not_launched(self):
        filler = FormFiller()

        with pytest.raises(RuntimeError, match="Browser not launched"):
            await filler.fill_application("https://example.com", [])

    @pytest.mark.asyncio
    async def test_navigates_to_url(self):
        filler, page = _make_filler_with_page()

        await filler.fill_application("https://example.com/apply", [])

        page.goto.assert_awaited_once_with(
            "https://example.com/apply", wait_until="networkidle"
        )

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        filler, _ = _make_filler_with_page()

        result = await filler.fill_application("https://example.com/apply", [])

        assert result is True

    @pytest.mark.asyncio
    async def test_fills_text_fields(self):
        filler, page = _make_filler_with_page()
        fields = [
            FormField(selector="#name", value="Jane Doe"),
            FormField(selector="#email", value="jane@test.com"),
        ]

        await filler.fill_application("https://example.com/apply", fields)

        page.fill.assert_any_await("#name", "Jane Doe")
        page.fill.assert_any_await("#email", "jane@test.com")
        assert page.fill.await_count == 2

    @pytest.mark.asyncio
    async def test_fills_select_field(self):
        filler, page = _make_filler_with_page()
        fields = [FormField(selector="#country", value="US", field_type="select")]

        await filler.fill_application("https://example.com/apply", fields)

        page.select_option.assert_awaited_once_with("#country", "US")

    @pytest.mark.asyncio
    async def test_fills_checkbox_true(self):
        filler, page = _make_filler_with_page()
        fields = [FormField(selector="#agree", value="true", field_type="checkbox")]

        await filler.fill_application("https://example.com/apply", fields)

        page.check.assert_awaited_once_with("#agree")

    @pytest.mark.asyncio
    async def test_checkbox_yes_and_1_also_check(self):
        filler, page = _make_filler_with_page()
        fields = [
            FormField(selector="#terms", value="yes", field_type="checkbox"),
            FormField(selector="#newsletter", value="1", field_type="checkbox"),
        ]

        await filler.fill_application("https://example.com/apply", fields)

        page.check.assert_any_await("#terms")
        page.check.assert_any_await("#newsletter")
        assert page.check.await_count == 2

    @pytest.mark.asyncio
    async def test_checkbox_false_does_not_check(self):
        filler, page = _make_filler_with_page()
        fields = [FormField(selector="#spam", value="false", field_type="checkbox")]

        await filler.fill_application("https://example.com/apply", fields)

        page.check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fills_file_field(self):
        filler, page = _make_filler_with_page()
        fields = [
            FormField(selector="#upload", value="/path/to/doc.pdf", field_type="file")
        ]

        await filler.fill_application("https://example.com/apply", fields)

        page.set_input_files.assert_awaited_once_with("#upload", "/path/to/doc.pdf")

    @pytest.mark.asyncio
    async def test_resume_upload_via_file_input(self):
        filler, page = _make_filler_with_page()
        file_input = page.locator.return_value.first

        await filler.fill_application(
            "https://example.com/apply", [], resume_path="/tmp/resume.docx"
        )

        page.locator.assert_called_with("input[type='file']")
        file_input.set_input_files.assert_awaited_once_with("/tmp/resume.docx")

    @pytest.mark.asyncio
    async def test_no_resume_skips_file_upload(self):
        filler, page = _make_filler_with_page()

        await filler.fill_application("https://example.com/apply", [], resume_path=None)

        page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_field_types(self):
        filler, page = _make_filler_with_page()
        fields = [
            FormField(selector="#name", value="Jane"),
            FormField(selector="#role", value="eng", field_type="select"),
            FormField(selector="#agree", value="yes", field_type="checkbox"),
            FormField(selector="#cv", value="/cv.pdf", field_type="file"),
        ]

        await filler.fill_application("https://example.com/apply", fields)

        page.fill.assert_awaited_once_with("#name", "Jane")
        page.select_option.assert_awaited_once_with("#role", "eng")
        page.check.assert_awaited_once_with("#agree")
        page.set_input_files.assert_awaited_once_with("#cv", "/cv.pdf")

    @pytest.mark.asyncio
    async def test_unknown_field_type_is_noop(self):
        """An unrecognized field_type should not raise."""
        filler, page = _make_filler_with_page()
        fields = [FormField(selector="#x", value="y", field_type="radio")]

        await filler.fill_application("https://example.com/apply", fields)

        # None of the known handlers should have been called
        page.fill.assert_not_awaited()
        page.select_option.assert_not_awaited()
        page.check.assert_not_awaited()
        page.set_input_files.assert_not_awaited()


# ===================================================================
# submit
# ===================================================================

class TestSubmit:

    @pytest.mark.asyncio
    async def test_raises_if_not_launched(self):
        filler = FormFiller()

        with pytest.raises(RuntimeError, match="Browser not launched"):
            await filler.submit()

    @pytest.mark.asyncio
    async def test_clicks_default_submit_button(self):
        filler, page = _make_filler_with_page()

        await filler.submit()

        page.click.assert_awaited_once_with("button[type='submit']")
        page.wait_for_load_state.assert_awaited_once_with("networkidle")

    @pytest.mark.asyncio
    async def test_clicks_custom_selector(self):
        filler, page = _make_filler_with_page()

        await filler.submit(submit_selector="#apply-btn")

        page.click.assert_awaited_once_with("#apply-btn")

    @pytest.mark.asyncio
    async def test_waits_for_network_idle_after_click(self):
        filler, page = _make_filler_with_page()

        await filler.submit()

        page.wait_for_load_state.assert_awaited_once_with("networkidle")


# ===================================================================
# close
# ===================================================================

class TestClose:

    @pytest.mark.asyncio
    async def test_closes_browser_and_clears_refs(self):
        filler, _ = _make_filler_with_page()
        mock_browser = filler._browser

        await filler.close()

        mock_browser.close.assert_awaited_once()
        assert filler._browser is None
        assert filler._page is None

    @pytest.mark.asyncio
    async def test_noop_when_not_launched(self):
        filler = FormFiller()

        await filler.close()

        assert filler._browser is None
        assert filler._page is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        filler, _ = _make_filler_with_page()

        await filler.close()
        await filler.close()

        assert filler._browser is None


# ===================================================================
# Helpers — fake UserProfile
# ===================================================================

@dataclass
class _FakeProfile:
    """Minimal stand-in for UserProfile used in tests."""

    full_name: str = "Jane Doe"
    email: str = "jane@example.com"
    phone: str = "555-1234"
    location: str = "New York"
    linkedin_url: str = "https://linkedin.com/in/janedoe"
    github_url: str = "https://github.com/janedoe"
    portfolio_url: str = "https://janedoe.dev"
    summary: str = "Experienced developer"
    skills: list = field(default_factory=lambda: ["Python", "SQL"])
    experience_years: int = 5
    education: list = field(default_factory=lambda: [{"degree": "B.S. Computer Science"}])
    work_history: list = field(default_factory=list)
    base_resume_path: str = ""


def _make_element(
    *,
    aria_label: str = "",
    el_id: str = "",
    placeholder: str = "",
    name: str = "",
    el_type: str = "text",
    is_checked: bool = False,
) -> AsyncMock:
    """Build a mock Playwright Locator for a form element."""
    el = AsyncMock()

    attrs = {
        "aria-label": aria_label or None,
        "id": el_id or None,
        "placeholder": placeholder or None,
        "name": name or None,
        "type": el_type,
    }
    el.get_attribute = AsyncMock(side_effect=lambda a: attrs.get(a))
    el.is_checked = AsyncMock(return_value=is_checked)
    return el


def _make_page_with_fields(
    *,
    inputs: list | None = None,
    selects: list | None = None,
    textareas: list | None = None,
    url: str = "https://example.com/apply",
    label_text: str = "",
) -> AsyncMock:
    """Build a mock Page that returns given form elements for locator queries."""
    page = AsyncMock()
    page.url = url

    inputs = inputs or []
    selects = selects or []
    textareas = textareas or []

    def locator_side_effect(selector):
        loc = AsyncMock()
        if "input:not" in selector:
            loc.all = AsyncMock(return_value=inputs)
        elif selector == "select":
            loc.all = AsyncMock(return_value=selects)
        elif selector == "textarea":
            loc.all = AsyncMock(return_value=textareas)
        elif selector.startswith("label[for="):
            if label_text:
                loc.count = AsyncMock(return_value=1)
                loc.first = AsyncMock()
                loc.first.inner_text = AsyncMock(return_value=label_text)
            else:
                loc.count = AsyncMock(return_value=0)
        else:
            loc.count = AsyncMock(return_value=0)
            loc.first = AsyncMock()
        return loc

    page.locator = MagicMock(side_effect=locator_side_effect)
    return page


# ===================================================================
# _normalize
# ===================================================================

class TestNormalize:

    def test_lowercase(self):
        assert _normalize("HELLO") == "hello"

    def test_strip_whitespace(self):
        assert _normalize("  hello  ") == "hello"

    def test_collapse_whitespace(self):
        assert _normalize("full   name") == "full name"

    def test_mixed(self):
        assert _normalize("  First   Name  ") == "first name"

    def test_empty(self):
        assert _normalize("") == ""


# ===================================================================
# _fuzzy_score
# ===================================================================

class TestFuzzyScore:

    def test_exact_match_returns_one(self):
        assert _fuzzy_score("email", "email") == 1.0

    def test_exact_match_case_insensitive(self):
        assert _fuzzy_score("Email", "email") == 1.0

    def test_substring_match_high_score(self):
        score = _fuzzy_score("Your Email Address", "email")
        assert 0.8 <= score < 1.0

    def test_no_overlap_returns_zero(self):
        assert _fuzzy_score("phone number", "github") == 0.0

    def test_empty_haystack_returns_zero(self):
        assert _fuzzy_score("", "email") == 0.0

    def test_empty_needle_returns_zero(self):
        assert _fuzzy_score("email", "") == 0.0

    def test_both_empty_returns_zero(self):
        assert _fuzzy_score("", "") == 0.0

    def test_partial_token_overlap(self):
        score = _fuzzy_score("first name here", "first name")
        assert score > 0.4

    def test_single_token_overlap(self):
        score = _fuzzy_score("your phone number", "phone")
        # "phone" is substring of haystack
        assert score > 0.8


# ===================================================================
# _match_profile_key
# ===================================================================

class TestMatchProfileKey:

    def test_exact_email(self):
        key, score = _match_profile_key("email")
        assert key == "email"
        assert score == 1.0

    def test_email_address_label(self):
        key, _ = _match_profile_key("Email Address")
        assert key == "email"

    def test_first_name(self):
        key, _ = _match_profile_key("First Name")
        assert key == "first_name"

    def test_last_name(self):
        key, _ = _match_profile_key("Last Name")
        assert key == "last_name"

    def test_phone_number(self):
        key, _ = _match_profile_key("Phone Number")
        assert key == "phone"

    def test_linkedin_url(self):
        key, _ = _match_profile_key("LinkedIn Profile URL")
        assert key == "linkedin_url"

    def test_github(self):
        key, _ = _match_profile_key("GitHub URL")
        assert key == "github_url"

    def test_years_of_experience(self):
        key, _ = _match_profile_key("Years of Experience")
        assert key == "experience_years"

    def test_education_degree(self):
        key, _ = _match_profile_key("Highest Education")
        assert key == "education"

    def test_no_match_returns_empty(self):
        key, score = _match_profile_key("xyzzy")
        assert key == ""
        assert score == 0.0

    def test_low_confidence_returns_empty(self):
        key, score = _match_profile_key("random unrelated label")
        assert key == ""
        assert score == 0.0

    def test_full_name_label(self):
        key, _ = _match_profile_key("Full Name")
        assert key == "full_name"

    def test_location_city(self):
        key, _ = _match_profile_key("City")
        assert key == "location"


# ===================================================================
# Keyword detection helpers
# ===================================================================

class TestKeywordDetection:

    def test_is_resume_field_resume(self):
        assert _is_resume_field("Upload Resume") is True

    def test_is_resume_field_cv(self):
        assert _is_resume_field("Attach CV") is True

    def test_is_resume_field_negative(self):
        assert _is_resume_field("First Name") is False

    def test_is_cover_letter_field_positive(self):
        assert _is_cover_letter_field("Upload Cover Letter") is True

    def test_is_cover_letter_field_negative(self):
        assert _is_cover_letter_field("Resume") is False

    def test_is_agreement_field_agree(self):
        assert _is_agreement_field("I agree to terms") is True

    def test_is_agreement_field_consent(self):
        assert _is_agreement_field("Privacy consent") is True

    def test_is_agreement_field_negative(self):
        assert _is_agreement_field("Email") is False

    def test_is_resume_field_case_insensitive(self):
        assert _is_resume_field("UPLOAD RESUME") is True

    def test_is_agreement_field_authorization(self):
        assert _is_agreement_field("I provide authorization") is True


# ===================================================================
# _detect_ats_platform
# ===================================================================

class TestDetectAtsPlatform:

    def test_greenhouse_io(self):
        assert _detect_ats_platform("https://boards.greenhouse.io/company/jobs/123") == "greenhouse"

    def test_greenhouse_boards(self):
        assert _detect_ats_platform("https://boards.greenhouse.io/apply") == "greenhouse"

    def test_lever(self):
        assert _detect_ats_platform("https://jobs.lever.co/company/123") == "lever"

    def test_lever_co(self):
        assert _detect_ats_platform("https://lever.co/apply") == "lever"

    def test_workday(self):
        assert _detect_ats_platform("https://company.myworkday.com/apply") == "workday"

    def test_workday_dot_com(self):
        assert _detect_ats_platform("https://workday.com/apply") == "workday"

    def test_unknown_returns_empty(self):
        assert _detect_ats_platform("https://example.com/apply") == ""

    def test_case_insensitive(self):
        assert _detect_ats_platform("https://BOARDS.GREENHOUSE.IO/apply") == "greenhouse"


# ===================================================================
# _get_field_label
# ===================================================================

class TestGetFieldLabel:

    @pytest.mark.asyncio
    async def test_returns_aria_label_first(self):
        el = _make_element(aria_label="Full Name", el_id="name", placeholder="Enter name")
        page = AsyncMock()

        result = await _get_field_label(page, el)

        assert result == "Full Name"

    @pytest.mark.asyncio
    async def test_falls_back_to_label_for(self):
        el = _make_element(el_id="email_input")
        page = _make_page_with_fields(url="https://x.com", label_text="Email Address")

        result = await _get_field_label(page, el)

        assert result == "Email Address"

    @pytest.mark.asyncio
    async def test_falls_back_to_placeholder(self):
        el = _make_element(placeholder="Enter your phone")
        page = _make_page_with_fields(url="https://x.com")

        result = await _get_field_label(page, el)

        assert result == "Enter your phone"

    @pytest.mark.asyncio
    async def test_falls_back_to_name_attribute(self):
        el = _make_element(name="first_name")
        page = _make_page_with_fields(url="https://x.com")

        result = await _get_field_label(page, el)

        assert result == "first name"

    @pytest.mark.asyncio
    async def test_name_with_brackets_cleaned(self):
        el = _make_element(name="urls[LinkedIn]")
        page = _make_page_with_fields(url="https://x.com")

        result = await _get_field_label(page, el)

        assert result == "urls LinkedIn"

    @pytest.mark.asyncio
    async def test_falls_back_to_id(self):
        el = _make_element(el_id="phone-number")
        page = _make_page_with_fields(url="https://x.com")

        result = await _get_field_label(page, el)

        assert result == "phone number"


# ===================================================================
# _get_profile_value
# ===================================================================

class TestGetProfileValue:

    def setup_method(self):
        self.profile = _FakeProfile()

    def test_simple_field(self):
        assert _get_profile_value(self.profile, "email") == "jane@example.com"

    def test_first_name_from_full(self):
        assert _get_profile_value(self.profile, "first_name") == "Jane"

    def test_last_name_from_full(self):
        assert _get_profile_value(self.profile, "last_name") == "Doe"

    def test_last_name_single_word(self):
        p = _FakeProfile(full_name="Madonna")
        assert _get_profile_value(p, "last_name") == ""

    def test_first_name_empty(self):
        p = _FakeProfile(full_name="")
        assert _get_profile_value(p, "first_name") == ""

    def test_experience_years_as_string(self):
        assert _get_profile_value(self.profile, "experience_years") == "5"

    def test_experience_years_zero(self):
        p = _FakeProfile(experience_years=0)
        assert _get_profile_value(p, "experience_years") == ""

    def test_education_dict_extracts_degree(self):
        assert _get_profile_value(self.profile, "education") == "B.S. Computer Science"

    def test_education_empty_list(self):
        p = _FakeProfile(education=[])
        assert _get_profile_value(p, "education") == ""

    def test_missing_attribute(self):
        assert _get_profile_value(self.profile, "nonexistent_key") == ""

    def test_linkedin_url(self):
        assert _get_profile_value(self.profile, "linkedin_url") == "https://linkedin.com/in/janedoe"

    def test_last_name_multi_word(self):
        p = _FakeProfile(full_name="Mary Jane Watson")
        assert _get_profile_value(p, "last_name") == "Jane Watson"


# ===================================================================
# _detect_form_fields
# ===================================================================

class TestDetectFormFields:

    @pytest.mark.asyncio
    async def test_detects_text_inputs(self):
        inp = _make_element(placeholder="Email", el_type="text")
        page = _make_page_with_fields(inputs=[inp])

        fields = await _detect_form_fields(page)

        assert len(fields) == 1
        assert fields[0].tag == "input"
        assert fields[0].input_type == "text"
        assert fields[0].profile_key == "email"

    @pytest.mark.asyncio
    async def test_detects_selects(self):
        sel = _make_element(placeholder="Education")
        page = _make_page_with_fields(selects=[sel])

        fields = await _detect_form_fields(page)

        assert len(fields) == 1
        assert fields[0].tag == "select"
        assert fields[0].input_type == "select"

    @pytest.mark.asyncio
    async def test_detects_textareas(self):
        ta = _make_element(placeholder="Summary")
        page = _make_page_with_fields(textareas=[ta])

        fields = await _detect_form_fields(page)

        assert len(fields) == 1
        assert fields[0].tag == "textarea"
        assert fields[0].input_type == "textarea"

    @pytest.mark.asyncio
    async def test_detects_file_inputs(self):
        inp = _make_element(placeholder="Upload Resume", el_type="file")
        page = _make_page_with_fields(inputs=[inp])

        fields = await _detect_form_fields(page)

        assert len(fields) == 1
        assert fields[0].input_type == "file"

    @pytest.mark.asyncio
    async def test_detects_multiple_field_types(self):
        inp = _make_element(placeholder="Email", el_type="text")
        sel = _make_element(placeholder="Education")
        ta = _make_element(placeholder="Summary")
        page = _make_page_with_fields(inputs=[inp], selects=[sel], textareas=[ta])

        fields = await _detect_form_fields(page)

        assert len(fields) == 3

    @pytest.mark.asyncio
    async def test_empty_page_returns_empty(self):
        page = _make_page_with_fields()

        fields = await _detect_form_fields(page)

        assert fields == []

    @pytest.mark.asyncio
    async def test_input_type_defaults_to_text(self):
        inp = _make_element(placeholder="Name")
        # Override get_attribute to return None for type
        original = inp.get_attribute
        async def _get(a):
            if a == "type":
                return None
            return await original(a)
        inp.get_attribute = _get

        page = _make_page_with_fields(inputs=[inp])

        fields = await _detect_form_fields(page)

        assert fields[0].input_type == "text"


# ===================================================================
# _fill_with_ats_selectors
# ===================================================================

class TestFillWithAtsSelectors:

    @pytest.mark.asyncio
    async def test_fills_lever_text_fields(self):
        profile = _FakeProfile()
        page = AsyncMock()

        loc_mock = AsyncMock()
        loc_mock.count = AsyncMock(return_value=1)
        loc_mock.first = AsyncMock()
        page.locator = MagicMock(return_value=loc_mock)

        count = await _fill_with_ats_selectors(page, "lever", profile, "", "")

        assert count > 0
        assert loc_mock.first.fill.call_count > 0

    @pytest.mark.asyncio
    async def test_fills_resume_upload(self):
        profile = _FakeProfile()
        page = AsyncMock()

        loc_mock = AsyncMock()
        loc_mock.count = AsyncMock(return_value=1)
        loc_mock.first = AsyncMock()
        page.locator = MagicMock(return_value=loc_mock)

        count = await _fill_with_ats_selectors(page, "greenhouse", profile, "/tmp/resume.pdf", "")

        # Should have uploaded resume
        loc_mock.first.set_input_files.assert_called()

    @pytest.mark.asyncio
    async def test_fills_cover_letter_upload(self):
        profile = _FakeProfile()
        page = AsyncMock()

        loc_mock = AsyncMock()
        loc_mock.count = AsyncMock(return_value=1)
        loc_mock.first = AsyncMock()
        page.locator = MagicMock(return_value=loc_mock)

        await _fill_with_ats_selectors(page, "greenhouse", profile, "", "/tmp/cover.pdf")

        loc_mock.first.set_input_files.assert_called()

    @pytest.mark.asyncio
    async def test_skips_missing_selectors(self):
        profile = _FakeProfile()
        page = AsyncMock()

        loc_mock = AsyncMock()
        loc_mock.count = AsyncMock(return_value=0)
        page.locator = MagicMock(return_value=loc_mock)

        count = await _fill_with_ats_selectors(page, "lever", profile, "", "")

        assert count == 0
        loc_mock.first.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_platform_returns_zero(self):
        profile = _FakeProfile()
        page = AsyncMock()

        count = await _fill_with_ats_selectors(page, "unknown", profile, "", "")

        assert count == 0

    @pytest.mark.asyncio
    async def test_handles_fill_exception(self):
        profile = _FakeProfile()
        page = AsyncMock()

        loc_mock = AsyncMock()
        loc_mock.count = AsyncMock(return_value=1)
        loc_mock.first = AsyncMock()
        loc_mock.first.fill = AsyncMock(side_effect=Exception("element detached"))
        page.locator = MagicMock(return_value=loc_mock)

        # Should not raise, just return 0 for failed fields
        count = await _fill_with_ats_selectors(page, "lever", profile, "", "")

        # Some may succeed (resume/cover_letter skipped), some may fail
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_skips_resume_key_when_no_path(self):
        profile = _FakeProfile()
        page = AsyncMock()

        loc_mock = AsyncMock()
        loc_mock.count = AsyncMock(return_value=1)
        loc_mock.first = AsyncMock()
        page.locator = MagicMock(return_value=loc_mock)

        await _fill_with_ats_selectors(page, "greenhouse", profile, "", "")

        # resume and cover_letter keys should be skipped, not uploaded
        loc_mock.first.set_input_files.assert_not_called()


# ===================================================================
# _fill_select
# ===================================================================

class TestFillSelect:

    @pytest.mark.asyncio
    async def test_selects_by_value_first(self):
        loc = AsyncMock()
        loc.select_option = AsyncMock()

        await _fill_select(loc, "US")

        loc.select_option.assert_awaited_once_with(value="US")

    @pytest.mark.asyncio
    async def test_falls_back_to_label(self):
        loc = AsyncMock()
        loc.select_option = AsyncMock(
            side_effect=[Exception("no value match"), None]
        )

        await _fill_select(loc, "United States")

        assert loc.select_option.call_count == 2
        loc.select_option.assert_awaited_with(label="United States")

    @pytest.mark.asyncio
    async def test_falls_back_to_fuzzy_match(self):
        loc = AsyncMock()
        loc.select_option = AsyncMock(
            side_effect=[Exception("no value"), Exception("no label"), None]
        )

        opt = AsyncMock()
        opt.inner_text = AsyncMock(return_value="United States of America")
        options_loc = AsyncMock()
        options_loc.all = AsyncMock(return_value=[opt])
        loc.locator = MagicMock(return_value=options_loc)

        await _fill_select(loc, "United States")

        assert loc.select_option.call_count == 3
        loc.select_option.assert_awaited_with(label="United States of America")

    @pytest.mark.asyncio
    async def test_raises_when_no_option_matches(self):
        loc = AsyncMock()
        loc.select_option = AsyncMock(side_effect=Exception("no match"))

        opt = AsyncMock()
        opt.inner_text = AsyncMock(return_value="totally unrelated")
        options_loc = AsyncMock()
        options_loc.all = AsyncMock(return_value=[opt])
        loc.locator = MagicMock(return_value=options_loc)

        with pytest.raises(ValueError, match="No matching option"):
            await _fill_select(loc, "Python")

    @pytest.mark.asyncio
    async def test_handles_empty_options_list(self):
        loc = AsyncMock()
        loc.select_option = AsyncMock(side_effect=Exception("fail"))

        options_loc = AsyncMock()
        options_loc.all = AsyncMock(return_value=[])
        loc.locator = MagicMock(return_value=options_loc)

        with pytest.raises(ValueError, match="No matching option"):
            await _fill_select(loc, "anything")


# ===================================================================
# FillResult dataclass
# ===================================================================

class TestFillResult:

    def test_defaults(self):
        r = FillResult(success=False)
        assert r.success is False
        assert r.fields_filled == 0
        assert r.fields_total == 0
        assert r.screenshot_path == ""
        assert r.errors == []

    def test_errors_are_independent(self):
        r1 = FillResult(success=True)
        r2 = FillResult(success=True)
        r1.errors.append("oops")
        assert r2.errors == []


# ===================================================================
# fill_application_form — integration
# ===================================================================

class TestFillApplicationForm:

    def _make_detected_field(
        self,
        *,
        label: str,
        input_type: str = "text",
        tag: str = "input",
        profile_key: str = "",
        confidence: float = 0.8,
    ) -> DetectedField:
        loc = AsyncMock()
        loc.is_checked = AsyncMock(return_value=False)
        return DetectedField(
            locator=loc,
            tag=tag,
            input_type=input_type,
            label_text=label,
            profile_key=profile_key,
            confidence=confidence,
        )

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_fills_text_field_from_profile(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Email", profile_key="email")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"
        profile = _FakeProfile()

        result = await fill_application_form(page, profile)

        df.locator.fill.assert_awaited_once_with("jane@example.com")
        assert result.fields_filled == 1
        assert result.success is True

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_uploads_resume_to_file_input(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Upload Resume", input_type="file")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"
        profile = _FakeProfile()

        result = await fill_application_form(page, profile, resume_path="/tmp/resume.pdf")

        df.locator.set_input_files.assert_awaited_once_with("/tmp/resume.pdf")
        assert result.fields_filled == 1

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_uploads_cover_letter_to_file_input(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Upload Cover Letter", input_type="file")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"
        profile = _FakeProfile()

        result = await fill_application_form(
            page, profile, cover_letter_path="/tmp/cover.pdf"
        )

        df.locator.set_input_files.assert_awaited_once_with("/tmp/cover.pdf")
        assert result.fields_filled == 1

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_generic_file_input_defaults_to_resume(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Attach document", input_type="file")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(
            page, _FakeProfile(), resume_path="/tmp/resume.pdf"
        )

        df.locator.set_input_files.assert_awaited_once_with("/tmp/resume.pdf")
        assert result.fields_filled == 1

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_checks_agreement_checkbox(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(
            label="I agree to the terms", input_type="checkbox"
        )
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df.locator.check.assert_awaited_once()
        assert result.fields_filled == 1

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_skips_already_checked_checkbox(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(
            label="I agree to the terms", input_type="checkbox"
        )
        df.locator.is_checked = AsyncMock(return_value=True)
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df.locator.check.assert_not_awaited()
        assert result.fields_filled == 0

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_skips_non_agreement_checkbox(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(
            label="Subscribe to newsletter", input_type="checkbox"
        )
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df.locator.check.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_skips_radio_buttons(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Gender", input_type="radio")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df.locator.fill.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler._fill_select")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_fills_select_via_fill_select(self, mock_mkdir, mock_fill_sel, mock_detect):
        df = self._make_detected_field(
            label="Education", tag="select", input_type="select",
            profile_key="education",
        )
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        mock_fill_sel.assert_awaited_once_with(df.locator, "B.S. Computer Science")
        assert result.fields_filled == 1

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_does_not_fill_same_key_twice(self, mock_mkdir, mock_detect):
        df1 = self._make_detected_field(label="Email", profile_key="email")
        df2 = self._make_detected_field(label="Email Address", profile_key="email")
        mock_detect.return_value = [df1, df2]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        assert result.fields_filled == 1
        df1.locator.fill.assert_awaited_once()
        df2.locator.fill.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_records_errors_on_exception(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Email", profile_key="email")
        df.locator.fill = AsyncMock(side_effect=Exception("element gone"))
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        assert len(result.errors) == 1
        assert "element gone" in result.errors[0]

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_takes_screenshot(self, mock_mkdir, mock_detect):
        mock_detect.return_value = []
        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        page.screenshot.assert_awaited_once()
        assert "pre_submit_" in result.screenshot_path
        assert result.screenshot_path.endswith(".png")

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_screenshot_failure_is_not_fatal(self, mock_mkdir, mock_detect):
        mock_detect.return_value = []
        page = AsyncMock()
        page.url = "https://example.com/apply"
        page.screenshot = AsyncMock(side_effect=Exception("screenshot failed"))

        result = await fill_application_form(page, _FakeProfile())

        assert result.screenshot_path == ""

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_returns_fields_total_count(self, mock_mkdir, mock_detect):
        df1 = self._make_detected_field(label="Email", profile_key="email")
        df2 = self._make_detected_field(label="Phone", profile_key="phone")
        df3 = self._make_detected_field(label="Misc", profile_key="")
        mock_detect.return_value = [df1, df2, df3]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        assert result.fields_total == 3
        assert result.fields_filled == 2  # email + phone, not misc

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_success_false_when_nothing_filled(self, mock_mkdir, mock_detect):
        mock_detect.return_value = []
        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        assert result.success is False

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler._fill_with_ats_selectors")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_greenhouse_url_triggers_ats_fill(self, mock_mkdir, mock_ats, mock_detect):
        mock_detect.return_value = []
        mock_ats.return_value = 3

        page = AsyncMock()
        page.url = "https://boards.greenhouse.io/company/jobs/123"

        result = await fill_application_form(page, _FakeProfile())

        mock_ats.assert_awaited_once()
        assert result.fields_filled == 3
        assert result.success is True

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler._fill_with_ats_selectors")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_non_ats_url_skips_ats_fill(self, mock_mkdir, mock_ats, mock_detect):
        mock_detect.return_value = []
        page = AsyncMock()
        page.url = "https://example.com/apply"

        await fill_application_form(page, _FakeProfile())

        mock_ats.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_fills_first_name_and_last_name(self, mock_mkdir, mock_detect):
        df1 = self._make_detected_field(label="First Name", profile_key="first_name")
        df2 = self._make_detected_field(label="Last Name", profile_key="last_name")
        mock_detect.return_value = [df1, df2]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df1.locator.fill.assert_awaited_once_with("Jane")
        df2.locator.fill.assert_awaited_once_with("Doe")
        assert result.fields_filled == 2

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_skips_field_with_no_profile_key(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Unknown field", profile_key="")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df.locator.fill.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.automation.form_filler._detect_form_fields")
    @patch("src.automation.form_filler.Path.mkdir")
    async def test_file_input_skipped_when_no_paths(self, mock_mkdir, mock_detect):
        df = self._make_detected_field(label="Attach document", input_type="file")
        mock_detect.return_value = [df]

        page = AsyncMock()
        page.url = "https://example.com/apply"

        result = await fill_application_form(page, _FakeProfile())

        df.locator.set_input_files.assert_not_awaited()
        assert result.fields_filled == 0
