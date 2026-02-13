#!/usr/bin/env python3
"""Test parser implementation."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

# Test entity parsing
test_dsl = """
module test.core

app test_app "Test Application"

entity User "User":
  id: uuid pk
  email: email unique required
  name: str(120) required
  age: int optional
  created_at: datetime auto_add

  index email
  unique email

entity Post "Post":
  id: uuid pk
  author: ref User required
  title: str(200) required
  content: text
  status: enum[draft,published,archived]=draft
  views: int=0
  metadata: json

  index author
"""


def main():
    print("Testing lexer and parser...")
    print("=" * 60)

    module_name, app_name, app_title, _, uses, fragment = parse_dsl(test_dsl, Path("test.dsl"))

    print(f"Module: {module_name}")
    print(f"App: {app_name} - {app_title}")
    print(f"Uses: {uses}")
    print()

    print(f"Entities parsed: {len(fragment.entities)}")
    for entity in fragment.entities:
        print(f"\n  Entity: {entity.name} ({entity.title})")
        print(f"    Fields: {len(entity.fields)}")
        for field in entity.fields:
            print(
                f"      - {field.name}: {field.type.kind.value} "
                + f"(modifiers: {[m.value for m in field.modifiers]}, "
                + f"default: {field.default})"
            )
        print(f"    Constraints: {len(entity.constraints)}")
        for constraint in entity.constraints:
            print(f"      - {constraint.kind.value}: {constraint.fields}")

    print("\n" + "=" * 60)
    print("✅ Parser test passed!")


class TestFieldTypes:
    """Tests for field type parsing (v0.9.5)."""

    def test_money_field_default_currency(self):
        """Test money field with default GBP currency."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk
  total: money required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        invoice = fragment.entities[0]
        total_field = next(f for f in invoice.fields if f.name == "total")

        assert total_field.type.kind.value == "money"
        assert total_field.type.currency_code == "GBP"

    def test_money_field_custom_currency(self):
        """Test money field with custom currency."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk
  total: money(USD) required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        invoice = fragment.entities[0]
        total_field = next(f for f in invoice.fields if f.name == "total")

        assert total_field.type.kind.value == "money"
        assert total_field.type.currency_code == "USD"

    def test_file_field(self):
        """Test file field type."""
        dsl = """
module test.core
app MyApp "My App"

entity Document "Document":
  id: uuid pk
  attachment: file
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        doc = fragment.entities[0]
        attachment_field = next(f for f in doc.fields if f.name == "attachment")

        assert attachment_field.type.kind.value == "file"

    def test_url_field(self):
        """Test url field type."""
        dsl = """
module test.core
app MyApp "My App"

entity Link "Link":
  id: uuid pk
  target: url required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        link = fragment.entities[0]
        target_field = next(f for f in link.fields if f.name == "target")

        assert target_field.type.kind.value == "url"

    def test_has_many_via_junction(self):
        """Test many-to-many relationship via junction table."""
        dsl = """
module test.core
app MyApp "My App"

entity Client "Client":
  id: uuid pk
  name: str(200) required
  contacts: has_many Contact via ClientContact

entity Contact "Contact":
  id: uuid pk
  email: email required

entity ClientContact "Client Contact":
  id: uuid pk
  client: ref Client
  contact: ref Contact
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        client = fragment.entities[0]
        contacts_field = next(f for f in client.fields if f.name == "contacts")

        assert contacts_field.type.kind.value == "has_many"
        assert contacts_field.type.ref_entity == "Contact"
        assert contacts_field.type.via_entity == "ClientContact"


class TestV025KeywordsAsIdentifiers:
    """Tests that v0.25.0 keywords can be used as enum values and identifiers."""

    def test_webhook_as_enum_value(self):
        """v0.25.0 keywords (webhook, approval, sla) usable as enum values."""
        dsl = """
module test.core
app MyApp "My App"

entity Event "Event":
  id: uuid pk
  actor_type: enum[system, user, webhook] = system
  source: enum[manual, approval, sla] = manual
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        event = fragment.entities[0]
        actor_field = next(f for f in event.fields if f.name == "actor_type")
        assert "webhook" in actor_field.type.enum_values

        source_field = next(f for f in event.fields if f.name == "source")
        assert "approval" in source_field.type.enum_values
        assert "sla" in source_field.type.enum_values

    def test_enum_keyword_in_module_name(self):
        """The 'enum' keyword can appear in module names."""
        dsl = """
module test.enum.types
app MyApp "My App"

entity Task "Task":
  id: uuid pk
"""
        module_name, _, _, _, _, _ = parse_dsl(dsl, Path("test.dsl"))
        assert module_name == "test.enum.types"


class TestWorkspaceDisplayModes:
    """Tests for workspace display mode parsing (v0.9.5)."""

    def test_kanban_display_mode(self):
        """Test kanban display mode."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk
  status: enum[todo, in_progress, done]

workspace task_board "Task Board":
  tasks:
    source: Task
    display: kanban
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        workspace = fragment.workspaces[0]
        region = workspace.regions[0]

        assert region.display.value == "kanban"

    def test_bar_chart_display_mode(self):
        """Test bar_chart display mode."""
        dsl = """
module test.core
app MyApp "My App"

entity Sale "Sale":
  id: uuid pk
  amount: decimal(10,2)

workspace sales_dashboard "Sales Dashboard":
  chart:
    source: Sale
    display: bar_chart
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        workspace = fragment.workspaces[0]
        region = workspace.regions[0]

        assert region.display.value == "bar_chart"

    def test_funnel_chart_display_mode(self):
        """Test funnel_chart display mode."""
        dsl = """
