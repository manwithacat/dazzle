# Parser Reference: Events and Subscriptions
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# EVENT MODEL:
# - [x] event_model:
# - [x] topic name:
# - [x] retention: Nd (duration)
# - [x] partition_key: field
# - [x] event Name:
# - [x] topic: topic_name
# - [x] payload: EntityName
# - [x] fields: block with custom fields
#
# SUBSCRIBE:
# - [x] subscribe topic as group_id:
# - [x] subscribe topic.subtopic as group_id:
# - [x] on EventName:
# - [x] call service name
# - [x] call service name.method
# - [x] when condition:
#
# PROJECT:
# - [x] project Name from topic:
# - [x] on EventName:
# - [x] upsert with key_field, field=value
# - [x] update field=value
# - [x] delete
#
# PUBLISH (entity-level):
# - [x] publish EventName when created
# - [x] publish EventName when updated
# - [x] publish EventName when deleted
# - [x] publish EventName when field changed
#
# =============================================================================

module pra.events

use pra
use pra.entities
use pra.relationships

# =============================================================================
# EVENT MODEL: BASIC TOPIC
# =============================================================================

event_model:
  # Basic topic with retention
  topic orders:
    retention: 30
    partition_key: order_id

  # Topic with short retention
  topic alerts:
    retention: 7
    partition_key: alert_id

  # Topic with long retention (weeks)
  topic audit:
    retention: 364
    partition_key: entity_id

  # Basic event with payload
  event OrderCreated:
    topic: orders
    payload: OrderWithTotals

  # Event with custom fields
  event OrderStatusChanged:
    topic: orders
    fields:
      order_id: uuid required
      old_status: str required
      new_status: str required
      changed_by: uuid required
      changed_at: datetime required
      reason: str

  # Event with just topic reference
  event OrderCancelled:
    topic: orders
    payload: OrderWithTotals

  # Alert events
  event AlertRaised:
    topic: alerts
    fields:
      alert_id: uuid required
      severity: str required
      message: str required
      source: str required
      timestamp: datetime required

  event AlertResolved:
    topic: alerts
    fields:
      alert_id: uuid required
      resolved_by: uuid
      resolution: str

  # Audit event
  event AuditEntry:
    topic: audit
    payload: AuditLog

# =============================================================================
# SUBSCRIBE: BASIC
# =============================================================================

subscribe orders as order_notification_handler:
  on OrderCreated:
    call service send_order_confirmation

  on OrderStatusChanged:
    call service send_status_update

  on OrderCancelled:
    call service send_cancellation_email

# =============================================================================
# SUBSCRIBE: DOTTED TOPIC
# =============================================================================

subscribe dazzle.events.orders as app_order_handler:
  on OrderCreated:
    call service order_service.handle_new_order

  on OrderStatusChanged:
    call service order_service.handle_status_change

# =============================================================================
# SUBSCRIBE: WITH SERVICE METHOD
# =============================================================================

subscribe alerts as alert_handler:
  on AlertRaised:
    call service notification_service.send_alert

  on AlertResolved:
    call service notification_service.send_resolution

# =============================================================================
# SUBSCRIBE: WITH CONDITIONAL HANDLERS
# =============================================================================

subscribe orders as conditional_handler:
  on OrderStatusChanged:
    when new_status = shipped:
      call service send_shipping_notification

  on OrderCreated:
    call service log_new_order

# =============================================================================
# PROJECT: BASIC UPSERT
# =============================================================================

project OrderDashboard from orders:
  on OrderCreated:
    upsert with order_id, status=pending

  on OrderStatusChanged:
    update status=new_status

# =============================================================================
# PROJECT: WITH DELETE
# =============================================================================

project ActiveOrders from orders:
  on OrderCreated:
    upsert with order_id

  on OrderCancelled:
    delete

  on OrderStatusChanged:
    update status=new_status, updated_at=changed_at

# =============================================================================
# PROJECT: DOTTED TOPIC
# =============================================================================

project AlertMetrics from dazzle.events.alerts:
  on AlertRaised:
    upsert with alert_id, severity=severity, active=true

  on AlertResolved:
    update active=false, resolved_at=timestamp

# =============================================================================
# PROJECT: MULTIPLE HANDLERS
# =============================================================================

project AuditHistory from audit:
  on AuditEntry:
    upsert with entity_id, action=action, actor=actor

# =============================================================================
# ENTITY WITH PUBLISH DECLARATIONS
# =============================================================================

entity TrackedOrder "Tracked Order":
  intent: "Order entity with comprehensive event publishing"
  domain: commerce

  id: uuid pk
  order_number: str(50) unique required
  status: enum[pending,confirmed,processing,shipped,delivered,cancelled]=pending
  assigned_to: uuid optional
  priority: enum[low,normal,high,urgent]=normal
  total: decimal(15,2)=0.00

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Lifecycle events
  publish TrackedOrderCreated when created
  publish TrackedOrderUpdated when updated
  publish TrackedOrderDeleted when deleted

  # Field change events
  publish TrackedOrderStatusChanged when status changed
  publish TrackedOrderAssigned when assigned_to changed
  publish TrackedOrderPriorityChanged when priority changed

