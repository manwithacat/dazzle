# Parser Reference: Processes and Schedules
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# PROCESS BASICS:
# - [x] process name "Title":
# - [x] process name: (no title)
# - [x] description: "..." (docstring style)
# - [x] implements: [story_ids]
#
# PROCESS TRIGGER:
# - [x] trigger: when: entity EntityName created
# - [x] trigger: when: entity EntityName updated
# - [x] trigger: when: entity EntityName deleted
# - [x] trigger: when: entity EntityName status -> state
# - [x] trigger: when: entity EntityName status from_state -> to_state
# - [x] trigger: when: manual
# - [x] trigger: when: signal signal_name
# - [x] trigger: when: process process_name completed
#
# PROCESS INPUT/OUTPUT:
# - [x] input: block with fields
# - [x] input field: type required
# - [x] input field: type = default
# - [x] output: block with fields
#
# PROCESS STEPS:
# - [x] - step name: with service
# - [x] - step name: with channel/message (SEND)
# - [x] - step name: with wait: duration
# - [x] - step name: with wait: signal_name
# - [x] - step name: with human_task
# - [x] - step name: with subprocess
# - [x] - step name: with condition/on_true/on_false
# - [x] - parallel block
# - [x] inputs: mappings
# - [x] output: mapping
# - [x] timeout: duration
# - [x] retry: block (max_attempts, backoff, interval)
# - [x] on_success: step_name
# - [x] on_failure: step_name
# - [x] compensate: handler_name
#
# HUMAN TASK:
# - [x] surface: name
# - [x] entity: path
# - [x] assignee_role: role
# - [x] assignee: expression
# - [x] timeout: duration
# - [x] outcomes: block
# - [x] outcome: label, goto, sets, confirm, style
#
# COMPENSATIONS:
# - [x] compensations: block
# - [x] - name: with service, inputs, timeout
#
# PROCESS POLICIES:
# - [x] timeout: duration (s, m, h, d)
# - [x] overlap: skip
# - [x] overlap: queue
# - [x] overlap: cancel_previous
# - [x] overlap: allow
#
# PROCESS EVENTS:
# - [x] emits: on_start, on_complete, on_failure
#
# SCHEDULE BASICS:
# - [x] schedule name "Title":
# - [x] cron: "expression"
# - [x] interval: duration
# - [x] timezone: "tz"
# - [x] catch_up: true/false
# - [x] overlap: policy
# - [x] steps: block
# - [x] timeout: duration
# - [x] emits: block
#
# RETRY BACKOFF STRATEGIES:
# - [x] backoff: fixed
# - [x] backoff: exponential
# - [x] backoff: linear
#
# PARALLEL POLICIES:
# - [x] on_any_failure: fail_fast
# - [x] on_any_failure: wait_all
# - [x] on_any_failure: rollback
#
# =============================================================================

module pra.processes

use pra
use pra.entities
use pra.services
use pra.surfaces

# =============================================================================
# PROCESS: BASIC WITH ENTITY TRIGGER
# =============================================================================

process order_fulfillment "Order Fulfillment":
  "Processes new orders through inventory check, payment, and shipping"

  implements: [ST-001, ST-002]

  trigger:
    when: entity Order status -> confirmed

  input:
    order_id: uuid required
    customer_id: uuid required
    priority: str = "normal"

  output:
    tracking_number: str
    estimated_delivery: date

  steps:
    - step check_inventory:
        service: validate_order
        timeout: 30s

    - step process_payment:
        service: process_payment
        timeout: 2m
        retry:
          max_attempts: 3
          backoff: exponential
          interval: 5s
        compensate: refund_payment

    - step create_shipment:
        service: sync_to_external
        timeout: 1m
        on_success: notify_customer
        on_failure: escalate_to_support

    - step notify_customer:
        channel: notifications
        message: OrderShippedNotification
        timeout: 10s

  compensations:
    - refund_payment:
        service: process_payment
        inputs:
          - order_id -> order_id
          - action -> refund
        timeout: 1m

  timeout: 2h
  overlap: skip

  emits:
    on_start: OrderFulfillmentStarted
    on_complete: OrderFulfillmentCompleted
    on_failure: OrderFulfillmentFailed

# =============================================================================
# PROCESS: ENTITY CREATED TRIGGER
# =============================================================================

process new_user_onboarding "New User Onboarding":
  "Welcome sequence for new users"

  trigger:
    when: entity Employee created

  input:
    user_id: uuid required
    email: str(255) required
    department: str

  steps:
    - step send_welcome:
        channel: notifications
        message: WelcomeEmail
        timeout: 30s

    - step setup_workspace:
        service: simple_operation
        timeout: 1m

    - step assign_mentor:
        service: auto_assign_task
        timeout: 30s
        inputs:
          - department -> department
          - task_type -> mentorship

  timeout: 30m