module test.core
app MyApp "My App"

entity Lead "Lead":
  id: uuid pk
  stage: enum[awareness, interest, decision, action]

workspace pipeline "Pipeline":
  funnel:
    source: Lead
    display: funnel_chart
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        workspace = fragment.workspaces[0]
        region = workspace.regions[0]

        assert region.display.value == "funnel_chart"


class TestAppConfig:
    """Tests for app config block parsing (v0.9.5)."""

    def test_app_config_basic(self):
        """Test basic app config with all options."""
        dsl = """
module test.core

app MyApp "My Application":
  description: "A test application"
  multi_tenant: true
  audit_trail: true

entity User "User":
  id: uuid pk
  name: str(100) required
"""
        module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(
            dsl, Path("test.dsl")
        )

        assert app_name == "MyApp"
        assert app_title == "My Application"
        assert app_config is not None
        assert app_config.description == "A test application"
        assert app_config.multi_tenant is True
        assert app_config.audit_trail is True
        assert len(fragment.entities) == 1

    def test_app_config_partial(self):
        """Test app config with only some options."""
        dsl = """
module test.core

app MyApp "My Application":
  description: "Just a description"

entity User "User":
  id: uuid pk
"""
        _, _, _, app_config, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.description == "Just a description"
        assert app_config.multi_tenant is False  # Default
        assert app_config.audit_trail is False  # Default
        assert len(fragment.entities) == 1

    def test_app_config_features(self):
        """Test app config with custom features."""
        dsl = """
module test.core

app MyApp "My Application":
  multi_tenant: true
  custom_feature: "enabled"
  another_flag: true

entity User "User":
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.multi_tenant is True
        assert app_config.features.get("custom_feature") == "enabled"
        assert app_config.features.get("another_flag") is True

    def test_app_without_config(self):
        """Test app declaration without config body."""
        dsl = """
module test.core

app MyApp "My Application"

entity User "User":
  id: uuid pk
"""
        _, app_name, app_title, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_name == "MyApp"
        assert app_title == "My Application"
        assert app_config is None


class TestStoryParsing:
    """Tests for story DSL parsing (v0.22.0)."""

    def test_basic_story(self):
        """Test basic story parsing with actor and trigger."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk
  status: enum[draft,sent,paid]

story ST-001 "Staff sends invoice to client":
  actor: StaffUser
  trigger: status_changed
  scope: [Invoice]
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.stories) == 1
        story = fragment.stories[0]
        assert story.story_id == "ST-001"
        assert story.title == "Staff sends invoice to client"
        assert story.actor == "StaffUser"
        assert story.trigger.value == "status_changed"
        assert story.scope == ["Invoice"]

    def test_story_with_given_when_then(self):
        """Test story with Gherkin-style conditions."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk
  status: enum[draft,sent]

story ST-002 "Invoice status changes":
  actor: Admin
  trigger: form_submitted
  scope: [Invoice]

  given:
    - "Invoice.status is draft"

  when:
    - "User submits form"

  then:
    - "Invoice.status changes to sent"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.stories) == 1
        story = fragment.stories[0]
        assert len(story.given) == 1
        assert story.given[0].expression == "Invoice.status is draft"
        assert len(story.when) == 1
        assert story.when[0].expression == "User submits form"
        assert len(story.then) == 1
        assert story.then[0].expression == "Invoice.status changes to sent"

    def test_story_with_unless(self):
        """Test story with unless exception branch."""
        dsl = """
module test.core
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk

entity FollowupTask "Followup":
  id: uuid pk

story ST-003 "Send invoice with fallback":
  actor: Staff
  trigger: user_click
  scope: [Invoice, FollowupTask]

  then:
    - "Invoice is sent"

  unless:
    - "Client.email is missing":
        then: "FollowupTask is created"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.stories) == 1
        story = fragment.stories[0]
        assert len(story.unless) == 1
        assert story.unless[0].condition == "Client.email is missing"
        assert len(story.unless[0].then_outcomes) == 1
        assert story.unless[0].then_outcomes[0] == "FollowupTask is created"

    def test_story_all_triggers(self):
        """Test all supported story triggers."""
        triggers = [
            "form_submitted",
            "status_changed",
            "timer_elapsed",
            "external_event",
            "user_click",
            "cron_daily",
            "cron_hourly",
        ]
        for trigger in triggers:
            dsl = f"""
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk

story ST-TRIG "Test trigger":
  actor: User
  trigger: {trigger}
"""
            _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
            assert len(fragment.stories) == 1
            assert fragment.stories[0].trigger.value == trigger

    def test_multiple_stories(self):
        """Test parsing multiple stories in one module."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk

story ST-001 "First story":
  actor: Admin
  trigger: form_submitted

story ST-002 "Second story":
  actor: User
  trigger: user_click
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.stories) == 2
        assert fragment.stories[0].story_id == "ST-001"
        assert fragment.stories[1].story_id == "ST-002"


class TestProcessParsing:
    """Tests for process DSL parsing (v0.23.0)."""

    def test_basic_process(self):
        """Test basic process parsing with trigger and step."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  status: enum[pending,confirmed,shipped]=pending

