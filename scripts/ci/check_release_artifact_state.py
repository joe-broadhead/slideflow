#!/usr/bin/env python3
"""Validate release artifact state before publishing or reusing a release."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PACKAGE_NAME = "slideflow-presentations"


def _url_exists(url: str, headers: dict[str, str] | None = None) -> bool:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _resolve_commitish(commitish: str) -> str:
    result = _run_git("rev-parse", "--verify", f"{commitish}^{{commit}}")
    if result.returncode != 0:
        raise RuntimeError(f"Unable to resolve expected commit {commitish!r}")
    return result.stdout.strip()


def _tag_commit(tag: str) -> str | None:
    result = _run_git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected 'true' or 'false'")


def _pypi_version_exists(
    *,
    package_name: str,
    version: str,
    override: bool | None,
) -> bool:
    if override is not None:
        return override
    return _url_exists(f"https://pypi.org/pypi/{package_name}/{version}/json")


def _github_release_exists(
    *,
    repository: str,
    tag: str,
    token: str | None,
    override: bool | None,
) -> bool:
    if override is not None:
        return override
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _url_exists(
        f"https://api.github.com/repos/{repository}/releases/tags/{tag}",
        headers=headers,
    )


def _write_github_outputs(
    *,
    output_file: Path | None,
    package_exists: bool,
    tag_exists: bool,
    release_exists: bool,
    tag_sha: str | None,
) -> None:
    if output_file is None:
        return

    lines = [
        f"package_exists={str(package_exists).lower()}",
        f"tag_exists={str(tag_exists).lower()}",
        f"release_exists={str(release_exists).lower()}",
    ]
    if tag_sha is not None:
        lines.append(f"tag_sha={tag_sha}")

    with output_file.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def _validate_release_state(
    *,
    version: str,
    tag: str,
    expected_commit: str,
    package_exists: bool,
    tag_sha: str | None,
) -> list[str]:
    errors: list[str] = []

    if tag_sha is not None and tag_sha != expected_commit:
        errors.append(
            f"Release tag {tag} points at {tag_sha}, "
            f"but expected artifact-producing commit {expected_commit}."
        )

    if package_exists and tag_sha is None:
        errors.append(
            f"PyPI version {version} already exists, but matching tag {tag} is missing."
        )

    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--output-file", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--package-exists-override", type=_parse_bool)
    parser.add_argument("--release-exists-override", type=_parse_bool)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.repository and args.release_exists_override is None:
        parser.error("--repository is required unless --release-exists-override is set")

    tag = f"v{args.version}"
    output_file = Path(args.output_file) if args.output_file else None

    try:
        expected_commit = _resolve_commitish(args.expected_commit)
        package_exists = _pypi_version_exists(
            package_name=args.package_name,
            version=args.version,
            override=args.package_exists_override,
        )
        tag_sha = _tag_commit(tag)
        release_exists = _github_release_exists(
            repository=args.repository,
            tag=tag,
            token=args.github_token,
            override=args.release_exists_override,
        )
    except (RuntimeError, urllib.error.URLError) as error:
        print(str(error), file=sys.stderr)
        return 1

    _write_github_outputs(
        output_file=output_file,
        package_exists=package_exists,
        tag_exists=tag_sha is not None,
        release_exists=release_exists,
        tag_sha=tag_sha,
    )

    errors = _validate_release_state(
        version=args.version,
        tag=tag,
        expected_commit=expected_commit,
        package_exists=package_exists,
        tag_sha=tag_sha,
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(
        "Release artifact state validated: "
        f"version={args.version}, "
        f"package_exists={str(package_exists).lower()}, "
        f"tag_exists={str(tag_sha is not None).lower()}, "
        f"release_exists={str(release_exists).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