# =============================================================================
# PROCESS: ENTITY UPDATED TRIGGER
# =============================================================================

process inventory_sync "Inventory Sync":
  trigger:
    when: entity Product updated

  steps:
    - step sync_inventory:
        service: sync_to_external
        timeout: 1m

  timeout: 5m
  overlap: queue

# =============================================================================
# PROCESS: ENTITY DELETED TRIGGER
# =============================================================================

process cleanup_deleted_account "Cleanup Deleted Account":
  trigger:
    when: entity Employee deleted

  steps:
    - step archive_data:
        service: simple_operation
        timeout: 5m

    - step revoke_access:
        service: simple_operation
        timeout: 1m

  timeout: 30m

# =============================================================================
# PROCESS: STATUS TRANSITION WITH FROM AND TO
# =============================================================================

process escalate_overdue "Escalate Overdue Tasks":
  trigger:
    when: entity Task status pending -> overdue

  input:
    task_id: uuid required

  steps:
    - step notify_manager:
        channel: notifications
        message: EscalationNotification
        timeout: 30s

    - step update_priority:
        service: simple_operation
        timeout: 30s

  timeout: 10m

# =============================================================================
# PROCESS: MANUAL TRIGGER
# =============================================================================

process manual_data_export "Manual Data Export":
  trigger:
    when: manual

  input:
    report_type: str(255) required "Type of report to generate"
    date_from: date required
    date_to: date required
    format: str = "csv"

  output:
    export_url: str
    record_count: int

  steps:
    - step validate_dates:
        service: validate_order
        timeout: 10s

    - step generate_report:
        service: generate_report
        timeout: 10m

    - step upload_to_storage:
        service: sync_to_external
        timeout: 2m

  timeout: 30m

# =============================================================================
# PROCESS: SIGNAL TRIGGER
# =============================================================================

process handle_payment_webhook "Handle Payment Webhook":
  trigger:
    when: signal payment_received

  input:
    payment_id: uuid required
    amount: str(255) required
    currency: str(255) required

  steps:
    - step validate_payment:
        service: validate_order
        timeout: 30s

    - step update_invoice:
        service: simple_operation
        timeout: 30s

  timeout: 5m

# =============================================================================
# PROCESS: PROCESS COMPLETED TRIGGER
# =============================================================================

process post_fulfillment_survey "Post-Fulfillment Survey":
  trigger:
    when: process order_fulfillment completed

  steps:
    - step wait_for_delivery:
        wait: 3d

    - step send_survey:
        channel: notifications
        message: SurveyRequest
        timeout: 30s

  timeout: 7d

# =============================================================================
# PROCESS: WITH WAIT STEPS
# =============================================================================

process delayed_notification "Delayed Notification":
  trigger:
    when: entity Task created

  steps:
    - step initial_notification:
        channel: notifications
        message: TaskCreatedNotification
        timeout: 30s

    - step wait_period:
        wait: 1h

    - step reminder:
        channel: notifications
        message: TaskReminderNotification
        timeout: 30s

    - step wait_for_signal:
        wait: task_completed

    - step final_notification:
        channel: notifications
        message: TaskCompletedNotification
        timeout: 30s

  timeout: 24h

# =============================================================================
# PROCESS: WITH HUMAN TASK
# =============================================================================

process expense_approval "Expense Report Approval":
  implements: [EXP-001]

  trigger:
    when: entity Invoice status -> pending_approval

  input:
    expense_id: uuid required
    submitter_id: uuid required
    amount: str(255) required

  steps:
    - step validate_expense:
        service: validate_order
        timeout: 30s

    - step manager_review:
        human_task:
          surface: invoice_list
          entity: Invoice
          assignee_role: manager
          timeout: 3d
          outcomes:
            - approve "Approve Expense":
                label: "Approve"
                goto: process_reimbursement
                sets:
                  - Invoice.status -> approved
                style: primary

            - reject "Reject Expense":
                label: "Reject"
                goto: notify_rejection
                sets:
                  - Invoice.status -> rejected
                confirm: "Are you sure you want to reject this expense?"
                style: danger

            - request_info "Request Information":
                label: "Need More Info"
                goto: wait_for_info
                sets:
                  - Invoice.status -> needs_info

    - step wait_for_info:
        wait: additional_info_provided

    - step process_reimbursement:
        service: process_payment
        timeout: 2m

    - step notify_rejection:
        channel: notifications
        message: ExpenseRejectedNotification
        timeout: 30s

  timeout: 7d

# =============================================================================
# PROCESS: WITH SUBPROCESS
# =============================================================================

