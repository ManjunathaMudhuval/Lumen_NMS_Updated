#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8788}"
SUBNET="66.162.110.0/24"
ENC_SUBNET="66.162.110.0~24"

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; exit 1; }

require_http_200() {
  local code
  code="$(curl -s -o /tmp/nms_smoke_resp.json -w '%{http_code}' "$1" ${2:-})"
  [[ "$code" == "200" ]] || fail "$3 (HTTP $code)"
  pass "$3"
}

echo "Running Phase 2 inventory smoke checks against ${BASE_URL}"

# 1) Health
require_http_200 "${BASE_URL}/api/health" "" "Health endpoint reachable"

# 2) Reset subnet to make run deterministic
require_http_200 "${BASE_URL}/api/inventory/subnet/${ENC_SUBNET}" "-X DELETE" "Subnet cleanup before test"

# 3) Add range
add_code="$(curl -s -o /tmp/nms_add.json -w '%{http_code}' -X POST "${BASE_URL}/api/inventory/range-add" -H 'Content-Type: application/json' -d '{"subnet":"66.162.110.0/24","host_start":1,"host_end":3}')"
[[ "$add_code" == "200" ]] || fail "Range add failed (HTTP $add_code)"
pass "Range add 1-3"

# 4) Run discovery state update
mock_code="$(curl -s -o /tmp/nms_mock.json -w '%{http_code}' -X POST "${BASE_URL}/api/inventory/discover/mock")"
[[ "$mock_code" == "200" ]] || fail "Discovery run failed (HTTP $mock_code)"
pass "Discovery state update"

# 5) Fetch inventory and validate schema/data rules
list_code="$(curl -s -o /tmp/nms_list.json -w '%{http_code}' "${BASE_URL}/api/inventory?subnet=${SUBNET}")"
[[ "$list_code" == "200" ]] || fail "Inventory list failed (HTTP $list_code)"

python3 - <<'PY'
import json
import sys

with open('/tmp/nms_list.json', 'r', encoding='utf-8') as f:
    payload = json.load(f)

items = payload.get('items', [])
if len(items) == 0:
    print('[FAIL] Inventory list empty after add+discover')
    sys.exit(1)

for item in items:
    for required in [
        'hostname', 'mgmt_ip', 'vendor', 'model', 'os_version',
        'serial_number', 'netconf', 'site', 'role', 'source', 'status', 'subnet'
    ]:
        if required not in item:
            print(f'[FAIL] Missing field: {required}')
            sys.exit(1)

    # No dummy placeholders are allowed.
    bad_fragments = ['Fetching...', 'Fetching via NETCONF...', 'node-', 'SN-000']
    for key in ['hostname', 'vendor', 'model', 'os_version', 'serial_number', 'site', 'role']:
        value = str(item.get(key, ''))
        if any(fragment in value for fragment in bad_fragments):
            print(f'[FAIL] Dummy value detected for {key}: {value}')
            sys.exit(1)

print(f'[PASS] Inventory schema and non-dummy-value checks ({len(items)} records)')
PY

# 6) Delete one IP and verify API behavior
ip_del_code="$(curl -s -o /tmp/nms_ipdel.json -w '%{http_code}' -X DELETE "${BASE_URL}/api/inventory/ip/66.162.110.2")"
[[ "$ip_del_code" == "200" ]] || fail "Delete single IP failed (HTTP $ip_del_code)"
pass "Single IP delete"

# 7) Cleanup subnet
require_http_200 "${BASE_URL}/api/inventory/subnet/${ENC_SUBNET}" "-X DELETE" "Subnet cleanup after test"

echo "Phase 2 inventory smoke checks completed successfully."
