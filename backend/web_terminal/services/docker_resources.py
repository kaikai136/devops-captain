from .commands import run_one_shot_ssh_command
from .containers import json_lines
from .errors import TerminalConnectionError


DOCKER_RESOURCE_COMMANDS = {
    "images": "docker image ls --no-trunc --format '{{json .}}'",
    "networks": "docker network ls --no-trunc --format '{{json .}}'",
    "volumes": "docker volume ls --format '{{json .}}'",
}


def parse_docker_resources(resource, output):
    rows = []
    images = {}
    for item in json_lines(output):
        if resource == "images":
            identifier = str(item.get("ID", ""))
            if not identifier:
                continue
            if identifier not in images:
                images[identifier] = {
                    "id": identifier, "repositories": [], "tags": [], "references": [],
                    "createdAt": str(item.get("CreatedAt", "")), "size": str(item.get("Size", "")),
                    "diskUsage": str(item.get("DiskUsage") or item.get("Size") or ""),
                    "contentSize": str(item.get("ContentSize") or ""),
                    "extra": str(item.get("Extra") or ""),
                }
                rows.append(images[identifier])
            row = images[identifier]
            repository = str(item.get("Repository") or "")
            tag = str(item.get("Tag") or "")
            reference = f"{repository}:{tag}" if repository and tag else repository
            if reference and reference not in row["references"]:
                row["references"].append(reference)
            for source, target in (("Repository", "repositories"), ("Tag", "tags")):
                value = str(item.get(source, ""))
                if value and value not in row[target]:
                    row[target].append(value)
        elif resource == "networks":
            rows.append({"id": str(item.get("ID", "")), "name": str(item.get("Name", "")), "driver": str(item.get("Driver", "")), "scope": str(item.get("Scope", ""))})
        else:
            rows.append({"name": str(item.get("Name", "")), "driver": str(item.get("Driver", ""))})
    return rows


def get_remote_docker_resources(host, resource):
    command = DOCKER_RESOURCE_COMMANDS[resource]
    try:
        output = run_one_shot_ssh_command(host, command)
    except TerminalConnectionError as error:
        if any(text in str(error).lower() for text in ("not found", "permission denied", "cannot connect", "is the docker daemon running")):
            return {"available": False, resource: [], "total": 0, "reason": "Docker 服务不可用"}
        raise
    rows = parse_docker_resources(resource, output)
    return {"available": True, resource: rows, "total": len(rows)}
