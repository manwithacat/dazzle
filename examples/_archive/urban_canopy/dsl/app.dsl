module urbancanopy.core

app UrbanCanopy "Urban Canopy"

# =============================================================================
# ENTITIES - Domain Models
# =============================================================================

entity Volunteer "Volunteer":
  id: uuid pk
  name: str(200) required
  preferred_area: str(300)
  skill_level: enum[Beginner, Intermediate, TrainedArborist]=Beginner
  is_active: bool
  joined_at: datetime auto_add

entity Tree "Tree":
  id: uuid pk
  species: str(200) required
  location_lat: decimal(9,6) required
  location_lng: decimal(9,6) required
  street_address: str(300)
  condition_status: enum[Healthy, ModerateStress, SevereStress, Dead]=Healthy
  soil_condition: enum[Compact, Loose, Mulched, Unknown]=Unknown
  last_inspection_date: datetime
  created_at: datetime auto_add
  updated_at: datetime auto_update
  steward: ref Volunteer

entity Observation "Observation":
  id: uuid pk
  tree: ref Tree required
  observer: ref Volunteer required
  moisture_level: enum[Low, Medium, High] required
  leaf_condition: enum[Normal, Yellowing, Browning, Spotting] required
  has_insect_signs: bool
  insect_notes: text
  photo_url: str(500)
  notes: text
  submitted_at: datetime auto_add

entity MaintenanceTask "Maintenance Task":
  id: uuid pk
  tree: ref Tree required
  task_type: enum[Watering, Mulching, PruningRequest, SoilAeration, DiseaseInspection] required
  created_by: ref Volunteer required
  assigned_to: ref Volunteer
  status: enum[Open, InProgress, Completed, Cancelled]=Open
  notes: text
  created_at: datetime auto_add
  updated_at: datetime auto_update

# =============================================================================
# SURFACES - User Interface Screens
# =============================================================================

# Tree Surfaces
surface tree_list "All Trees":
  uses entity Tree
  mode: list

  section main "Trees":
    field species "Species"
    field street_address "Location"
    field condition_status "Condition"
    field steward "Steward"
    field last_inspection_date "Last Checked"

surface tree_detail "Tree Details":
  uses entity Tree
  mode: view

  section main "Tree Information":
    field species "Species"
    field street_address "Address"
    field location_lat "Latitude"
    field location_lng "Longitude"
    field condition_status "Condition"
    field soil_condition "Soil Condition"
    field steward "Steward"
    field last_inspection_date "Last Inspection"

surface tree_create "Add Tree":
  uses entity Tree
  mode: create

  section main "New Tree":
    field species "Species"
    field street_address "Street Address"
    field location_lat "Latitude"
    field location_lng "Longitude"
    field condition_status "Condition"
    field soil_condition "Soil Condition"
    field steward "Assign Steward"

surface tree_edit "Edit Tree":
  uses entity Tree
  mode: edit

  section main "Edit Tree":
    field species "Species"
    field street_address "Street Address"
    field location_lat "Latitude"
    field location_lng "Longitude"
    field condition_status "Condition"
    field soil_condition "Soil Condition"
    field steward "Assign Steward"

# Observation Surfaces
surface observation_list "All Observations":
  uses entity Observation
  mode: list

  section main "Observations":
    field tree "Tree"
    field observer "Observer"
    field moisture_level "Moisture"
    field leaf_condition "Leaf Condition"
    field submitted_at "Date"

surface observation_detail "Observation Details":
  uses entity Observation
  mode: view

  section main "Observation":
    field tree "Tree"
    field observer "Observer"
    field moisture_level "Moisture Level"
    field leaf_condition "Leaf Condition"
    field has_insect_signs "Insect Signs"
    field insect_notes "Insect Notes"
    field photo_url "Photo"
    field notes "Notes"
    field submitted_at "Submitted"

surface observation_create "Log Observation":
  uses entity Observation
  mode: create

  section main "New Observation":
    field tree "Tree"
    field observer "Observer"
    field moisture_level "Moisture Level"
    field leaf_condition "Leaf Condition"
    field has_insect_signs "Insect Signs Present?"
    field insect_notes "Insect Notes"
    field photo_url "Photo"
    field notes "Additional Notes"

surface observation_edit "Edit Observation":
  uses entity Observation
  mode: edit

  section main "Edit Observation":
    field tree "Tree"
    field observer "Observer"
    field moisture_level "Moisture Level"
    field leaf_condition "Leaf Condition"
    field has_insect_signs "Insect Signs Present?"
    field insect_notes "Insect Notes"
    field photo_url "Photo"
    field notes "Additional Notes"

# Maintenance Task Surfaces
surface task_list "All Tasks":
  uses entity MaintenanceTask
  mode: list

  section main "Tasks":
    field tree "Tree"
    field task_type "Type"
    field status "Status"
    field assigned_to "Assigned To"
    field created_at "Created"

surface task_detail "Task Details":
  uses entity MaintenanceTask
  mode: view

  section main "Task Information":
    field tree "Tree"
    field task_type "Task Type"
    field status "Status"
    field created_by "Created By"
    field assigned_to "Assigned To"
    field notes "Notes"
    field created_at "Created"
    field updated_at "Last Updated"

surface task_create "Create Task":
  uses entity MaintenanceTask
  mode: create

  section main "New Task":
    field tree "Tree"
    field task_type "Task Type"
    field created_by "Created By"
    field assigned_to "Assign To"
    field status "Status"
    field notes "Notes"

surface task_edit "Edit Task":
  uses entity MaintenanceTask
  mode: edit

  section main "Edit Task":
    field tree "Tree"
    field task_type "Task Type"
    field assigned_to "Assign To"
    field status "Status"
    field notes "Notes"

# Volunteer Surfaces
surface volunteer_list "Volunteers":
  uses entity Volunteer
  mode: list

  section main "Volunteers":
    field name "Name"
    field skill_level "Skill Level"
    field preferred_area "Preferred Area"
    field is_active "Active"
    field joined_at "Joined"

surface volunteer_detail "Volunteer Profile":
  uses entity Volunteer
  mode: view

  section main "Profile":
    field name "Name"
    field skill_level "Skill Level"
    field preferred_area "Preferred Area"
    field is_active "Active"
    field joined_at "Joined"

surface volunteer_create "Add Volunteer":
  uses entity Volunteer
  mode: create

  section main "New Volunteer":
    field name "Name"
    field skill_level "Skill Level"
    field preferred_area "Preferred Area"
    field is_active "Active"

surface volunteer_edit "Edit Volunteer":
  uses entity Volunteer
  mode: edit

  section main "Edit Volunteer":
    field name "Name"
    field skill_level "Skill Level"
    field preferred_area "Preferred Area"
    field is_active "Active"