process complex_order "Complex Order Processing":
  trigger:
    when: entity Order status -> submitted

  steps:
    - step validate:
        service: validate_order
        timeout: 30s

    - step fulfill_order:
        subprocess: order_fulfillment
        timeout: 4h

    - step post_processing:
        service: simple_operation
        timeout: 1m

  timeout: 8h

# =============================================================================
# PROCESS: WITH CONDITION
# =============================================================================

process conditional_routing "Conditional Routing":
  trigger:
    when: entity Task created

  input:
    task_id: uuid required
    priority: str(255) required

  steps:
    - step check_priority:
        condition: priority = urgent
        on_true: expedite
        on_false: standard_processing

    - step expedite:
        service: simple_operation
        timeout: 1m
        on_success: notify_urgent

    - step standard_processing:
        service: simple_operation
        timeout: 5m

    - step notify_urgent:
        channel: notifications
        message: UrgentTaskNotification
        timeout: 30s

  timeout: 1h

# =============================================================================
# PROCESS: WITH PARALLEL STEPS
# =============================================================================

process parallel_notifications "Parallel Notifications":
  trigger:
    when: entity Order status -> confirmed

  steps:
    - parallel notify_all:
        - step notify_customer:
            channel: notifications
            message: OrderConfirmedCustomer
            timeout: 30s

        - step notify_warehouse:
            channel: notifications
            message: OrderConfirmedWarehouse
            timeout: 30s

        - step notify_shipping:
            channel: notifications
            message: OrderConfirmedShipping
            timeout: 30s

        on_any_failure: fail_fast

    - step log_completion:
        service: simple_operation
        timeout: 10s

  timeout: 5m

# =============================================================================
# PROCESS: WITH PARALLEL WAIT_ALL
# =============================================================================

process parallel_validation "Parallel Validation":
  trigger:
    when: entity Invoice created

  steps:
    - parallel validate_all:
        - step validate_customer:
            service: validate_order
            timeout: 30s

        - step validate_products:
            service: validate_order
            timeout: 30s

        - step validate_payment_method:
            service: validate_order
            timeout: 30s

        on_any_failure: wait_all

    - step summarize:
        service: simple_operation
        timeout: 30s

  timeout: 5m

# =============================================================================
# PROCESS: WITH PARALLEL ROLLBACK
# =============================================================================

process parallel_saga "Parallel Saga":
  trigger:
    when: manual

  steps:
    - parallel execute_all:
        - step reserve_inventory:
            service: simple_operation
            timeout: 1m
            compensate: release_inventory

        - step reserve_payment:
            service: process_payment
            timeout: 1m
            compensate: release_payment

        on_any_failure: rollback

    - step finalize:
        service: simple_operation
        timeout: 30s

  compensations:
    - release_inventory:
        service: simple_operation
        timeout: 1m

    - release_payment:
        service: process_payment
        timeout: 1m

  timeout: 10m

# =============================================================================
# PROCESS: ALL OVERLAP POLICIES
# =============================================================================

process overlap_skip "Skip Overlap":
  trigger:
    when: manual
  overlap: skip
  steps:
    - step work:
        service: simple_operation
        timeout: 1m
  timeout: 5m

process overlap_queue "Queue Overlap":
  trigger:
    when: manual
  overlap: queue
  steps:
    - step work:
        service: simple_operation
        timeout: 1m
  timeout: 5m

process overlap_cancel "Cancel Previous":
  trigger:
    when: manual
  overlap: cancel_previous
  steps:
    - step work:
        service: simple_operation
        timeout: 1m
  timeout: 5m

process overlap_allow "Allow Concurrent":
  trigger:
    when: manual
  overlap: allow
  steps:
    - step work:
        service: simple_operation
        timeout: 1m
  timeout: 5m

# =============================================================================
# PROCESS: ALL RETRY BACKOFF STRATEGIES
# =============================================================================

process retry_strategies "Retry Strategy Demo":
  trigger:
    when: manual

  steps:
    - step fixed_retry:
        service: simple_operation
        timeout: 30s
        retry:
          max_attempts: 5
          backoff: fixed
          interval: 10s

    - step exponential_retry:
        service: simple_operation
        timeout: 30s
        retry:
          max_attempts: 3
          backoff: exponential
          interval: 1s

    - step linear_retry:
        service: simple_operation
        timeout: 30s
        retry:
          max_attempts: 4
          backoff: linear
          interval: 5s

  timeout: 10m

# =============================================================================
# PROCESS: WITH INPUT/OUTPUT MAPPINGS
# =============================================================================

process data_transformation "Data Transformation":
  trigger:
    when: manual

  input:
    source_id: uuid required
    target_format: str(255) required

  output:
    result_id: str
    success: bool

  steps:
    - step extract:
        service: simple_operation
        timeout: 2m
        inputs:
          - source_id -> id
          - target_format -> format
        output: extracted_data

    - step transform:
        service: simple_operation
        timeout: 5m
        inputs:
          - extracted_data -> input_data
        output: transformed_data

    - step load:
        service: sync_to_external
        timeout: 2m
        inputs:
          - transformed_data -> payload

  timeout: 15m

