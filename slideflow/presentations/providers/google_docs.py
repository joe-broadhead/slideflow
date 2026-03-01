"""Google Docs provider for marker-anchored newsletter workflows.

The provider maps `slide.id` values to explicit marker tokens in the target
document (for example `{{SECTION:intro}}`) and scopes chart/text operations to
those marker-defined sections.
"""

from __future__ import annotations

import io
import os
import re
import threading
import time
from bisect import bisect_left
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from pydantic import Field, field_validator

from slideflow.citations import CitationEntry, format_citation_line
from slideflow.constants import Environment, GoogleSlides, Timing
from slideflow.presentations.providers.base import (
    PresentationProvider,
    PresentationProviderConfig,
)
from slideflow.presentations.providers.google_drive_ownership import (
    append_transfer_owner_preflight_check,
    is_shared_drive_file,
    normalize_transfer_owner_email,
    transfer_drive_file_ownership,
)
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import AuthenticationError, RenderingError
from slideflow.utilities.logging import get_logger
from slideflow.utilities.rate_limiter import RateLimiter

logger = get_logger(__name__)
_docs_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def _get_rate_limiter(rps: float, force_update: bool = False) -> RateLimiter:
    """Get or create the global Google Docs API rate limiter."""
    global _docs_rate_limiter
    with _rate_limiter_lock:
        if _docs_rate_limiter is None:
            _docs_rate_limiter = RateLimiter(rps)
        elif force_update:
            _docs_rate_limiter.set_rate(rps)
        return _docs_rate_limiter


class GoogleDocsProviderConfig(PresentationProviderConfig):
    """Configuration for the Google Docs provider."""

    provider_type: Literal["google_docs"] = "google_docs"
    credentials: Optional[str] = Field(
        None,
        description="Google credentials as a file path or JSON string.",
    )
    template_id: Optional[str] = Field(
        None,
        description="Google Docs template ID to copy from when creating documents.",
    )
    document_folder_id: Optional[str] = Field(
        None,
        description="Google Drive folder ID for created documents.",
    )
    drive_folder_id: Optional[str] = Field(
        None,
        description="Google Drive folder ID for uploaded chart images.",
    )
    section_marker_prefix: str = Field(
        "{{SECTION:",
        description="Section marker prefix for marker-based section resolution.",
    )
    section_marker_suffix: str = Field(
        "}}",
        description="Section marker suffix for marker-based section resolution.",
    )
    remove_section_markers: bool = Field(
        False,
        description="Whether to remove section markers after rendering.",
    )
    default_chart_width_pt: float = Field(
        GoogleSlides.DEFAULT_CHART_WIDTH,
        gt=0,
        description="Default inline chart width for docs insertion.",
    )
    share_with: List[str] = Field(
        default_factory=list,
        description="Email addresses to share the generated document with.",
    )
    share_role: str = Field(
        GoogleSlides.PERMISSION_WRITER,
        description="Share role: reader, writer, or commenter.",
    )
    requests_per_second: float = Field(
        1.0,
        gt=0,
        description="Maximum Google API requests per second.",
    )
    strict_cleanup: bool = Field(
        False,
        description="If true, fail rendering when chart image cleanup fails.",
    )
    transfer_ownership_to: Optional[str] = Field(
        None,
        description="Optional email address that should become the owner after rendering completes.",
    )
    transfer_ownership_strict: bool = Field(
        False,
        description="If true, fail rendering when ownership transfer fails.",
    )

    @field_validator("transfer_ownership_to")
    @classmethod
    def _validate_transfer_ownership_to(cls, value: Optional[str]) -> Optional[str]:
        return normalize_transfer_owner_email(value)


