from __future__ import annotations

from host_management.models import ManagedHost

from .commands import run_one_shot_ssh_command
from .errors import TerminalConnectionError
from .file_parsers import natural_sort_key


REMOTE_MONITOR_SAMPLE_INTERVAL_SECONDS = 1

REMOTE_MONITOR_COMMAND = r"""
set -eu
test -r /proc/stat
test -r /proc/meminfo
test -r /proc/net/dev
printf 'SECTION:system\n'
printf 'hostname=%s\n' "$(hostname 2>/dev/null || printf '-')"
printf 'arch=%s\n' "$(uname -m 2>/dev/null || printf '-')"
printf 'kernel=%s\n' "$(uname -sr 2>/dev/null || printf '-')"
printf 'cpuModel=%s\n' "$(awk -F: '/^model name/{sub(/^ +/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null || printf '-')"
printf 'hostTime=%s\n' "$(date -Is 2>/dev/null || printf '-')"
if [ -r /etc/os-release ]; then
  . /etc/os-release
  printf 'os=%s\n' "${PRETTY_NAME:-${NAME:-Linux}}"
else
  printf 'os=%s\n' "$(uname -s 2>/dev/null || printf Linux)"
fi
printf 'uptime=%s\n' "$(cut -d' ' -f1 /proc/uptime 2>/dev/null || printf 0)"
printf 'SECTION:cpu1\n'
grep '^cpu' /proc/stat
printf 'SECTION:net1\n'
cat /proc/net/dev
printf 'SECTION:load\n'
cat /proc/loadavg
sleep 1
printf 'SECTION:cpu2\n'
grep '^cpu' /proc/stat
printf 'SECTION:net2\n'
cat /proc/net/dev
printf 'SECTION:mem\n'
cat /proc/meminfo
printf 'SECTION:details\n'
printf 'dns=%s\n' "$(awk '/^nameserver/{printf "%s ", $2}' /etc/resolv.conf 2>/dev/null || true)"
printf 'tcpCongestion=%s\n' "$(cat /proc/sys/net/ipv4/tcp_congestion_control 2>/dev/null || printf '-')"
printf 'ipv6=%s\n' "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null || printf '-')"
printf 'ipv4=%s\n' "$(test -r /proc/net/route && printf 1 || printf 0)"
printf 'SECTION:df\n'
df -PT -B1 2>/dev/null
"""

def get_remote_resource_monitor(host: ManagedHost) -> dict:
    try:
        output = run_one_shot_ssh_command(host, REMOTE_MONITOR_COMMAND)
        payload = parse_remote_resource_monitor_output(output)
        if "management" in payload:
            payload["management"]["sshPort"] = host.port
        return payload
    except TerminalConnectionError as error:
        message = str(error)
        if "No such file" in message or "can't open" in message or "test:" in message or "远端命令退出码" in message:
            raise TerminalConnectionError("当前主机不支持资源监控")
        raise

def parse_remote_resource_monitor_output(output: str) -> dict:
    sections = split_monitor_sections(output)
    required_sections = {"system", "cpu1", "cpu2", "load", "mem", "net1", "net2", "df"}
    if not required_sections.issubset(sections):
        raise TerminalConnectionError("当前主机不支持资源监控")

    system = parse_monitor_key_values(sections["system"])
    cpu1 = parse_monitor_cpu_line(sections["cpu1"])
    cpu2 = parse_monitor_cpu_line(sections["cpu2"])
    network1 = parse_monitor_network(sections["net1"])
    network2 = parse_monitor_network(sections["net2"])

    payload = {
        "system": {
            "hostname": system.get("hostname", "-") or "-",
            "arch": system.get("arch", "-") or "-",
            "os": system.get("os", system.get("kernel", "Linux")) or "Linux",
            "kernel": system.get("kernel", "-") or "-",
            "uptimeSeconds": parse_monitor_float(system.get("uptime", "0")),
        },
        "cpu": {
            "usagePercent": calculate_monitor_cpu_usage(cpu1, cpu2),
            "perCore": parse_monitor_cpu_cores(sections["cpu1"], sections["cpu2"]),
            "cores": detect_monitor_cpu_cores(sections["cpu2"]),
            **parse_monitor_load(sections["load"]),
        },
        "memory": parse_monitor_memory(sections["mem"]),
        "network": parse_monitor_network_rates(network1, network2, REMOTE_MONITOR_SAMPLE_INTERVAL_SECONDS),
        "disks": parse_monitor_disks(sections["df"]),
    }
    if "details" in sections:
        details = parse_monitor_key_values(sections["details"])
        payload["system"].update({
            "cpuModel": system.get("cpuModel", "-") or "-",
            "cpuCores": payload["cpu"]["cores"],
            "hostTime": system.get("hostTime", "-") or "-",
        })
        memory_values = parse_monitor_key_values(sections["mem"].replace(":", "="))
        swap_total = max(0, parse_monitor_int((memory_values.get("SwapTotal") or "0").split()[0])) * 1024
        swap_free = max(0, parse_monitor_int((memory_values.get("SwapFree") or "0").split()[0])) * 1024
        swap_used = max(0, min(swap_total, swap_total - swap_free))
        payload["swap"] = {
            "totalBytes": swap_total, "usedBytes": swap_used,
            "usagePercent": round(swap_used / swap_total * 100, 1) if swap_total else 0.0,
            "available": swap_total > 0,
        }
        congestion = details.get("tcpCongestion", "-") or "-"
        payload["management"] = {
            "sshPort": None,
            "dnsServers": details.get("dns", "").split(),
            "tcpCongestionControl": congestion,
            "ipv4Enabled": details.get("ipv4") == "1",
            "ipv6Enabled": details.get("ipv6") == "0",
            "bbrEnabled": congestion == "bbr" if congestion != "-" else None,
        }
        for interface in payload["network"]:
            interface.update(network2[interface["name"]])
    return payload