process OrderFulfillment "Order Fulfillment":
  trigger: entity Order status -> confirmed
  implements: [ST-001]
  steps:
    - step CheckInventory:
        service: InventoryService
        timeout: 30s
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.processes) == 1
        process = fragment.processes[0]
        assert process.name == "OrderFulfillment"
        assert process.title == "Order Fulfillment"
        assert "ST-001" in process.implements

        # Check trigger
        assert process.trigger is not None
        assert process.trigger.kind.value == "entity_status_transition"
        assert process.trigger.entity_name == "Order"
        assert process.trigger.from_status is None
        assert process.trigger.to_status == "confirmed"

        # Check step
        assert len(process.steps) == 1
        step = process.steps[0]
        assert step.name == "CheckInventory"
        assert step.kind.value == "service"
        assert step.service == "InventoryService"
        assert step.timeout_seconds == 30

    def test_process_with_entity_event_trigger(self):
        """Test process with entity event trigger."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process OrderCreated "Handle Order Created":
  trigger: entity Order created
  implements: [ST-002]
  steps:
    - step NotifyAdmin:
        channel: email
        message: new_order_notification
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        process = fragment.processes[0]
        assert process.trigger.kind.value == "entity_event"
        assert process.trigger.entity_name == "Order"
        assert process.trigger.event_type == "created"

        step = process.steps[0]
        assert step.kind.value == "send"
        assert step.channel == "email"
        assert step.message == "new_order_notification"

    def test_process_with_wait_step(self):
        """Test process with WAIT step."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process OrderWithWait "Order With Wait":
  trigger: entity Order created
  steps:
    - step WaitForPayment:
        wait: 24h
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.kind.value == "wait"
        assert step.wait_duration_seconds == 86400  # 24 hours in seconds

    def test_process_with_wait_for_signal(self):
        """Test process with WAIT step waiting for signal."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process OrderWithSignalWait "Order With Signal Wait":
  trigger: entity Order created
  steps:
    - step WaitForPayment:
        wait: PaymentReceived
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.kind.value == "wait"
        assert step.wait_for_signal == "PaymentReceived"

    def test_process_with_human_task(self):
        """Test process with HUMAN_TASK step."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process OrderApproval "Order Approval":
  trigger: entity Order created
  steps:
    - step ApproveOrder:
        human_task:
          assignee: manager
          surface: ApprovalForm
          timeout: 2d
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.kind.value == "human_task"
        assert step.human_task is not None
        assert step.human_task.assignee_expression == "manager"
        assert step.human_task.surface == "ApprovalForm"
        assert step.human_task.timeout_seconds == 172800  # 2 days

    def test_process_with_subprocess(self):
        """Test process with SUBPROCESS step."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process MainProcess "Main Process":
  trigger: entity Order created
  steps:
    - step RunSubProcess:
        subprocess: PaymentProcess
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.kind.value == "subprocess"
        assert step.subprocess == "PaymentProcess"

    def test_process_with_condition_step(self):
        """Test process with CONDITION step."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process ConditionalProcess "Conditional Process":
  trigger: entity Order created
  steps:
    - step CheckAmount:
        condition: "Order.total > 1000"
        on_true: HighValueApproval
        on_false: AutoApprove
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.kind.value == "condition"
        assert step.condition == "Order.total > 1000"
        assert step.on_true == "HighValueApproval"
        assert step.on_false == "AutoApprove"

    def test_process_with_parallel_steps(self):
        """Test process with PARALLEL step containing multiple branches."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process ParallelProcess "Parallel Process":
  trigger: entity Order created
  steps:
    - parallel ParallelNotifications:
        - step NotifyCustomer:
            channel: email
            message: customer_notification
        - step NotifyWarehouse:
            channel: email
            message: warehouse_notification
        - step UpdateAnalytics:
            service: AnalyticsService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.kind.value == "parallel"
        assert len(step.parallel_steps) == 3
        # Parallel steps are ProcessStepSpec objects with names
        step_names = [s.name for s in step.parallel_steps]
        assert "NotifyCustomer" in step_names
        assert "NotifyWarehouse" in step_names
        assert "UpdateAnalytics" in step_names

    def test_process_with_multiple_steps(self):
        """Test process with multiple sequential steps."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process MultiStepProcess "Multi Step Process":
  trigger: entity Order created
  implements: [ST-001, ST-002]
  steps:
    - step Step1:
        service: Service1
        timeout: 30s
    - step Step2:
        service: Service2
        timeout: 1m
    - step Step3:
        channel: email
        message: completion_notification
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        process = fragment.processes[0]
        assert len(process.steps) == 3
        assert process.steps[0].name == "Step1"
        assert process.steps[1].name == "Step2"
        assert process.steps[2].name == "Step3"
        assert process.steps[1].timeout_seconds == 60  # 1 minute

    def test_process_with_inputs(self):
        """Test process with input parameters."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process ProcessWithInputs "Process With Inputs":
  trigger: entity Order created
  input:
    order_id: uuid
    priority: str
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        process = fragment.processes[0]
        assert len(process.inputs) == 2
        assert process.inputs[0].name == "order_id"
        assert process.inputs[0].type == "uuid"
        assert process.inputs[1].name == "priority"
        assert process.inputs[1].type == "str"

    def test_process_with_manual_trigger(self):
        """Test process with manual trigger."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process ManualProcess "Manual Process":
  trigger: manual
  steps:
    - step DoWork:
        service: WorkService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        process = fragment.processes[0]
        assert process.trigger.kind.value == "manual"

    def test_process_with_signal_trigger(self):
        """Test process with signal trigger."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process SignalProcess "Signal Process":
  trigger: signal PaymentComplete
  steps:
    - step ProcessPayment:
        service: PaymentService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        process = fragment.processes[0]
        assert process.trigger.kind.value == "signal"
        assert process.trigger.process_name == "PaymentComplete"

    def test_process_with_timeout(self):
        """Test process with overall timeout."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process TimedProcess "Timed Process":
  trigger: entity Order created
  timeout: 1h
  steps:
    - step DoWork:
        service: WorkService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        process = fragment.processes[0]
        assert process.timeout_seconds == 3600  # 1 hour

    def test_process_with_step_compensate(self):
        """Test process step with compensation handler."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

process SagaProcess "Saga Process":
  trigger: entity Order created
  steps:
    - step ReserveInventory:
        service: InventoryService
        compensate: ReleaseInventory
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        step = fragment.processes[0].steps[0]
        assert step.compensate_with == "ReleaseInventory"


class TestScheduleParsing:
    """Tests for schedule DSL parsing (v0.23.0)."""

    def test_basic_cron_schedule(self):
        """Test basic schedule with cron expression."""
        dsl = """
