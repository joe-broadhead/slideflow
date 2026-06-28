"""Reject tracked credentials that generic high-entropy scanners may miss."""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SECRET_FILENAME_PATTERNS = (
    ".env",
    ".env.*",
    "sa.json",
    "*credential*.json",
    "*credentials*.json",
    "client_secret*.json",
    "*client-secret*.json",
    "*refresh-token*.json",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.der",
)

TOKEN_PATTERNS = (
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("Google OAuth token", re.compile(r"\bya29\.[A-Za-z0-9._-]{20,}\b")),
    ("Google OAuth refresh token", re.compile(r"\b1//[A-Za-z0-9._-]{20,}\b")),
    (
        "Google OAuth client secret",
        re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "GitHub token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b"),
    ),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("PyPI API token", re.compile(r"\bpypi-[A-Za-z0-9_-]{20,}\b")),
    (
        "SendGrid API key",
        re.compile(r"\bSG\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)

SENSITIVE_ASSIGNMENT_SUFFIXES = (
    ".cfg",
    ".env",
    ".ini",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
)

SENSITIVE_ASSIGNMENT = re.compile(
    r"""
    (?P<key>
        client_secret
        |refresh_token
        |private_key
        |access_token
        |api_key
        |openai_api_key
        |gemini_api_key
        |databricks_access_token
    )
    ["']?\s*[:=]\s*
    (?P<quote>["'])
    (?P<value>[^"'\n]{8,})
    (?P=quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)

PLACEHOLDER_VALUES = {
    "abc",
    "def",
    "example",
    "fake",
    "placeholder",
    "provider-token",
    "raw-token",
    "redacted",
    "secret",
    "secret-value",
    "test",
    "token",
}


@dataclass(frozen=True)
class Finding:
    path: Path
    reason: str
    line_number: int | None = None

    def format(self, root: Path) -> str:
        display_path = self.path.relative_to(root)
        if self.line_number is None:
            return f"{display_path}: {self.reason}"
        return f"{display_path}:{self.line_number}: {self.reason}"


def _git_scanned_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        root / filename.decode() for filename in result.stdout.split(b"\0") if filename
    ]


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    if normalized.startswith(("<", "${", "$")):
        return True
    if normalized.startswith(("/path/", "/absolute/path")):
        return True
    return any(token in normalized for token in ("example", "fake", "dummy"))


def _matches_secret_filename(path: Path) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_FILENAME_PATTERNS)


def _should_scan_sensitive_assignments(path: Path) -> bool:
    return (
        path.name.startswith(".env")
        or path.suffix.lower() in SENSITIVE_ASSIGNMENT_SUFFIXES
    )


def scan_paths(paths: list[Path], root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []

    for path in paths:
        if not path.exists() or not path.is_file():
            continue

        if _matches_secret_filename(path):
            findings.append(
                Finding(
                    path=path,
                    reason="tracked credential/key filename; keep this untracked or in a secret manager",
                )
            )

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            for reason, pattern in TOKEN_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        Finding(path=path, line_number=line_number, reason=reason)
                    )

            if not _should_scan_sensitive_assignments(path):
                continue

            for match in SENSITIVE_ASSIGNMENT.finditer(line):
                value = match.group("value")
                if not _is_placeholder(value):
                    key = match.group("key")
                    findings.append(
                        Finding(
                            path=path,
                            line_number=line_number,
                            reason=f"non-placeholder value assigned to {key}",
                        )
                    )

    return findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject tracked credentials and high-risk secret literals."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files to scan. Defaults to all git-tracked files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = ROOT
    paths = (
        [root / path for path in args.paths] if args.paths else _git_scanned_files(root)
    )
    findings = scan_paths(paths, root=root)

    if not findings:
        print("Secret hygiene check passed.")
        return 0

    print("Secret hygiene check failed:")
    for finding in findings:
        print(f"- {finding.format(root)}")
    print(
        "\nMove real credentials to environment variables, GitHub Secrets, or a secret manager."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
