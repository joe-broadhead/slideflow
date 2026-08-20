"""Run pip-audit with bounded, auditable dependency exceptions."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class AuditException:
    package: str
    vulnerability: str
    reason: str
    expires: dt.date

    def metadata(self) -> dict[str, str]:
        return {
            "package": self.package,
            "vulnerability": self.vulnerability,
            "reason": self.reason,
            "expires": self.expires.isoformat(),
        }


def _canonicalize_package_name(package: str) -> str:
    """Normalize a Python distribution name using the package-index rules."""
    return re.sub(r"[-_.]+", "-", package).lower()


def _load_policy(
    policy_path: Path, *, today: dt.date | None = None
) -> dict[tuple[str, str], AuditException]:
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"dependency audit exception policy is invalid: {error}"
        ) from error
    if not isinstance(policy, list):
        raise SystemExit("dependency audit exception policy must be a JSON list")

    current_date = today or dt.date.today()
    exceptions: dict[tuple[str, str], AuditException] = {}
    for entry in policy:
        if not isinstance(entry, dict):
            raise SystemExit("dependency audit exception entries must be objects")
        vulnerability = entry.get("vulnerability")
        package = entry.get("package")
        reason = entry.get("reason")
        try:
            expires = dt.date.fromisoformat(entry["expires"])
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit("dependency audit exception has invalid expiry") from error
        if not isinstance(vulnerability, str) or not vulnerability:
            raise SystemExit("dependency audit exception is missing vulnerability")
        if not isinstance(package, str) or not package:
            raise SystemExit("dependency audit exception is missing package")
        if not isinstance(reason, str) or not reason:
            raise SystemExit("dependency audit exception is missing required metadata")
        if current_date > expires:
            raise SystemExit(
                f"dependency audit exception expired for {package} {vulnerability}"
            )

        exception = AuditException(
            package=package,
            vulnerability=vulnerability,
            reason=reason,
            expires=expires,
        )
        key = (_canonicalize_package_name(package), vulnerability.casefold())
        if key in exceptions:
            raise SystemExit(
                f"duplicate dependency audit exception for {package} {vulnerability}"
            )
        exceptions[key] = exception
    return exceptions


def _extract_wrapper_args(args: Sequence[str]) -> tuple[list[str], Path | None]:
    forwarded: list[str] = []
    output_path: Path | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--output", "-o"}:
            if index + 1 >= len(args):
                raise SystemExit(f"{arg} requires a path")
            if output_path is not None:
                raise SystemExit("dependency audit output may only be specified once")
            output_path = Path(args[index + 1])
            index += 2
            continue
        if arg.startswith("--output="):
            if output_path is not None:
                raise SystemExit("dependency audit output may only be specified once")
            output_path = Path(arg.split("=", 1)[1])
            index += 1
            continue
        if arg in {"--format", "-f"}:
            if index + 1 >= len(args):
                raise SystemExit(f"{arg} requires a format")
            if args[index + 1] != "json":
                raise SystemExit("dependency audit wrapper only supports JSON output")
            index += 2
            continue
        if arg.startswith("--format="):
            if arg.split("=", 1)[1] != "json":
                raise SystemExit("dependency audit wrapper only supports JSON output")
            index += 1
            continue
        if arg == "--ignore-vuln" or arg.startswith("--ignore-vuln="):
            raise SystemExit(
                "dependency audit exceptions must be declared in the policy"
            )
        forwarded.append(arg)
        index += 1
    return forwarded, output_path


def _validate_vulnerability_ids(vulnerability: dict[str, Any]) -> list[str]:
    vulnerability_id = vulnerability.get("id")
    aliases = vulnerability.get("aliases", [])
    if not isinstance(vulnerability_id, str) or not vulnerability_id:
        raise SystemExit("pip-audit JSON contains a vulnerability without an id")
    if not isinstance(aliases, list) or not all(
        isinstance(alias, str) and alias for alias in aliases
    ):
        raise SystemExit("pip-audit JSON contains invalid vulnerability aliases")
    return [vulnerability_id, *aliases]


def _postprocess_audit(
    audit: Any,
    exceptions: dict[tuple[str, str], AuditException],
) -> tuple[dict[str, Any], int, int]:
    if not isinstance(audit, dict):
        raise SystemExit("pip-audit JSON output must be an object")
    dependencies = audit.get("dependencies")
    if not isinstance(dependencies, list):
        raise SystemExit("pip-audit JSON output must contain dependencies")

    active_count = 0
    suppressed_count = 0
    enriched_dependencies: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise SystemExit("pip-audit JSON contains an invalid dependency")
        enriched_dependency = dict(dependency)
        vulnerabilities = dependency.get("vulns", [])
        if not isinstance(vulnerabilities, list):
            raise SystemExit("pip-audit JSON contains invalid vulnerabilities")

        package = dependency.get("name")
        if vulnerabilities and (not isinstance(package, str) or not package):
            raise SystemExit(
                "pip-audit JSON contains a vulnerable package without a name"
            )
        canonical_package = (
            _canonicalize_package_name(package) if isinstance(package, str) else ""
        )

        enriched_vulnerabilities: list[dict[str, Any]] = []
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise SystemExit("pip-audit JSON contains an invalid vulnerability")
            vulnerability_ids = _validate_vulnerability_ids(vulnerability)
            matches = {
                exceptions[(canonical_package, identifier.casefold())]
                for identifier in vulnerability_ids
                if (canonical_package, identifier.casefold()) in exceptions
            }
            if len(matches) > 1:
                raise SystemExit(
                    f"multiple dependency audit exceptions match {package} "
                    f"{vulnerability_ids[0]}"
                )

            enriched_vulnerability = dict(vulnerability)
            if matches:
                exception = next(iter(matches))
                enriched_vulnerability["status"] = "suppressed"
                enriched_vulnerability["suppression"] = exception.metadata()
                suppressed_count += 1
            else:
                enriched_vulnerability["status"] = "active"
                active_count += 1
            enriched_vulnerabilities.append(enriched_vulnerability)
        enriched_dependency["vulns"] = enriched_vulnerabilities
        enriched_dependencies.append(enriched_dependency)

    enriched_audit = dict(audit)
    enriched_audit["dependencies"] = enriched_dependencies
    enriched_audit["summary"] = {
        "active_vulnerabilities": active_count,
        "suppressed_vulnerabilities": suppressed_count,
    }
    return enriched_audit, active_count, suppressed_count


def _write_audit(audit: dict[str, Any], output_path: Path | None) -> None:
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        sys.stdout.write(rendered)
    else:
        output_path.write_text(rendered, encoding="utf-8")


def main(
    argv: Sequence[str] | None = None,
    *,
    policy_path: Path | None = None,
    today: dt.date | None = None,
) -> int:
    root = Path(__file__).resolve().parents[2]
    resolved_policy_path = policy_path or (
        root / ".github" / "dependency-audit-exceptions.json"
    )
    exceptions = _load_policy(resolved_policy_path, today=today)
    forwarded_args, output_path = _extract_wrapper_args(
        list(sys.argv[1:] if argv is None else argv)
    )

    with tempfile.TemporaryDirectory(prefix="slideflow-pip-audit-") as temp_dir:
        raw_output = Path(temp_dir) / "pip-audit.json"
        command = [
            sys.executable,
            "-m",
            "pip_audit",
            "--format=json",
            "--output",
            str(raw_output),
            *forwarded_args,
        ]
        result = subprocess.run(command, check=False)
        if not raw_output.is_file():
            return result.returncode or 1
        try:
            raw_audit = json.loads(raw_output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(
                f"pip-audit produced invalid JSON output: {error}"
            ) from error

    enriched_audit, active_count, suppressed_count = _postprocess_audit(
        raw_audit, exceptions
    )
    _write_audit(enriched_audit, output_path)
    print(
        f"Dependency audit policy: {active_count} active, "
        f"{suppressed_count} suppressed",
        file=sys.stderr,
    )

    total_findings = active_count + suppressed_count
    if result.returncode not in {0, 1}:
        return result.returncode
    if result.returncode != 0 and total_findings == 0:
        return result.returncode
    return 1 if active_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
