"""Tests for the FormFiller browser automation."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.automation.form_filler import FormFiller, FormField


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
