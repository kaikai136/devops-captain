from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import HostCredential, HostGroup, ManagedHost
from .services import next_group_sort_order, resolve_creator

HOST_TABLE_IMPORT_MODE = "host-table"
HOST_TABLE_DEFAULT_GROUP_NAME = "default"

DEFAULT_GROUP_NAME = "默认分组"


def parse_datetime_or_none(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def build_group_path(group: HostGroup | None, groups_by_id: dict[int, HostGroup] | None = None) -> str:
    names = []
    current = group
    while current:
        names.append(current.name)
        if groups_by_id is not None and current.parent_id:
            current = groups_by_id.get(current.parent_id)
        else:
            current = current.parent
    return "/".join(reversed(names))


def export_host_management_payload() -> dict:
    groups = list(HostGroup.objects.select_related("parent").order_by("sort_order", "id"))
    groups_by_id = {group.id: group for group in groups}
    hosts = ManagedHost.objects.select_related("group", "created_by").order_by("id")
    credentials = HostCredential.objects.order_by("id")

    return {
        "version": 1,
        "groups": [
            {
                "name": group.name,
                "path": build_group_path(group, groups_by_id),
                "parentPath": build_group_path(groups_by_id.get(group.parent_id), groups_by_id) if group.parent_id else "",
                "sortOrder": group.sort_order,
            }
            for group in groups
        ],
        "hosts": [
            {
                "name": host.name,
                "groupPath": build_group_path(groups_by_id.get(host.group_id, host.group), groups_by_id),
                "publicIp": str(host.public_ip) if host.public_ip else "",
                "privateIp": str(host.private_ip),
                "port": host.port,
                "loginUser": host.login_user,
                "loginPassword": host.login_password,
                "privateKeyName": host.private_key_name,
                "privateKey": host.private_key,
                "remark": host.remark,
                "machineName": host.machine_name,
                "systemArch": host.system_arch,
                "systemType": host.system_type,
                "cpu": host.cpu,
                "memory": host.memory,
                "disk": host.disk,
                "os": host.os,
                "creator": host.created_by.username if host.created_by_id and host.created_by else "system",
                "createdAt": host.created_at.isoformat() if host.created_at else None,
                "updatedAt": host.updated_at.isoformat() if host.updated_at else None,
                "verified": host.verified,
                "verifyStatus": host.verify_status,
            }
            for host in hosts
        ],
        "credentials": [
            {
                "name": credential.name,
                "credentialType": credential.credential_type,
                "username": credential.username,
                "password": credential.password,
                "port": credential.port,
                "privateKeyName": credential.private_key_name,
                "privateKey": credential.private_key,
                "remark": credential.remark,
            }
            for credential in credentials
        ],
    }


def ensure_group_by_path(path: str) -> HostGroup:
    names = [name.strip() for name in str(path).split("/") if name.strip()]
    if not names:
        raise ValueError("分组路径不能为空")

    parent = None
    group = None
    for name in names:
        group, _created = HostGroup.objects.get_or_create(
            parent=parent,
            name=name,
            defaults={"sort_order": next_group_sort_order(parent, "", None)},
        )
        parent = group
    return group


def import_host_management_payload(payload: dict) -> dict:
    if payload.get("importMode") == HOST_TABLE_IMPORT_MODE:
        return import_host_table_payload(payload)

    groups = payload.get("groups", [])
    hosts = payload.get("hosts", [])
    credentials = payload.get("credentials", [])

    if not isinstance(groups, list) or not isinstance(hosts, list) or not isinstance(credentials, list):
        raise ValueError("导入文件格式不正确")

    imported = {"groups": 0, "hosts": 0, "credentials": 0}
    with transaction.atomic():
        import_groups(groups, imported)
        import_credentials(credentials, imported)
        import_hosts(hosts, imported)
    return imported


def import_groups(groups: list, imported: dict[str, int]) -> None:
    for item in sorted(groups, key=group_import_depth):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("name") or "").strip()
        if not path:
            continue
        group = ensure_group_by_path(path)
        sort_order = item.get("sortOrder")
        if isinstance(sort_order, int) and group.sort_order != sort_order:
            group.sort_order = sort_order
            group.save(update_fields=["sort_order"])
        imported["groups"] += 1


def group_import_depth(value) -> int:
    if not isinstance(value, dict):
        return 0
    return len(str(value.get("path", value.get("name", ""))).split("/"))


def import_host_table_payload(payload: dict) -> dict[str, dict[str, int]]:
    hosts = payload.get("hosts", [])
    if not isinstance(hosts, list):
        raise ValueError("导入文件格式不正确")

    imported = {"groups": 0, "hosts": 0, "credentials": 0}
    skipped = {"hosts": 0}
    with transaction.atomic():
        for item in hosts:
            if not isinstance(item, dict):
                skipped["hosts"] += 1
                continue
            normalized = normalize_host_table_item(item)
            if normalized is None:
                skipped["hosts"] += 1
                continue
            group = ensure_group_by_path(normalized["groupPath"])
            if ManagedHost.objects.filter(group=group, name=normalized["name"], private_ip=normalized["privateIp"]).exists():
                skipped["hosts"] += 1
                continue
            ManagedHost.objects.create(
                name=normalized["name"],
                group=group,
                private_ip=normalized["privateIp"],
                port=normalized["port"],
                remark=normalized["remark"],
                os=host_table_os_from_platform(normalized["platformType"]),
                verified=False,
                verify_status="unverified",
            )
            imported["hosts"] += 1
    return {"imported": imported, "skipped": skipped}