# =============================================================================
# PROCESS: COMPLEX HUMAN TASK WITH ASSIGNEE EXPRESSION
# =============================================================================

process approval_chain "Multi-Level Approval":
  trigger:
    when: entity Invoice status -> pending_approval

  steps:
    - step level_1_approval:
        human_task:
          surface: invoice_list
          assignee: Invoice.submitted_by.manager
          timeout: 2d
          outcomes:
            - approve "Approve":
                goto: check_amount
            - reject "Reject":
                goto: complete
                sets:
                  - Invoice.status -> rejected

    - step check_amount:
        condition: Invoice.total > 10000
        on_true: level_2_approval
        on_false: finalize

    - step level_2_approval:
        human_task:
          surface: invoice_list
          assignee_role: finance_director
          timeout: 3d
          outcomes:
            - approve "Final Approve":
                goto: finalize
                sets:
                  - Invoice.status -> approved
            - reject "Final Reject":
                goto: complete
                sets:
                  - Invoice.status -> rejected

    - step finalize:
        service: simple_operation
        timeout: 1m

  timeout: 14d

# =============================================================================
# SCHEDULE: BASIC WITH CRON
# =============================================================================

schedule daily_report "Daily Report Generation":
  "Generates daily summary reports every morning"

  implements: [RPT-001]

  cron: "0 8 * * *"
  timezone: "Europe/London"

  steps:
    - step generate:
        service: generate_report
        timeout: 10m

    - step distribute:
        channel: notifications
        message: DailyReportEmail
        timeout: 1m

  timeout: 30m

# =============================================================================
# SCHEDULE: WITH INTERVAL
# =============================================================================

schedule health_check "System Health Check":
  interval: 5m

  steps:
    - step check_services:
        service: simple_operation
        timeout: 30s

    - step check_database:
        service: simple_operation
        timeout: 30s

  timeout: 2m

# =============================================================================
# SCHEDULE: WITH ALL OPTIONS
# =============================================================================

schedule full_sync "Full Data Sync":
  "Weekly full synchronization with external systems"

  implements: [SYNC-001]

  cron: "0 2 * * 0"
  timezone: "America/New_York"
  catch_up: true
  overlap: skip

  steps:
    - step sync_customers:
        service: sync_to_external
        timeout: 30m
        retry:
          max_attempts: 3
          backoff: exponential

    - step sync_products:
        service: sync_to_external
        timeout: 30m

    - step sync_orders:
        service: sync_to_external
        timeout: 1h

    - step verify:
        service: validate_order
        timeout: 10m

  timeout: 3h

  emits:
    on_start: FullSyncStarted
    on_complete: FullSyncCompleted
    on_failure: FullSyncFailed

# =============================================================================
# SCHEDULE: CATCH UP DISABLED
# =============================================================================

schedule realtime_metrics "Real-time Metrics":
  interval: 1m
  catch_up: false
  overlap: skip

  steps:
    - step collect:
        service: simple_operation
        timeout: 30s

  timeout: 45s

# =============================================================================
# SCHEDULE: WITH QUEUE OVERLAP
# =============================================================================

schedule batch_processing "Batch Processing":
  cron: "*/15 * * * *"
  overlap: queue

  steps:
    - step process_batch:
        service: simple_operation
        timeout: 10m

  timeout: 12m

# =============================================================================
# SCHEDULE: HOURLY CLEANUP
# =============================================================================

schedule hourly_cleanup "Hourly Cleanup":
  cron: "0 * * * *"
  timezone: "UTC"

  steps:
    - step cleanup_temp:
        service: simple_operation
        timeout: 5m

    - step cleanup_logs:
        service: simple_operation
        timeout: 5m

  timeout: 15m

# =============================================================================
# SCHEDULE: COMPLEX WITH PARALLEL
# =============================================================================

schedule comprehensive_backup "Comprehensive Backup":
  cron: "0 3 * * *"
  timezone: "UTC"
  catch_up: false
  overlap: cancel_previous

  steps:
    - parallel backup_all:
        - step backup_database:
            service: simple_operation
            timeout: 1h

        - step backup_files:
            service: simple_operation
            timeout: 30m

        - step backup_configs:
            service: simple_operation
            timeout: 5m

        on_any_failure: wait_all

    - step verify_backups:
        service: validate_order
        timeout: 15m

    - step notify_completion:
        channel: notifications
        message: BackupCompleteNotification
        timeout: 30s

  timeout: 2h

  emits:
    on_complete: BackupCompleted
    on_failure: BackupFailed
