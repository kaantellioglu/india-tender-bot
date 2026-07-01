"""Content and access classification helpers for tender sources.

The bot must not assume that a URL ending in .pdf is a real PDF. Many tender
portals return HTML access/error pages behind PDF-looking links. This module
classifies the received content before a parser decides what to do next.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

PDF_MAGIC = b"%PDF"
HTML_MAGIC_RE = re.compile(br"<\s*(html|!doctype|head|body|script|form)\b", re.I)


@dataclass
class ContentClassification:
    url: str
    final_url: str = ""
    http_status: Optional[int] = None
    content_type: str = ""
    detected_type: str = "unknown"  # pdf/html/doc/xls/json/text/binary/unknown
    is_real_pdf: bool = False
    looks_like_login: bool = False
    looks_like_error: bool = False
    failure_type: Optional[str] = None
    signals: list[str] = field(default_factory=list)


def is_probably_pdf(data: bytes | None) -> bool:
    if not data:
        return False
    return data.lstrip().startswith(PDF_MAGIC)


def is_probably_html(data: bytes | None, content_type: str = "") -> bool:
    if not data:
        return False
    ctype = (content_type or "").lower()
    if "html" in ctype:
        return True
    return bool(HTML_MAGIC_RE.search(data[:2048]))


def extension_hint(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".doc", ".docx")):
        return "doc"
    if path.endswith((".xls", ".xlsx", ".csv")):
        return "xls"
    if path.endswith((".json",)):
        return "json"
    return "unknown"


def classify_bytes(
    url: str,
    data: bytes | None,
    content_type: str = "",
    http_status: Optional[int] = None,
    final_url: str = "",
    text_preview: str | None = None,
) -> ContentClassification:
    c = ContentClassification(
        url=url,
        final_url=final_url or url,
        http_status=http_status,
        content_type=content_type or "",
    )

    ext = extension_hint(final_url or url)
    ctype = (content_type or "").lower()

    if http_status and http_status >= 400:
        c.looks_like_error = True
        c.failure_type = f"http_{http_status}"
        c.signals.append(c.failure_type)

    if is_probably_pdf(data):
        c.detected_type = "pdf"
        c.is_real_pdf = True
        return c

    if is_probably_html(data, ctype):
        c.detected_type = "html"
        if ext == "pdf":
            c.failure_type = c.failure_type or "not_a_pdf_html_response"
            c.signals.append("pdf_url_returned_html")
    elif "json" in ctype:
        c.detected_type = "json"
    elif ext in {"doc", "xls"}:
        c.detected_type = ext
    elif "text" in ctype:
        c.detected_type = "text"
    elif ext == "pdf":
        c.detected_type = "binary"
        c.failure_type = c.failure_type or "not_a_valid_pdf_binary"
        c.signals.append("pdf_url_binary_without_magic")
    else:
        c.detected_type = ext if ext != "unknown" else "unknown"

    preview = (text_preview or "")
    low = preview.lower()
    if any(x in low for x in ["login", "sign in", "user name", "username", "password", "captcha", "vendor login", "supplier login"]):
        c.looks_like_login = True
        c.failure_type = c.failure_type or "credentials_required"
        c.signals.append("access_signal")
    if any(x in low for x in ["404", "not found", "access denied", "forbidden", "unauthorized", "error occurred"]):
        c.looks_like_error = True
        c.signals.append("error_page_signal")

    return c


def classify_exception(exc: Exception) -> tuple[str, list[str]]:
    msg = str(exc).lower()
    if "certificate" in msg or "ssl" in msg:
        return "ssl_error", ["ssl"]
    if "name or service not known" in msg or "failed to resolve" in msg:
        return "dns_error", ["dns"]
    if "timed out" in msg or "timeout" in msg:
        return "timeout", ["timeout"]
    if "too many redirects" in msg or "exceeded 30 redirects" in msg:
        return "redirect_loop", ["redirect"]
    if "connection refused" in msg:
        return "connection_refused", ["connection_refused"]
    return "request_error", ["request_error"]
