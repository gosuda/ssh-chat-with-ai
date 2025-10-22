#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_PROTO="${PROJECT_ROOT}/../ssh-chat/proto/middleware.proto"
TARGET_PROTO="${PROJECT_ROOT}/proto/middleware.proto"

if [[ ! -f "${SOURCE_PROTO}" ]]; then
  echo "Source proto not found: ${SOURCE_PROTO}" >&2
  exit 1
fi

cp "${SOURCE_PROTO}" "${TARGET_PROTO}"

pushd "${PROJECT_ROOT}/proto" > /dev/null
if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run python)
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=(python3)
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=(python)
elif command -v py >/dev/null 2>&1; then
  PYTHON_CMD=(py -3)
else
  echo "No suitable Python interpreter found. Install python3 or ensure 'py' launcher is available." >&2
  exit 1
fi

"${PYTHON_CMD[@]}" -m grpc_tools.protoc \
  --python_out=. \
  --grpc_python_out=. \
  --proto_path=. \
  middleware.proto
popd > /dev/null

PROJECT_ROOT="${PROJECT_ROOT}" "${PYTHON_CMD[@]}" "${SCRIPT_DIR}/fix_proto_import.py"

echo "Updated proto and regenerated Python gRPC stubs."
