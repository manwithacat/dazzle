# DAZZLE Operations Dashboard - High Signal Count Example
# Demonstrates many signals across multiple entities for complex monitoring

module ops_dashboard.core

app ops_dashboard "Operations Dashboard"

# Server entity
entity Server "Server":
  id: uuid pk
  hostname: str(200) required unique
  ip_address: str(50) required
  status: enum[online,offline,degraded]=online
  cpu_usage: decimal(5,2)
  memory_usage: decimal(5,2)
  last_seen: datetime auto_update
  created_at: datetime auto_add

# Deployment entity
entity Deployment "Deployment":
  id: uuid pk
  app_name: str(200) required
  version: str(50) required
  environment: enum[dev,staging,prod]=dev
  status: enum[pending,running,failed,success]=pending
  started_at: datetime auto_add
  finished_at: datetime optional

# Alert entity
entity Alert "Alert":
  id: uuid pk
  severity: enum[info,warn,err,critical]=warn
  message: str(500) required
  alert_source: str(200) required
  status: enum[new,acknowledged,resolved]=new
  created_at: datetime auto_add
  resolved_at: datetime optional

# Workspace with many signals (8+) - triggers MONITOR_WALL or COMMAND_CENTER
# For COMMAND_CENTER: needs 5+ signals, 3+ kinds, expert persona (not inferrable)
# Without persona, will get MONITOR_WALL with high signal count
workspace operations "Operations Center":
  purpose: "Comprehensive system monitoring and operations"

  # Critical metrics KPI
  system_health:
    source: Server
    aggregate:
      total_servers: count(Server)
      online_servers: count(Server WHERE status = 'online')
      avg_cpu: avg(cpu_usage)

  # Recent deployments
  recent_deploys:
    source: Deployment
    limit: 5

  # Failed deployments
  failed_deploys:
    source: Deployment
    limit: 3

  # Critical alerts
  critical_alerts:
    source: Alert
    limit: 5

  # All servers table
  all_servers:
    source: Server

  # Active deployments
  active_deployments:
    source: Deployment

  # Alert feed
  alert_feed:
    source: Alert
    limit: 10

  # Deployment stats
  deployment_stats:
    source: Deployment
    aggregate:
      total_today: count(Deployment)
      failed_today: count(Deployment WHERE status = 'failed')
