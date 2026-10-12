"""Stable demo persona principal ids (#1626 / #1627).

Shared by the test-mode routes (``/__test__/*``), demo reset-and-load and
the RBAC persona-id validator. Lives in ``core`` so every layer may read it.
"""

# #1626 re-eval: fixed auth user UUIDs so demo jsonl can assign
# Task/Ticket/Invoice rows to the same principals QA capture logs in as.
# Pattern: a1 + persona index in the last hex group (version/variant valid).
STABLE_PERSONA_USER_IDS: dict[str, str] = {
    "member": "a1000000-0000-4000-8000-000000000001",
    "manager": "a1000000-0000-4000-8000-000000000002",
    "admin": "a1000000-0000-4000-8000-000000000003",
    "agent": "a1000000-0000-4000-8000-000000000004",
    "customer": "a1000000-0000-4000-8000-000000000005",
    "requester": "a1000000-0000-4000-8000-000000000006",
    "approver": "a1000000-0000-4000-8000-000000000007",
    "finance": "a1000000-0000-4000-8000-000000000008",
    "auditor": "a1000000-0000-4000-8000-000000000009",
    "user": "a1000000-0000-4000-8000-00000000000a",
    "designer": "a1000000-0000-4000-8000-00000000000b",
    "reviewer": "a1000000-0000-4000-8000-00000000000c",
    # Showcase product personas beyond the core set (#1626 re-eval).
    "tester": "a1000000-0000-4000-8000-00000000000d",
    "engineer": "a1000000-0000-4000-8000-00000000000e",
    "ops_engineer": "a1000000-0000-4000-8000-00000000000f",
    "employee": "a1000000-0000-4000-8000-000000000010",
    "hr_admin": "a1000000-0000-4000-8000-000000000011",
    "tenant_admin": "a1000000-0000-4000-8000-000000000012",
    "finance_admin": "a1000000-0000-4000-8000-000000000013",
}
