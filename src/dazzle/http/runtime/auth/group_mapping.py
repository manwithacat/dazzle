"""IdP group → app role mapping, default-deny (DD-013).

One rule shared by every protocol that asserts groups: SCIM ``/Groups`` membership
(``scim_provisioning.recompute_membership_roles``) and OIDC sign-in. A group the
connection's ``group_mapping`` does not name grants nothing.
"""


def map_groups_to_roles(groups: list[str], group_mapping: dict[str, str]) -> list[str]:
    """Map IdP groups → app roles via the connection's ``group_mapping`` (default-deny).

    Unmapped groups contribute nothing. Returns a de-duplicated, order-preserving role
    list. An empty result means the member gets in with no app roles — the
    ``permit:``/``scope:`` layer then default-denies their actions.
    """
    roles: list[str] = []
    for group in groups:
        role = group_mapping.get(group)
        if role and role not in roles:
            roles.append(role)
    return roles
