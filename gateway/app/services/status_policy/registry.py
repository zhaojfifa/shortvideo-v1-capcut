from __future__ import annotations

from .base import StatusPolicy
from .apollo_avatar import ApolloAvatarStatusPolicy


_DEFAULT = StatusPolicy()
_APOLLO_AVATAR = ApolloAvatarStatusPolicy()


def get_policy(kind: str | None) -> StatusPolicy:
    k = (kind or "").strip().lower()
    if k in ("apollo_avatar", "apollo-avatar"):
        return _APOLLO_AVATAR
    return _DEFAULT


def get_status_policy(task: dict | None) -> StatusPolicy:
    if not task:
        return _DEFAULT
    kind = (
        (task.get("kind") if isinstance(task, dict) else None)
        or (task.get("task_kind") if isinstance(task, dict) else None)
        or (task.get("category") if isinstance(task, dict) else None)
        or (task.get("category_key") if isinstance(task, dict) else None)
        or (task.get("platform") if isinstance(task, dict) else None)
    )
    return get_policy(kind)
