#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="${1:-dist}"
SMOKE_DIR="${2:-docs/quickstart/smoke}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_PATH="$(cd "${DIST_DIR}" && pwd)"
SMOKE_PATH="$(cd "${SMOKE_DIR}" && pwd)"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

python -m twine check "${DIST_PATH}"/*
python -m pip check

slideflow --help >/dev/null
templates_output="$(slideflow templates list)"
grep -q "bars/bar_basic" <<<"${templates_output}"
template_info="$(slideflow templates info bars/bar_basic)"
grep -q "name: Bar Basic" <<<"${template_info}"

pushd "${TMP_DIR}" >/dev/null
python - <<'PY'
from importlib import resources

templates_root = resources.files("slideflow").joinpath("templates")
bar_template = templates_root.joinpath("bars", "bar_basic.yml")
if not bar_template.is_file():
    raise SystemExit(f"Packaged template not found: {bar_template}")

from slideflow.builtins.template_engine import get_template_engine

engine = get_template_engine()
template_names = engine.list_templates()
if "bars/bar_basic" not in template_names:
    raise SystemExit(f"bars/bar_basic missing from template catalog: {template_names}")

rendered = engine.render_template(
    "bars/bar_basic",
    {
        "title": "Smoke",
        "x_column": "region",
        "y_column": "revenue",
    },
)
if rendered["traces"][0]["type"] != "bar":
    raise SystemExit(f"Unexpected rendered template payload: {rendered}")

print("Installed wheel template resource smoke passed.")
PY
popd >/dev/null

bash "${REPO_ROOT}/scripts/ci/run_quickstart_smoke.sh" "${SMOKE_PATH}"
