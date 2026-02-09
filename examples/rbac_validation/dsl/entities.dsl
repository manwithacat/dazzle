# RBAC Validation Example — Medical Clinic Entities
# =============================================================================
# Exercises every Cedar-style permit/forbid/audit pattern for NIST SP 800-162
# compliance validation.
# =============================================================================

module clinic.entities

# =============================================================================
# PATIENT — Role hierarchy (receptionist < nurse < doctor < admin)
# =============================================================================

entity Patient "Patient":
  intent: "Core patient record — tests role hierarchy and delete restriction"
  domain: clinical

  id: uuid pk
  first_name: str(100) required
  last_name: str(100) required
  date_of_birth: date required
  email: email optional
  phone: str(20) optional
  address: text optional
  insurance_id: str(50) optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(receptionist) or role(nurse) or role(doctor) or role(admin)
    read: role(receptionist) or role(nurse) or role(doctor) or role(admin)
    update: role(receptionist) or role(nurse) or role(doctor) or role(admin)
    delete: role(admin)
    list: role(receptionist) or role(nurse) or role(doctor) or role(admin)

  forbid:
    delete: role(receptionist) or role(nurse) or role(doctor) or role(pharmacist) or role(lab_tech) or role(billing_clerk) or role(intern)

  audit: all

# =============================================================================
# MEDICAL RECORD — Owner-based + role exclusion + condition-based forbid
# =============================================================================

entity MedicalRecord "Medical Record":
  intent: "Sensitive clinical data — tests role exclusion and immutability"
  domain: clinical

  id: uuid pk
  patient: ref Patient required
  record_type: enum[consultation,diagnosis,treatment,lab,imaging]=consultation
  summary: text required
  details: json optional
  is_archived: bool=false
  created_by_doctor: ref Staff optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(doctor) or role(admin)
    read: role(nurse) or role(doctor) or role(admin)
    update: role(doctor) or role(admin)
    delete: role(admin)
    list: role(nurse) or role(doctor) or role(admin)

  forbid:
    read: role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)
    create: role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)
    update: role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)
    delete: role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)
    list: role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)

  audit: all

# =============================================================================
# PRESCRIPTION — Separation of duty (doctor creates, pharmacist dispenses)
# =============================================================================

entity Prescription "Prescription":
  intent: "Separation of duty — doctor creates, pharmacist dispenses, neither does both"
  domain: clinical

  id: uuid pk
  patient: ref Patient required
  medication: str(200) required
  dosage: str(100) required
  frequency: str(100) required
  duration_days: int required
  status: enum[draft,issued,dispensed,cancelled]=draft
  notes: text optional
  prescribed_by: ref Staff optional
  dispensed_by: ref Staff optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(doctor) or role(admin)
    read: role(doctor) or role(pharmacist) or role(nurse) or role(admin)
    update: role(pharmacist) or role(admin)
    delete: role(admin)
    list: role(doctor) or role(pharmacist) or role(nurse) or role(admin)

  forbid:
    create: role(pharmacist) or role(intern)
    update: role(doctor) or role(intern)

  audit: all

# =============================================================================
# APPOINTMENT — Multi-role with ownership, condition-based immutability
# =============================================================================

entity Appointment "Appointment":
  intent: "Scheduling — tests multi-role create and status immutability"
  domain: scheduling

  id: uuid pk
  patient: ref Patient required
  doctor: ref Staff required
  appointment_date: datetime required
  duration_minutes: int=30
  status: enum[scheduled,confirmed,completed,cancelled]=scheduled
  reason: str(500) optional
  notes: text optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(receptionist) or role(nurse) or role(doctor) or role(admin)
    read: role(receptionist) or role(nurse) or role(doctor) or role(admin)
    update: role(receptionist) or role(nurse) or role(doctor) or role(admin)
    delete: role(admin)
    list: role(receptionist) or role(nurse) or role(doctor) or role(admin)

  forbid:
    delete: role(receptionist) or role(nurse) or role(doctor) or role(pharmacist) or role(lab_tech) or role(billing_clerk) or role(intern)

  audit: [create, update, delete]