module test.core
app MyApp "My App"

entity Report "Report":
  id: uuid pk

schedule DailyReport "Daily Report Generation":
  cron: "0 6 * * *"
  implements: [ST-010]
  steps:
    - step GenerateReport:
        service: ReportService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.schedules) == 1
        schedule = fragment.schedules[0]
        assert schedule.name == "DailyReport"
        assert schedule.title == "Daily Report Generation"
        assert schedule.cron == "0 6 * * *"
        assert "ST-010" in schedule.implements

    def test_interval_schedule(self):
        """Test schedule with interval."""
        dsl = """
module test.core
app MyApp "My App"

schedule HealthCheck "Health Check":
  interval: 5m
  steps:
    - step Check:
        service: HealthService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        schedule = fragment.schedules[0]
        assert schedule.interval_seconds == 300  # 5 minutes
        assert schedule.cron is None

    def test_schedule_with_timezone(self):
        """Test schedule with timezone specification."""
        dsl = """
module test.core
app MyApp "My App"

schedule TimezoneJob "Timezone Job":
  cron: "0 9 * * 1-5"
  timezone: "Europe/London"
  steps:
    - step Work:
        service: WorkService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        schedule = fragment.schedules[0]
        assert schedule.timezone == "Europe/London"

    def test_schedule_with_catch_up(self):
        """Test schedule with catch_up enabled."""
        dsl = """
module test.core
app MyApp "My App"

schedule CatchUpJob "Catch Up Job":
  cron: "0 0 * * *"
  catch_up: true
  steps:
    - step Work:
        service: WorkService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        schedule = fragment.schedules[0]
        assert schedule.catch_up is True

    def test_multiple_schedules(self):
        """Test parsing multiple schedules."""
        dsl = """
module test.core
app MyApp "My App"

schedule Schedule1 "First Schedule":
  cron: "0 0 * * *"
  steps:
    - step Work1:
        service: Service1

schedule Schedule2 "Second Schedule":
  interval: 1h
  steps:
    - step Work2:
        service: Service2
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.schedules) == 2
        assert fragment.schedules[0].name == "Schedule1"
        assert fragment.schedules[1].name == "Schedule2"
        assert fragment.schedules[0].cron == "0 0 * * *"
        assert fragment.schedules[1].interval_seconds == 3600


class TestProcessAndScheduleIntegration:
    """Tests for process and schedule integration with other DSL constructs."""

    def test_process_and_schedule_together(self):
        """Test process and schedule in same module."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk

process TaskProcess "Task Process":
  trigger: entity Task created
  steps:
    - step ProcessTask:
        service: TaskService
        timeout: 30s

schedule TaskCleanup "Task Cleanup":
  cron: "0 0 * * *"
  steps:
    - step Cleanup:
        service: CleanupService
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.processes) == 1
        assert len(fragment.schedules) == 1
        assert fragment.processes[0].name == "TaskProcess"
        assert fragment.schedules[0].name == "TaskCleanup"

    def test_process_with_story_link(self):
        """Test process implements multiple stories."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk

story ST-001 "Create order":
  actor: Customer
  trigger: form_submitted
  scope: [Order]

story ST-002 "Fulfill order":
  actor: System
  trigger: status_changed
  scope: [Order]

process OrderWorkflow "Order Workflow":
  trigger: entity Order created
  implements: [ST-001, ST-002]
  steps:
    - step ProcessOrder:
        service: OrderService
        timeout: 30s
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.stories) == 2
        assert len(fragment.processes) == 1
        process = fragment.processes[0]
        assert "ST-001" in process.implements
        assert "ST-002" in process.implements


