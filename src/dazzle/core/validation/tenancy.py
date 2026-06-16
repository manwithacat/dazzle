"""Tenancy partition-key and tenant-host validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from typing import Any

from .. import ir


def validate_tenancy_partition_key(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Verify `tenancy.partition_key` names a field on at least one entity.

    A `tenancy: partition_key: tenant_id` block silently produces an
    un-partitioned runtime if no entity carries that field (found in
    support_tickets during /fuzz).
    """
    errors: list[str] = []
    warnings: list[str] = []

    tenancy = appspec.tenancy
    if tenancy is None or tenancy.isolation is None:
        return errors, warnings
    partition_key = tenancy.isolation.partition_key
    if not partition_key:
        return errors, warnings
    # SHARED_SCHEMA mode is the only one that needs the column to exist on
    # tenanted entities; single-tenant mode has no partition key in use.
    if tenancy.isolation.mode == ir.TenancyMode.SINGLE:
        return errors, warnings

    has_partition_field = any(
        field.name == partition_key for entity in appspec.domain.entities for field in entity.fields
    )
    if not has_partition_field:
        warnings.append(
            f"tenancy.partition_key={partition_key!r} but no entity "
            f"declares a field with that name. Multi-tenancy is "
            f"effectively disabled — data is not partitioned."
        )
    return errors, warnings


# =============================================================================
# tenant_host: validator rules (#1289)
# =============================================================================


def _get_entities(appspec_or_fragment: object) -> list[Any]:
    """Return the entity list from either an AppSpec or a ModuleFragment."""
    entities = getattr(appspec_or_fragment, "entities", None)
    if entities is not None:
        return list(entities)
    domain = getattr(appspec_or_fragment, "domain", None)
    if domain is not None:
        return list(domain.entities)
    return []


def validate_tenant_host_blocks(
    appspec_or_fragment: object,
) -> tuple[list[str], list[str]]:
    """Hard-error rules for tenant_host: blocks (#1289).

    Rules 1-6 from docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md.
    Returns (errors, warnings).
    """
    import importlib.util
    import re

    errors: list[str] = []
    warnings: list[str] = []

    entities = _get_entities(appspec_or_fragment)
    entity_names: set[str] = {e.name for e in entities}

    by_domain: dict[str, list[tuple[int, Any]]] = {}

    for idx, entity in enumerate(entities):
        th = getattr(entity, "tenant_host", None)
        if th is None:
            continue

        # Rule 1: slug_field must name a slug-typed field on the same entity
        match = next((f for f in entity.fields if f.name == th.slug_field), None)
        if match is None:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.slug_field "
                f"{th.slug_field!r} does not match any field on the entity."
            )
        elif getattr(match.type, "kind", None) != ir.FieldTypeKind.SLUG:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.slug_field {th.slug_field!r} "
                f"must point at a `slug:` typed field (got {match.type.kind})."
            )

        # Rule 2: domain must look like a host
        if "." not in th.domain or " " in th.domain:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.domain {th.domain!r} "
                "is not a syntactically valid host."
            )

        # Rule 4: history_entity must exist
        if th.history_entity and th.history_entity not in entity_names:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.history_entity "
                f"{th.history_entity!r} is not declared in this AppSpec."
            )

        # Rule 5: dotted-path templates must resolve to an importable module.
        # We use importlib.util.find_spec (metadata-only, no module execution)
        # after validating that the path is a safe dotted-identifier shape.
        # This avoids dynamic import of user-controlled strings while still
        # catching genuinely missing module paths at validate time.
        _DOTTED_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
        for attr, label in (
            (th.not_found_template, "not_found_template"),
            (th.expired_template, "expired_template"),
        ):
            if attr is None:
                continue
            if ":" not in attr:
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} must be in 'module.path:symbol' format."
                )
                continue
            mod_name, _, sym = attr.partition(":")
            if not _DOTTED_IDENT.match(mod_name) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", sym):
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} contains invalid characters in module path or symbol name."
                )
                continue
            try:
                spec = importlib.util.find_spec(mod_name)
                if spec is None:
                    errors.append(
                        f"Entity {entity.name!r}: tenant_host.{label} "
                        f"{attr!r} could not be imported: No module named {mod_name!r}"
                    )
            except (ModuleNotFoundError, ValueError) as exc:
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} could not be imported: {exc}"
                )

        by_domain.setdefault(th.domain, []).append((idx, entity))

    # Rule 3: when 2+ entities share a domain, each MUST carry distinct order:
    for domain, items in by_domain.items():
        if len(items) < 2:
            continue
        orders = [e.tenant_host.order for _, e in items]
        if any(o is None for o in orders) or len(set(orders)) != len(orders):
            errors.append(
                f"Domain {domain!r}: 2+ entities declare tenant_host on this "
                "domain; each must carry a distinct `order: N` sub-field. "
                f"Entities involved: {[e.name for _, e in items]}."
            )

    # Rule 6: domain-level sub-fields must agree across entities sharing a domain
    for domain, items in by_domain.items():
        if len(items) < 2:
            continue
        for shared in ("cookie_scope", "super_admin_role", "canonical_hosts"):
            values = {
                tuple(getattr(e.tenant_host, shared))
                if shared == "canonical_hosts"
                else getattr(e.tenant_host, shared)
                for _, e in items
            }
            if len(values) > 1:
                errors.append(
                    f"Domain {domain!r}: entities {[e.name for _, e in items]} "
                    f"disagree on tenant_host.{shared} {values!r}; values must be "
                    "identical across all entities sharing the same domain."
                )

    # Warning: print resolution order for multi-entity domains
    for domain, items in by_domain.items():
        if len(items) >= 2:
            ordered = sorted(items, key=lambda t: t[1].tenant_host.order or 0)
            chain = " -> ".join(e.name for _, e in ordered)
            warnings.append(f"Domain {domain!r} resolution order: {chain}")

    # Warning: multiple domains declared — slugs not globally unique
    if len(by_domain) >= 2:
        warnings.append(
            "Multiple tenant_host domains declared "
            f"({sorted(by_domain.keys())}); slugs are not unique across domains."
        )

    return errors, warnings