entity TrackedTask "Tracked Task":
  intent: "Task entity demonstrating publish declarations"
  domain: project_management

  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,review,done]=todo
  assignee: uuid optional
  reviewer: uuid optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Lifecycle events
  publish TaskCreated when created
  publish TaskUpdated when updated

  # Field change events
  publish TaskStatusChanged when status changed
  publish TaskAssigneeChanged when assignee changed
  publish TaskReviewerChanged when reviewer changed

entity TrackedDocument "Tracked Document":
  intent: "Document with all publish trigger types"
  domain: documentation

  id: uuid pk
  title: str(200) required
  content: text required
  version: int=1
  status: enum[draft,review,approved,published,archived]=draft
  author: uuid required
  approver: uuid optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # All trigger types demonstrated
  publish DocumentCreated when created
  publish DocumentUpdated when updated
  publish DocumentDeleted when deleted
  publish DocumentStatusChanged when status changed
  publish DocumentVersionBumped when version changed
  publish DocumentApproved when approver changed

# =============================================================================
# COMPLEX EVENT MODEL
# =============================================================================

event_model:
  # E-commerce events topic
  topic ecommerce:
    retention: 90
    partition_key: customer_id

  # User activity topic
  topic user_activity:
    retention: 30
    partition_key: user_id

  # System events
  topic system:
    retention: 14
    partition_key: component

  # Cart events
  event CartCreated:
    topic: ecommerce
    fields:
      cart_id: uuid required
      customer_id: uuid required
      created_at: datetime required

  event CartItemAdded:
    topic: ecommerce
    fields:
      cart_id: uuid required
      product_id: uuid required
      quantity: int required
      unit_price: decimal required

  event CartItemRemoved:
    topic: ecommerce
    fields:
      cart_id: uuid required
      product_id: uuid required

  event CartAbandoned:
    topic: ecommerce
    fields:
      cart_id: uuid required
      customer_id: uuid required
      abandoned_at: datetime required
      cart_value: decimal required

  # User activity events
  event UserLoggedIn:
    topic: user_activity
    fields:
      user_id: uuid required
      ip_address: str
      user_agent: str
      timestamp: datetime required

  event UserLoggedOut:
    topic: user_activity
    fields:
      user_id: uuid required
      session_duration: int
      timestamp: datetime required

  event PageViewed:
    topic: user_activity
    fields:
      user_id: uuid required
      page_path: str required
      referrer: str
      timestamp: datetime required

  # System events
  event ServiceStarted:
    topic: system
    fields:
      component: str required
      version: str required
      environment: str required
      started_at: datetime required

  event ServiceStopped:
    topic: system
    fields:
      component: str required
      stopped_at: datetime required
      reason: str

  event HealthCheckFailed:
    topic: system
    fields:
      component: str required
      check_name: str required
      error_message: str required
      timestamp: datetime required

# =============================================================================
# COMPLEX SUBSCRIPTIONS
# =============================================================================

subscribe ecommerce as cart_analytics:
  on CartCreated:
    call service analytics.track_cart_created

  on CartItemAdded:
    call service analytics.track_item_added

  on CartItemRemoved:
    call service analytics.track_item_removed

  on CartAbandoned:
    call service remarketing.trigger_abandoned_cart_email

subscribe user_activity as user_tracking:
  on UserLoggedIn:
    call service session.start_session

  on UserLoggedOut:
    call service session.end_session

  on PageViewed:
    call service analytics.track_page_view

subscribe system as ops_monitoring:
  on ServiceStarted:
    call service monitoring.log_service_start

  on ServiceStopped:
    call service monitoring.log_service_stop

  on HealthCheckFailed:
    call service alerting.raise_health_alert

# =============================================================================
# COMPLEX PROJECTIONS
# =============================================================================

project CartAnalytics from ecommerce:
  on CartCreated:
    upsert with cart_id, customer_id=customer_id, status=active

  on CartItemAdded:
    update item_count=item_count, last_updated=timestamp

  on CartAbandoned:
    update status=abandoned, abandoned_at=abandoned_at

project SessionMetrics from user_activity:
  on UserLoggedIn:
    upsert with user_id, session_start=timestamp, active=true

  on UserLoggedOut:
    update session_end=timestamp, duration=session_duration, active=false

project ServiceHealth from system:
  on ServiceStarted:
    upsert with component, status=running, started_at=started_at

  on ServiceStopped:
    update status=stopped, stopped_at=stopped_at

  on HealthCheckFailed:
    update status=unhealthy, last_error=error_message
