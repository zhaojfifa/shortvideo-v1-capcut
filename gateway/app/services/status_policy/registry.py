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

