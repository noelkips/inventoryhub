#!/bin/bash
# Usage: bash rename_hardware.sh

echo "Running hardware name updater..."

# Activate virtual environment if needed
# source venv/bin/activate

python manage.py shell <<'EOF'
from devices.models import Import  # adjust 'devices' to your actual app name
from django.db.models import Q

# 🧩 Define your replacements (word to fix)
replacements = {
    "Systen": "System",
}

for old, new in replacements.items():
    qs = Import.objects.filter(Q(hardware__icontains=old))
    count = qs.count()
    if count:
        print(f"\n🔍 Found {count} records containing '{old}' — updating...")
        for item in qs:
            original = item.hardware
            if original:
                corrected = original.replace(old, new)
                if corrected != original:
                    print(f"   {original} → {corrected}")
                    item.hardware = corrected
                    item.save(update_fields=["hardware"])
    else:
        print(f"No matches found for '{old}'")

print("\n✅ Partial hardware name update complete.")
EOF

