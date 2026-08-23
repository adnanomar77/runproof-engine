from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PolicyDenied(PermissionError):
    """Raised when a requested action is not allowed by the run policy."""


@dataclass
class Policy:
    allowed_actions: set[str] = field(default_factory=lambda: {"read", "write_artifact", "execute_python"})
    approval_required: set[str] = field(default_factory=lambda: {"install_package", "network", "upload", "publish", "delete", "shell"})
    denied_actions: set[str] = field(default_factory=set)

    def authorize(self, action: str, *, approved: bool = False, target: str | None = None) -> dict[str, Any]:
        action = str(action)
        if action in self.denied_actions:
            raise PolicyDenied(f"action denied by policy: {action}")
        if action not in self.allowed_actions and action not in self.approval_required:
            raise PolicyDenied(f"action is not declared in policy: {action}")
        if action in self.approval_required and not approved:
            raise PolicyDenied(f"approval required for action: {action}")
        return {"action": action, "target": target, "approved": approved}


def safe_default_policy() -> Policy:
    return Policy()
