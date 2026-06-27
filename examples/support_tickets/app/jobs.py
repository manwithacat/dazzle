"""Job handlers for support_tickets.

Each `job … run: app.jobs:<fn>` in `dsl/runtime.dsl` resolves to a function
here. The worker invokes them as ``handler(**payload)`` — triggered jobs
receive the entity's fields as keyword args; scheduled (cron) jobs receive an
empty payload. These are worked stubs: they log what they would do, the shape a
real deployment fills in (send a page, enqueue an email, write a metric row).
"""

import logging

logger = logging.getLogger("support_tickets.jobs")


def notify_oncall(**payload: object) -> dict[str, object]:
    """job notify_oncall_critical — page on-call when a critical Ticket is created."""
    ticket_id = payload.get("id")
    priority = payload.get("priority")
    logger.info("notify_oncall: ticket=%s priority=%s — would page on-call", ticket_id, priority)
    return {"paged": True, "ticket_id": ticket_id}


def send_survey(**payload: object) -> dict[str, object]:
    """job send_resolution_survey — email a CSAT survey when a Ticket is resolved."""
    ticket_id = payload.get("id")
    status = payload.get("status")
    logger.info("send_survey: ticket=%s status=%s — would email survey", ticket_id, status)
    return {"survey_sent": True, "ticket_id": ticket_id}


def flag_stale(**payload: object) -> dict[str, object]:
    """job stale_ticket_sweep — hourly cron; flag open tickets idle > 48h."""
    logger.info("flag_stale: sweep run — would flag tickets open > 48h")
    return {"flagged": 0}


def rollup_metrics(**payload: object) -> dict[str, object]:
    """job daily_metrics_rollup — daily cron; aggregate ticket metrics for the dashboard."""
    logger.info("rollup_metrics: daily roll-up — would aggregate ticket metrics")
    return {"rolled_up": True}
