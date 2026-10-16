from __future__ import annotations


class TerminalConnectionError(RuntimeError):
    pass


class TerminalFileChangedError(TerminalConnectionError):
    pass