# ---------------------------------------------------------------------------
# Tenant-hierarchy + membership validator (ADR-0036 D2 + ADR-0037 D2/D5)
# ---------------------------------------------------------------------------


def validate_tenant_hierarchy_and_membership(
    appspec_or_fragment: object,
) -> tuple[list[str], list[str]]:
    """Hard-error rules for `tenant_host.parent:` (ADR-0036) and `membership:` (ADR-0037).

    Hierarchy (ADR-0036 D2):
      H1 — `parent:` names a `ref` field on the same entity whose target is
           another entity that itself declares `tenant_host:` (a tenant kind).
      H2 — the `parent:` chain has no cycle.

    Membership (ADR-0037 D2 / the statically-checkable part of D5):
      M1 — `membership:` is declared only on a `tenant_host` kind.
      M2 — `membership:` is declared only on a hierarchy **root** (`parent` is
           None) — the membership-root == hierarchy-root leg of D5.
      M3 — `membership.roles` (when set) names a field on the same entity.

    The third leg of D5 (membership/hierarchy root == RLS partition root) binds
    at the runtime phase where the RLS-root↔entity mapping is established; it is
    not statically derivable from `tenancy.partition_key` (a column name) alone.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    entities = _get_entities(appspec_or_fragment)
    by_name: dict[str, Any] = {e.name: e for e in entities}

    def _is_tenant_host(entity_name: str) -> bool:
        ent = by_name.get(entity_name)
        return ent is not None and getattr(ent, "tenant_host", None) is not None

    for entity in entities:
        th = getattr(entity, "tenant_host", None)

        # ---- Hierarchy: parent edge -------------------------------------
        parent_field = getattr(th, "parent", None) if th is not None else None
        if parent_field is not None:
            fld = next((f for f in entity.fields if f.name == parent_field), None)
            if fld is None:
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.parent {parent_field!r} "
                    "does not name a field on the entity."
                )
            elif getattr(fld.type, "kind", None) != ir.FieldTypeKind.REF:
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.parent {parent_field!r} "
                    f"must be a `ref` field (got {getattr(fld.type, 'kind', None)})."
                )
            else:
                target = getattr(fld.type, "ref_entity", None)
                if not target or not _is_tenant_host(str(target)):
                    errors.append(
                        f"Entity {entity.name!r}: tenant_host.parent {parent_field!r} "
                        f"points at {target!r}, which is not a `tenant_host` entity. "
                        "A hierarchy parent must itself be a tenant kind."
                    )

        # ---- Membership block placement ---------------------------------
        membership = getattr(entity, "membership", None)
        if membership is not None:
            if th is None:
                errors.append(
                    f"Entity {entity.name!r}: membership: requires this entity to be a "
                    "`tenant_host` kind (membership is declared on the tenant-root kind)."
                )
            elif parent_field is not None:
                errors.append(
                    f"Entity {entity.name!r}: membership: must be declared on the "
                    "tenant-root kind (a hierarchy root with no `parent:`), not on a "
                    f"child kind (this entity's parent is {parent_field!r})."
                )
            roles_field = getattr(membership, "roles", None)
            if roles_field is not None and not any(f.name == roles_field for f in entity.fields):
                errors.append(
                    f"Entity {entity.name!r}: membership.roles {roles_field!r} "
                    "does not name a field on the entity."
                )

    # ---- Hierarchy: cycle detection (H2) --------------------------------
    # Edge: entity -> parent-target entity (via the parent FK's ref_entity).
    parent_of: dict[str, str] = {}
    for entity in entities:
        th = getattr(entity, "tenant_host", None)
        pf = getattr(th, "parent", None) if th is not None else None
        if pf is None:
            continue
        fld = next((f for f in entity.fields if f.name == pf), None)
        target = getattr(getattr(fld, "type", None), "ref_entity", None) if fld else None
        if target:
            parent_of[entity.name] = str(target)
    for start in parent_of:
        seen: set[str] = set()
        node: str | None = start
        while node is not None and node in parent_of:
            if node in seen:
                errors.append(
                    f"Tenant hierarchy has a cycle: the `parent:` chain starting at "
                    f"{start!r} loops back on itself (no entity can be its own ancestor)."
                )
                break
            seen.add(node)
            node = parent_of.get(node)

    return errors, warnings
