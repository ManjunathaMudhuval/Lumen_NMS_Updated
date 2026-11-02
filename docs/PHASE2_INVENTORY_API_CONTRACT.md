# Phase 2 Inventory API Contract

Date: 2026-10-16
Scope: Inventory only
Test subnet: 66.162.110.0/24
Test host range: 1-5

## 1) Purpose
Lock a stable API contract for real-time inventory using NETCONF discovery and YANG data fetch.

## 2) Base URL
- Local: http://127.0.0.1:8788

## 3) Endpoints

1. GET /api/health
- Purpose: service health check.
- Response:
```json
{
  "status": "ok",
  "service": "nms-inventory-api"
}
```

2. GET /api/inventory
- Purpose: list inventory records.
- Query params:
  - subnet (optional): CIDR or ALL
  - host_ip (optional): full IP or ALL
- Response:
```json
{
  "items": [
    {
      "hostname": "",
      "mgmt_ip": "66.162.110.1",
      "vendor": "",
      "model": "",
      "os_version": "",
      "serial_number": "",
      "netconf": "Enabled",
      "site": "",
      "role": "",
      "source": "NETCONF",
      "status": "Discovered",
      "subnet": "66.162.110.0/24",
      "fetch_reason": "Live values fetched via NETCONF + YANG."
    }
  ]
}
```

3. POST /api/inventory/range-add
- Purpose: add pending inventory rows for host range.
- Request:
```json
{
  "subnet": "66.162.110.0/24",
  "host_start": 1,
  "host_end": 5
}
```
- Response:
```json
{
  "message": "Added 5 IP(s); skipped 0 duplicate(s)."
}
```

4. DELETE /api/inventory/ip/{ip}
- Purpose: delete a single IP record.
- Response:
```json
{
  "message": "Deleted 66.162.110.1."
}
```

5. DELETE /api/inventory/subnet/{subnet}
- Purpose: delete all records under one subnet.
- Note: encode slash as ~ in path.
- Example path: /api/inventory/subnet/66.162.110.0~24
- Response:
```json
{
  "message": "Deleted 5 IP(s) under 66.162.110.0/24."
}
```

6. POST /api/inventory/discover/netconf-probe
- Purpose: perform live NETCONF TCP reachability probe (port 830) per selected inventory IPs.
- Request:
```json
{
  "subnet": "66.162.110.0/24",
  "host_ip": "ALL",
  "timeout_seconds": 2.0
}
```
- Response:
```json
{
  "message": "NETCONF probe complete: 3 reachable, 2 unreachable (timeout 2.0s)."
}
```
- Behavior notes:
  - This validates port reachability only.
  - It does not fetch model/version/serial from live YANG.

7. POST /api/inventory/credentials/upsert
- Purpose: save default and per-device NETCONF credentials for live YANG fetch.
- Request:
```json
{
  "default_username": "netops",
  "default_password": "replace-me",
  "default_secret": "",
  "per_device": [
    {
      "mgmt_ip": "66.162.110.3",
      "username": "noc-user",
      "password": "replace-me-3",
      "secret": ""
    }
  ]
}
```
- Response:
```json
{
  "message": "Saved credentials: default=yes, per_device=1."
}
```

8. POST /api/inventory/discover/netconf-yang
- Purpose: fetch live device metadata through NETCONF + YANG.
- Request:
```json
{
  "subnet": "66.162.110.0/24",
  "host_ip": "ALL",
  "timeout_seconds": 8.0
}
```
- Response:
```json
{
  "message": "NETCONF+YANG fetch complete: 4 discovered, 1 failed. Failed IPs: 66.162.110.3."
}
```

9. POST /api/inventory/netconf-yang-snapshot
- Purpose: run NETCONF discovery first, then NETCONF+YANG fetch, and return current inventory in one response.
- Request:
```json
{
  "subnet": "66.162.110.0/24",
  "host_ip": "ALL",
  "timeout_seconds": 8.0
}
```
- Response:
```json
{
  "message": "NETCONF probe complete: 4 reachable, 1 unreachable (timeout 3.0s). | NETCONF+YANG fetch complete: 4 discovered, 1 failed. Failed IPs: 66.162.110.3.",
  "items": []
}
```

10. GET /health
- Purpose: compatibility health endpoint alias for /api/health.

11. POST /api/inventory/discover/metadata and /api/inventory/discover/mock
- Status: disabled in strict real-time mode.
- Response: HTTP 410 with guidance to use /api/inventory/netconf-yang-snapshot.

12. WebSocket /api/ws/inventory/netconf-yang
- Purpose: push near real-time inventory snapshots to frontend without manual refresh.
- Query params:
  - subnet (default ALL)
  - host_ip (default ALL)
  - interval_seconds (default 10)
  - timeout_seconds (default 8)

## 4) Field Dictionary

Required fields per item:
1. hostname: string
2. mgmt_ip: string (IPv4)
3. vendor: string
4. model: string
5. os_version: string
6. serial_number: string
7. netconf: enum
8. site: string
9. role: string
10. source: enum
11. status: enum
12. subnet: string (CIDR)

## 5) Enum Rules

netconf:
1. Pending
2. Enabled
3. Disabled

source:
1. Manual
2. NETCONF
3. SNMP

status:
1. Pending Discovery
2. Discovered
3. Fetch Failed

## 6) Validation Rules
1. subnet must equal 66.162.110.0/24 in current test scope.
2. host_start and host_end must be integer and between 1 and 5.
3. host_start must be <= host_end.
4. duplicate mgmt_ip must not be inserted twice.

## 7) NETCONF + YANG Mapping Targets (Phase 3 Ready)
1. hostname -> system hostname leaf
2. vendor/model/serial_number -> hardware inventory/chassis leaves
3. os_version -> software/system version leaves
4. netconf -> capability/session state
5. site/role -> policy or CMDB mapping layer

## 8) Contract Freeze Note
No frontend schema changes should be made without updating this contract document first.
