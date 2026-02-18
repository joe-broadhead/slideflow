#!/usr/bin/env bash
set -euo pipefail

SMOKE_DIR="${1:-docs/quickstart/smoke}"

if [[ ! -d "${SMOKE_DIR}" ]]; then
  echo "Smoke sample directory not found: ${SMOKE_DIR}" >&2
  exit 1
fi

pushd "${SMOKE_DIR}" >/dev/null
slideflow validate config.yml
slideflow build config.yml --params-path params.csv --dry-run
popd >/dev/null
