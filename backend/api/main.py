from __future__ import annotations

import asyncio
from datetime import datetime
from ipaddress import ip_network
import os
from pathlib import Path
import re
import socket
from typing import Literal
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

TEST_SUBNET = "66.162.110.0/24"
HOST_MIN = 1
HOST_MAX = 254

StatusType = Literal["Pending Discovery", "Discovered", "Fetch Failed"]
SourceType = Literal["Manual", "NETCONF", "SNMP", "Imported", "SSH"]
NetconfType = Literal["Pending", "Enabled", "Disabled"]


class DeviceRecord(BaseModel):
    hostname: str
    mgmt_ip: str
    vendor: str
    model: str
    os_version: str
    serial_number: str
    routing_protocols: str = ""
    mgmt_vlan: str = ""
    routing_domain: str = ""
    snmp_profile: str = ""
    ntp_profile: str = ""
    security_profile: str = ""
    netconf: NetconfType
    site: str
    role: str
    source: SourceType
    status: StatusType
    subnet: str
    fetch_reason: str = ""


class RangeAddRequest(BaseModel):
    subnet: str = Field(..., examples=[TEST_SUBNET])
    host_start: int = Field(..., ge=HOST_MIN, le=HOST_MAX)
    host_end: int = Field(..., ge=HOST_MIN, le=HOST_MAX)


class InventoryResponse(BaseModel):
    items: list[DeviceRecord]


class ActionResponse(BaseModel):
    message: str


class LiveSnapshotResponse(BaseModel):
    message: str
    items: list[DeviceRecord]


class DeviceInterface(BaseModel):
    name: str
    description: str = ""
    admin_status: str
    oper_status: str
    vlan: str = ""
    mac: str = ""


class DeviceInterfacesResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    polled_at: str
    items: list[DeviceInterface]
    health: dict | None = None
    health_message: str = ""
    message: str = ""


class LldpNeighbor(BaseModel):
    local_interface: str
    neighbor_hostname: str
    neighbor_interface: str = ""
    neighbor_mgmt_ip: str = ""


class DeviceLldpTopologyResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    polled_at: str
    items: list[LldpNeighbor]
    message: str = ""


class SafeScanResponse(BaseModel):
    message: str
    scanned: int
    discovered: int
    failed: int
    items: list[DeviceRecord]


class CredentialsStatusResponse(BaseModel):
    default_configured: bool
    per_device_count: int
    per_device_ips: list[str]


class MetadataEntry(BaseModel):
    mgmt_ip: str
    hostname: str
    vendor: str
    model: str
    os_version: str
    serial_number: str
    site: str = ""
    role: str = ""


class MetadataUpsertRequest(BaseModel):
    items: list[MetadataEntry]


class NetconfProbeRequest(BaseModel):
    subnet: str | None = Field(default=None, examples=[TEST_SUBNET])
    host_ip: str | None = Field(default=None, examples=["66.162.110.1"])
    timeout_seconds: float = Field(default=2.0, ge=0.2, le=10.0)


class NetconfYangFetchRequest(BaseModel):
    subnet: str | None = Field(default=None, examples=[TEST_SUBNET])
    host_ip: str | None = Field(default=None, examples=["66.162.110.1"])
    username: str | None = None
    password: str | None = None
    timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)


class NetconfYangSafeScanRequest(NetconfYangFetchRequest):
    max_concurrency: int = Field(default=4, ge=1, le=10)
    max_retries: int = Field(default=1, ge=0, le=3)


class DeviceCredentialEntry(BaseModel):
    mgmt_ip: str
    username: str
    password: str
    secret: str = ""


class CredentialsUpsertRequest(BaseModel):
    default_username: str = ""
    default_password: str = ""
    default_secret: str = ""
    per_device: list[DeviceCredentialEntry] = []


class ConfigBackupRecord(BaseModel):
    backup_id: str
    mgmt_ip: str
    hostname: str
    created_at: str
    source: str
    content: str


class ConfigHistoryRecord(BaseModel):
    event_id: str
    mgmt_ip: str
    hostname: str
    timestamp: str
    action: str
    message: str


class DeviceCurrentConfigResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    source: str
    fetched_at: str
    content: str
    message: str = ""


class DeviceBackupListResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    items: list[ConfigBackupRecord]


class DeviceHistoryResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    items: list[ConfigHistoryRecord]


class DeviceCompareRequest(BaseModel):
    left_backup_id: str | None = None
    right_backup_id: str | None = None
    left_text: str | None = None
    right_text: str | None = None


class DeviceCompareResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    left_label: str
    right_label: str
    added_lines: int
    removed_lines: int
    diff: str


class DeviceFactsResponse(BaseModel):
    mgmt_ip: str
    hostname: str
    vendor: str
    model: str
    os_version: str
    serial_number: str
    site: str
    role: str
    status: str
    netconf: str
    backup_count: int
    history_count: int