# =============================================================================
# LAB RESULT — Status-gated updates, role-specific create
# =============================================================================

entity LabResult "Lab Result":
  intent: "Lab workflow — only lab_tech creates, status-gated updates"
  domain: clinical

  id: uuid pk
  patient: ref Patient required
  test_type: str(200) required
  result_value: text optional
  reference_range: str(100) optional
  status: enum[pending,completed,reviewed]=pending
  notes: text optional
  performed_by: ref Staff optional
  reviewed_by: ref Staff optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(lab_tech) or role(admin)
    read: role(lab_tech) or role(doctor) or role(nurse) or role(admin)
    update: role(lab_tech) or role(doctor) or role(admin)
    delete: role(admin)
    list: role(lab_tech) or role(doctor) or role(nurse) or role(admin)

  forbid:
    create: role(doctor) or role(nurse) or role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)
    update: role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)

  audit: all

# =============================================================================
# BILLING RECORD — Data segregation (clinical staff forbidden), immutability
# =============================================================================

entity BillingRecord "Billing Record":
  intent: "Financial data — clinical staff explicitly forbidden"
  domain: finance

  id: uuid pk
  patient: ref Patient required
  appointment: ref Appointment optional
  amount: decimal(10,2) required
  status: enum[pending,invoiced,paid,refunded]=pending
  invoice_number: str(50) optional
  payment_method: str(50) optional
  notes: text optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(billing_clerk) or role(admin)
    read: role(billing_clerk) or role(admin)
    update: role(billing_clerk) or role(admin)
    delete: role(admin)
    list: role(billing_clerk) or role(admin)

  forbid:
    read: role(doctor) or role(nurse) or role(lab_tech) or role(intern)
    create: role(doctor) or role(nurse) or role(lab_tech) or role(receptionist) or role(pharmacist) or role(intern)
    update: role(doctor) or role(nurse) or role(lab_tech) or role(receptionist) or role(pharmacist) or role(intern)
    delete: role(doctor) or role(nurse) or role(lab_tech) or role(receptionist) or role(pharmacist) or role(billing_clerk) or role(intern)

  audit: all

# =============================================================================
# STAFF — Self-service read, admin-only management
# =============================================================================

entity Staff "Staff":
  intent: "Employee records — any authenticated can read, admin manages"
  domain: administration

  id: uuid pk
  first_name: str(100) required
  last_name: str(100) required
  email: email required
  role: enum[admin,doctor,nurse,receptionist,pharmacist,lab_tech,billing_clerk,intern]=intern
  department: str(100) optional
  is_active: bool=true

  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(admin)
    read: authenticated
    update: role(admin)
    delete: role(admin)
    list: authenticated

  forbid:
    create: role(doctor) or role(nurse) or role(receptionist) or role(pharmacist) or role(lab_tech) or role(billing_clerk) or role(intern)
    update: role(doctor) or role(nurse) or role(receptionist) or role(pharmacist) or role(lab_tech) or role(billing_clerk) or role(intern)
    delete: role(doctor) or role(nurse) or role(receptionist) or role(pharmacist) or role(lab_tech) or role(billing_clerk) or role(intern)

  audit: [create, update, delete]

# =============================================================================
# AUDIT LOG — Immutable: forbid update/delete for all, append-only
# =============================================================================

entity AuditLog "Audit Log":
  intent: "Immutable audit trail — append-only, no updates or deletes"
  domain: compliance

  id: uuid pk
  action: str(50) required
  entity_type: str(100) required
  entity_id: str(100) required
  performed_by: str(100) required
  details: json optional
  ip_address: str(45) optional

  created_at: datetime auto_add

  permit:
    create: authenticated
    read: role(admin)
    list: role(admin)

  forbid:
    create: role(intern)
    update: authenticated
    delete: authenticated

  audit: false