class TestSurfaceFieldSourceOption:
    """Tests for source= option on surface fields."""

    def test_field_with_source_option(self):
        """Test parser handles field with source=pack.operation."""
        dsl = """
module test.core
app test_app "Test App"

entity Client "Client":
  id: uuid pk
  company_name: str(200) required

surface client_create "Create Client":
  uses entity Client
  mode: create
  section main "Details":
    field company_name "Company" source=companies_house_lookup.search_companies
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        assert surface.name == "client_create"
        element = surface.sections[0].elements[0]
        assert element.field_name == "company_name"
        assert element.label == "Company"
        assert element.options.get("source") == "companies_house_lookup.search_companies"

    def test_field_without_source_option(self):
        """Test parser still works for fields without options."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_create "Create Task":
  uses entity Task
  mode: create
  section main "Details":
    field title "Title"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        element = surface.sections[0].elements[0]
        assert element.field_name == "title"
        assert element.label == "Title"
        assert element.options == {}


class TestBusinessPriority:
    """Tests for priority: modifier on surfaces and experiences."""

    def test_surface_priority_critical(self):
        """Surface with priority: critical."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  priority: critical
  section main:
    field title "Title"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surface = fragment.surfaces[0]
        assert surface.priority.value == "critical"

    def test_surface_priority_low(self):
        """Surface with priority: low."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  priority: low
  section main:
    field title "Title"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surface = fragment.surfaces[0]
        assert surface.priority.value == "low"

    def test_surface_priority_defaults_to_medium(self):
        """Surface without priority defaults to medium."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surface = fragment.surfaces[0]
        assert surface.priority.value == "medium"

    def test_experience_priority_critical(self):
        """Experience with priority: critical."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_create "Create":
  uses entity Task
  mode: create
  section main:
    field title "Title"

surface task_done "Done":
  uses entity Task
  mode: view
  section main:
    field title "Title"

experience task_wizard "Task Wizard":
  priority: critical
  start at step intake
  step intake:
    kind: surface
    surface task_create
    on success -> step finished
  step finished:
    kind: surface
    surface task_done
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        exp = fragment.experiences[0]
        assert exp.priority.value == "critical"

    def test_experience_priority_defaults_to_medium(self):
        """Experience without priority defaults to medium."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_create "Create":
  uses entity Task
  mode: create
  section main:
    field title "Title"

experience task_wizard "Task Wizard":
  start at step intake
  step intake:
    kind: surface
    surface task_create
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        exp = fragment.experiences[0]
        assert exp.priority.value == "medium"

    def test_experience_priority_with_access(self):
        """Experience with both access and priority."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_create "Create":
  uses entity Task
  mode: create
  section main:
    field title "Title"

experience task_wizard "Task Wizard":
  access: authenticated
  priority: high
  start at step intake
  step intake:
    kind: surface
    surface task_create
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        exp = fragment.experiences[0]
        assert exp.priority.value == "high"
        assert exp.access is not None
        assert exp.access.require_auth is True

    def test_all_priority_levels_valid(self):
        """All four priority levels parse correctly."""
        from dazzle.core.ir import BusinessPriority

        for level in ("critical", "high", "medium", "low"):
            dsl = f"""
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  priority: {level}
  section main:
    field title "Title"
"""
            _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
            surface = fragment.surfaces[0]
            assert surface.priority == BusinessPriority(level)


class TestEnumParsing:
    """Tests for shared enum DSL parsing (v0.25.0)."""

    def test_basic_enum(self):
        """Test basic shared enum with title and values."""
        dsl = """
module test.core
app MyApp "My App"

enum OrderStatus "Order Status":
  draft "Draft"
  pending_review "Pending Review"
  approved "Approved"
  rejected "Rejected"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.enums) == 1
        e = fragment.enums[0]
        assert e.name == "OrderStatus"
        assert e.title == "Order Status"
        assert len(e.values) == 4
        assert e.values[0].name == "draft"
        assert e.values[0].title == "Draft"
        assert e.values[3].name == "rejected"
        assert e.values[3].title == "Rejected"

    def test_enum_without_title(self):
        """Test shared enum without a display title."""
        dsl = """
module test.core
app MyApp "My App"

enum Priority:
  low
  medium
  high
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.enums) == 1
        e = fragment.enums[0]
        assert e.name == "Priority"
        assert e.title is None
        assert len(e.values) == 3
        assert e.values[0].name == "low"
        assert e.values[0].title is None

    def test_enum_values_without_titles(self):
        """Test enum values can omit display titles."""
        dsl = """
module test.core
app MyApp "My App"

enum Color "Color Choices":
  red
  green
  blue
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        e = fragment.enums[0]
        assert len(e.values) == 3
        assert all(v.title is None for v in e.values)
        assert [v.name for v in e.values] == ["red", "green", "blue"]

    def test_multiple_enums(self):
        """Test parsing multiple enum blocks."""
        dsl = """
module test.core
app MyApp "My App"

enum Status "Status":
  active "Active"
  inactive "Inactive"

enum Priority "Priority":
  low "Low"
  high "High"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.enums) == 2
        assert fragment.enums[0].name == "Status"
        assert fragment.enums[1].name == "Priority"


