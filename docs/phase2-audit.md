# Phase 2 Audit (2026-02-18)

This report captures the first full hardening pass across reliability, security, dependency hygiene, and documentation fidelity.

## Scope

- CLI behavior parity and failure modes
- Config loading and parameter rendering
- Registry import correctness and module isolation
- CI quality gates and audit automation
- Documentation accuracy against current implementation

## Findings

| ID | Severity | Area | Status | Summary |
| --- | --- | --- | --- | --- |
| A-001 | P1 | Registry loading | Fixed | Ensure target registry package path is forced to front and transient `package.*` modules are purged after load. |
| A-002 | P1 | CLI behavior | Fixed | `validate` now honors YAML `registry:` like `build`, preventing command parity drift. |
| A-003 | P2 | Config rendering | Fixed | `{param}` substitution now works in strings that also contain `{{PLACEHOLDER}}`. |
| A-004 | P2 | Batch reliability | Fixed | Empty `--params-path` CSV now fails fast with a clear error instead of executor failure. |
| A-005 | P2 | Dependency security | Mitigated | Added automated `pip-audit` and `bandit` workflow with artifact reporting. |
| A-006 | P2 | Dependency policy | Open | Runtime dependencies are mostly unbounded; upgrade risk remains high without upper-bound or lock strategy. |
| A-007 | P2 | Runtime compatibility | Open | Pydantic v1-style `@root_validator` still present; future pydantic major upgrade risk. |
| A-008 | P3 | Runtime compatibility | Open | `ast.Num` deprecation warning in positioning parser indicates upcoming Python compatibility debt. |

## Evidence

- Registry import hardening and cleanup: `slideflow/utilities/config.py`
- CLI parity fix (`validate` registry resolution): `slideflow/cli/commands/validate.py`
- Batch empty CSV guard: `slideflow/cli/commands/build.py`
- Added/updated regression tests: `tests/test_config_utilities.py`, `tests/test_cli_commands.py`
- CI dependency sanity gate: `.github/workflows/ci.yml`
- Audit automation workflow: `.github/workflows/audit.yml`

## Remediation plan

1. Close open compatibility debt
   - migrate `@root_validator` -> `@model_validator`
   - replace `ast.Num` usage with `ast.Constant`
2. Define dependency policy
   - decide lock approach for runtime deps (constraints file or upper bounds)
   - enforce policy in CI
3. Expand test suite by module (Phase 3)
   - CLI edge cases
   - connector error paths
   - provider cleanup behaviors
   - config/model validation boundaries

## Exit criteria for Phase 2

- No unresolved P0/P1 findings
- CI includes audit automation with reviewable artifacts
- Critical CLI/config reliability issues covered by tests
- Documentation reflects implemented behavior and operational workflows
