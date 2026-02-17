"""Browser automation package."""

from .form_filler import (
    FormFiller,
    FormField,
    FillResult,
    DetectedField,
    fill_application_form,
)
from .application_submitter import ApplicationSubmitter

__all__ = [
    "FormFiller",
    "FormField",
    "FillResult",
    "DetectedField",
    "fill_application_form",
    "ApplicationSubmitter",
]