def split_monitor_sections(output: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_section = ""

    for line in output.splitlines():
        if line.startswith("SECTION:"):
            current_section = line.split(":", 1)[1].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section:
            sections[current_section].append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items()}

def parse_monitor_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values

def parse_monitor_cpu_cores(previous: str, current: str) -> list[dict]:
    def samples(output: str) -> dict:
        result = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].startswith("cpu") and parts[0][3:].isdigit():
                result[parts[0]] = [parse_monitor_int(value) for value in parts[1:]]
        return result

    before = samples(previous)
    after = samples(current)
    return [
        {"name": name, "usagePercent": calculate_monitor_cpu_usage(before[name], after[name])}
        for name in sorted(after, key=lambda name: int(name[3:]))
        if name in before
    ]


def parse_monitor_cpu_line(output: str) -> list[int]:
    line = next((item for item in output.splitlines() if item.startswith("cpu ")), "")
    parts = line.split()
    if len(parts) < 5:
        raise TerminalConnectionError("CPU 数据解析失败")
    return [parse_monitor_int(value) for value in parts[1:]]

def calculate_monitor_cpu_usage(previous: list[int], current: list[int]) -> float:
    previous_idle = previous[3] + (previous[4] if len(previous) > 4 else 0)
    current_idle = current[3] + (current[4] if len(current) > 4 else 0)
    previous_total = sum(previous)
    current_total = sum(current)
    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle
    if total_delta <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)

def parse_monitor_load(output: str) -> dict:
    values = output.strip().split()
    return {
        "load1": parse_monitor_float(values[0]) if len(values) > 0 else 0.0,
        "load5": parse_monitor_float(values[1]) if len(values) > 1 else 0.0,
        "load15": parse_monitor_float(values[2]) if len(values) > 2 else 0.0,
    }

def detect_monitor_cpu_cores(output: str) -> int:
    return max(1, len([line for line in output.splitlines() if line.startswith("cpu") and not line.startswith("cpu ")]))

def parse_monitor_memory(output: str) -> dict:
    values: dict[str, int] = {}
    for line in output.splitlines():
        parts = line.replace(":", "").split()
        if len(parts) >= 2:
            values[parts[0]] = parse_monitor_int(parts[1]) * 1024

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    free = values.get("MemFree", 0)
    buffers = values.get("Buffers", 0)
    cached = values.get("Cached", 0) + values.get("SReclaimable", 0)
    if total <= 0:
        raise TerminalConnectionError("内存数据解析失败")
    if available <= 0:
        available = free + buffers + cached
    used = max(0, total - available)

    return {
        "totalBytes": total,
        "usedBytes": used,
        "availableBytes": available,
        "cacheBytes": cached,
        "usagePercent": round(used / total * 100, 1),
    }

def parse_monitor_network(output: str) -> dict[str, dict[str, int]]:
    interfaces: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        interface = name.strip()
        if interface == "lo":
            continue
        values = data.split()
        if len(values) < 16:
            continue
        interfaces[interface] = {
            "rxBytes": parse_monitor_int(values[0]),
            "txBytes": parse_monitor_int(values[8]),
        }
    return interfaces

def parse_monitor_network_rates(previous: dict[str, dict[str, int]], current: dict[str, dict[str, int]], interval_seconds: int) -> list[dict]:
    interfaces: list[dict] = []
    interval = max(1, interval_seconds)
    for name in sorted(current.keys(), key=natural_sort_key):
        current_values = current[name]
        previous_values = previous.get(name, current_values)
        rx_rate = max(0, current_values["rxBytes"] - previous_values["rxBytes"]) / interval
        tx_rate = max(0, current_values["txBytes"] - previous_values["txBytes"]) / interval
        interfaces.append(
            {
                "name": name,
                "rxBytesPerSecond": round(rx_rate, 1),
                "txBytesPerSecond": round(tx_rate, 1),
            }
        )
    return interfaces

def parse_monitor_disks(output: str) -> list[dict]:
    disks: list[dict] = []
    ignored_types = {"tmpfs", "devtmpfs", "overlay", "squashfs"}

    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        filesystem, file_type, total, used, available, percent, mountpoint = parts[:7]
        if file_type in ignored_types:
            continue
        total_bytes = parse_monitor_int(total)
        if total_bytes <= 0:
            continue
        disks.append(
            {
                "filesystem": filesystem,
                "type": file_type,
                "mountpoint": mountpoint,
                "totalBytes": total_bytes,
                "usedBytes": parse_monitor_int(used),
                "availableBytes": parse_monitor_int(available),
                "usagePercent": round(parse_monitor_float(percent.rstrip("%")), 1),
            }
        )

    return disks

def parse_monitor_int(value: str) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0

def parse_monitor_float(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0

__all__ = [
    'get_remote_resource_monitor',
    'parse_remote_resource_monitor_output',
    'split_monitor_sections',
    'parse_monitor_key_values',
    'parse_monitor_cpu_line',
    'calculate_monitor_cpu_usage',
    'parse_monitor_load',
    'detect_monitor_cpu_cores',
    'parse_monitor_memory',
    'parse_monitor_network',
    'parse_monitor_network_rates',
    'parse_monitor_disks',
    'parse_monitor_int',
    'parse_monitor_float',
]
