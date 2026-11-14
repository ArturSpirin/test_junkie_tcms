"""Rich text: one structured JSON doc per field, read and written as Markdown through the API."""

from .markdown import doc_to_md, md_to_doc
from .schema import RichTextError, doc_to_text, empty_doc, validate

__all__ = ["RichTextError", "doc_to_md", "doc_to_text", "empty_doc", "md_to_doc", "validate"]
