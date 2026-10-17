from __future__ import annotations

import json
import math
import re
import shlex
import time

from .commands import run_one_shot_ssh_command
from .connections import open_ssh_client
from .errors import TerminalConnectionError


CONTAINER_IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")
CONTAINER_ID = re.compile(r"[a-f0-9]{64}")
CONTAINER_ACTIONS = {"start", "stop", "restart"}
MAX_LOG_BYTES = 1024 * 1024


def parse_percent(value):
    try:
        number = float(str(value).rstrip("%"))
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_bytes(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGTPE]?i?B)", str(value).strip(), re.IGNORECASE)
    if not match:
        return None
    unit = match[2].upper()
    power = "BKMGTPE".index(unit[0])
    return int(float(match[1]) * (1024 if "I" in unit else 1000) ** power)


def json_lines(output):
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict):
            yield item


def parse_docker_containers(output, stats_output=""):
    stats = {item.get("ID", item.get("Container", "")): item for item in json_lines(stats_output)}
    containers = []
    for item in json_lines(output):
        identifier = str(item.get("ID", ""))
        if not CONTAINER_ID.fullmatch(identifier):
            continue
        stat = stats.get(identifier, {})
        memory = str(stat.get("MemUsage", "")).split("/")
        state = str(item.get("State", "unknown"))
        containers.append({
            "id": identifier, "name": str(item.get("Names", "")),
            "image": str(item.get("Image", "")), "command": str(item.get("Command", "")),
            "status": str(item.get("Status", "")),
            "state": state if state in {"running", "paused", "exited", "created"} else "unknown",
            "uptime": str(item.get("RunningFor", "")), "ports": str(item.get("Ports", "")),
            "cpuPercent": parse_percent(stat.get("CPUPerc")),
            "memoryUsageBytes": parse_bytes(memory[0]),
            "memoryLimitBytes": parse_bytes(memory[1]) if len(memory) > 1 else None,
            "memoryPercent": parse_percent(stat.get("MemPerc")),
        })
    return containers


def get_remote_containers(host):
    try:
        output = run_one_shot_ssh_command(host, "docker ps -a --no-trunc --format '{{json .}}'")
    except TerminalConnectionError as error:
        message = str(error).lower()
        if any(text in message for text in ("not found", "permission denied", "cannot connect", "is the docker daemon running")):
            return {"available": False, "containers": [], "reason": "容器服务不可用"}
        raise
    try:
        stats = run_one_shot_ssh_command(host, "docker stats --no-stream --no-trunc --format '{{json .}}'") if output.strip() else ""
    except TerminalConnectionError:
        stats = ""
    return {"available": True, "containers": parse_docker_containers(output, stats)}


def validate_container(host, identifier, running=False):
    if not isinstance(identifier, str) or not CONTAINER_IDENTIFIER.fullmatch(identifier):
        raise ValueError("容器标识无效")
    output = run_one_shot_ssh_command(host, f"docker inspect --type container --format '{{{{json .}}}}' {shlex.quote(identifier)}")
    item = next(json_lines(output), None)
    if not item or not CONTAINER_ID.fullmatch(str(item.get("Id", ""))):
        raise ValueError("容器不存在或无法读取")
    if running and not item.get("State", {}).get("Running"):
        raise ValueError("容器未运行，无法进入终端")
    return item["Id"]


def container_action_command(host, identifier, action):
    if action not in CONTAINER_ACTIONS:
        raise ValueError("不支持的容器操作")
    return f"docker {action} {validate_container(host, identifier)}"


def container_terminal_command(host, identifier):
    identifier = validate_container(host, identifier, running=True)
    return f"docker exec -it {identifier} /bin/sh\r"


def read_bounded_logs(host, identifier, tail):
    if isinstance(tail, bool) or not isinstance(tail, int) or not 1 <= tail <= 1000:
        raise ValueError("日志行数必须在 1 到 1000 之间")
    identifier = validate_container(host, identifier)
    command = f"docker logs --tail {tail} --timestamps {identifier} 2>&1"
    client = open_ssh_client(host)
    channel = None
    try:
        _, stdout, _ = client.exec_command(command, timeout=30)
        channel = stdout.channel
        chunks = []
        size = 0
        deadline = time.monotonic() + 30
        while True:
            if time.monotonic() >= deadline:
                raise TerminalConnectionError("读取容器日志超时")
            if channel.recv_ready():
                chunk = channel.recv(min(65536, MAX_LOG_BYTES + 1 - size))
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_LOG_BYTES:
                    return {"logs": b"".join(chunks)[:MAX_LOG_BYTES].decode("utf-8", errors="replace"), "truncated": True}
                continue
            if channel.exit_status_ready():
                if channel.recv_exit_status() != 0:
                    raise TerminalConnectionError(b"".join(chunks).decode("utf-8", errors="replace")[:1000] or "读取容器日志失败")
                return {"logs": b"".join(chunks).decode("utf-8", errors="replace"), "truncated": False}
            time.sleep(0.01)
    except (OSError, TimeoutError) as error:
        raise TerminalConnectionError(f"读取容器日志失败：{error}") from error
    finally:
        if channel is not None:
            channel.close()
        client.close()
