import sys

with open('/Volumes/SSD/Dazzle/tests/build_validation/validate_examples.py', 'r') as f:
    content = f.read()

# Fix references to entities and surfaces
content = content.replace('appspec.domain.entities', 'appspec.domain.entities')
content = content.replace('appspec.domain.surfaces', 'appspec.surfaces')

# Also fix where we set the counts
content = content.replace(
    'entity_count = len(appspec.domain.entities)\n            surface_count = len(appspec.domain.surfaces)',
    'entity_count = len(appspec.domain.entities)\n            surface_count = len(appspec.surfaces)'
)

with open('/Volumes/SSD/Dazzle/tests/build_validation/validate_examples.py', 'w') as f:
    f.write(content)

print("Fixed surface references")