def _subnet_base(cidr: str) -> str:
    try:
        network = ip_network(cidr, strict=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid subnet: {cidr}") from exc
    octets = str(network.network_address).split(".")
    return f"{octets[0]}.{octets[1]}.{octets[2]}"


def _validate_test_scope(subnet: str, host_start: int, host_end: int) -> None:
    if subnet != TEST_SUBNET:
        raise HTTPException(status_code=400, detail=f"Only subnet {TEST_SUBNET} is allowed in this phase.")
    if host_start > host_end:
        raise HTTPException(status_code=400, detail="host_start must be <= host_end")


app = FastAPI(title="NMS Phase 2 Inventory API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_FILE = DATA_DIR / "inventory_store.json"
METADATA_OVERRIDES_FILE = DATA_DIR / "device_metadata_overrides.json"
DEVICE_CREDENTIALS_FILE = DATA_DIR / "device_credentials.json"
CONFIG_BACKUPS_FILE = DATA_DIR / "device_config_backups.json"
CONFIG_HISTORY_FILE = DATA_DIR / "device_config_history.json"
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"
HOME_ENV_FILE = PROJECT_ROOT.parent / ".env"


def _load_inventory() -> list[DeviceRecord]:
    if not INVENTORY_FILE.exists():
        return []
    try:
        import json

        payload = json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
        return [DeviceRecord.model_validate(item) for item in payload]
    except Exception:
        return []


def _save_inventory(items: list[DeviceRecord]) -> None:
    import json

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INVENTORY_FILE.write_text(
        json.dumps([item.model_dump() for item in items], indent=2),
        encoding="utf-8",
    )


def _load_metadata_overrides() -> dict[str, dict[str, str]]:
    if not METADATA_OVERRIDES_FILE.exists():
        return {}
    try:
        import json

        payload = json.loads(METADATA_OVERRIDES_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        # Keep only string keyed/object valued entries.
        return {
            str(ip): value
            for ip, value in payload.items()
            if isinstance(value, dict)
        }
    except Exception:
        return {}


def _save_metadata_overrides(overrides: dict[str, dict[str, str]]) -> None:
    import json

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_OVERRIDES_FILE.write_text(
        json.dumps(overrides, indent=2),
        encoding="utf-8",
    )


def _load_device_credentials() -> dict:
    if not DEVICE_CREDENTIALS_FILE.exists():
        return {
            "default": {"username": "", "password": "", "secret": ""},
            "per_device": {},
        }
    try:
        import json

        payload = json.loads(DEVICE_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}

        # Backward-compat: flat schema with username/password/secret.
        if "default" not in payload and ("username" in payload or "password" in payload or "secret" in payload):
            return {
                "default": {
                    "username": str(payload.get("username", "")),
                    "password": str(payload.get("password", "")),
                    "secret": str(payload.get("secret", "")),
                },
                "per_device": {},
            }

        default = payload.get("default", {}) if isinstance(payload.get("default", {}), dict) else {}
        per_device_raw = payload.get("per_device", {}) if isinstance(payload.get("per_device", {}), dict) else {}
        per_device: dict[str, dict[str, str]] = {}
        for ip, value in per_device_raw.items():
            if isinstance(value, dict):
                per_device[str(ip)] = {
                    "username": str(value.get("username", "")),
                    "password": str(value.get("password", "")),
                    "secret": str(value.get("secret", "")),
                }

        return {
            "default": {
                "username": str(default.get("username", "")),
                "password": str(default.get("password", "")),
                "secret": str(default.get("secret", "")),
            },
            "per_device": per_device,
        }
    except Exception:
        return {
            "default": {"username": "", "password": "", "secret": ""},
            "per_device": {},
        }


def _save_device_credentials(payload: dict) -> None:
    import json

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEVICE_CREDENTIALS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []
    except Exception:
        return []


def _save_json_list(path: Path, items: list[dict]) -> None:
    import json

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env_credentials() -> tuple[str, str, str]:
    # Process env has first priority because it is explicit runtime configuration.
    user = (
        os.getenv("SSH_USER")
        or os.getenv("NETCONF_USER")
        or os.getenv("USERNAME")
        or os.getenv("DEVICE_USERNAME")
        or ""
    ).strip()
    password = (
        os.getenv("SSH_PASS")
        or os.getenv("NETCONF_PASS")
        or os.getenv("PASSWORD")
        or os.getenv("DEVICE_PASSWORD")
        or ""
    ).strip()
    secret = (os.getenv("SSH_SECRET") or os.getenv("DEVICE_SECRET") or "").strip()
    if user and password:
        return user, password, secret

    # Fallback to .env file values (project root first, then user home).
    env_file_values = _parse_env_file(PROJECT_ENV_FILE)
    if not env_file_values:
        env_file_values = _parse_env_file(HOME_ENV_FILE)

    user = (
        env_file_values.get("SSH_USER")
        or env_file_values.get("NETCONF_USER")
        or env_file_values.get("USERNAME")
        or env_file_values.get("DEVICE_USERNAME")
        or ""
    ).strip()
    password = (
        env_file_values.get("SSH_PASS")
        or env_file_values.get("NETCONF_PASS")
        or env_file_values.get("PASSWORD")
        or env_file_values.get("DEVICE_PASSWORD")
        or ""
    ).strip()
    secret = (
        env_file_values.get("SSH_SECRET")
        or env_file_values.get("DEVICE_SECRET")
        or ""
    ).strip()
    return user, password, secret


def _resolve_device_credentials(
    ip: str,
    request_username: str,
    request_password: str,
    request_secret: str,
) -> tuple[str, str, str]:
    # Request-scoped explicit creds override all saved credentials.
    if request_username and request_password:
        return request_username, request_password, request_secret

    creds_file = _load_device_credentials()
    per_device = creds_file.get("per_device", {}) if isinstance(creds_file, dict) else {}
    default = creds_file.get("default", {}) if isinstance(creds_file, dict) else {}

    if isinstance(per_device.get(ip), dict):
        entry = per_device[ip]
        user = str(entry.get("username", "")).strip()
        password = str(entry.get("password", "")).strip()
        secret = str(entry.get("secret", "")).strip()
        if user and password:
            return user, password, secret

    user = str(default.get("username", "")).strip()
    password = str(default.get("password", "")).strip()
    secret = str(default.get("secret", "")).strip()
    if user and password:
        return user, password, secret

    env_user, env_password, env_secret = _env_credentials()
    if env_user and env_password:
        return env_user, env_password, env_secret

    return user, password, secret


def _filter_inventory(subnet: str | None, host_ip: str | None) -> list[DeviceRecord]:
    items = inventory_store
    if subnet and subnet != "ALL":
        items = [item for item in items if item.subnet == subnet]
    if host_ip and host_ip != "ALL":
        items = [item for item in items if item.mgmt_ip == host_ip]
    return items


@app.get("/api/inventory/credentials/status", response_model=CredentialsStatusResponse)
def credentials_status() -> CredentialsStatusResponse:
    creds = _load_device_credentials()
    default = creds.get("default", {}) if isinstance(creds, dict) else {}
    per_device = creds.get("per_device", {}) if isinstance(creds, dict) else {}

    default_user = str(default.get("username", "")).strip()
    default_pass = str(default.get("password", "")).strip()
    ips = sorted([str(ip) for ip in per_device.keys()])
    return CredentialsStatusResponse(
        default_configured=bool(default_user and default_pass),
        per_device_count=len(ips),
        per_device_ips=ips,
    )


def _validate_test_ip(ip: str) -> None:
    base = _subnet_base(TEST_SUBNET)
    if not ip.startswith(f"{base}."):
        raise HTTPException(status_code=400, detail=f"IP {ip} is outside allowed subnet {TEST_SUBNET}.")
    try:
        host_octet = int(ip.split(".")[-1])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid IP format: {ip}") from exc
    if host_octet < HOST_MIN or host_octet > HOST_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"IP {ip} is outside allowed host range {HOST_MIN}-{HOST_MAX} for {TEST_SUBNET}.",
        )


def _apply_metadata(item: DeviceRecord, metadata: dict[str, str]) -> bool:
    required = ["hostname", "vendor", "model", "os_version", "serial_number"]
    if not all(str(metadata.get(field, "")).strip() for field in required):
        return False

    item.hostname = str(metadata["hostname"]).strip()
    item.vendor = str(metadata["vendor"]).strip()
    item.model = str(metadata["model"]).strip()
    item.os_version = str(metadata["os_version"]).strip()
    item.serial_number = str(metadata["serial_number"]).strip()
    item.site = str(metadata.get("site", "")).strip()
    item.role = str(metadata.get("role", "")).strip()
    return True


def _clear_identity_fields(item: DeviceRecord) -> None:
    item.hostname = ""
    item.vendor = ""
    item.model = ""
    item.os_version = ""
    item.serial_number = ""
    item.routing_protocols = ""
    item.mgmt_vlan = ""
    item.routing_domain = ""
    item.snmp_profile = ""
    item.ntp_profile = ""
    item.security_profile = ""


# Phase 3 start: persisted inventory store (JSON-backed).
inventory_store: list[DeviceRecord] = _load_inventory()
config_backups_store: list[dict] = _load_json_list(CONFIG_BACKUPS_FILE)
config_history_store: list[dict] = _load_json_list(CONFIG_HISTORY_FILE)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nms-inventory-api"}


@app.get("/health")
def health_compat() -> dict[str, str]:
    # Compatibility alias for external checks expecting /health.
    return health()


@app.get("/api/inventory", response_model=InventoryResponse)
def list_inventory(
    subnet: str | None = Query(default=None),
    host_ip: str | None = Query(default=None),
) -> InventoryResponse:
    return InventoryResponse(items=_filter_inventory(subnet=subnet, host_ip=host_ip))


def _mock_interfaces_for_device(item: DeviceRecord) -> list[DeviceInterface]:
    last_octet = int(item.mgmt_ip.split(".")[-1]) if item.mgmt_ip and "." in item.mgmt_ip else 1
    down = (last_octet % 5) == 0

    if "palo" in (item.vendor or "").lower():
        return [
            DeviceInterface(
                name="ethernet1/1",
                description="Internet Uplink",
                admin_status="up",
                oper_status="down" if down else "up",
                vlan="-",
                mac=f"A4:5E:60:FA:19:{last_octet:02X}",
            ),
            DeviceInterface(
                name="ethernet1/2",
                description="Inside",
                admin_status="up",
                oper_status="up",
                vlan="100",
                mac=f"A4:5E:60:FA:1A:{last_octet:02X}",
            ),
        ]

    if "arista" in (item.vendor or "").lower():
        return [
            DeviceInterface(
                name="Et1",
                description="To Core",
                admin_status="up",
                oper_status="up",
                vlan="200",
                mac=f"44:38:39:AA:01:{last_octet:02X}",
            ),
            DeviceInterface(
                name="Et2",
                description="To Access",
                admin_status="up",
                oper_status="down" if down else "up",
                vlan="210",
                mac=f"44:38:39:AA:02:{last_octet:02X}",
            ),
        ]

    return [
        DeviceInterface(
            name="Gi0/0/0",
            description="WAN Uplink",
            admin_status="up",
            oper_status="down" if down else "up",
            vlan="100",
            mac=f"00:1A:2B:3C:4D:{last_octet:02X}",
        ),
        DeviceInterface(
            name="Gi0/0/1",
            description="Core Switch",
            admin_status="up",
            oper_status="up",
            vlan="200",
            mac=f"00:1A:2B:3C:4E:{last_octet:02X}",
        ),
        DeviceInterface(
            name="Gi0/0/2",
            description="Spare",
            admin_status="down",
            oper_status="down",
            vlan="-",
            mac=f"00:1A:2B:3C:4F:{last_octet:02X}",
        ),
    ]


def _extract_live_interfaces(root: ET.Element) -> list[DeviceInterface]:
    """Extract interface rows from common YANG/operational trees.

    This parser is vendor-agnostic and intentionally tolerant: it scans all
    interface-like elements and keeps entries that at least expose an interface
    name plus one operational attribute.
    """
    interfaces_by_name: dict[str, DeviceInterface] = {}

    for element in root.iter():
        if element.tag.split("}")[-1].lower() != "interface":
            continue

        name = ""
        description = ""
        admin_status = ""
        oper_status = ""
        vlan = ""
        mac = ""

        for child in element.iter():
            local = child.tag.split("}")[-1].lower()
            value = (child.text or "").strip()
            if not value:
                continue

            if local in {"name", "if-name"} and not name:
                name = value
            elif local in {"description", "if-description"} and not description:
                description = value
            elif local in {"admin-status", "enabled"} and not admin_status:
                if local == "enabled":
                    admin_status = "up" if value.lower() in {"true", "1", "up"} else "down"
                else:
                    admin_status = value
            elif local in {"oper-status", "oper-state", "state"} and not oper_status:
                oper_status = value
            elif local in {"phys-address", "mac-address", "hardware-address"} and not mac:
                mac = value
            elif local in {"vlan-id", "access-vlan", "native-vlan", "pvid"} and not vlan:
                vlan = value

        # Guard against unrelated interface nodes that don't represent ports.
        if not name:
            continue
        if not any([admin_status, oper_status, description, vlan, mac]):
            continue

        if not admin_status:
            admin_status = "unknown"
        if not oper_status:
            oper_status = "unknown"

        existing = interfaces_by_name.get(name)
        candidate = DeviceInterface(
            name=name,
            description=description,
            admin_status=admin_status,
            oper_status=oper_status,
            vlan=vlan,
            mac=mac,
        )

        if not existing:
            interfaces_by_name[name] = candidate
            continue

        # Prefer richer records if duplicate interface names appear across trees.
        existing_score = sum(1 for v in [existing.description, existing.vlan, existing.mac] if v)
        candidate_score = sum(1 for v in [candidate.description, candidate.vlan, candidate.mac] if v)
        if candidate_score > existing_score:
            interfaces_by_name[name] = candidate

    return sorted(interfaces_by_name.values(), key=lambda item: item.name)


def _first_child_text(node: ET.Element, local_names: set[str]) -> str:
    for child in node.iter():
        local = child.tag.split("}")[-1].lower()
        if local in local_names:
            value = (child.text or "").strip()
            if value:
                return value
    return ""


def _first_number(value: str) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _extract_realtime_health_from_junos_rpc(session) -> dict | None:
    """Read route-engine metrics from Junos RPC (show chassis routing-engine equivalent)."""
    try:
        from ncclient.xml_ import to_ele

        rpc = """
        <get-route-engine-information>
          <detail/>
        </get-route-engine-information>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
    except Exception:
        return None

    route_engines: list[ET.Element] = []
    for element in root.iter():
        local = element.tag.split("}")[-1].lower()
        if local == "route-engine":
            route_engines.append(element)

    if not route_engines:
        return None

    best_cpu: float | None = None
    best_memory: float | None = None
    best_temp: float | None = None

    for route_engine in route_engines:
      cpu_idle = _first_number(_first_child_text(route_engine, {"cpu-idle", "cpu-idle2"}))
      cpu_user = _first_number(_first_child_text(route_engine, {"cpu-user", "cpu-user1", "cpu-user2"}))
      cpu_system = _first_number(_first_child_text(route_engine, {"cpu-system", "cpu-system1", "cpu-system2"}))
      cpu_background = _first_number(_first_child_text(route_engine, {"cpu-background", "cpu-background1", "cpu-background2"}))
      cpu_interrupt = _first_number(_first_child_text(route_engine, {"cpu-interrupt", "cpu-interrupt1", "cpu-interrupt2"}))

      cpu_util = None
      if cpu_idle is not None:
          cpu_util = max(0.0, min(100.0, 100.0 - cpu_idle))
      else:
          parts = [v for v in [cpu_user, cpu_system, cpu_background, cpu_interrupt] if v is not None]
          if parts:
              cpu_util = max(0.0, min(100.0, sum(parts)))

      memory_util = _first_number(
          _first_child_text(
              route_engine,
              {
                  "memory-buffer-utilization",
                  "memory-dram-utilization",
                  "memory-system-utilization",
                  "memory-utilization",
                  "memory-buffer-util",
                  "memory-dram-util",
              },
          )
      )
      if memory_util is not None:
          memory_util = max(0.0, min(100.0, memory_util))

      temperature = _first_number(
          _first_child_text(
              route_engine,
              {
                  "temperature",
                  "cpu-temperature",
                  "master-temperature",
                  "re-temperature",
              },
          )
      )

      if cpu_util is not None and best_cpu is None:
          best_cpu = cpu_util
      if memory_util is not None and best_memory is None:
          best_memory = memory_util
      if temperature is not None and best_temp is None:
          best_temp = temperature

    if best_cpu is None and best_memory is None and best_temp is None:
        return None

    return {
        "cpu_utilization": round(best_cpu, 1) if best_cpu is not None else None,
        "memory_utilization": round(best_memory, 1) if best_memory is not None else None,
        "temperature_c": round(best_temp, 1) if best_temp is not None else None,
        "source": "show chassis routing-engine",
    }


def _extract_realtime_health_from_junos_cli_output(session) -> dict | None:
    """Fallback parser using Junos CLI command output for routing-engine health."""
    try:
        from ncclient.xml_ import to_ele

        rpc = """
        <command format=\"text\">show chassis routing-engine</command>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
    except Exception:
        return None

    # Try extracting plain output text; fall back to raw XML string scanning.
    text_fragments = re.findall(r"<output>(.*?)</output>", raw, flags=re.IGNORECASE | re.DOTALL)
    text_blob = "\n".join(text_fragments).strip() if text_fragments else raw

    cpu_util = None
    memory_util = None
    temp_c = None

    idle_match = re.search(r"(?:cpu\s+)?idle\s*(?:[:=]|\s)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)?", text_blob, flags=re.IGNORECASE)
    if idle_match:
        cpu_util = max(0.0, min(100.0, 100.0 - float(idle_match.group(1))))
    else:
        cpu_line = re.search(r"cpu\s+utilization[^\n]*", text_blob, flags=re.IGNORECASE)
        if cpu_line:
            nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*percent", cpu_line.group(0), flags=re.IGNORECASE)]
            if nums:
                # Typical line has user/background/system/interrupt/idle. If idle is present as last, compute 100-idle.
                if len(nums) >= 2:
                    last = nums[-1]
                    cpu_util = max(0.0, min(100.0, 100.0 - last))
                else:
                    cpu_util = max(0.0, min(100.0, nums[0]))

    if cpu_util is None:
        user = re.search(r"\buser\b\s*(?:[:=]|\s)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)", text_blob, flags=re.IGNORECASE)
        background = re.search(r"\bbackground\b\s*(?:[:=]|\s)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)", text_blob, flags=re.IGNORECASE)
        system = re.search(r"\b(?:kernel|system)\b\s*(?:[:=]|\s)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)", text_blob, flags=re.IGNORECASE)
        interrupt = re.search(r"\binterrupt\b\s*(?:[:=]|\s)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)", text_blob, flags=re.IGNORECASE)
        parts = []
        for match in [user, background, system, interrupt]:
            if match:
                parts.append(float(match.group(1)))
        if parts:
            cpu_util = max(0.0, min(100.0, sum(parts)))

    if cpu_util is None:
        generic_cpu = re.search(r"cpu\s*(?:utilization)?\s*(?:[:=]|\s)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)", text_blob, flags=re.IGNORECASE)
        if generic_cpu:
            cpu_util = max(0.0, min(100.0, float(generic_cpu.group(1))))

    mem_match = re.search(r"memory\s+(?:dram\s+)?utilization\s*[:=]?\s*(\d+(?:\.\d+)?)\s*percent", text_blob, flags=re.IGNORECASE)
    if mem_match:
        memory_util = max(0.0, min(100.0, float(mem_match.group(1))))

    temp_match = re.search(r"(?:cpu\s+)?temperature\s*[:=]?\s*(\d+(?:\.\d+)?)", text_blob, flags=re.IGNORECASE)
    if temp_match:
        temp_c = float(temp_match.group(1))

    if cpu_util is None and memory_util is None and temp_c is None:
        return None

    return {
        "cpu_utilization": round(cpu_util, 1) if cpu_util is not None else None,
        "memory_utilization": round(memory_util, 1) if memory_util is not None else None,
        "temperature_c": round(temp_c, 1) if temp_c is not None else None,
        "source": "show chassis routing-engine (cli)",
    }


def _extract_exact_uptime_from_junos_rpc(session) -> str | None:
    """Read exact uptime from Junos RPC (show system uptime equivalent)."""
    try:
        from ncclient.xml_ import to_ele

        rpc = """
        <get-system-uptime-information/>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
    except Exception:
        return None

    # 1) Prefer explicit uptime-like fields when present.
    preferred_tags = {"up-time", "uptime", "time-length", "elapsed-time", "system-uptime"}
    for element in root.iter():
        local = element.tag.split("}")[-1].lower()
        if local in preferred_tags:
            text = (element.text or "").strip()
            if text:
                return text

    # 2) Parse elapsed uptime text embedded in richer strings, e.g.:
    #    "System booted: 2024-11-14 06:23:00 UTC (101w4d 00:52 ago)"
    raw_text = ET.tostring(root, encoding="unicode")
    paren_elapsed = re.search(r"\(([^()]*?\bago)\)", raw_text, flags=re.IGNORECASE)
    if paren_elapsed:
        return paren_elapsed.group(1).strip()

    # 3) Parse shell-like uptime line when present, e.g.:
    #    "7:15AM up 711 days, 52 mins, 1 users, load averages: ..."
    shell_uptime = re.search(
        r"\bup\s+([^,]*?(?:days?|hrs?|hours?|mins?|minutes?)(?:,\s*[^,]+){0,2})",
        raw_text,
        flags=re.IGNORECASE,
    )
    if shell_uptime:
        return shell_uptime.group(1).strip()

    # 4) Last fallback: surface boot time text if nothing elapsed is available.
    for element in root.iter():
        local = element.tag.split("}")[-1].lower()
        if local in {"system-booted-time", "date-time", "time"}:
            candidate = (element.text or "").strip()
            if candidate:
                return candidate
    return None


def _fetch_realtime_device_health_via_netconf(ip: str, username: str, password: str, timeout: float) -> tuple[dict | None, str]:
    try:
        from ncclient import manager
    except Exception:
        return None, "ncclient not installed in backend environment."

    try:
        with manager.connect(
            host=ip,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=int(timeout),
        ) as session:
            health = _extract_realtime_health_from_junos_rpc(session)
            if not health:
                health = _extract_realtime_health_from_junos_cli_output(session)
            health = health or {}
            uptime = _extract_exact_uptime_from_junos_rpc(session)
            if uptime:
                health["uptime"] = uptime

            if not health:
                return None, "NETCONF reachable but realtime health/uptime could not be parsed from device output."
            return health, "Realtime health poll succeeded via NETCONF RPC."
    except Exception as exc:
        return None, f"NETCONF realtime health poll failed: {str(exc)}"


def _enrich_interfaces_from_junos_rpc(session, interfaces: list[DeviceInterface]) -> list[DeviceInterface]:
    """Enrich interface fields from Junos operational RPC output.

    Junos often exposes admin/oper/MAC on get-interface-information RPC trees.
    This pass merges those fields by interface name when available.
    """
    try:
        from ncclient.xml_ import to_ele

        rpc = """
        <get-interface-information>
          <detail/>
        </get-interface-information>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
    except Exception:
        return interfaces

    by_name: dict[str, DeviceInterface] = {item.name: item for item in interfaces}

    for element in root.iter():
        local = element.tag.split("}")[-1].lower()
        if local not in {"physical-interface", "logical-interface", "interface"}:
            continue

        name = _first_child_text(element, {"name", "if-name"})
        if not name:
            continue

        admin = _first_child_text(element, {"admin-status", "admin-state"})
        oper = _first_child_text(element, {"oper-status", "oper-state"})
        description = _first_child_text(element, {"description", "if-description"})
        mac = _first_child_text(element, {"current-physical-address", "phys-address", "mac-address"})
        vlan = _first_child_text(element, {"vlan-id", "vlan-tag", "vlan-name"})

        current = by_name.get(name)
        if not current:
            by_name[name] = DeviceInterface(
                name=name,
                description=description,
                admin_status=admin or "unknown",
                oper_status=oper or "unknown",
                vlan=vlan,
                mac=mac,
            )
            continue

        if (not current.description) and description:
            current.description = description
        if (current.admin_status in {"", "unknown"}) and admin:
            current.admin_status = admin
        if (current.oper_status in {"", "unknown"}) and oper:
            current.oper_status = oper
        if (not current.vlan) and vlan:
            current.vlan = vlan
        if (not current.mac) and mac:
            current.mac = mac

    return sorted(by_name.values(), key=lambda item: item.name)


def _extract_interfaces_from_junos_rpc(session) -> list[DeviceInterface]:
    """Return interface inventory directly from Junos RPC output when available."""
    try:
        from ncclient.xml_ import to_ele

        rpc = """
        <get-interface-information>
          <detail/>
        </get-interface-information>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
    except Exception:
        return []

    out: dict[str, DeviceInterface] = {}
    for element in root.iter():
        local = element.tag.split("}")[-1].lower()
        if local not in {"physical-interface", "logical-interface"}:
            continue

        name = _first_child_text(element, {"name", "if-name"})
        if not name:
            continue
        # Skip noisy system pseudo names seen in some payloads.
        if name.startswith("."):
            continue

        admin = _first_child_text(element, {"admin-status", "admin-state"}) or "unknown"
        oper = _first_child_text(element, {"oper-status", "oper-state"}) or "unknown"
        description = _first_child_text(element, {"description", "if-description"})
        mac = _first_child_text(element, {"current-physical-address", "phys-address", "mac-address"})
        vlan = _first_child_text(element, {"vlan-id", "vlan-tag", "vlan-name"})

        out[name] = DeviceInterface(
            name=name,
            description=description,
            admin_status=admin,
            oper_status=oper,
            vlan=vlan,
            mac=mac,
        )

    return sorted(out.values(), key=lambda item: item.name)


def _fetch_live_interfaces_via_netconf(ip: str, username: str, password: str, timeout: float) -> tuple[list[DeviceInterface] | None, str]:
    try:
        from ncclient import manager
    except Exception:
        return None, "ncclient not installed in backend environment."

    try:
        with manager.connect(
            host=ip,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=int(timeout),
        ) as session:
            caps = list(session.server_capabilities)
            vendor = _extract_vendor_from_netconf_caps(caps)
            raw_reply = session.get().data_xml
            root = ET.fromstring(raw_reply)
            interfaces = _extract_live_interfaces(root)
            if vendor == "Juniper":
                junos_interfaces = _extract_interfaces_from_junos_rpc(session)
                if junos_interfaces:
                    interfaces = junos_interfaces
                elif interfaces:
                    interfaces = _enrich_interfaces_from_junos_rpc(session, interfaces)
            if interfaces:
                return interfaces, f"Live interface poll succeeded ({len(interfaces)} interfaces)."
            return None, "NETCONF reachable but no interface list was returned by device YANG data."
    except Exception as exc:
        return None, f"NETCONF interface poll failed: {str(exc)}"


def _extract_lldp_neighbors_from_junos_rpc(session) -> list[LldpNeighbor]:
    try:
        from ncclient.xml_ import to_ele

        rpc = """
        <get-lldp-neighbors-information>
          <detail/>
        </get-lldp-neighbors-information>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
    except Exception:
        return []

    neighbors: list[LldpNeighbor] = []
    seen: set[tuple[str, str, str, str]] = set()

    for element in root.iter():
        local = element.tag.split("}")[-1].lower()
        if local not in {"lldp-neighbor-information", "neighbor", "lldp-neighbor"}:
            continue

        local_if = _first_child_text(element, {"lldp-local-port-id", "local-interface", "interface-name", "local-port-id"})
        remote_host = _first_child_text(element, {"lldp-remote-system-name", "remote-system-name", "system-name", "neighbor-name"})
        remote_if = _first_child_text(element, {"lldp-remote-port-id", "remote-port-id", "port-id", "neighbor-port-id"})
        remote_ip = _first_child_text(element, {"lldp-remote-management-address", "management-address", "remote-management-address"})

        if not (local_if or remote_host or remote_if or remote_ip):
            continue

        record = LldpNeighbor(
            local_interface=local_if or "unknown",
            neighbor_hostname=remote_host or "unknown-neighbor",
            neighbor_interface=remote_if,
            neighbor_mgmt_ip=remote_ip,
        )
        key = (record.local_interface, record.neighbor_hostname, record.neighbor_interface, record.neighbor_mgmt_ip)
        if key in seen:
            continue
        seen.add(key)
        neighbors.append(record)

    return neighbors


def _mock_lldp_neighbors_for_device(item: DeviceRecord, local_interface_candidates: list[str] | None = None) -> list[LldpNeighbor]:
    peers = [entry for entry in inventory_store if entry.mgmt_ip != item.mgmt_ip and entry.hostname.strip()][:4]
    out: list[LldpNeighbor] = []
    interfaces = [name for name in (local_interface_candidates or []) if str(name).strip()]
    for idx, peer in enumerate(peers, start=1):
        local_if = interfaces[idx - 1] if idx - 1 < len(interfaces) else f"xe-0/0/{idx}"
        out.append(
            LldpNeighbor(
                local_interface=local_if,
                neighbor_hostname=peer.hostname,
                neighbor_interface=f"xe-0/0/{idx}",
                neighbor_mgmt_ip=peer.mgmt_ip,
            )
        )
    return out


def _fetch_live_lldp_neighbors_via_netconf(ip: str, username: str, password: str, timeout: float) -> tuple[list[LldpNeighbor] | None, str]:
    try:
        from ncclient import manager
    except Exception:
        return None, "ncclient not installed in backend environment."

    try:
        with manager.connect(
            host=ip,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=int(timeout),
        ) as session:
            caps = list(session.server_capabilities)
            vendor = _extract_vendor_from_netconf_caps(caps)
            if vendor != "Juniper":
                return None, f"LLDP NETCONF parser currently supports Juniper best-effort; detected vendor {vendor}."

            neighbors = _extract_lldp_neighbors_from_junos_rpc(session)
            if neighbors:
                return neighbors, f"Live LLDP topology poll succeeded ({len(neighbors)} neighbors)."
            return None, "NETCONF reachable but no LLDP neighbors were returned by device RPC output."
    except Exception as exc:
        return None, f"NETCONF LLDP poll failed: {str(exc)}"


@app.get("/api/inventory/device/{ip}/interfaces", response_model=DeviceInterfacesResponse)
def get_device_interfaces(ip: str, timeout_seconds: float = Query(default=8.0, ge=2.0, le=30.0)) -> DeviceInterfacesResponse:
    item = next((entry for entry in inventory_store if entry.mgmt_ip == ip), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Device {ip} not found")

    username, password, _ = _resolve_device_credentials(
        ip=item.mgmt_ip,
        request_username="",
        request_password="",
        request_secret="",
    )

    interfaces: list[DeviceInterface]
    msg = ""
    health_payload: dict | None = None

    if username and password:
        live_interfaces, reason = _fetch_live_interfaces_via_netconf(
            ip=item.mgmt_ip,
            username=username,
            password=password,
            timeout=timeout_seconds,
        )

        # Retry once for transient NETCONF latency/timeouts.
        if (not live_interfaces) and ("timed out" in reason.lower() or "timeout" in reason.lower()):
            retry_timeout = min(timeout_seconds + 4.0, 30.0)
            retry_live_interfaces, retry_reason = _fetch_live_interfaces_via_netconf(
                ip=item.mgmt_ip,
                username=username,
                password=password,
                timeout=retry_timeout,
            )
            if retry_live_interfaces:
                live_interfaces = retry_live_interfaces
                reason = f"Live interface poll succeeded on retry ({len(live_interfaces)} interfaces)."
            else:
                reason = f"{reason} Retry failed: {retry_reason}"

        health_payload, health_reason = _fetch_realtime_device_health_via_netconf(
            ip=item.mgmt_ip,
            username=username,
            password=password,
            timeout=timeout_seconds,
        )

        if live_interfaces:
            interfaces = live_interfaces
            msg = reason
        else:
            interfaces = _mock_interfaces_for_device(item)
            msg = f"{reason} Fallback template used."
        health_msg = health_reason or ""
    else:
        interfaces = _mock_interfaces_for_device(item)
        msg = "Missing NETCONF credentials; fallback interface template used."
        health_msg = "Health poll skipped: missing NETCONF credentials."

    return DeviceInterfacesResponse(
        mgmt_ip=item.mgmt_ip,
        hostname=item.hostname,
        polled_at=datetime.utcnow().isoformat() + "Z",
        items=interfaces,
        health=health_payload,
        health_message=health_msg,
        message=msg,
    )


@app.get("/api/inventory/device/{ip}/topology/lldp", response_model=DeviceLldpTopologyResponse)
def get_device_lldp_topology(ip: str, timeout_seconds: float = Query(default=8.0, ge=2.0, le=30.0)) -> DeviceLldpTopologyResponse:
    item = next((entry for entry in inventory_store if entry.mgmt_ip == ip), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Device {ip} not found")

    username, password, _ = _resolve_device_credentials(
        ip=item.mgmt_ip,
        request_username="",
        request_password="",
        request_secret="",
    )

    neighbors: list[LldpNeighbor]
    msg = ""

    if username and password:
        live_neighbors, reason = _fetch_live_lldp_neighbors_via_netconf(
            ip=item.mgmt_ip,
            username=username,
            password=password,
            timeout=timeout_seconds,
        )
        if live_neighbors is not None:
            neighbors = live_neighbors
            msg = reason
        else:
            interface_candidates: list[str] = []
            live_interfaces, _ = _fetch_live_interfaces_via_netconf(
                ip=item.mgmt_ip,
                username=username,
                password=password,
                timeout=timeout_seconds,
            )
            if live_interfaces:
                interface_candidates = [itf.name for itf in live_interfaces if itf.name][:8]

            neighbors = _mock_lldp_neighbors_for_device(item, interface_candidates)
            msg = f"{reason} Fallback LLDP topology template used."
    else:
        neighbors = _mock_lldp_neighbors_for_device(item)
        msg = "Missing NETCONF credentials; fallback LLDP topology template used."

    return DeviceLldpTopologyResponse(
        mgmt_ip=item.mgmt_ip,
        hostname=item.hostname,
        polled_at=datetime.utcnow().isoformat() + "Z",
        items=neighbors,
        message=msg,
    )


@app.post("/api/inventory/range-add", response_model=ActionResponse)
def add_range(payload: RangeAddRequest) -> ActionResponse:
    _validate_test_scope(payload.subnet, payload.host_start, payload.host_end)
    base = _subnet_base(payload.subnet)

    existing_ips = {item.mgmt_ip for item in inventory_store}
    added = 0
    skipped = 0

    for host in range(payload.host_start, payload.host_end + 1):
        ip = f"{base}.{host}"
        if ip in existing_ips:
            skipped += 1
            continue
        existing_ips.add(ip)
        inventory_store.append(
            DeviceRecord(
                hostname="",
                mgmt_ip=ip,
                vendor="",
                model="",
                os_version="",
                serial_number="",
                routing_protocols="",
                mgmt_vlan="",
                routing_domain="",
                snmp_profile="",
                ntp_profile="",
                security_profile="",
                netconf="Pending",
                site="",
                role="",
                source="Manual",
                status="Pending Discovery",
                subnet=payload.subnet,
                fetch_reason="Awaiting real-time SSH fetch.",
            )
        )
        added += 1

    _save_inventory(inventory_store)
    return ActionResponse(message=f"Added {added} IP(s); skipped {skipped} duplicate(s).")


@app.delete("/api/inventory/ip/{ip}", response_model=ActionResponse)
def delete_ip(ip: str) -> ActionResponse:
    original = len(inventory_store)
    inventory_store[:] = [item for item in inventory_store if item.mgmt_ip != ip]
    if len(inventory_store) == original:
        raise HTTPException(status_code=404, detail=f"IP {ip} not found")
    _save_inventory(inventory_store)
    return ActionResponse(message=f"Deleted {ip}.")


@app.delete("/api/inventory/subnet/{subnet}", response_model=ActionResponse)
def delete_subnet(subnet: str) -> ActionResponse:
    normalized = subnet.replace("~", "/")
    original = len(inventory_store)
    inventory_store[:] = [item for item in inventory_store if item.subnet != normalized]
    removed = original - len(inventory_store)
    _save_inventory(inventory_store)
    return ActionResponse(message=f"Deleted {removed} IP(s) under {normalized}.")


def _run_metadata_discovery() -> ActionResponse:
    overrides = _load_metadata_overrides()
    discovered = 0
    failed = 0
    failed_ips: list[str] = []
    for item in inventory_store:
        metadata = overrides.get(item.mgmt_ip)
        if metadata and _apply_metadata(item, metadata):
            item.netconf = "Disabled"
            item.source = "Imported"
            item.status = "Discovered"
            item.fetch_reason = "Metadata imported from overrides source (not live-polled)."
            discovered += 1
            continue

        item.netconf = "Disabled"
        item.source = "Manual"
        item.status = "Fetch Failed"
        item.fetch_reason = "No complete metadata found for this IP in overrides source."
        failed += 1
        failed_ips.append(item.mgmt_ip)

    _save_inventory(inventory_store)
    return ActionResponse(
        message=(
            f"Metadata fetch complete: {discovered} discovered, "
            f"{failed} fetch failed. Missing data for: {', '.join(failed_ips) if failed_ips else 'none'}."
        )
    )


def _extract_vendor_from_netconf_caps(caps: list[str]) -> str:
    joined = " ".join(caps).lower()
    if "juniper" in joined or "junos" in joined:
        return "Juniper"
    if "cisco" in joined:
        return "Cisco"
    if "nokia" in joined or "sr" in joined or "sros" in joined:
        return "Nokia"
    return "Unknown"


def _infer_model_fallback(vendor: str, hostname: str, caps: list[str]) -> str:
    host = (hostname or "").lower()
    joined_caps = " ".join(caps).lower()

    if vendor == "Juniper":
        if "mx960" in host:
            return "mx960"
        if "mx480" in host:
            return "mx480"
        if "mx" in host:
            return "mx-series"

    if vendor == "Nokia":
        if "7750" in joined_caps or "7750" in host:
            return "7750 SR"
        if "7950" in joined_caps or "7950" in host:
            return "7950 SR"
        return "SR-series"

    if vendor == "Cisco":
        if "ncs" in host:
            return "NCS-series"
        if "asr" in host:
            return "ASR-series"
        return "Cisco Router"

    return "Unknown Model"


def _find_first_text_by_local_name(root: ET.Element, local_names: list[str]) -> str:
    wanted = {name.lower() for name in local_names}
    for element in root.iter():
        local_name = element.tag.split("}")[-1].lower()
        if local_name in wanted:
            value = (element.text or "").strip()
            if value:
                return value
    return ""


def _is_meaningful(value: str) -> bool:
    text = (value or "").strip().lower()
    return bool(text) and text not in {"unknown", "unknown model", "n/a", "na", "none", "-"}


def _extract_from_subtree(session, subtree_xml: str, keys: list[str]) -> str:
    try:
        reply = session.get(filter=("subtree", subtree_xml)).data_xml
        root = ET.fromstring(reply)
        return _find_first_text_by_local_name(root, keys)
    except Exception:
        return ""


def _extract_from_rpc(session, rpc_xml: str, keys: list[str]) -> str:
    try:
        from ncclient.xml_ import to_ele

        reply = session.dispatch(to_ele(rpc_xml))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
        return _find_first_text_by_local_name(root, keys)
    except Exception:
        return ""


def _extract_model_vendor_rpc(session, vendor: str) -> str:
    # Vendor RPC fallback is best-effort and intentionally silent on unsupported RPCs.
    if vendor == "Juniper":
        return _extract_from_rpc(
            session,
            """
            <get-software-information/>
            """,
            ["product-model", "model", "chassis-model"],
        )

    if vendor == "Cisco":
        return _extract_from_rpc(
            session,
            """
            <get-inventory xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"/>
            """,
            ["model-name", "model", "part-number", "product-name"],
        )

    if vendor == "Nokia":
        return _extract_from_rpc(
            session,
            """
            <get-chassis-information/>
            """,
            ["model", "chassis-model", "product-model", "part-number"],
        )

    return ""


def _extract_junos_configured_protocols(session) -> set[str]:
    protocols: set[str] = set()
    try:
        from ncclient.xml_ import to_ele

        rpc = """
                <get-configuration xmlns="http://xml.juniper.net/xnm/1.1/xnm" format="set">
                    <configuration>
                        <protocols/>
                    </configuration>
        </get-configuration>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
        for element in root.iter():
            if element.tag.split("}")[-1].lower() not in {"configuration-set", "output", "data"}:
                continue
            text = (element.text or "")
            for line in text.splitlines():
                line = line.strip().lower()
                if not line.startswith("set protocols "):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    proto = parts[2]
                    canon = _canonical_routing_protocol(proto)
                    if canon:
                        protocols.add(canon)
    except Exception:
        return set()
    return protocols


def _extract_junos_set_lines(session, subtree_xml: str) -> list[str]:
    try:
        from ncclient.xml_ import to_ele

        rpc = f"""
        <get-configuration xmlns=\"http://xml.juniper.net/xnm/1.1/xnm\" format=\"set\">
            <configuration>
                {subtree_xml}
            </configuration>
        </get-configuration>
        """
        reply = session.dispatch(to_ele(rpc))
        raw = getattr(reply, "xml", "") or str(reply)
        root = ET.fromstring(raw)
        lines: list[str] = []
        for element in root.iter():
            local = element.tag.split("}")[-1].lower()
            if local not in {"configuration-set", "output", "data"}:
                continue
            text = (element.text or "").strip()
            if text:
                lines.extend([line.strip() for line in text.splitlines() if line.strip()])
        return lines
    except Exception:
        return []


def _extract_config_profiles(session, vendor: str) -> dict[str, str]:
    profiles = {
        "mgmt_vlan": "",
        "routing_domain": "",
        "snmp_profile": "",
        "ntp_profile": "",
        "security_profile": "",
    }

    if vendor != "Juniper":
        return profiles

    lines: list[str] = []
    lines.extend(_extract_junos_set_lines(session, "<vlans/>"))
    lines.extend(_extract_junos_set_lines(session, "<routing-instances/>"))
    lines.extend(_extract_junos_set_lines(session, "<snmp/>"))
    lines.extend(_extract_junos_set_lines(session, "<system><ntp/></system>"))
    lines.extend(_extract_junos_set_lines(session, "<security/>"))
    lines.extend(_extract_junos_set_lines(session, "<firewall/>"))

    if not lines:
        return profiles

    vlan_hits: list[str] = []
    for line in lines:
        match = re.match(r"^set vlans (\S+) vlan-id (\d+)$", line, flags=re.IGNORECASE)
        if match:
            vlan_hits.append(f"{match.group(1)}({match.group(2)})")
    if vlan_hits:
        profiles["mgmt_vlan"] = ", ".join(sorted(set(vlan_hits))[:4])

    routing_instances: list[str] = []
    for line in lines:
        match = re.match(r"^set routing-instances (\S+) ", line, flags=re.IGNORECASE)
        if match:
            name = match.group(1)
            if name.lower() not in {"master", "default"}:
                routing_instances.append(name)
    if routing_instances:
        profiles["routing_domain"] = ", ".join(sorted(set(routing_instances))[:4])
    else:
        profiles["routing_domain"] = "default"

    snmp_communities: list[str] = []
    snmp_v3_groups: list[str] = []
    has_snmp = False
    for line in lines:
        if line.lower().startswith("set snmp "):
            has_snmp = True
        match_comm = re.match(r"^set snmp community (\S+) ", line, flags=re.IGNORECASE)
        if match_comm:
            snmp_communities.append(match_comm.group(1))
        match_v3 = re.match(r"^set snmp v3 usm local-engine user (\S+) ", line, flags=re.IGNORECASE)
        if match_v3:
            snmp_v3_groups.append(match_v3.group(1))
    if snmp_communities:
        profiles["snmp_profile"] = "community:" + ",".join(sorted(set(snmp_communities))[:3])
    elif snmp_v3_groups:
        profiles["snmp_profile"] = "v3-user:" + ",".join(sorted(set(snmp_v3_groups))[:3])
    elif has_snmp:
        profiles["snmp_profile"] = "configured"

    ntp_servers: list[str] = []
    for line in lines:
        match = re.match(r"^set system ntp server (\S+)", line, flags=re.IGNORECASE)
        if match:
            ntp_servers.append(match.group(1))
    if ntp_servers:
        profiles["ntp_profile"] = ", ".join(sorted(set(ntp_servers))[:4])

    security_bits: list[str] = []
    has_security = False
    for line in lines:
        lower = line.lower()
        if lower.startswith("set security "):
            has_security = True
            if "policies" in lower:
                security_bits.append("policies")
            if "zones" in lower:
                security_bits.append("zones")
            if "screen" in lower:
                security_bits.append("screen")
        if lower.startswith("set firewall family ") and " filter " in lower:
            has_security = True
            security_bits.append("filters")
    if security_bits:
        profiles["security_profile"] = ", ".join(sorted(set(security_bits)))
    elif has_security:
        profiles["security_profile"] = "configured"

    return profiles


def _canonical_routing_protocol(name: str) -> str:
    value = (name or "").strip().lower()
    mapping = {
        "bgp": "BGP",
        "ospf": "OSPF",
        "ospfv2": "OSPF",
        "ospf3": "OSPFv3",
        "isis": "IS-IS",
        "rip": "RIP",
        "static": "STATIC",
    }
    return mapping.get(value, "")


def _extract_protocols_from_root(root: ET.Element) -> set[str]:
    found: set[str] = set()

    # Strict match: explicit protocol identifiers and exact protocol tag names only.
    for element in root.iter():
        local_name = element.tag.split("}")[-1].lower()
        canon_from_tag = _canonical_routing_protocol(local_name)
        if canon_from_tag:
            found.add(canon_from_tag)

        if local_name in {"identifier", "protocol-name", "protocol"}:
            text = (element.text or "").strip().lower()
            token = text.split(":")[-1] if ":" in text else text
            canon_from_text = _canonical_routing_protocol(token)
            if canon_from_text:
                found.add(canon_from_text)

    return found


def _detect_routing_protocols(session, vendor: str) -> str:
    protocols: set[str] = set()

    if vendor == "Juniper":
        protocols.update(_extract_junos_configured_protocols(session))

    # Vendor/config-oriented query for protocol containers.
    junos_config_filter = """
    <filter>
      <configuration xmlns="http://xml.juniper.net/xnm/1.1/xnm">
        <protocols/>
      </configuration>
    </filter>
    """
    openconfig_protocols_filter = """
    <filter>
      <network-instances xmlns="http://openconfig.net/yang/network-instance">
        <network-instance>
          <protocols/>
        </network-instance>
      </network-instances>
    </filter>
    """

    # Generic config trees (fallback for non-Juniper or if Junos RPC yields nothing).
    try:
        junos_xml = session.get_config(source="running", filter=("subtree", junos_config_filter)).data_xml
        junos_root = ET.fromstring(junos_xml)
        for element in junos_root.iter():
            if element.tag.split("}")[-1].lower() == "protocols":
                for child in list(element):
                    name = child.tag.split("}")[-1]
                    canon = _canonical_routing_protocol(name)
                    if canon:
                        protocols.add(canon)
    except Exception:
        pass

    # OpenConfig: parse protocol identifiers and names.
    for source, flt in (("running", openconfig_protocols_filter),):
        try:
            cfg_xml = session.get_config(source=source, filter=("subtree", flt)).data_xml
            cfg_root = ET.fromstring(cfg_xml)
            protocols.update(_extract_protocols_from_root(cfg_root))
        except Exception:
            continue

    preferred_order = ["BGP", "OSPF", "OSPFv3", "IS-IS", "RIP", "STATIC"]
    ordered = [name for name in preferred_order if name in protocols]
    if not ordered:
        return ""
    return ", ".join(ordered)


def _fetch_live_metadata_via_netconf_yang(ip: str, username: str, password: str, timeout: float) -> tuple[dict[str, str] | None, str]:
    try:
        from ncclient import manager
    except Exception:
        return None, "ncclient not installed in backend environment."

    try:
        with manager.connect(
            host=ip,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=int(timeout),
        ) as session:
            caps = list(session.server_capabilities)
            vendor = _extract_vendor_from_netconf_caps(caps)

            hostname = ""
            os_version = ""
            model = ""
            serial = ""
            routing_protocols = ""
            mgmt_vlan = ""
            routing_domain = ""
            snmp_profile = ""
            ntp_profile = ""
            security_profile = ""
            raw_root: ET.Element | None = None

            system_filter = """
            <filter>
              <system xmlns=\"urn:ietf:params:xml:ns:yang:ietf-system\">
                <state>
                  <hostname/>
                </state>
              </system>
            </filter>
            """

            try:
                system_reply = session.get(filter=("subtree", system_filter)).data_xml
                system_root = ET.fromstring(system_reply)
                hostname = _find_first_text_by_local_name(system_root, ["hostname", "host-name"])
            except Exception:
                hostname = ""

            # Best-effort fetch from common model tags in operational data.
            try:
                raw_reply = session.get().data_xml
                raw_root = ET.fromstring(raw_reply)
                if not hostname:
                    hostname = _find_first_text_by_local_name(raw_root, ["hostname", "host-name"])
                os_version = _find_first_text_by_local_name(raw_root, ["os-version", "software-version", "version"])
                model = _find_first_text_by_local_name(raw_root, ["model", "hardware-model", "product-name", "chassis-model"])
                serial = _find_first_text_by_local_name(raw_root, ["serial-number", "chassis-serial-number", "serial"])
            except Exception:
                pass

            routing_protocols = _detect_routing_protocols(session=session, vendor=vendor)
            config_profiles = _extract_config_profiles(session=session, vendor=vendor)
            mgmt_vlan = config_profiles.get("mgmt_vlan", "")
            routing_domain = config_profiles.get("routing_domain", "")
            snmp_profile = config_profiles.get("snmp_profile", "")
            ntp_profile = config_profiles.get("ntp_profile", "")
            security_profile = config_profiles.get("security_profile", "")

            # Targeted YANG subtree queries for common platform/inventory leaves.
            if not _is_meaningful(model):
                model = _extract_from_subtree(
                    session,
                    """
                    <filter>
                        <hardware xmlns="urn:ietf:params:xml:ns:yang:ietf-hardware">
                            <component>
                                <model-name/>
                            </component>
                        </hardware>
                    </filter>
                    """,
                    ["model-name", "model", "part-number", "product-name"],
                )
            if not _is_meaningful(model):
                model = _extract_from_subtree(
                    session,
                    """
                    <filter>
                        <components xmlns="http://openconfig.net/yang/platform">
                            <component>
                                <state>
                                    <description/>
                                    <part-no/>
                                </state>
                            </component>
                        </components>
                    </filter>
                    """,
                    ["part-no", "description", "part-number", "product-name"],
                )

            if not _is_meaningful(os_version):
                os_version = _extract_from_subtree(
                    session,
                    """
                    <filter>
                        <system xmlns="http://openconfig.net/yang/system">
                            <state>
                                <software-version/>
                            </state>
                        </system>
                    </filter>
                    """,
                    ["software-version", "os-version", "version"],
                )

            if not _is_meaningful(serial):
                serial = _extract_from_subtree(
                    session,
                    """
                    <filter>
                        <hardware xmlns="urn:ietf:params:xml:ns:yang:ietf-hardware">
                            <component>
                                <serial-num/>
                            </component>
                        </hardware>
                    </filter>
                    """,
                    ["serial-num", "serial-number", "chassis-serial-number", "serial"],
                )

            # Some platforms expose model in vendor operational RPCs rather than common YANG trees.
            if not _is_meaningful(model):
                rpc_model = _extract_model_vendor_rpc(session, vendor)
                if _is_meaningful(rpc_model):
                    model = rpc_model

            if not model:
                model = _infer_model_fallback(vendor=vendor, hostname=hostname, caps=caps)

            if not hostname:
                # Some vendors do not expose hostname in common YANG leaves.
                # Keep discovery successful with an IP fallback label so inventory is not dropped.
                hostname = ip

            return {
                "hostname": hostname,
                "vendor": vendor,
                "model": model,
                "os_version": os_version,
                "serial_number": serial,
                "routing_protocols": routing_protocols,
                "mgmt_vlan": mgmt_vlan,
                "routing_domain": routing_domain,
                "snmp_profile": snmp_profile,
                "ntp_profile": ntp_profile,
                "security_profile": security_profile,
            }, "live"
    except Exception as exc:
        return None, f"NETCONF+YANG fetch failed: {str(exc)}"


def _fetch_live_metadata_via_ssh_netmiko(ip: str, username: str, password: str, timeout: float) -> tuple[dict[str, str] | None, str]:
    """Best-effort SSH fallback discovery for non-NETCONF devices.

    This targets common vendors in the environment (Juniper/Cisco/Nokia/Alcatel)
    using Netmiko autodetect and lightweight `show version` parsing.
    """
    try:
        from netmiko import ConnectHandler, SSHDetect
        from netmiko import NetMikoAuthenticationException, NetmikoTimeoutException
    except Exception:
        return None, "Netmiko not installed in backend environment."

    vendor_map = {
        "juniper_junos": "Juniper",
        "cisco_ios": "Cisco",
        "cisco_xe": "Cisco",
        "cisco_xr": "Cisco",
        "nokia_sros": "Nokia",
        "alcatel_aos": "Alcatel",
    }

    def _parse_show_version(raw: str, prompt_host: str, device_type: str) -> tuple[str, str, str]:
        text = raw or ""
        model = ""
        os_version = ""
        serial = ""

        device_type_l = (device_type or "").lower()

        # Hostname from prompt first. Handle common forms like:
        # - device#
        # - device>
        # - user@device#
        prompt_text = (prompt_host or "").strip()
        hostname = ip
        if prompt_text:
            if "@" in prompt_text:
                # For user@device#, keep the portion after '@'.
                prompt_text = prompt_text.split("@", 1)[1]
            ph = re.search(r"^([\w\-.]+)[>#]", prompt_text)
            hostname = ph.group(1).strip() if ph else prompt_text.strip()

        # Juniper-style version (from reference parser).
        if "junos" in device_type_l or "juniper" in device_type_l:
            vv = re.search(r"Junos:\s*([\S]+)", text, re.I)
            if vv:
                os_version = vv.group(1).strip()

        # Nokia/SR OS patterns (from reference parser).
        if (not os_version) and ("nokia" in device_type_l or "sros" in device_type_l or "alcatel" in device_type_l):
            vv = re.search(r"System\s*Version\s*[:\-]?\s*([\S ]+)", text, re.I)
            if not vv:
                vv = re.search(r"Version\s*[:\-]?\s*([0-9A-Za-z\.\-_/]+)", text, re.I)
            if vv:
                os_version = vv.group(1).strip()

        # Cisco generic version pattern (from reference parser).
        if not os_version:
            vv = re.search(r"Version\s+([0-9A-Za-z\.\-_/]+)", text, re.I)
            if vv:
                os_version = vv.group(1).strip()

        # Legacy version fallbacks.
        if not os_version:
            version_patterns = [
                r"\bVersion\s*[: ]\s*([^\n,]+)",
                r"\bJUNOS\s+([^\n]+)",
                r"\bSoftware\s+Version\s*[: ]\s*([^\n,]+)",
                r"\bSR\s+OS\s+([^\n,]+)",
            ]
            for pattern in version_patterns:
                m = re.search(pattern, text, re.I)
                if m:
                    os_version = m.group(1).strip()
                    break

        # Cisco model patterns (from reference parser).
        model_patterns = [
            r"Model number\s*[:\-]?\s*(\S+)",
            r"PID\s*[:\-]?\s*(\S+)",
            r"cisco\s+([A-Za-z0-9\-_]+)\s+.*Software",
            r"^Cisco\s+(.+?)\s+\(",
            r"\bModel\s*:\s*([^\n]+)",
            r"\b[Hh]ardware\s*:\s*([^\n,]+)",
            r"\b[Cc]hassis\s*:\s*([^\n]+)",
            r"\b[cC]isco\s+([^\s,]+)",
            r"\bJUNOS\s+([A-Za-z0-9\-_/\.]+)",
        ]
        for pattern in model_patterns:
            m = re.search(pattern, text, re.I | re.M)
            if m:
                model = m.group(1).strip()
                break

        # Nokia model pattern.
        if (not model) and ("nokia" in device_type_l or "sros" in device_type_l or "alcatel" in device_type_l):
            mv = re.search(r"System\s*Type\s*[:\-]?\s*(\S+)", text, re.I) or re.search(r"Type\s*[:\-]?\s*(\S+)", text, re.I)
            if mv:
                model = f"nokia {mv.group(1).strip()}"

        model_patterns = [
            r"\bSerial(?:\s+[Nn]umber)?\s*[:#]?\s*([^\n,]+)",
            r"\bProcessor\s+board\s+ID\s+([^\n,]+)",
            r"\bSystem\s+serial\s+number\s*[: ]\s*([^\n,]+)",
        ]
        for pattern in model_patterns:
            m = re.search(pattern, text, re.I)
            if m:
                serial = m.group(1).strip()
                break

        return hostname or ip, model, os_version, serial

    # Step 1: autodetect best device type.
    detected_type = ""
    try:
        detect_params = {
            "device_type": "autodetect",
            "host": ip,
            "username": username,
            "password": password,
            "timeout": int(timeout),
            "conn_timeout": int(timeout),
            "auth_timeout": int(timeout),
            "banner_timeout": int(timeout),
            "fast_cli": False,
        }
        detected_type = SSHDetect(**detect_params).autodetect() or ""
    except Exception:
        detected_type = ""

    candidate_types = [detected_type] if detected_type else []
    for fallback in ["juniper_junos", "cisco_ios", "nokia_sros", "alcatel_aos"]:
        if fallback not in candidate_types:
            candidate_types.append(fallback)

    last_error = ""
    for device_type in candidate_types:
        if not device_type:
            continue
        try:
            params = {
                "device_type": device_type,
                "host": ip,
                "username": username,
                "password": password,
                "timeout": int(timeout),
                "conn_timeout": int(timeout),
                "auth_timeout": int(timeout),
                "banner_timeout": int(timeout),
                "fast_cli": False,
            }
            with ConnectHandler(**params) as conn:
                prompt = conn.find_prompt() or ip
                prompt_host = re.sub(r"[>#\$].*$", "", prompt).strip() or ip
                command = "show version"
                if device_type == "juniper_junos":
                    command = "show version | no-more"
                raw = conn.send_command(command, read_timeout=max(15, int(timeout) * 2))
                hostname, model, os_version, serial = _parse_show_version(raw, prompt_host, device_type)
                vendor = vendor_map.get(device_type, "Unknown")
                return {
                    "hostname": hostname or ip,
                    "vendor": vendor,
                    "model": model or _infer_model_fallback(vendor=vendor, hostname=hostname, caps=[]),
                    "os_version": os_version,
                    "serial_number": serial,
                    "routing_protocols": "",
                    "mgmt_vlan": "",
                    "routing_domain": "",
                    "snmp_profile": "",
                    "ntp_profile": "",
                    "security_profile": "",
                }, f"SSH discovery succeeded via Netmiko ({device_type})."
        except (NetmikoTimeoutException, NetMikoAuthenticationException) as exc:
            last_error = str(exc)
            continue
        except Exception as exc:
            last_error = str(exc)
            continue

    # Telnet fallback when SSH is unavailable/unsupported on the target.
    telnet_candidates = ["cisco_ios_telnet", "cisco_xe_telnet", "nokia_sros_telnet"]
    for device_type in telnet_candidates:
        try:
            params = {
                "device_type": device_type,
                "host": ip,
                "username": username,
                "password": password,
                "timeout": int(timeout),
                "conn_timeout": int(timeout),
                "auth_timeout": int(timeout),
                "banner_timeout": int(timeout),
                "fast_cli": False,
            }
            with ConnectHandler(**params) as conn:
                prompt = conn.find_prompt() or ip
                prompt_host = re.sub(r"[>#\$].*$", "", prompt).strip() or ip
                command = "show version"
                if "nokia" in device_type:
                    command = "show system information"
                raw = conn.send_command(command, read_timeout=max(15, int(timeout) * 2))
                hostname, model, os_version, serial = _parse_show_version(raw, prompt_host, device_type)
                vendor = "Cisco" if "cisco" in device_type else "Nokia"
                return {
                    "hostname": hostname or ip,
                    "vendor": vendor,
                    "model": model or _infer_model_fallback(vendor=vendor, hostname=hostname, caps=[]),
                    "os_version": os_version,
                    "serial_number": serial,
                    "routing_protocols": "",
                    "mgmt_vlan": "",
                    "routing_domain": "",
                    "snmp_profile": "",
                    "ntp_profile": "",
                    "security_profile": "",
                }, f"Discovery succeeded via Telnet ({device_type})."
        except Exception as exc:
            last_error = str(exc)
            continue

    return None, f"SSH/Telnet discovery failed: {last_error or 'unable to detect device type or run show version'}"


def _find_device_or_404(ip: str) -> DeviceRecord:
    item = next((entry for entry in inventory_store if entry.mgmt_ip == ip), None)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Device {ip} not found in inventory.")
    return item


def _append_config_history(item: DeviceRecord, action: str, message: str) -> None:
    import uuid

    config_history_store.append(
        {
            "event_id": str(uuid.uuid4()),
            "mgmt_ip": item.mgmt_ip,
            "hostname": item.hostname or item.mgmt_ip,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "action": action,
            "message": message,
        }
    )
    _save_json_list(CONFIG_HISTORY_FILE, config_history_store)


def _build_fallback_config(item: DeviceRecord) -> str:
    interfaces = _mock_interfaces_for_device(item)
    lines: list[str] = [
        f"! Generated fallback config for {item.hostname or item.mgmt_ip}",
        f"hostname {item.hostname or 'device'}",
        "!",
    ]
    for itf in interfaces:
        lines.append(f"interface {itf.name}")
        lines.append(f" description {itf.description or '-'}")
        lines.append(f" admin-status {itf.admin_status}")
        lines.append(f" oper-status {itf.oper_status}")
        if itf.vlan:
            lines.append(f" vlan {itf.vlan}")
        if itf.mac:
            lines.append(f" mac-address {itf.mac}")
        lines.append("!")
    return "\n".join(lines)


def _fetch_running_config_via_ssh(
    ip: str,
    username: str,
    password: str,
    secret: str,
    timeout: float,
    mode: Literal["hierarchical", "raw"] = "hierarchical",
) -> tuple[str | None, str]:
    try:
        from netmiko import ConnectHandler, SSHDetect
        from netmiko import NetMikoAuthenticationException, NetmikoTimeoutException
    except Exception:
        return None, "Netmiko not installed in backend environment."

    detect_params = {
        "device_type": "autodetect",
        "host": ip,
        "username": username,
        "password": password,
        "timeout": int(timeout),
        "conn_timeout": int(timeout),
        "auth_timeout": int(timeout),
        "banner_timeout": int(timeout),
        "fast_cli": False,
    }
    detected_type = ""
    try:
        detected_type = SSHDetect(**detect_params).autodetect() or ""
    except Exception:
        detected_type = ""

    candidates = [detected_type] if detected_type else []
    for fallback in ["juniper_junos", "cisco_ios", "nokia_sros", "alcatel_aos"]:
        if fallback not in candidates:
            candidates.append(fallback)

    hierarchical_command_by_type = {
        "juniper_junos": "show configuration | no-more",
        "cisco_ios": "show running-config",
        "cisco_xe": "show running-config",
        "cisco_xr": "show running-config",
        "nokia_sros": "show configuration",
        "alcatel_aos": "show configuration snapshot",
    }
    raw_command_by_type = {
        "juniper_junos": "show configuration | display set | no-more",
        "cisco_ios": "show running-config",
        "cisco_xe": "show running-config",
        "cisco_xr": "show running-config",
        "nokia_sros": "show configuration | display set",
        "alcatel_aos": "show configuration snapshot",
    }

    last_error = ""
    for device_type in candidates:
        if not device_type:
            continue
        command_map = raw_command_by_type if mode == "raw" else hierarchical_command_by_type
        command = command_map.get(device_type, "show running-config")
        try:
            params = {
                "device_type": device_type,
                "host": ip,
                "username": username,
                "password": password,
                "timeout": int(timeout),
                "conn_timeout": int(timeout),
                "auth_timeout": int(timeout),
                "banner_timeout": int(timeout),
                "fast_cli": False,
            }
            if secret:
                params["secret"] = secret
            with ConnectHandler(**params) as conn:
                if secret:
                    try:
                        conn.enable()
                    except Exception:
                        pass
                raw = conn.send_command(command, read_timeout=max(20, int(timeout) * 2))
                if raw and raw.strip():
                    return raw.strip(), f"SSH {mode} config collected via Netmiko ({device_type}) using '{command}'."
        except (NetmikoTimeoutException, NetMikoAuthenticationException) as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
    # Telnet fallback for devices where SSH is disabled/unavailable.
    telnet_candidates = ["cisco_ios_telnet", "cisco_xe_telnet", "nokia_sros_telnet"]
    for device_type in telnet_candidates:
        command_map = raw_command_by_type if mode == "raw" else hierarchical_command_by_type
        command = command_map.get(device_type, "show running-config")
        if "nokia" in device_type and mode == "raw":
            command = "show configuration | display set"
        if "nokia" in device_type and mode == "hierarchical":
            command = "show configuration"
        try:
            params = {
                "device_type": device_type,
                "host": ip,
                "username": username,
                "password": password,
                "timeout": int(timeout),
                "conn_timeout": int(timeout),
                "auth_timeout": int(timeout),
                "banner_timeout": int(timeout),
                "fast_cli": False,
            }
            with ConnectHandler(**params) as conn:
                raw = conn.send_command(command, read_timeout=max(20, int(timeout) * 2))
                if raw and raw.strip():
                    return raw.strip(), f"Telnet {mode} config collected via Netmiko ({device_type}) using '{command}'."
        except Exception as exc:
            last_error = str(exc)

    return None, f"Unable to collect running config over SSH/Telnet: {last_error or 'unknown error'}"


@app.get("/api/device-config/{ip}/current", response_model=DeviceCurrentConfigResponse)
def get_device_current_config(
    ip: str,
    mode: Literal["hierarchical", "raw"] = Query(default="hierarchical"),
    timeout_seconds: float = Query(default=12.0, ge=3.0, le=40.0),
) -> DeviceCurrentConfigResponse:
    item = _find_device_or_404(ip)
    username, password, secret = _resolve_device_credentials(
        ip=ip,
        request_username="",
        request_password="",
        request_secret="",
    )

    content = None
    message = ""
    source = "fallback"
    if username and password:
        content, message = _fetch_running_config_via_ssh(
            ip=ip,
            username=username,
            password=password,
            secret=secret,
            timeout=timeout_seconds,
            mode=mode,
        )
        if content:
            source = "ssh"

    if not content:
        content = _build_fallback_config(item)
        if not message:
            message = "Using fallback generated config because live retrieval was unavailable."

    _append_config_history(item, f"current_config_read_{mode}", message or f"{mode} config viewed.")
    return DeviceCurrentConfigResponse(
        mgmt_ip=item.mgmt_ip,
        hostname=item.hostname or item.mgmt_ip,
        source=source,
        fetched_at=datetime.utcnow().isoformat() + "Z",
        content=content,
        message=message,
    )




@app.post("/api/inventory/metadata/upsert", response_model=ActionResponse)
def metadata_upsert(payload: MetadataUpsertRequest) -> ActionResponse:
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one metadata item is required.")

    overrides = _load_metadata_overrides()
    written = 0
    for entry in payload.items:
        _validate_test_ip(entry.mgmt_ip)
        overrides[entry.mgmt_ip] = {
            "hostname": entry.hostname,
            "vendor": entry.vendor,
            "model": entry.model,
            "os_version": entry.os_version,
            "serial_number": entry.serial_number,
            "site": entry.site,
            "role": entry.role,
        }
        written += 1

    _save_metadata_overrides(overrides)
    return ActionResponse(message=f"Upserted metadata for {written} IP(s).")


@app.post("/api/inventory/credentials/upsert", response_model=ActionResponse)
def credentials_upsert(payload: CredentialsUpsertRequest) -> ActionResponse:
    data = _load_device_credentials()
    data["default"] = {
        "username": payload.default_username,
        "password": payload.default_password,
        "secret": payload.default_secret,
    }

    per_device_map: dict[str, dict[str, str]] = {}
    for entry in payload.per_device:
        _validate_test_ip(entry.mgmt_ip)
        per_device_map[entry.mgmt_ip] = {
            "username": entry.username,
            "password": entry.password,
            "secret": entry.secret,
        }

    data["per_device"] = per_device_map
    _save_device_credentials(data)
    return ActionResponse(
        message=(
            f"Saved credentials: default={'yes' if payload.default_username and payload.default_password else 'no'}, "
            f"per_device={len(per_device_map)}."
        )
    )


@app.post("/api/inventory/discover/netconf-probe", response_model=ActionResponse)
def discover_netconf_probe(payload: NetconfProbeRequest) -> ActionResponse:
    subset = inventory_store
    if payload.subnet and payload.subnet != "ALL":
        subset = [item for item in subset if item.subnet == payload.subnet]
    if payload.host_ip and payload.host_ip != "ALL":
        subset = [item for item in subset if item.mgmt_ip == payload.host_ip]

    reachable = 0
    unreachable = 0
    for item in subset:
        try:
            with socket.create_connection((item.mgmt_ip, 830), timeout=payload.timeout_seconds):
                pass
            item.netconf = "Enabled"
            item.source = "NETCONF"
            if item.status != "Discovered":
                item.status = "Pending Discovery"
            item.fetch_reason = "Step 1 complete: NETCONF reachable. Run Step 2 Fetch Values."
            reachable += 1
        except OSError:
            item.netconf = "Disabled"
            item.source = "NETCONF"
            if item.status != "Discovered":
                item.status = "Fetch Failed"
            item.fetch_reason = "Step 1 failed: NETCONF port 830 unreachable or timed out."
            unreachable += 1

    _save_inventory(inventory_store)
    return ActionResponse(
        message=(
            f"NETCONF probe complete: {reachable} reachable, {unreachable} unreachable "
            f"(timeout {payload.timeout_seconds:.1f}s)."
        )
    )


@app.post("/api/inventory/discover/netconf-yang", response_model=ActionResponse)
def discover_netconf_yang(payload: NetconfYangFetchRequest) -> ActionResponse:
    subset = _filter_inventory(subnet=payload.subnet, host_ip=payload.host_ip)

    discovered = 0
    failed = 0
    failed_ips: list[str] = []

    for item in subset:
        username, password, _ = _resolve_device_credentials(
            ip=item.mgmt_ip,
            request_username=(payload.username or "").strip(),
            request_password=(payload.password or "").strip(),
            request_secret="",
        )

        if not username or not password:
            item.netconf = "Disabled"
            if item.source != "NETCONF":
                _clear_identity_fields(item)
            item.source = "NETCONF"
            item.status = "Fetch Failed"
            item.fetch_reason = "Missing NETCONF credentials for this IP."
            failed += 1
            failed_ips.append(item.mgmt_ip)
            continue

        metadata: dict[str, str] | None = None
        reason = ""
        if item.netconf == "Enabled":
            metadata, reason = _fetch_live_metadata_via_netconf_yang(
                ip=item.mgmt_ip,
                username=username,
                password=password,
                timeout=payload.timeout_seconds,
            )

        # Always allow SSH fallback, including when NETCONF is disabled/unreachable.
        if not metadata:
            ssh_metadata, ssh_reason = _fetch_live_metadata_via_ssh_netmiko(
                ip=item.mgmt_ip,
                username=username,
                password=password,
                timeout=payload.timeout_seconds,
            )
            if ssh_metadata:
                metadata = ssh_metadata
                reason = ssh_reason
        elif not _is_meaningful(metadata.get("os_version", "")) or not _is_meaningful(metadata.get("model", "")) or not _is_meaningful(metadata.get("serial_number", "")):
            # NETCONF may succeed but omit inventory/version leaves; enrich from CLI over SSH/Telnet.
            ssh_metadata, ssh_reason = _fetch_live_metadata_via_ssh_netmiko(
                ip=item.mgmt_ip,
                username=username,
                password=password,
                timeout=payload.timeout_seconds,
            )
            if ssh_metadata:
                for key in ["hostname", "vendor", "model", "os_version", "serial_number"]:
                    current_val = str(metadata.get(key, "") or "").strip()
                    incoming_val = str(ssh_metadata.get(key, "") or "").strip()
                    if (not _is_meaningful(current_val)) and _is_meaningful(incoming_val):
                        metadata[key] = incoming_val
                if ssh_reason:
                    reason = f"{reason} | enriched: {ssh_reason}" if reason else ssh_reason
        if metadata:
            item.hostname = metadata.get("hostname", "") or item.hostname
            item.vendor = metadata.get("vendor", "") or item.vendor
            model_value = metadata.get("model", "")
            os_value = metadata.get("os_version", "")
            serial_value = metadata.get("serial_number", "")
            protocols_value = metadata.get("routing_protocols", "")
            mgmt_vlan_value = metadata.get("mgmt_vlan", "")
            routing_domain_value = metadata.get("routing_domain", "")
            snmp_profile_value = metadata.get("snmp_profile", "")
            ntp_profile_value = metadata.get("ntp_profile", "")
            security_profile_value = metadata.get("security_profile", "")
            if _is_meaningful(model_value):
                item.model = model_value
            if _is_meaningful(os_value):
                item.os_version = os_value
            if _is_meaningful(serial_value):
                item.serial_number = serial_value
            item.routing_protocols = protocols_value
            item.mgmt_vlan = mgmt_vlan_value
            item.routing_domain = routing_domain_value
            item.snmp_profile = snmp_profile_value
            item.ntp_profile = ntp_profile_value
            item.security_profile = security_profile_value
            item.netconf = "Enabled"
            item.source = "NETCONF"
            item.status = "Discovered"
            item.fetch_reason = reason if reason and reason != "live" else "Live values fetched via NETCONF + YANG."
            discovered += 1
            continue

        item.netconf = "Disabled"
        if item.source != "NETCONF":
            _clear_identity_fields(item)
        item.source = "NETCONF"
        item.status = "Fetch Failed"
        item.fetch_reason = reason
        failed += 1
        failed_ips.append(item.mgmt_ip)

    _save_inventory(inventory_store)
    return ActionResponse(
        message=(
            f"NETCONF+YANG fetch complete: {discovered} discovered, {failed} failed. "
            f"Failed IPs: {', '.join(failed_ips) if failed_ips else 'none'}."
        )
    )


@app.post("/api/inventory/netconf-yang-snapshot", response_model=LiveSnapshotResponse)
def netconf_yang_snapshot(payload: NetconfYangFetchRequest) -> LiveSnapshotResponse:
    probe_result = discover_netconf_probe(
        NetconfProbeRequest(
            subnet=payload.subnet,
            host_ip=payload.host_ip,
            timeout_seconds=payload.timeout_seconds,
        )
    )
    fetch_result = discover_netconf_yang(payload)
    items = _filter_inventory(subnet=payload.subnet, host_ip=payload.host_ip)
    return LiveSnapshotResponse(message=f"{probe_result.message} | {fetch_result.message}", items=items)


@app.post("/api/inventory/netconf-yang-safe-scan", response_model=SafeScanResponse)
async def netconf_yang_safe_scan(payload: NetconfYangSafeScanRequest) -> SafeScanResponse:
    subset = _filter_inventory(subnet=payload.subnet, host_ip=payload.host_ip)
    semaphore = asyncio.Semaphore(payload.max_concurrency)

    discovered = 0
    failed = 0

    async def _scan_item(item: DeviceRecord) -> None:
        nonlocal discovered, failed

        username, password, _ = _resolve_device_credentials(
            ip=item.mgmt_ip,
            request_username=(payload.username or "").strip(),
            request_password=(payload.password or "").strip(),
            request_secret="",
        )

        if not username or not password:
            item.netconf = "Disabled"
            item.source = "NETCONF"
            item.status = "Fetch Failed"
            item.fetch_reason = "Missing NETCONF credentials for this IP."
            failed += 1
            return

        async with semaphore:
            metadata: dict[str, str] | None = None
            last_reason = ""
            for attempt in range(payload.max_retries + 1):
                metadata, reason = await asyncio.to_thread(
                    _fetch_live_metadata_via_netconf_yang,
                    item.mgmt_ip,
                    username,
                    password,
                    payload.timeout_seconds,
                )
                if not metadata:
                    ssh_metadata, ssh_reason = await asyncio.to_thread(
                        _fetch_live_metadata_via_ssh_netmiko,
                        item.mgmt_ip,
                        username,
                        password,
                        payload.timeout_seconds,
                    )
                    if ssh_metadata:
                        metadata = ssh_metadata
                        reason = ssh_reason
                elif not _is_meaningful(metadata.get("os_version", "")) or not _is_meaningful(metadata.get("model", "")) or not _is_meaningful(metadata.get("serial_number", "")):
                    ssh_metadata, ssh_reason = await asyncio.to_thread(
                        _fetch_live_metadata_via_ssh_netmiko,
                        item.mgmt_ip,
                        username,
                        password,
                        payload.timeout_seconds,
                    )
                    if ssh_metadata:
                        for key in ["hostname", "vendor", "model", "os_version", "serial_number"]:
                            current_val = str(metadata.get(key, "") or "").strip()
                            incoming_val = str(ssh_metadata.get(key, "") or "").strip()
                            if (not _is_meaningful(current_val)) and _is_meaningful(incoming_val):
                                metadata[key] = incoming_val
                        if ssh_reason:
                            reason = f"{reason} | enriched: {ssh_reason}" if reason else ssh_reason
                if metadata:
                    break
                last_reason = reason
                if attempt < payload.max_retries:
                    await asyncio.sleep(0.25)

            if metadata:
                item.hostname = metadata.get("hostname", "") or item.hostname
                item.vendor = metadata.get("vendor", "") or item.vendor
                model_value = metadata.get("model", "")
                os_value = metadata.get("os_version", "")
                serial_value = metadata.get("serial_number", "")
                protocols_value = metadata.get("routing_protocols", "")
                mgmt_vlan_value = metadata.get("mgmt_vlan", "")
                routing_domain_value = metadata.get("routing_domain", "")
                snmp_profile_value = metadata.get("snmp_profile", "")
                ntp_profile_value = metadata.get("ntp_profile", "")
                security_profile_value = metadata.get("security_profile", "")
                if _is_meaningful(model_value):
                    item.model = model_value
                if _is_meaningful(os_value):
                    item.os_version = os_value
                if _is_meaningful(serial_value):
                    item.serial_number = serial_value
                item.routing_protocols = protocols_value
                item.mgmt_vlan = mgmt_vlan_value
                item.routing_domain = routing_domain_value
                item.snmp_profile = snmp_profile_value
                item.ntp_profile = ntp_profile_value
                item.security_profile = security_profile_value
                item.netconf = "Enabled"
                item.source = "NETCONF"
                item.status = "Discovered"
                item.fetch_reason = "Live values fetched via NETCONF + YANG (safe scan)."
                discovered += 1
                return

            item.netconf = "Disabled"
            if item.source != "NETCONF":
                _clear_identity_fields(item)
            item.source = "NETCONF"
            item.status = "Fetch Failed"
            item.fetch_reason = last_reason or "NETCONF+YANG fetch failed."
            failed += 1

    await asyncio.gather(*[_scan_item(item) for item in subset])

    _save_inventory(inventory_store)
    items = _filter_inventory(subnet=payload.subnet, host_ip=payload.host_ip)
    return SafeScanResponse(
        message=(
            f"Safe scan complete: {discovered} discovered, {failed} failed, scanned {len(subset)} "
            f"(concurrency={payload.max_concurrency}, retries={payload.max_retries})."
        ),
        scanned=len(subset),
        discovered=discovered,
        failed=failed,
        items=items,
    )


@app.websocket("/api/ws/inventory/netconf-yang")
async def ws_netconf_yang_stream(
    websocket: WebSocket,
    subnet: str = "ALL",
    host_ip: str = "ALL",
    interval_seconds: float = 10.0,
    timeout_seconds: float = 8.0,
) -> None:
    await websocket.accept()

    interval = max(2.0, min(interval_seconds, 60.0))
    timeout = max(2.0, min(timeout_seconds, 30.0))

    try:
        while True:
            payload = NetconfYangFetchRequest(
                subnet=subnet,
                host_ip=host_ip,
                timeout_seconds=timeout,
            )
            snapshot = await asyncio.to_thread(netconf_yang_snapshot, payload)
            await websocket.send_json(
                {
                    "message": snapshot.message,
                    "items": [item.model_dump() for item in snapshot.items],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"error": str(exc)})
        except Exception:
            pass


@app.post("/api/inventory/discover/metadata", response_model=ActionResponse)
def discover_metadata() -> ActionResponse:
    raise HTTPException(
        status_code=410,
        detail="Metadata discovery is disabled in strict real-time mode. Use /api/inventory/netconf-yang-snapshot.",
    )


@app.post("/api/inventory/discover/mock", response_model=ActionResponse)
def discover_mock() -> ActionResponse:
    raise HTTPException(
        status_code=410,
        detail="Mock discovery is disabled in strict real-time mode. Use /api/inventory/netconf-yang-snapshot.",
    )


# Serve the frontend from the same port as the API so only one port needs to
# be reachable/forwarded (avoids cross-port access issues in remote/dev
# environments). All API routes are registered above under /api, so mounting
# static files at "/" here does not shadow any API endpoint.
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