def normalize_host_table_item(item: dict) -> dict | None:
    name = str(item.get("name", "")).strip()
    private_ip = str(item.get("privateIp") or item.get("ip") or "").strip()
    if not name or not private_ip:
        return None
    return {
        "groupPath": str(item.get("groupPath") or item.get("group") or HOST_TABLE_DEFAULT_GROUP_NAME).strip() or HOST_TABLE_DEFAULT_GROUP_NAME,
        "name": name,
        "privateIp": private_ip,
        "platformType": str(item.get("platformType") or "linux").strip().lower() or "linux",
        "port": normalize_host_table_port(item.get("port")),
        "remark": str(item.get("remark") or ""),
    }


def normalize_host_table_port(value) -> int:
    try:
        port = int(value or 22)
    except (TypeError, ValueError):
        return 22
    return port if port > 0 else 22


def host_table_os_from_platform(platform_type: str) -> str:
    return "windows" if platform_type.lower() == "windows" else "centos"


def import_credentials(credentials: list, imported: dict[str, int]) -> None:
    for item in credentials:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        defaults = build_credential_defaults(item)
        if not defaults:
            continue
        HostCredential.objects.update_or_create(name=name, defaults=defaults)
        imported["credentials"] += 1


def build_credential_defaults(item: dict) -> dict:
    defaults = {}
    if "credentialType" in item:
        credential_type = str(item.get("credentialType") or HostCredential.TYPE_HOST)
        if credential_type not in dict(HostCredential.TYPE_CHOICES):
            credential_type = HostCredential.TYPE_HOST
        defaults["credential_type"] = credential_type
    if "username" in item:
        defaults["username"] = str(item.get("username") or "").strip()
    if "password" in item:
        defaults["password"] = str(item.get("password", ""))
    if "port" in item:
        defaults["port"] = int(item.get("port") or 22)
    if "privateKeyName" in item:
        defaults["private_key_name"] = str(item.get("privateKeyName", ""))
    if "privateKey" in item:
        defaults["private_key"] = str(item.get("privateKey", ""))
    if "remark" in item:
        defaults["remark"] = str(item.get("remark", ""))
    return defaults


def import_hosts(hosts: list, imported: dict[str, int]) -> None:
    for item in hosts:
        if not isinstance(item, dict):
            continue
        private_ip = str(item.get("privateIp", "")).strip()
        name = str(item.get("name", "")).strip()
        group_path_value = str(item.get("groupPath") or item.get("group") or DEFAULT_GROUP_NAME).strip()
        if not private_ip or not name:
            continue
        group = ensure_group_by_path(group_path_value)
        defaults = build_host_defaults(item, name, group)
        ManagedHost.objects.update_or_create(
            name=name,
            group=group,
            defaults={**defaults, "private_ip": private_ip},
        )
        imported["hosts"] += 1


def build_host_defaults(item: dict, name: str, group: HostGroup) -> dict:
    defaults = {
        "name": name,
        "group": group,
    }
    optional_fields = {
        "publicIp": ("public_ip", lambda value: str(value or "") or None),
        "port": ("port", lambda value: int(value or 22)),
        "loginUser": ("login_user", lambda value: str(value or "")),
        "loginPassword": ("login_password", lambda value: str(value or "")),
        "privateKeyName": ("private_key_name", lambda value: str(value or "")),
        "privateKey": ("private_key", lambda value: str(value or "")),
        "remark": ("remark", lambda value: str(value or "")),
        "machineName": ("machine_name", lambda value: str(value or "")),
        "systemArch": ("system_arch", lambda value: str(value or "")),
        "systemType": ("system_type", lambda value: str(value or "")),
        "cpu": ("cpu", lambda value: int(value or 0)),
        "memory": ("memory", lambda value: int(value or 0)),
        "disk": ("disk", lambda value: str(value or "")[:260]),
        "os": ("os", lambda value: str(value or "centos")),
        "verified": ("verified", parse_bool),
        "verifyStatus": (
            "verify_status",
            lambda value: str(value or ("verified" if parse_bool(item.get("verified")) else "unverified")),
        ),
    }
    for source, (target, converter) in optional_fields.items():
        if source in item:
            defaults[target] = converter(item.get(source))
    if "createdAt" in item:
        defaults["created_at"] = parse_datetime_or_none(item.get("createdAt")) or timezone.now()
    if "updatedAt" in item:
        defaults["updated_at"] = parse_datetime_or_none(item.get("updatedAt"))
    creator = resolve_creator(item.get("creator"))
    if creator:
        defaults["created_by"] = creator
    return defaults


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "已验证", "verified"}
    return bool(value)
