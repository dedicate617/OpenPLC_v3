#!/usr/bin/env bash
set -euo pipefail

# Prepare mplc_runtime migration branch with phase-based single-purpose commits.
# Usage:
#   ./prepare_mpi_pr.sh /path/to/mplc_runtime

TARGET_DIR="${1:-}"
if [[ -z "$TARGET_DIR" ]]; then
  echo "usage: $0 /path/to/mplc_runtime" >&2
  exit 1
fi

if [[ ! -d "$TARGET_DIR/.git" ]]; then
  echo "target is not a git repo: $TARGET_DIR" >&2
  exit 2
fi

cd "$TARGET_DIR"

echo "[1/6] checkout mpi + create mb_free_protocol"
git fetch origin mpi
git checkout mpi
git pull --ff-only origin mpi
git checkout -B mb_free_protocol

echo "[2/6] add migration source remote (OpenPLC_v3)"
if ! git remote get-url openplc_v3 >/dev/null 2>&1; then
  git remote add openplc_v3 /workspace/OpenPLC_v3
fi
git fetch openplc_v3

echo "[3/6] cherry-pick phase commits"
# Phase A~E commits from OpenPLC_v3 work branch (single-function sequence)
COMMITS=(
  a3958fd  # Python compiler + C++ compiled runtime primitives
  5695f94  # TCP/RTU full-chain transport/runtime demo
  5b7aa3d  # web compile/list API for frontend->python compile
  cf9c59a  # move runtime to C++ core
)

for c in "${COMMITS[@]}"; do
  echo "  - cherry-pick $c"
  git cherry-pick "$c"
done

echo "[4/6] optional docs commit"
# migration playbook/docs can be included separately if desired
# git cherry-pick 6f36479

echo "[5/6] basic validation"
python -m py_compile webserver/protocol_dsl_compiler.py webserver/protocol_dsl_runtime.py documentation/Protocol-DSL/tools/demo_runtime_flow.py

if [[ -f webserver/core/protocol_dsl_runtime.cpp ]]; then
  g++ -std=c++11 -fsyntax-only webserver/core/protocol_dsl_runtime.cpp -Iwebserver/core || true
fi

echo "[6/6] push branch"
git push -u origin mb_free_protocol

echo "done: branch mb_free_protocol is ready for PR"
