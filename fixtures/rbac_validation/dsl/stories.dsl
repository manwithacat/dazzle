# RBAC Validation Example — Medical Clinic Stories
# =============================================================================
# 6 stories documenting expected access behavior for key workflows.
# =============================================================================

module clinic.stories

story ST-001 "Doctor creates prescription for patient":
  actor: doctor
  trigger: form_submitted
  scope: [Prescription, Patient]

  given:
    - "Patient record exists"
    - "Doctor is authenticated with doctor role"

  when:
    - "Doctor submits new prescription form"

  then:
    - "Prescription is created with status draft"
    - "Prescription.prescribed_by is set to current doctor"

story ST-002 "Pharmacist dispenses prescription":
  actor: pharmacist
  trigger: form_submitted
  scope: [Prescription]

  given:
    - "Prescription exists with status issued"
    - "Pharmacist is authenticated"

  when:
    - "Pharmacist updates prescription status to dispensed"

  then:
    - "Prescription.status changes to dispensed"
    - "Prescription.dispensed_by is set to current pharmacist"

story ST-003 "Receptionist registers new patient":
  actor: receptionist
  trigger: form_submitted
  scope: [Patient]

  given:
    - "Receptionist is authenticated"

  when:
    - "Receptionist submits patient registration form"

  then:
    - "Patient record is created"

  unless:
    - "Patient with same email already exists":
        then: "Error is shown to receptionist"

story ST-004 "Lab tech enters lab results":
  actor: lab_tech
  trigger: form_submitted
  scope: [LabResult, Patient]

  given:
    - "Patient record exists"
    - "Lab tech is authenticated"

  when:
    - "Lab tech submits lab result form"

  then:
    - "LabResult is created with status pending"
    - "LabResult.performed_by is set to current lab tech"

story ST-005 "Billing clerk creates invoice":
  actor: billing_clerk
  trigger: form_submitted
  scope: [BillingRecord, Patient]

  given:
    - "Patient record exists"
    - "Billing clerk is authenticated"

  when:
    - "Billing clerk submits billing form"

  then:
    - "BillingRecord is created with status pending"

story ST-006 "Intern is denied access to clinical data":
  actor: intern
  trigger: user_click
  scope: [MedicalRecord, Prescription, LabResult, BillingRecord]

  given:
    - "Intern is authenticated with intern role"

  when:
    - "Intern attempts to access any clinical entity"

  then:
    - "Access is denied by default-deny policy"
