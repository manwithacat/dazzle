# DAZZLE Uptime Monitor - FOCUS_METRIC Archetype Example
# Demonstrates single critical metric with minimal supporting context

module uptime_monitor.core

app uptime_monitor "Uptime Monitor"

# Simple entity for service status
entity Service "Service":
  id: uuid pk
  name: str(200) required
  endpoint: str(500) required
  status: enum[up,down,degraded]=up
  uptime_percentage: decimal(5,2)
  last_check: datetime auto_update
  created_at: datetime auto_add

# Workspace with single dominant KPI
# Should trigger FOCUS_METRIC archetype (single KPI signal)
workspace uptime "System Uptime":
  purpose: "Monitor overall system availability"

  # Single critical metric - triggers FOCUS_METRIC with 1 signal
  system_uptime:
    source: Service
    aggregate:
      average_uptime: avg(uptime_percentage)
      total_services: count(Service)
      services_down: count(Service WHERE status = 'down')
