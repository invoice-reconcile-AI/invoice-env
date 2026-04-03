#!/usr/bin/env bash
# Local pre-submission validator for Invoice Reconciliation OpenEnv env.
# Usage:
#   bash scripts/validate-submission.sh [optional_space_url]
# Example:
#   bash scripts/validate-submission.sh https://mathir14-invoice-reconciliation-env-v2.hf.space

set -euo pipefail

SPACE_URL="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OPENENV_VALIDATE_HELP="$(openenv validate --help 2>&1 || true)"
HAS_OPENENV_JSON=0
HAS_OPENENV_URL=0

if grep -q -- "--json" <<<"${OPENENV_VALIDATE_HELP}"; then
  HAS_OPENENV_JSON=1
fi
if grep -q -- "--url" <<<"${OPENENV_VALIDATE_HELP}"; then
  HAS_OPENENV_URL=1
fi

runtime_check_url() {
  local target_url="$1"
  python - "$target_url" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")

checks = [
  ("openapi", "/openapi.json", lambda data: isinstance(data.get("info", {}).get("version"), str)),
  ("health", "/health", lambda data: data.get("status") in {"healthy", "ok"}),
  ("metadata", "/metadata", lambda data: "name" in data and "description" in data),
  ("schema", "/schema", lambda data: all(k in data for k in ("action", "observation", "state"))),
]

for name, path, predicate in checks:
  url = f"{base}{path}"
  try:
    with urllib.request.urlopen(url, timeout=20) as response:
      payload = response.read().decode("utf-8")
      status = response.status
    data = json.loads(payload)
  except (urllib.error.URLError, TimeoutError) as exc:
    print(f"[FAIL] {name} endpoint request failed: {exc}")
    sys.exit(1)
  except json.JSONDecodeError as exc:
    print(f"[FAIL] {name} endpoint returned non-JSON payload: {exc}")
    sys.exit(1)

  if status != 200:
    print(f"[FAIL] {name} endpoint returned status {status}")
    sys.exit(1)
  if not predicate(data):
    print(f"[FAIL] {name} endpoint returned unexpected payload")
    sys.exit(1)
  print(f"[PASS] {name} endpoint")

try:
  mcp_url = f"{base}/mcp"
  request = urllib.request.Request(
    mcp_url,
    data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
  )
  with urllib.request.urlopen(request, timeout=20) as response:
    payload = response.read().decode("utf-8")
    status = response.status
  mcp_data = json.loads(payload)
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
  print(f"[FAIL] mcp endpoint request failed: {exc}")
  sys.exit(1)

if status != 200 or mcp_data.get("jsonrpc") != "2.0":
  print("[FAIL] mcp endpoint returned unexpected payload")
  sys.exit(1)
print("[PASS] mcp endpoint")

try:
  with urllib.request.urlopen(f"{base}/openapi.json", timeout=20) as response:
    openapi = json.loads(response.read().decode("utf-8"))
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
  print(f"[FAIL] openapi endpoint request failed during path check: {exc}")
  sys.exit(1)

paths = openapi.get("paths", {})
required_paths = ["/reset", "/step", "/state"]
missing = [path for path in required_paths if path not in paths]
if missing:
  print(f"[FAIL] Missing required OpenEnv paths: {', '.join(missing)}")
  sys.exit(1)
print("[PASS] required OpenEnv paths present")

print("[PASS] Runtime endpoint checks completed")
PY
}

echo "[CHECK] Root directory: ${ROOT_DIR}"
cd "${ROOT_DIR}"

if [[ ! -f "inference.py" ]]; then
  echo "[FAIL] Missing inference.py at project root"
  exit 1
fi

if [[ ! -f "openenv.yaml" ]]; then
  echo "[FAIL] Missing openenv.yaml"
  exit 1
fi

if [[ ! -f "Dockerfile" ]]; then
  echo "[FAIL] Missing Dockerfile"
  exit 1
fi

echo "[CHECK] Python compile"
python -m py_compile models.py client.py inference.py server/app.py server/environment.py scripts/smoke_test.py

echo "[CHECK] Smoke test"
python scripts/smoke_test.py

echo "[CHECK] openenv local validation"
if [[ "${HAS_OPENENV_JSON}" == "1" ]]; then
  openenv validate --json > /tmp/openenv_local_validation.json
  cat /tmp/openenv_local_validation.json
else
  openenv validate > /tmp/openenv_local_validation.txt
  cat /tmp/openenv_local_validation.txt
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  IMAGE_NAME="invoice-reconciliation-env:precheck"
  CONTAINER_NAME="invoice-reconciliation-precheck"

  echo "[CHECK] Docker build"
  docker build -t "${IMAGE_NAME}" .

  echo "[CHECK] Docker runtime health"
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker run -d --name "${CONTAINER_NAME}" -p 8000:8000 "${IMAGE_NAME}" >/dev/null

  for i in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
      echo "[PASS] Container health endpoint is live"
      break
    fi
    sleep 1
    if [[ "${i}" == "20" ]]; then
      echo "[FAIL] Container did not become healthy in time"
      docker logs "${CONTAINER_NAME}" || true
      docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
      exit 1
    fi
  done

  if [[ "${HAS_OPENENV_URL}" == "1" ]]; then
    echo "[CHECK] openenv runtime validation (local container)"
    openenv validate --url "http://127.0.0.1:8000" > /tmp/openenv_runtime_local_validation.json
    cat /tmp/openenv_runtime_local_validation.json
  else
    echo "[CHECK] Runtime endpoint validation (local container fallback)"
    runtime_check_url "http://127.0.0.1:8000"
  fi

  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
else
  echo "[WARN] Docker unavailable (missing CLI or daemon not running). Skipping Docker checks."
fi

if [[ -n "${SPACE_URL}" ]]; then
  if [[ "${HAS_OPENENV_URL}" == "1" ]]; then
    echo "[CHECK] Runtime validation against ${SPACE_URL}"
    openenv validate --url "${SPACE_URL}" > /tmp/openenv_runtime_validation.json
    cat /tmp/openenv_runtime_validation.json
  else
    echo "[CHECK] Runtime endpoint validation against ${SPACE_URL} (fallback)"
    runtime_check_url "${SPACE_URL}"
  fi
fi

echo "[PASS] Pre-submission checks completed"