class TestViewParsing:
    """Tests for view DSL parsing (v0.25.0)."""

    def test_basic_view(self):
        """Test basic view with source, group_by, and aggregate fields."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  amount: decimal(10,2) required

view OrderSummary "Order Summary":
  source: Order
  group_by: [status]
  fields:
    total_amount: sum(amount)
    order_count: count()
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.views) == 1
        v = fragment.views[0]
        assert v.name == "OrderSummary"
        assert v.title == "Order Summary"
        assert v.source_entity == "Order"
        assert v.group_by == ["status"]
        assert len(v.fields) == 2
        assert v.fields[0].name == "total_amount"
        assert v.fields[0].expression is not None
        assert v.fields[1].name == "order_count"

    def test_view_with_filter(self):
        """Test view with filter condition."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  status: enum[draft,completed]=draft
  amount: decimal(10,2) required

view CompletedOrders "Completed Orders":
  source: Order
  filter: status = completed
  fields:
    total: sum(amount)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        v = fragment.views[0]
        assert v.filter_condition is not None
        assert v.source_entity == "Order"

    def test_view_with_function_group_by(self):
        """Test view with function call in group_by: month(created_at)."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  created_at: datetime auto_add
  amount: decimal(10,2) required

view MonthlySales "Monthly Sales":
  source: Order
  group_by: [customer, month(created_at)]
  fields:
    total: sum(amount)
    count: count()
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        v = fragment.views[0]
        assert v.group_by == ["customer", "month(created_at)"]

    def test_view_with_typed_fields(self):
        """Test view fields that have explicit types instead of aggregates."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  amount: decimal(10,2) required

view OrderReport "Order Report":
  source: Order
  fields:
    label: str(200)
    total: sum(amount)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        v = fragment.views[0]
        assert len(v.fields) == 2
        # str type field
        assert v.fields[0].name == "label"
        assert v.fields[0].field_type is not None
        assert v.fields[0].expression is None
        # aggregate field
        assert v.fields[1].name == "total"
        assert v.fields[1].expression is not None
        assert v.fields[1].field_type is None

    def test_view_without_title(self):
        """Test view without display title."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  amount: decimal(10,2) required

view QuickReport:
  source: Order
  fields:
    total: sum(amount)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        v = fragment.views[0]
        assert v.name == "QuickReport"
        assert v.title is None


class TestWebhookParsing:
    """Tests for webhook DSL parsing (v0.25.0)."""

    def test_basic_webhook(self):
        """Test full webhook with all sub-blocks."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  status: enum[pending,shipped]=pending

webhook OrderNotification "Order Status Webhook":
  entity: Order
  events: [created, updated, deleted]
  url: config("ORDER_WEBHOOK_URL")
  auth:
    method: hmac_sha256
    secret: config("WEBHOOK_SECRET")
  payload:
    include: [id, status, total, customer.name]
    format: json
  retry:
    max_attempts: 3
    backoff: exponential
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.webhooks) == 1
        wh = fragment.webhooks[0]
        assert wh.name == "OrderNotification"
        assert wh.title == "Order Status Webhook"
        assert wh.entity == "Order"
        assert len(wh.events) == 3

        # Auth
        assert wh.auth is not None
        assert wh.auth.method.value == "hmac_sha256"
        assert wh.auth.secret_ref == 'config("WEBHOOK_SECRET")'

        # Payload
        assert wh.payload is not None
        assert wh.payload.include_fields == ["id", "status", "total", "customer.name"]
        assert wh.payload.format == "json"

        # Retry
        assert wh.retry is not None
        assert wh.retry.max_attempts == 3
        assert wh.retry.backoff == "exponential"

    def test_webhook_minimal(self):
        """Test webhook with only required fields."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk

webhook TaskHook:
  entity: Task
  events: [created]
  url: config("TASK_HOOK_URL")
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        wh = fragment.webhooks[0]
        assert wh.name == "TaskHook"
        assert wh.title is None
        assert wh.entity == "Task"
        assert len(wh.events) == 1
        assert wh.auth is None
        assert wh.payload is None
        assert wh.retry is None

    def test_webhook_events_parsing(self):
        """Test webhook events are parsed correctly as enums."""
        dsl = """
module test.core
app MyApp "My App"

entity Item "Item":
  id: uuid pk

webhook ItemEvents "Item Events":
  entity: Item
  events: [created, updated]
  url: config("ITEM_URL")
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        from dazzle.core.ir import WebhookEvent

        wh = fragment.webhooks[0]
        assert wh.events[0] == WebhookEvent.CREATED
        assert wh.events[1] == WebhookEvent.UPDATED


class TestApprovalParsing:
    """Tests for approval DSL parsing (v0.25.0)."""

    def test_full_approval(self):
        """Test full approval with all sub-blocks."""
        dsl = """
module test.core
app MyApp "My App"

entity PurchaseOrder "Purchase Order":
  id: uuid pk
  status: enum[draft,pending_approval,approved,rejected]=draft
  amount: decimal(10,2) required

approval PurchaseApproval "Purchase Order Approval":
  entity: PurchaseOrder
  trigger: status -> pending_approval
  approver_role: finance_manager
  quorum: 1
  threshold: amount > 1000
  escalation:
    after: 48 hours
    to: finance_director
  auto_approve:
    when: amount <= 100
  outcomes:
    approved -> approved
    rejected -> rejected
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.approvals) == 1
        ap = fragment.approvals[0]
        assert ap.name == "PurchaseApproval"
        assert ap.title == "Purchase Order Approval"
        assert ap.entity == "PurchaseOrder"
        assert ap.trigger_field == "status"
        assert ap.trigger_value == "pending_approval"
        assert ap.approver_role == "finance_manager"
        assert ap.quorum == 1

        # Threshold condition
        assert ap.threshold is not None

        # Escalation
        assert ap.escalation is not None
        assert ap.escalation.after_value == 48
        assert ap.escalation.after_unit == "hours"
        assert ap.escalation.to_role == "finance_director"

        # Auto approve
        assert ap.auto_approve is not None

        # Outcomes
        assert len(ap.outcomes) == 2
        assert ap.outcomes[0].decision == "approved"
        assert ap.outcomes[0].target_status == "approved"
        assert ap.outcomes[1].decision == "rejected"
        assert ap.outcomes[1].target_status == "rejected"

    def test_approval_minimal(self):
        """Test approval with only basic fields."""
        dsl = """
