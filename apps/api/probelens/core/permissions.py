from enum import StrEnum

from probelens.models.enums import Role


class Permission(StrEnum):
    view = "view"
    run_analytics = "run_analytics"
    manage_investigations = "manage_investigations"
    manage_experiments = "manage_experiments"
    decide_experiments = "decide_experiments"
    manage_releases = "manage_releases"
    manage_ops = "manage_ops"
    manage_decisions = "manage_decisions"
    use_analyst = "use_analyst"
    manage_users = "manage_users"


_ANALYST = {
    Permission.view,
    Permission.run_analytics,
    Permission.manage_investigations,
    Permission.use_analyst,
}
_PM = _ANALYST | {
    Permission.manage_experiments,
    Permission.decide_experiments,
    Permission.manage_releases,
    Permission.manage_ops,
    Permission.manage_decisions,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.viewer: frozenset({Permission.view, Permission.run_analytics}),
    Role.analyst: frozenset(_ANALYST),
    Role.pm: frozenset(_PM),
    Role.admin: frozenset(set(Permission)),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
