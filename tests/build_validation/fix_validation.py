import sys

with open('/Volumes/SSD/Dazzle/tests/build_validation/validate_examples.py', 'r') as f:
    lines = f.readlines()

# Find and replace the validate_appspec method
in_validate_appspec = False
new_lines = []
skip_until_return = False

i = 0
while i < len(lines):
    line = lines[i]
    
    # Find the start of validate_appspec
    if 'def validate_appspec(' in line:
        in_validate_appspec = True
        # Add the whole method up to the try block
        while i < len(lines):
            new_lines.append(lines[i])
            if 'try:' in lines[i]:
                break
            i += 1
        i += 1
        
        # Add new validation logic
        new_lines.append('            with open(appspec_path) as f:\n')
        new_lines.append('                appspec = json.load(f)\n')
        new_lines.append('\n')
        new_lines.append('            # Check required top-level fields\n')
        new_lines.append('            if "name" not in appspec:\n')
        new_lines.append('                errors.append("Missing required field: name")\n')
        new_lines.append('            if "domain" not in appspec:\n')
        new_lines.append('                errors.append("Missing required field: domain")\n')
        new_lines.append('\n')
        new_lines.append('            # Validate domain structure\n')
        new_lines.append('            if "domain" in appspec:\n')
        new_lines.append('                domain = appspec["domain"]\n')
        new_lines.append('                \n')
        new_lines.append('                # Check entities\n')
        new_lines.append('                if "entities" not in domain:\n')
        new_lines.append('                    errors.append("Domain missing \'entities\' field")\n')
        new_lines.append('                elif not isinstance(domain["entities"], list):\n')
        new_lines.append('                    errors.append("Domain entities should be a list")\n')
        new_lines.append('                else:\n')
        new_lines.append('                    # Validate each entity\n')
        new_lines.append('                    for i, entity in enumerate(domain["entities"]):\n')
        new_lines.append('                        if not isinstance(entity, dict):\n')
        new_lines.append('                            errors.append(f"Entity {i} is not a dict")\n')
        new_lines.append('                            continue\n')
        new_lines.append('                        if "name" not in entity:\n')
        new_lines.append('                            errors.append(f"Entity {i} missing \'name\' field")\n')
        new_lines.append('                        if "fields" not in entity:\n')
        new_lines.append('                            errors.append(f"Entity {i} missing \'fields\' field")\n')
        new_lines.append('\n')
        new_lines.append('            # Validate surfaces (at top level, not in domain)\n')
        new_lines.append('            if "surfaces" in appspec:\n')
        new_lines.append('                if not isinstance(appspec["surfaces"], list):\n')
        new_lines.append('                    errors.append("surfaces should be a list")\n')
        new_lines.append('                else:\n')
        new_lines.append('                    # Validate each surface\n')
        new_lines.append('                    for i, surface in enumerate(appspec["surfaces"]):\n')
        new_lines.append('                        if not isinstance(surface, dict):\n')
        new_lines.append('                            errors.append(f"Surface {i} is not a dict")\n')
        new_lines.append('                            continue\n')
        new_lines.append('                        if "name" not in surface:\n')
        new_lines.append('                            errors.append(f"Surface {i} missing \'name\' field")\n')
        new_lines.append('                        if "entity" not in surface:\n')
        new_lines.append('                            errors.append(f"Surface {i} missing \'entity\' field")\n')
        new_lines.append('                        if "mode" not in surface:\n')
        new_lines.append('                            errors.append(f"Surface {i} missing \'mode\' field")\n')
        new_lines.append('\n')
        new_lines.append('            return len(errors) == 0, errors\n')
        new_lines.append('\n')
        
        # Skip old validation code until we hit the exception handlers
        while i < len(lines) and 'except json.JSONDecodeError' not in lines[i]:
            i += 1
        continue
        
    new_lines.append(line)
    i += 1

with open('/Volumes/SSD/Dazzle/tests/build_validation/validate_examples.py', 'w') as f:
    f.writelines(new_lines)

print("Fixed validation logic")
