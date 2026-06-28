#!/usr/bin/env python3
"""Validate protected live Google workflow evidence for a release commit."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

EXPECTED_WORKFLOWS = {
    "slides": ".github/workflows/live-google-slides.yml",
    "docs": ".github/workflows/live-google-docs.yml",
    "sheets": ".github/workflows/live-google-sheets.yml",
}


def _fetch_workflow_run(
    *,
    api_base: str,
    repository: str,
    run_id: str,
    token: str | None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/repos/{repository}/actions/runs/{run_id}",
        headers={"Accept": "application/vnd.github+json"},
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read().decode("utf-8")

    import json

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Workflow run {run_id} response was not an object")
    return data


def _validate_run_payload(
    *,
    run_name: str,
    expected_sha: str,
    expected_workflow_path: str,
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    if payload.get("head_sha") != expected_sha:
        errors.append(
            f"{run_name} run SHA mismatch: "
            f"head_sha={payload.get('head_sha')!r} expected={expected_sha!r}"
        )

    if payload.get("status") != "completed":
        errors.append(f"{run_name} run is not completed: {payload.get('status')!r}")

    if payload.get("conclusion") != "success":
        errors.append(f"{run_name} run did not succeed: {payload.get('conclusion')!r}")

    if payload.get("path") != expected_workflow_path:
        errors.append(
            f"{run_name} workflow mismatch: "
            f"path={payload.get('path')!r} expected={expected_workflow_path!r}"
        )

    if not payload.get("html_url"):
        errors.append(f"{run_name} run response is missing html_url")

    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--expected-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--slides-run-id", required=True)
    parser.add_argument("--docs-run-id", required=True)
    parser.add_argument("--sheets-run-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    if not args.expected_sha:
        parser.error("--expected-sha or GITHUB_SHA is required")

    run_ids = {
        "slides": args.slides_run_id,
        "docs": args.docs_run_id,
        "sheets": args.sheets_run_id,
    }

    errors: list[str] = []
    validated_urls: list[str] = []

    for run_name, run_id in run_ids.items():
        try:
            payload = _fetch_workflow_run(
                api_base=args.api_base,
                repository=args.repository,
                run_id=run_id,
                token=args.github_token,
            )
        except (RuntimeError, urllib.error.URLError) as error:
            errors.append(f"{run_name} run {run_id} could not be fetched: {error}")
            continue

        errors.extend(
            _validate_run_payload(
                run_name=run_name,
                expected_sha=args.expected_sha,
                expected_workflow_path=EXPECTED_WORKFLOWS[run_name],
                payload=payload,
            )
        )
        if payload.get("html_url"):
            validated_urls.append(str(payload["html_url"]))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print("Live Google validation evidence passed for current release SHA:")
    for url in validated_urls:
        print(f"- {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