module test.core
app MyApp "My App"

entity Document "Document":
  id: uuid pk
  status: enum[draft,pending,approved]=draft

approval DocApproval:
  entity: Document
  trigger: status -> pending
  approver_role: manager
  outcomes:
    approved -> approved
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ap = fragment.approvals[0]
        assert ap.name == "DocApproval"
        assert ap.title is None
        assert ap.entity == "Document"
        assert ap.escalation is None
        assert ap.auto_approve is None
        assert ap.threshold is None
        assert len(ap.outcomes) == 1

    def test_approval_quorum(self):
        """Test approval with custom quorum."""
        dsl = """
module test.core
app MyApp "My App"

entity Contract "Contract":
  id: uuid pk
  status: enum[draft,review,approved]=draft

approval ContractReview "Contract Review":
  entity: Contract
  trigger: status -> review
  approver_role: legal_team
  quorum: 3
  outcomes:
    approved -> approved
    rejected -> draft
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ap = fragment.approvals[0]
        assert ap.quorum == 3


class TestSLAParsing:
    """Tests for SLA DSL parsing (v0.25.0)."""

    def test_full_sla(self):
        """Test full SLA with all sub-blocks."""
        dsl = """
module test.core
app MyApp "My App"

entity SupportTicket "Support Ticket":
  id: uuid pk
  status: enum[open,on_hold,resolved]=open
  escalated: bool=false

sla TicketResponse "Ticket Response SLA":
  entity: SupportTicket
  starts_when: status -> open
  pauses_when: status = on_hold
  completes_when: status -> resolved
  tiers:
    warning: 4 hours
    breach: 8 hours
    critical: 24 hours
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: "Europe/London"
  on_breach:
    notify: support_lead
    set: escalated = true
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.slas) == 1
        sla = fragment.slas[0]
        assert sla.name == "TicketResponse"
        assert sla.title == "Ticket Response SLA"
        assert sla.entity == "SupportTicket"

        # Conditions
        assert sla.starts_when is not None
        assert sla.starts_when.field == "status"
        assert sla.starts_when.operator == "->"
        assert sla.starts_when.value == "open"

        assert sla.pauses_when is not None
        assert sla.pauses_when.operator == "="
        assert sla.pauses_when.value == "on_hold"

        assert sla.completes_when is not None
        assert sla.completes_when.operator == "->"
        assert sla.completes_when.value == "resolved"

        # Tiers
        assert len(sla.tiers) == 3
        assert sla.tiers[0].name == "warning"
        assert sla.tiers[0].duration_value == 4
        assert sla.tiers[0].duration_unit == "hours"
        assert sla.tiers[1].name == "breach"
        assert sla.tiers[1].duration_value == 8
        assert sla.tiers[2].name == "critical"
        assert sla.tiers[2].duration_value == 24

        # Business hours
        assert sla.business_hours is not None
        assert sla.business_hours.schedule == "Mon-Fri 09:00-17:00"
        assert sla.business_hours.timezone == "Europe/London"

        # Breach action
        assert sla.on_breach is not None
        assert sla.on_breach.notify_role == "support_lead"
        assert len(sla.on_breach.field_assignments) == 1
        assert sla.on_breach.field_assignments[0].field_path == "escalated"
        assert sla.on_breach.field_assignments[0].value == "true"

    def test_sla_minimal(self):
        """Test SLA with only basic fields."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk
  status: enum[open,done]=open

sla TaskCompletion:
  entity: Task
  starts_when: status -> open
  completes_when: status -> done
  tiers:
    warning: 2 hours
    breach: 4 hours
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        sla = fragment.slas[0]
        assert sla.name == "TaskCompletion"
        assert sla.title is None
        assert sla.pauses_when is None
        assert sla.business_hours is None
        assert sla.on_breach is None
        assert len(sla.tiers) == 2

    def test_sla_tiers_with_different_units(self):
        """Test SLA tiers with various time units."""
        dsl = """
module test.core
app MyApp "My App"

entity Alert "Alert":
  id: uuid pk
  status: enum[open,ack,resolved]=open

sla AlertResponse "Alert Response":
  entity: Alert
  starts_when: status -> open
  completes_when: status -> ack
  tiers:
    immediate: 15 minutes
    warning: 1 hours
    breach: 2 days
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        sla = fragment.slas[0]
        assert sla.tiers[0].duration_value == 15
        assert sla.tiers[0].duration_unit == "minutes"
        assert sla.tiers[1].duration_unit == "hours"
        assert sla.tiers[2].duration_value == 2
        assert sla.tiers[2].duration_unit == "days"


