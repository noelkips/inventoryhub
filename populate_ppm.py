import os
import django
from datetime import datetime

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'itinventory.settings')
django.setup()

from devices.models import Import, Centre, CustomUser
from ppm.models import PPMPeriod, PPMActivity, PPMTask

# Get current datetime
current_datetime = datetime.now()

# Desired completed date
completed_date = datetime(2025, 10, 8).date()

# Centre lookup
centre = Centre.objects.filter(pk=32)
print(f"{centre}")
if not centre:
    print("Error: Centre 'Molo Turi High School' not found.")
    exit(1)

# Devices in centre
devices = Import.objects.filter(centre=centre)

# Active PPM period
active_period = PPMPeriod.objects.filter(is_active=True).first()
if not active_period:
    print("Error: No active PPM period found.")
    exit(1)

# Activities
activity_map = {
    "base": list(PPMActivity.objects.filter(id__in=[1, 2, 6, 7])),
    "laptop": list(PPMActivity.objects.filter(id__in=[1, 2, 3, 4, 5, 6, 7, 8, 10])),
    "monitor": list(PPMActivity.objects.filter(id=1)),
    "system_unit": list(PPMActivity.objects.filter(id__in=[6, 7])),
}

# Ensure all required activities exist
for key, activities in activity_map.items():
    if not activities:
        print(f"Error: Activities for {key} not found.")
        exit(1)

# Admin user
admin_user = CustomUser.objects.filter(is_superuser=True).first()
if not admin_user:
    print("Error: No superuser found.")
    exit(1)

# Start processing
created_tasks = 0
updated_tasks = 0

for device in devices:
    hardware = device.hardware.lower()

    # Select activities based on hardware
    if "monitor" in hardware:
        selected_activities = activity_map["monitor"]
    elif "system unit" in hardware or "system" in hardware:
        selected_activities = activity_map["system_unit"]
    elif "laptop" in hardware:
        selected_activities = activity_map["laptop"]
    else:
        selected_activities = activity_map["base"]

    selected_activity_ids = [a.id for a in selected_activities]

    # Check for existing PPM task
    task = PPMTask.objects.filter(device=device, period=active_period).first()

    if task:
        updated = False

        # Update completed date
        if task.completed_date != completed_date:
            task.completed_date = completed_date
            updated = True

        # Update remarks
        if task.remarks != "Device in good condition":
            task.remarks = "Device in good condition"
            updated = True

        # Update activities if they differ
        current_ids = list(task.activities.values_list('id', flat=True))
        if sorted(current_ids) != sorted(selected_activity_ids):
            task.activities.set(selected_activities)
            updated = True
            print(f"[{device.serial_number}] Activities updated.")

        if updated:
            task.save()
            updated_tasks += 1
            print(f"[{device.serial_number}] Task updated.")
        else:
            print(f"[{device.serial_number}] No changes needed.")
    else:
        # Create new task
        new_task = PPMTask.objects.create(
            device=device,
            period=active_period,
            created_by=admin_user,
            completed_date=completed_date,
            remarks="Device in good condition"
        )
        new_task.activities.set(selected_activities)
        created_tasks += 1
        print(f"[{device.serial_number}] New task created.")

# Summary
print(f"\nSummary:")
print(f"Tasks created: {created_tasks}")
print(f"Tasks updated: {updated_tasks}")
print(f"Finished at: {current_datetime.strftime('%Y-%m-%d %H:%M:%S')} EAT")
