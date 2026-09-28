"""Role -> permission matrix. Server-side only; the UI reads the resolved list
from /auth/me to decide what to show, but every endpoint re-checks here.

Roles (stored upper-case in ``memberships.role``):
- OWNER    everything, including billing and managing other owners;
- ADMIN    everything except billing and owner accounts;
- ANALYST  works the data: upload, map, process, review, export;
- VIEWER   read-only access to the organisation's data;
- SENDER   a coverholder/TPA user: no access to the provider's data
           (the sender portal in P8 grants its own, narrower permissions).

Unknown roles (including the retired REVIEWER) get no permissions at all.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"
    DATA_DELETE = "data:delete"
    AUDIT_READ = "audit:read"
    MEMBER_READ = "member:read"
    MEMBER_MANAGE = "member:manage"
    ORG_READ = "org:read"
    ORG_MANAGE = "org:manage"
    BILLING_MANAGE = "billing:manage"
    SENDER_SUBMIT = "sender:submit"


ROLES: tuple[str, ...] = ("OWNER", "ADMIN", "ANALYST", "VIEWER", "SENDER")
ASSIGNABLE_BY_ADMIN: frozenset[str] = frozenset({"ADMIN", "ANALYST", "VIEWER", "SENDER"})

_READ = frozenset({Permission.DATA_READ, Permission.AUDIT_READ, Permission.MEMBER_READ, Permission.ORG_READ})
_WORK = _READ | {Permission.DATA_WRITE}
_ADMIN = _WORK | {Permission.DATA_DELETE, Permission.MEMBER_MANAGE, Permission.ORG_MANAGE}

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "OWNER": frozenset(_ADMIN | {Permission.BILLING_MANAGE}),
    "ADMIN": frozenset(_ADMIN),
    "ANALYST": frozenset(_WORK),
    "VIEWER": frozenset(_READ),
    "SENDER": frozenset({Permission.ORG_READ, Permission.SENDER_SUBMIT}),
}


def permissions_for(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for(role)
