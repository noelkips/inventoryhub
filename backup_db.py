import os
import django
from django.core.management import call_command

# 1. Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'itinventory.settings')
django.setup()

# 2. Configuration
OUTPUT_FILE = 'full_db_dump_utf8.json'

print(f"Starting dump to {OUTPUT_FILE} in UTF-8...")

# 3. Open file with explicit UTF-8 encoding
try:
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        call_command(
            'dumpdata',
            # exclude=['sessions'], # Short name
            exclude=['contenttypes', 'auth.permission', 'sessions'], # RECOMMENDED EXCLUSIONS
            indent=4,               # Pretty print JSON
            natural_foreign=True,   # Helps with Foreign Keys to ContentTypes
            natural_primary=True,   # Helps prevent PK conflicts
            stdout=f                # Redirect output to the file
        )
    print("✅ Success! Data dumped successfully.")
except Exception as e:
    print(f"❌ Error: {e}")