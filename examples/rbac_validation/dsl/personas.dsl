# RBAC Validation Example — Medical Clinic Personas
# =============================================================================
# 8 personas with clear privilege boundaries for NIST validation.
# =============================================================================

module clinic.personas

persona admin "Administrator":
  description: "System administrator with full access — break-glass role"
  goals: "Manage staff", "Configure system", "Audit access"
  proficiency: expert

persona doctor "Doctor":
  description: "Licensed physician — full clinical access, no billing"
  goals: "Diagnose patients", "Prescribe medication", "Review lab results"
  proficiency: expert

persona nurse "Nurse":
  description: "Clinical support — read clinical data, assist with appointments"
  goals: "Assist patients", "Update appointments", "View lab results"
  proficiency: intermediate

persona receptionist "Receptionist":
  description: "Front desk — patient registration and scheduling only"
  goals: "Register patients", "Schedule appointments"
  proficiency: intermediate

persona pharmacist "Pharmacist":
  description: "Dispenses prescriptions — no medical record access"
  goals: "Dispense medication", "Verify prescriptions"
  proficiency: intermediate

persona lab_tech "Lab Technician":
  description: "Laboratory technician — creates and manages lab results only"
  goals: "Process lab orders", "Enter results"
  proficiency: intermediate

persona billing_clerk "Billing Clerk":
  description: "Finance staff — billing records only, no clinical data"
  goals: "Create invoices", "Process payments"
  proficiency: intermediate

persona intern "Intern":
  description: "Trainee with zero privileges — tests default-deny"
  goals: "Shadow staff", "Learn procedures"
  proficiency: novice