class TestV025AllConstructs:
    """Integration tests for all v0.25.0 constructs together."""

    def test_all_five_constructs_in_one_module(self):
        """All five new constructs parse correctly in a single module."""
        dsl = """
module test.core
app MyApp "My App"

entity Order "Order":
  id: uuid pk
  status: enum[draft,pending,approved,shipped]=draft
  amount: decimal(10,2) required
  escalated: bool=false

enum OrderStatus "Order Status":
  draft "Draft"
  pending "Pending"
  approved "Approved"
  shipped "Shipped"

view OrderDashboard "Order Dashboard":
  source: Order
  group_by: [status]
  fields:
    total_amount: sum(amount)
    order_count: count()

webhook OrderWebhook "Order Webhook":
  entity: Order
  events: [created, updated]
  url: config("ORDER_HOOK_URL")
  retry:
    max_attempts: 5
    backoff: exponential

approval OrderApproval "Order Approval":
  entity: Order
  trigger: status -> pending
  approver_role: manager
  quorum: 1
  outcomes:
    approved -> approved
    rejected -> draft

sla OrderFulfillment "Order Fulfillment SLA":
  entity: Order
  starts_when: status -> approved
  completes_when: status -> shipped
  tiers:
    warning: 24 hours
    breach: 48 hours
  on_breach:
    notify: ops_lead
    set: escalated = true
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.entities) == 1
        assert len(fragment.enums) == 1
        assert len(fragment.views) == 1
        assert len(fragment.webhooks) == 1
        assert len(fragment.approvals) == 1
        assert len(fragment.slas) == 1

        assert fragment.enums[0].name == "OrderStatus"
        assert fragment.views[0].name == "OrderDashboard"
        assert fragment.webhooks[0].name == "OrderWebhook"
        assert fragment.approvals[0].name == "OrderApproval"
        assert fragment.slas[0].name == "OrderFulfillment"


class TestV025EntityKeywordInBlocks:
    """Regression tests for #222: entity keyword inside construct blocks."""

    def test_sla_entity_property_parses(self):
        """entity: inside SLA block must not be captured by top-level entity dispatch."""
        dsl = """
module test.sla
app test_app "Test"

entity CustomerDueDiligence "CDD":
  id: uuid pk
  cdd_status: enum[complete, pending, requires_refresh]

sla CDDReview "CDD Periodic Review":
  entity: CustomerDueDiligence
  starts_when: cdd_status -> complete
  completes_when: cdd_status -> complete
  tiers:
    warning: 30 days
    breach: 7 days
    critical: 1 days
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: "Europe/London"
  on_breach:
    notify: manager
    set: cdd_status = requires_refresh
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.slas) == 1
        sla = fragment.slas[0]
        assert sla.name == "CDDReview"
        assert sla.entity == "CustomerDueDiligence"
        assert len(sla.tiers) == 3
        assert sla.business_hours is not None
        assert sla.business_hours.timezone == "Europe/London"
        assert sla.on_breach is not None
        assert sla.on_breach.notify_role == "manager"

    def test_approval_entity_property_parses(self):
        """entity: inside approval block must parse correctly."""
        dsl = """
module test.approval
app test_app "Test"

entity PurchaseOrder "PO":
  id: uuid pk
  status: enum[draft, pending_approval, approved, rejected]
  amount: int

approval PurchaseApproval "Purchase Approval":
  entity: PurchaseOrder
  trigger: status -> pending_approval
  approver_role: finance_manager
  quorum: 2
  outcomes:
    approved -> approved
    rejected -> rejected
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.approvals) == 1
        approval = fragment.approvals[0]
        assert approval.entity == "PurchaseOrder"
        assert approval.approver_role == "finance_manager"
        assert approval.quorum == 2

    def test_webhook_entity_property_parses(self):
        """entity: inside webhook block must parse correctly."""
        dsl = """
module test.webhook
app test_app "Test"

entity Order "Order":
  id: uuid pk
  status: enum[open, closed]

webhook OrderNotify "Order Webhook":
  entity: Order
  events: [created, updated, deleted]
  url: "https://example.com/hook"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.webhooks) == 1
        assert fragment.webhooks[0].entity == "Order"

    def test_all_v025_entity_properties_in_one_module(self):
        """All v0.25.0 constructs with entity: property in a single module."""
        dsl = """
module test.combined
app test_app "Test"

entity Task "Task":
  id: uuid pk
  status: enum[open, in_progress, done]
  priority: int

webhook TaskAlert "Task Alert":
  entity: Task
  events: [created]
  url: "https://hooks.example.com/tasks"

approval TaskApproval "Task Approval":
  entity: Task
  approver_role: lead
  quorum: 1
  outcomes:
    approved -> in_progress
    rejected -> open

sla TaskResolution "Task Resolution SLA":
  entity: Task
  starts_when: status -> open
  completes_when: status -> done
  tiers:
    warning: 8 hours
    breach: 24 hours
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.webhooks) == 1
        assert len(fragment.approvals) == 1
        assert len(fragment.slas) == 1
        assert fragment.webhooks[0].entity == "Task"
        assert fragment.approvals[0].entity == "Task"
        assert fragment.slas[0].entity == "Task"


if __name__ == "__main__":
    main()