class GoogleDocsProvider(PresentationProvider):
    """Google Docs provider implementation.

    This provider currently supports baseline operations and intentionally keeps
    slide-scoped/marker-scoped rendering behavior for a follow-up iteration.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]

    @dataclass(frozen=True)
    class _SectionAnchor:
        marker_id: str
        marker_start: int
        marker_end: int
        section_start: int
        section_end: int

    @dataclass
    class _SectionTextSegment:
        text: str
        boundaries: List[int]

    def __init__(self, config: GoogleDocsProviderConfig):
        super().__init__(config)
        self.config: GoogleDocsProviderConfig = config
        self._section_insert_indices: Dict[Tuple[str, str], int] = {}

        loaded_credentials = handle_google_credentials(
            config.credentials,
            env_var_names=[
                Environment.GOOGLE_DOCS_CREDENTIALS,
                Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
            ],
        )

        try:
            credentials = Credentials.from_service_account_info(
                loaded_credentials, scopes=self.SCOPES
            )
        except Exception as error_msg:  # pragma: no cover - exercised via tests
            raise AuthenticationError(f"Credentials authentication failed: {error_msg}")

        self.docs_service = build("docs", "v1", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.rate_limiter = _get_rate_limiter(self.config.requests_per_second)

    def _execute_request(self, request):
        """Execute Google API request with shared rate limiting."""
        self.rate_limiter.wait()
        return request.execute(num_retries=3)

    def run_preflight_checks(self) -> List[Tuple[str, bool, str]]:
        has_credentials = bool(self.config.credentials) or bool(
            os.getenv(Environment.GOOGLE_DOCS_CREDENTIALS)
            or os.getenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS)
        )
        checks: List[Tuple[str, bool, str]] = [
            (
                "google_docs_credentials_present",
                has_credentials,
                (
                    "Credentials found in config or supported environment variables"
                    if has_credentials
                    else "Missing credentials in config and environment"
                ),
            ),
            (
                "docs_service_initialized",
                self.docs_service is not None,
                (
                    "Google Docs API client initialized"
                    if self.docs_service is not None
                    else "Google Docs API client is not initialized"
                ),
            ),
            (
                "drive_service_initialized",
                self.drive_service is not None,
                (
                    "Google Drive API client initialized"
                    if self.drive_service is not None
                    else "Google Drive API client is not initialized"
                ),
            ),
            (
                "rate_limiter_initialized",
                self.rate_limiter is not None,
                (
                    f"Rate limiter configured at {self.config.requests_per_second} rps"
                    if self.rate_limiter is not None
                    else "Rate limiter is not initialized"
                ),
            ),
        ]

        append_transfer_owner_preflight_check(
            checks,
            getattr(self.config, "transfer_ownership_to", None),
        )
        return checks

    def create_presentation(self, name: str, template_id: Optional[str] = None) -> str:
        template_to_use = template_id or self.config.template_id
        if template_to_use:
            return self._copy_template(template_to_use, name)
        return self._create_document(name)

    def upload_chart_image(
        self, presentation_id: str, image_data: bytes, filename: str
    ) -> Tuple[str, str]:
        del presentation_id
        return self._upload_image_to_drive(image_data, filename)

    def insert_chart_to_slide(
        self,
        presentation_id: str,
        slide_id: str,
        image_url: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        """Insert chart inline in document.

        `slide_id` is treated as a section marker ID and must match a marker
        token in the document template (for example: ``{{SECTION:intro}}``).

        Positional arguments ``x`` and ``y`` are accepted for interface
        compatibility and ignored because Google Docs only supports inline
        image insertion in this provider.
        """
        if x != 0 or y != 0:
            logger.warning(
                "google_docs provider ignores chart positioning values (x=%s, y=%s) "
                "and inserts charts inline at section '%s'.",
                x,
                y,
                slide_id,
            )
        del x, y

        anchor, _ = self._resolve_section_anchor(
            presentation_id,
            slide_id,
        )
        section_key = (presentation_id, slide_id)
        insert_index = self._section_insert_indices.get(
            section_key, anchor.section_start
        )
        if insert_index < anchor.section_start:
            insert_index = anchor.section_start

        requests = [
            {
                "insertInlineImage": {
                    "uri": image_url,
                    "location": {"index": insert_index},
                    "objectSize": {
                        "width": {"magnitude": width, "unit": "PT"},
                        "height": {"magnitude": height, "unit": "PT"},
                    },
                }
            }
        ]
        self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=presentation_id, body={"requests": requests}
            )
        )
        # Docs inserts inline objects as a single position in the text stream.
        self._section_insert_indices[section_key] = insert_index + 1

    def finalize_presentation(self, presentation_id: str) -> None:
        if not self.config.remove_section_markers:
            return
        removed = self._remove_section_markers(presentation_id)
        if removed > 0:
            logger.info(
                "Removed %s section marker(s) from rendered document %s",
                removed,
                presentation_id,
            )

    def _get_document_content(self, document_id: str) -> List[Dict[str, Any]]:
        document = self._execute_request(
            self.docs_service.documents().get(documentId=document_id)
        )
        if not isinstance(document, dict):
            return []
        body = document.get("body", {})
        if not isinstance(body, dict):
            return []
        content = body.get("content", [])
        if not isinstance(content, list):
            return []
        return [item for item in content if isinstance(item, dict)]

    def _iter_text_segments(
        self, elements: Iterable[Dict[str, Any]], include_toc: bool = False
    ) -> Iterable[_SectionTextSegment]:
        for element in elements:
            paragraph = element.get("paragraph")
            if isinstance(paragraph, dict):
                para_elements = paragraph.get("elements", [])
                if isinstance(para_elements, list):
                    current_text: Optional[str] = None
                    current_boundaries: Optional[List[int]] = None
                    for para_element in para_elements:
                        if not isinstance(para_element, dict):
                            continue
                        text_run = para_element.get("textRun")
                        if not isinstance(text_run, dict):
                            continue
                        text_content = text_run.get("content")
                        start_index = para_element.get("startIndex")
                        end_index = para_element.get("endIndex")
                        if (
                            isinstance(text_content, str)
                            and isinstance(start_index, int)
                            and isinstance(end_index, int)
                            and end_index > start_index
                        ):
                            cumulative_units = self._utf16_cumulative_units(
                                text_content
                            )
                            run_boundaries = [
                                start_index + unit_offset
                                for unit_offset in cumulative_units
                            ]
                            if current_text is None or current_boundaries is None:
                                current_text = text_content
                                current_boundaries = run_boundaries
                            elif current_boundaries[-1] == run_boundaries[0]:
                                current_text += text_content
                                current_boundaries.extend(run_boundaries[1:])
                            else:
                                yield self._SectionTextSegment(
                                    text=current_text,
                                    boundaries=current_boundaries,
                                )
                                current_text = text_content
                                current_boundaries = run_boundaries
                    if current_text is not None and current_boundaries is not None:
                        yield self._SectionTextSegment(
                            text=current_text,
                            boundaries=current_boundaries,
                        )

            table = element.get("table")
            if isinstance(table, dict):
                rows = table.get("tableRows", [])
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        cells = row.get("tableCells", [])
                        if not isinstance(cells, list):
                            continue
                        for cell in cells:
                            if not isinstance(cell, dict):
                                continue
                            cell_content = cell.get("content", [])
                            if isinstance(cell_content, list):
                                yield from self._iter_text_segments(
                                    cell_content,
                                    include_toc=include_toc,
                                )

            toc = element.get("tableOfContents") if include_toc else None
            if isinstance(toc, dict):
                toc_content = toc.get("content", [])
                if isinstance(toc_content, list):
                    yield from self._iter_text_segments(
                        toc_content,
                        include_toc=True,
                    )

    def _marker_regex(self) -> re.Pattern[str]:
        return re.compile(
            f"{re.escape(self.config.section_marker_prefix)}"
            r"(?P<id>.+?)"
            f"{re.escape(self.config.section_marker_suffix)}"
        )

    def _utf16_cumulative_units(self, text: str) -> List[int]:
        cumulative = [0]
        for char in text:
            cumulative.append(cumulative[-1] + len(char.encode("utf-16-le")) // 2)
        return cumulative

    def _utf16_offset_to_py_index(
        self, cumulative: List[int], utf16_offset: int
    ) -> int:
        index = bisect_left(cumulative, utf16_offset)
        if index < len(cumulative):
            if cumulative[index] == utf16_offset:
                return index
        return max(0, min(index, len(cumulative) - 1))

    def _get_document_end_index(self, content: List[Dict[str, Any]]) -> int:
        minimum_insert_index = 1
        for element in reversed(content):
            end_index = element.get("endIndex")
            if isinstance(end_index, int):
                return max(minimum_insert_index, end_index - 1)
        return minimum_insert_index

    def _resolve_section_anchor(
        self, document_id: str, section_id: str
    ) -> Tuple[_SectionAnchor, List[Dict[str, Any]]]:
        content = self._get_document_content(document_id)
        marker_pattern = self._marker_regex()
        markers: List[Tuple[str, int, int]] = []
        for segment in self._iter_text_segments(content):
            for marker_match in marker_pattern.finditer(segment.text):
                marker_id = marker_match.group("id").strip()
                marker_start = segment.boundaries[marker_match.start()]
                marker_end = segment.boundaries[marker_match.end()]
                if marker_end > marker_start:
                    markers.append((marker_id, marker_start, marker_end))

        if not markers:
            raise RenderingError(
                "No section markers found in document. "
                f"Expected markers like "
                f"'{self.config.section_marker_prefix}<id>{self.config.section_marker_suffix}'."
            )

        marker_counts: Dict[str, int] = {}
        for marker_id, _, _ in markers:
            marker_counts[marker_id] = marker_counts.get(marker_id, 0) + 1
        duplicates = sorted(
            marker_id for marker_id, count in marker_counts.items() if count > 1
        )
        if duplicates:
            raise RenderingError(
                f"Duplicate section markers found in document: {', '.join(duplicates)}"
            )

        ordered_markers = sorted(markers, key=lambda marker: marker[1])
        document_end_index = self._get_document_end_index(content)
        sections: Dict[str, GoogleDocsProvider._SectionAnchor] = {}
        for index, (marker_id, marker_start, marker_end) in enumerate(ordered_markers):
            next_marker_start = (
                ordered_markers[index + 1][1]
                if index + 1 < len(ordered_markers)
                else document_end_index
            )
            section_start = marker_end
            section_end = max(section_start, next_marker_start)
            sections[marker_id] = self._SectionAnchor(
                marker_id=marker_id,
                marker_start=marker_start,
                marker_end=marker_end,
                section_start=section_start,
                section_end=section_end,
            )

        anchor = sections.get(section_id)
        if anchor is None:
            available_markers = ", ".join(sorted(sections))
            expected_marker = (
                f"{self.config.section_marker_prefix}{section_id}"
                f"{self.config.section_marker_suffix}"
            )
            raise RenderingError(
                f"Missing section marker '{expected_marker}' in document. "
                f"Available marker ids: {available_markers}"
            )

        return anchor, content

    def _build_section_text_segments(
        self, content: List[Dict[str, Any]], section_start: int, section_end: int
    ) -> List[_SectionTextSegment]:
        segments: List[GoogleDocsProvider._SectionTextSegment] = []
        for base_segment in self._iter_text_segments(content):
            text_content = base_segment.text
            run_start = base_segment.boundaries[0]
            run_end = base_segment.boundaries[-1]
            overlap_start = max(section_start, run_start)
            overlap_end = min(section_end, run_end)
            if overlap_start >= overlap_end:
                continue

            cumulative_units = self._utf16_cumulative_units(text_content)
            relative_start_units = overlap_start - run_start
            relative_end_units = overlap_end - run_start
            py_start = self._utf16_offset_to_py_index(
                cumulative_units, relative_start_units
            )
            py_end = self._utf16_offset_to_py_index(
                cumulative_units, relative_end_units
            )
            overlap_text = text_content[py_start:py_end]
            if not overlap_text:
                continue

            piece_units = self._utf16_cumulative_units(overlap_text)
            piece_boundaries = [
                overlap_start + unit_offset for unit_offset in piece_units
            ]

            if segments and segments[-1].boundaries[-1] == piece_boundaries[0]:
                segments[-1].text += overlap_text
                segments[-1].boundaries.extend(piece_boundaries[1:])
            else:
                segments.append(
                    self._SectionTextSegment(
                        text=overlap_text,
                        boundaries=piece_boundaries,
                    )
                )

        return segments

    def _remove_section_markers(self, document_id: str) -> int:
        content = self._get_document_content(document_id)
        marker_pattern = self._marker_regex()
        marker_ranges: List[Tuple[int, int]] = []

        for segment in self._iter_text_segments(content):
            for marker_match in marker_pattern.finditer(segment.text):
                marker_start = segment.boundaries[marker_match.start()]
                marker_end = segment.boundaries[marker_match.end()]
                if marker_end > marker_start:
                    marker_ranges.append((marker_start, marker_end))

        if not marker_ranges:
            return 0

        requests = [
            {
                "deleteContentRange": {
                    "range": {"startIndex": start_index, "endIndex": end_index}
                }
            }
            for start_index, end_index in sorted(marker_ranges, reverse=True)
        ]
        self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            )
        )
        return len(marker_ranges)

    def replace_text_in_slide(
        self, presentation_id: str, slide_id: str, placeholder: str, replacement: str
    ) -> int:
        """Replace placeholder text within the target marker section only."""
        if not placeholder:
            return 0

        anchor, content = self._resolve_section_anchor(
            presentation_id,
            slide_id,
        )
        section_segments = self._build_section_text_segments(
            content,
            anchor.section_start,
            anchor.section_end,
        )
        if not section_segments:
            return 0

        placeholder_occurrences: List[Tuple[int, int]] = []
        placeholder_length = len(placeholder)
        for segment in section_segments:
            search_position = 0
            while True:
                found_at = segment.text.find(placeholder, search_position)
                if found_at < 0:
                    break
                found_end = found_at + placeholder_length
                abs_start = segment.boundaries[found_at]
                abs_end = segment.boundaries[found_end]
                placeholder_occurrences.append((abs_start, abs_end))
                search_position = found_end

        if not placeholder_occurrences:
            return 0

        requests: List[Dict[str, Any]] = []
        for start_index, end_index in reversed(placeholder_occurrences):
            requests.append(
                {
                    "deleteContentRange": {
                        "range": {"startIndex": start_index, "endIndex": end_index}
                    }
                }
            )
            requests.append(
                {
                    "insertText": {
                        "location": {"index": start_index},
                        "text": replacement,
                    }
                }
            )
        self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=presentation_id,
                body={"requests": requests},
            )
        )
        return len(placeholder_occurrences)

    def _render_document_end_citations(
        self, document_id: str, citations: List[Dict[str, Any]]
    ) -> None:
        if not citations:
            return

        content = self._get_document_content(document_id)
        end_index = 1
        for element in content:
            if not isinstance(element, dict):
                continue
            candidate = element.get("endIndex")
            if isinstance(candidate, int):
                end_index = max(end_index, candidate)
        insertion_index = max(end_index - 1, 1)

        lines = ["", "Sources"]
        for citation_payload in citations:
            try:
                entry = CitationEntry.model_validate(citation_payload)
            except Exception:
                continue
            lines.append(format_citation_line(entry))
        if len(lines) <= 2:
            return

        self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": insertion_index},
                                "text": "\n".join(lines) + "\n",
                            }
                        }
                    ]
                },
            )
        )

    def _render_section_footnote_citations(
        self,
        document_id: str,
        section_id: str,
        citations: List[Dict[str, Any]],
    ) -> None:
        if not citations:
            return
        try:
            anchor, _ = self._resolve_section_anchor(document_id, section_id)
        except RenderingError:
            logger.warning(
                "Skipping citation footnote for unknown section '%s'", section_id
            )
            return

        create_response = self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "createFootnote": {
                                "location": {"index": max(anchor.section_end - 1, 1)}
                            }
                        }
                    ]
                },
            )
        )
        replies = create_response.get("replies", [])
        if not replies:
            return
        footnote = replies[0].get("createFootnote", {})
        footnote_id = footnote.get("footnoteId")
        if not footnote_id:
            return

        lines = ["Sources"]
        for citation_payload in citations:
            try:
                entry = CitationEntry.model_validate(citation_payload)
            except Exception:
                continue
            lines.append(format_citation_line(entry))
        if len(lines) <= 1:
            return

        self._execute_request(
            self.docs_service.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "endOfSegmentLocation": {"segmentId": footnote_id},
                                "text": "\n".join(lines),
                            }
                        }
                    ]
                },
            )
        )

    def render_citations(
        self,
        presentation_id: str,
        citations_by_scope: Dict[str, List[Dict[str, Any]]],
        location: str,
    ) -> None:
        """Render citations into Docs output (footnotes or document-end block)."""
        if not citations_by_scope:
            return

        if location == "document_end":
            combined: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for citations in citations_by_scope.values():
                for citation in citations:
                    source_id = str(citation.get("source_id", ""))
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    combined.append(citation)
            self._render_document_end_citations(presentation_id, combined)
            return

        # per_slide/per_section both map to section markers for Google Docs
        for section_id, citations in citations_by_scope.items():
            self._render_section_footnote_citations(
                presentation_id,
                section_id,
                citations,
            )

    def share_presentation(
        self, presentation_id: str, emails: List[str], role: str = "writer"
    ) -> None:
        if not emails:
            return

        for email in emails:
            permission = {"type": "user", "role": role, "emailAddress": email}
            self._execute_request(
                self.drive_service.permissions().create(
                    fileId=presentation_id,
                    body=permission,
                    sendNotificationEmail=True,
                    supportsAllDrives=True,
                )
            )

    def _is_shared_drive_file(self, file_id: str) -> bool:
        """Return True when the file is backed by a Shared Drive."""
        return is_shared_drive_file(
            execute_request=self._execute_request,
            drive_service=self.drive_service,
            file_id=file_id,
        )

    def transfer_presentation_ownership(
        self, presentation_id: str, new_owner_email: str
    ) -> None:
        """Transfer ownership of a generated document to another user."""
        if self._is_shared_drive_file(presentation_id):
            raise ValueError(
                "Ownership transfer is not supported for files in Shared Drives"
            )

        transfer_drive_file_ownership(
            execute_request=self._execute_request,
            drive_service=self.drive_service,
            file_id=presentation_id,
            new_owner_email=new_owner_email,
        )
        logger.info(
            "Transferred document ownership to %s (document_id=%s)",
            new_owner_email,
            presentation_id,
        )

    def get_presentation_url(self, presentation_id: str) -> str:
        return f"https://docs.google.com/document/d/{presentation_id}"

    def delete_chart_image(self, file_id: str) -> None:
        try:
            self._execute_request(
                self.drive_service.files().update(
                    fileId=file_id, body={"trashed": True}, supportsAllDrives=True
                )
            )
            logger.info(f"Trashed chart image with file_id: {file_id}")
        except HttpError as error:
            status = getattr(getattr(error, "resp", None), "status", None)
            if status == 403:
                logger.warning(
                    "Could not trash chart image %s due to permission constraints.",
                    file_id,
                )
            else:
                logger.error("Error trashing file %s: %s", file_id, error)
            if self.config.strict_cleanup:
                raise

    def _create_document(self, title: str) -> str:
        created = self._execute_request(
            self.docs_service.documents().create(body={"title": title})
        )
        document_id = created.get("documentId")
        destination_folder_id = self.config.document_folder_id
        if destination_folder_id:
            self._move_file_to_folder(document_id, destination_folder_id)
        return document_id

    def _copy_template(self, template_id: str, title: str) -> str:
        body: Dict[str, Any] = {"name": title}
        if self.config.document_folder_id:
            body["parents"] = [self.config.document_folder_id]
        copied = self._execute_request(
            self.drive_service.files().copy(
                fileId=template_id, body=body, supportsAllDrives=True
            )
        )
        return copied.get("id")

    def _move_file_to_folder(self, file_id: str, folder_id: str) -> None:
        file_details = self._execute_request(
            self.drive_service.files().get(
                fileId=file_id, fields="parents", supportsAllDrives=True
            )
        )
        previous_parents = ",".join(file_details.get("parents", []))
        self._execute_request(
            self.drive_service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields="id, parents",
                supportsAllDrives=True,
            )
        )

    def _upload_image_to_drive(
        self, image_bytes: bytes, filename: str
    ) -> Tuple[str, str]:
        file_metadata: Dict[str, Any] = {"name": filename}
        if self.config.drive_folder_id:
            file_metadata["parents"] = [self.config.drive_folder_id]

        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype="image/png")
        uploaded_file = self._execute_request(
            self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
        )

        file_id = uploaded_file.get("id")
        self._execute_request(
            self.drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            )
        )
        if Timing.GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S > 0:
            time.sleep(Timing.GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S)
        public_url = f"https://drive.google.com/uc?id={file_id}"
        return public_url, file_id
