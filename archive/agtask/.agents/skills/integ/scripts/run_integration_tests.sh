#!/usr/bin/env bash
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_ROOT="$(cd "$SKILL_ROOT/../../.." && pwd)"

INTEG_PARENT_THREAD_ID="${INTEG_PARENT_THREAD_ID:-${CODEX_THREAD_ID:-${SESSION_ID:-}}}"
if [[ -z "$INTEG_PARENT_THREAD_ID" ]]; then
  echo "Set INTEG_PARENT_THREAD_ID to the invoking Codex session ID." >&2
  exit 2
fi
export INTEG_PARENT_THREAD_ID

PROOF_DIR="${INTEG_PROOF_DIR:-$(python3 "$SKILL_ROOT/scripts/new_proof_dir.py")}"
mkdir -p "$PROOF_DIR"
PROOF_DIR="$(cd "$PROOF_DIR" && pwd)"

# Live lifecycle writes must never fall through to the user's default ledger.
# Preserve an explicit override for callers that provide their own isolated DB.
AGTASK_DB="${AGTASK_DB:-$PROOF_DIR/ledger.db}"
export AGTASK_DB

echo "Using proof dir: $PROOF_DIR"
echo "Using ledger: $AGTASK_DB"

(
  cd "$SOURCE_ROOT"
  PYTHONPYCACHEPREFIX=/tmp/agtask-pycache python3 -m unittest discover -s tests -v
  PYTHONPYCACHEPREFIX=/tmp/agtask-pycache python3 "$SKILL_ROOT/scripts/test_lifecycle.py" --source "$SOURCE_ROOT" --proof-dir "$PROOF_DIR"
) 2>&1 | tee "$PROOF_DIR/integration.log"
