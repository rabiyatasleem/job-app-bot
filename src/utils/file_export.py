"""Export tailored resumes and cover letters to PDF and DOCX."""

from pathlib import Path

from docx import Document


def save_as_docx(content: str, output_path: str) -> Path:
    """Save text content as a .docx file.

    Args:
        content: Plain text or markdown content.
        output_path: Destination file path.

    Returns:
        Path to the created file.
    """
    doc = Document()
    for paragraph in content.split("\n\n"):
        doc.add_paragraph(paragraph.strip())
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def save_as_text(content: str, output_path: str) -> Path:
    """Save content as a plain .txt file.

    Args:
        content: Text content to save.
        output_path: Destination file path.

    Returns:
        Path to the created file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
