"""Citation models and helpers for source provenance output.

This module centralizes citation entry shape, URL normalization/building, and
registry/dedup behavior used during rendering and build JSON output.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field


def fingerprint_text(value: str, length: int = 12) -> str:
    """Return a stable SHA-256 fingerprint prefix for a text value."""
    normalized = value.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:length]


def sanitize_repo_url(url: Optional[str]) -> Optional[str]:
    """Remove embedded basic-auth credentials from repository URLs."""
    if not url:
        return None
    return re.sub(r"(https?://)([^/@]+)@", r"\1", url)


def canonical_repo_web_url(repo_url: Optional[str]) -> Optional[str]:
    """Normalize git remotes to a browser-friendly repository URL."""
    if not repo_url:
        return None

    value = sanitize_repo_url(repo_url.strip())
    if not value:
        return None

    ssh_match = re.match(r"^git@([^:]+):(.+)$", value)
    if ssh_match:
        host = ssh_match.group(1).strip()
        path = ssh_match.group(2).strip()
        path = path[:-4] if path.endswith(".git") else path
        return f"https://{host}/{path}"

    if value.startswith("ssh://"):
        parsed = urlparse(value)
        host = parsed.hostname
        path = parsed.path.lstrip("/")
        if not host or not path:
            return None
        path = path[:-4] if path.endswith(".git") else path
        return f"https://{host}/{path}"

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        host = parsed.hostname
        path = parsed.path.lstrip("/")
        if not host or not path:
            return None
        path = path[:-4] if path.endswith(".git") else path
        return f"https://{host}/{path}"

    return None


def build_repo_file_url(
    repo_web_url: Optional[str], ref: Optional[str], file_path: Optional[str]
) -> Optional[str]:
    """Build a file URL for common git hosts using repository metadata."""
    if not repo_web_url or not ref or not file_path:
        return None
    clean_path = file_path.lstrip("/")
    if not clean_path:
        return None

    parsed = urlparse(repo_web_url)
    host = (parsed.hostname or "").lower()
    base = repo_web_url.rstrip("/")
    encoded_ref = ref.strip()

    if "github.com" in host:
        return f"{base}/blob/{encoded_ref}/{clean_path}"
    if "gitlab" in host:
        return f"{base}/-/blob/{encoded_ref}/{clean_path}"
    if "bitbucket" in host:
        return f"{base}/src/{encoded_ref}/{clean_path}"
    if "dev.azure.com" in host or host.endswith("visualstudio.com"):
        return f"{base}?path=/{clean_path}" f"&version=GB{encoded_ref}&_a=contents"

    return None


class CitationEntry(BaseModel):
    """Normalized citation entry for rendered artifacts and JSON output."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., description="Stable citation identifier")
    provider: str = Field(..., description="Source provider type")
    display_name: str = Field(..., description="Human-readable source label")
    repo_url: Optional[str] = Field(
        default=None, description="Repository root URL when available"
    )
    file_url: Optional[str] = Field(
        default=None, description="Direct source file URL when available"
    )
    model_unique_id: Optional[str] = Field(
        default=None, description="dbt unique_id when available"
    )
    model_path: Optional[str] = Field(
        default=None, description="dbt source path when available"
    )
    execution_ref: Optional[str] = Field(
        default=None, description="Execution reference URL/ID when available"
    )
    query_fingerprint: Optional[str] = Field(
        default=None, description="Hash for query-level traceability"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional provider-specific metadata"
    )


class CitationSummary(BaseModel):
    """Build-result citation summary payload."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    total_sources: int
    emitted_sources: int
    truncated: bool
    citations: List[CitationEntry]
    citations_by_scope: Dict[str, List[str]]


class CitationRegistry:
    """Deduplicated citation registry with per-scope usage tracking."""

    def __init__(self, max_items: int = 25, dedupe: bool = True) -> None:
        self.max_items = max(max_items, 1)
        self.dedupe = dedupe
        self._entries: Dict[str, CitationEntry] = {}
        self._order: List[str] = []
        self._scope_usage: Dict[str, List[str]] = defaultdict(list)
        self._truncated = False

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def size(self) -> int:
        return len(self._order)

    def add(
        self, entry: CitationEntry, scope_id: Optional[str] = None
    ) -> Optional[str]:
        """Register a citation entry and optional scope usage link."""
        source_id = entry.source_id
        if not self.dedupe:
            source_id = f"{source_id}#{len(self._order) + 1}"
            entry = entry.model_copy(update={"source_id": source_id})
        if source_id not in self._entries:
            if len(self._entries) >= self.max_items:
                self._truncated = True
                return None
            self._entries[source_id] = entry
            self._order.append(source_id)

        if scope_id:
            existing = self._scope_usage[scope_id]
            if source_id not in existing:
                existing.append(source_id)
        return source_id

    def entries(self) -> List[CitationEntry]:
        """Return citation entries in deterministic insertion order."""
        return [self._entries[source_id] for source_id in self._order]

    def entries_for_scope(self, scope_id: str) -> List[CitationEntry]:
        """Return citation entries linked to a scope key."""
        return [
            self._entries[source_id]
            for source_id in self._scope_usage.get(scope_id, [])
            if source_id in self._entries
        ]

    def summary(self, enabled: bool, total_sources: int) -> CitationSummary:
        """Return normalized citation summary for output payloads."""
        return CitationSummary(
            enabled=enabled,
            total_sources=total_sources,
            emitted_sources=len(self._order),
            truncated=self._truncated,
            citations=self.entries(),
            citations_by_scope={
                scope: list(source_ids)
                for scope, source_ids in sorted(self._scope_usage.items())
            },
        )


def format_citation_line(entry: CitationEntry) -> str:
    """Render a compact human-readable citation line."""
    detail = (
        entry.file_url
        or entry.execution_ref
        or entry.repo_url
        or entry.model_unique_id
        or entry.source_id
    )
    return f"- {entry.display_name}: {detail}"
