from __future__ import annotations

from host_management.models import ManagedHost

from ..models import TerminalFileAudit, TerminalSession


def record_file_audit(
    *,
    operation: str,
    host: ManagedHost,
    user=None,
    session: TerminalSession | None = None,
    path: str = "",
    target_path: str = "",
    size: int = 0,
    protocol: str = "sftp",
    status: str = TerminalFileAudit.STATUS_SUCCESS,
    error_message: str = "",
) -> TerminalFileAudit:
    username = getattr(user, "username", "") if user and getattr(user, "is_authenticated", False) else ""
    operation = normalize_choice(operation, {choice for choice, _label in TerminalFileAudit.OPERATION_CHOICES}, TerminalFileAudit.OPERATION_STAT)
    status = normalize_choice(status, {choice for choice, _label in TerminalFileAudit.STATUS_CHOICES}, TerminalFileAudit.STATUS_FAILED)
    return TerminalFileAudit.objects.create(
        session=session,
        host=host,
        user=user if user and getattr(user, "is_authenticated", False) else None,
        username=username or "anonymous",
        protocol=str(protocol or "sftp")[:20],
        operation=operation,
        path=str(path or ""),
        target_path=str(target_path or ""),
        size=max(0, int(size or 0)),
        status=status,
        error_message=str(error_message or ""),
    )


def normalize_choice(value: str, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default
