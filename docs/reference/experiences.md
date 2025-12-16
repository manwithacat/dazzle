# Experiences

Experiences define multi-step user flows and wizards.

## Basic Syntax

```dsl
experience experience_name "Display Title":
  start at step first_step

  step step_name:
    kind: surface|process|integration
    surface surface_name
    on event -> step next_step
```

## Experience Structure

An experience consists of:
1. **Start declaration** - Which step begins the flow
2. **Steps** - Individual stages in the flow
3. **Transitions** - How users move between steps

## Step Kinds

| Kind | Description | Properties |
|------|-------------|------------|
| `surface` | UI screen step | `surface` |
| `process` | Background processing | - |
| `integration` | External service call | `integration`, `action` |

## Transitions

Define how users move between steps:

```dsl
on event -> step next_step
```

### Transition Events

| Event | Description |
|-------|-------------|
| `submit` | Form submission |
| `success` | Successful completion |
| `failure` | Error occurred |
| `cancel` | User cancelled |
| `skip` | User skipped step |
| `back` | User went back |

## Examples

### Simple Onboarding Flow

```dsl
experience onboarding "User Onboarding":
  start at step welcome

  step welcome:
    kind: surface
    surface welcome_screen
    on submit -> step profile

  step profile:
    kind: surface
    surface profile_form
    on submit -> step preferences
    on skip -> step complete

  step preferences:
    kind: surface
    surface preferences_form
    on submit -> step complete
    on back -> step profile

  step complete:
    kind: surface
    surface onboarding_complete
```

### Order Checkout Flow

```dsl
experience checkout "Checkout":
  start at step cart_review

  step cart_review:
    kind: surface
    surface cart_summary
    on submit -> step shipping
    on cancel -> step abandoned

  step shipping:
    kind: surface
    surface shipping_form
    on submit -> step payment
    on back -> step cart_review

  step payment:
    kind: surface
    surface payment_form
    on submit -> step process_payment

  step process_payment:
    kind: integration
    integration payment_gateway action process
    on success -> step confirmation
    on failure -> step payment_error

  step payment_error:
    kind: surface
    surface payment_error
    on submit -> step payment

  step confirmation:
    kind: surface
    surface order_confirmation

  step abandoned:
    kind: surface
    surface cart_abandoned
```

### Multi-Step Form Wizard

```dsl
experience application_wizard "Loan Application":
  start at step personal_info

  step personal_info:
    kind: surface
    surface application_personal
    on submit -> step employment
    on cancel -> step cancelled

  step employment:
    kind: surface
    surface application_employment
    on submit -> step financial
    on back -> step personal_info

  step financial:
    kind: surface
    surface application_financial
    on submit -> step documents

  step documents:
    kind: surface
    surface application_documents
    on submit -> step review
    on back -> step financial

  step review:
    kind: surface
    surface application_review
    on submit -> step submit_application
    on back -> step documents

  step submit_application:
    kind: integration
    integration loan_service action submit
    on success -> step confirmation
    on failure -> step submission_error

  step confirmation:
    kind: surface
    surface application_submitted

  step submission_error:
    kind: surface
    surface application_error
    on submit -> step review

  step cancelled:
    kind: surface
    surface application_cancelled
```

### Support Ticket Flow

```dsl
experience support_request "Support Request":
  start at step describe_issue

  step describe_issue:
    kind: surface
    surface support_form
    on submit -> step categorize

  step categorize:
    kind: process
    on success -> step assign
    on failure -> step manual_review

  step assign:
    kind: integration
    integration ticketing_system action create_ticket
    on success -> step confirmation
    on failure -> step manual_review

  step manual_review:
    kind: surface
    surface support_manual_queue

  step confirmation:
    kind: surface
    surface support_confirmation
```

## Integration Steps

Integration steps call external services:

```dsl
step verify_identity:
  kind: integration
  integration identity_service action verify
  on success -> step approved
  on failure -> step manual_review
```

The integration must be defined elsewhere with the referenced action.

## Complete Example

```dsl
# Define the surfaces used in the experience
surface signup_email "Enter Email":
  uses entity User
  mode: create
  section main:
    field email "Email Address"
  action next "Continue":
    on submit -> experience signup step verify_email

surface verify_email_screen "Verify Email":
  uses entity User
  mode: edit
  section main:
    field verification_code "Verification Code"
  action verify "Verify":
    on submit -> experience signup step create_password

surface create_password_screen "Create Password":
  uses entity User
  mode: edit
  section main:
    field password "Password"
    field password_confirm "Confirm Password"
  action create "Create Account":
    on submit -> experience signup step welcome

surface welcome_screen "Welcome":
  uses entity User
  mode: view
  section main:
    field name "Welcome!"
  action start "Get Started":
    on click -> surface dashboard

# Define the experience
experience signup "User Signup":
  start at step enter_email

  step enter_email:
    kind: surface
    surface signup_email
    on submit -> step verify_email

  step verify_email:
    kind: surface
    surface verify_email_screen
    on submit -> step check_code

  step check_code:
    kind: integration
    integration email_service action verify_code
    on success -> step create_password
    on failure -> step verify_email

  step create_password:
    kind: surface
    surface create_password_screen
    on submit -> step create_account

  step create_account:
    kind: process
    on success -> step welcome
    on failure -> step signup_error

  step welcome:
    kind: surface
    surface welcome_screen

  step signup_error:
    kind: surface
    surface error_screen
    on submit -> step enter_email
```

## Best Practices

1. **Define clear entry and exit points** - Users should know where they are
2. **Handle all outcomes** - Include error and cancel paths
3. **Allow going back** - Multi-step flows should support navigation
4. **Keep steps focused** - Each step should do one thing
5. **Use process steps for background work** - Keep UI steps interactive
6. **Integrate carefully** - Handle integration failures gracefully
