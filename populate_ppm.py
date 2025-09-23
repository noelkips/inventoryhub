import os
import django
from datetime import datetime

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'itinventory.settings')
django.setup()

from devices.models import Import, Centre, CustomUser
from ppm.models import PPMPeriod, PPMActivity, PPMTask

# Get the current date and time
current_datetime = datetime.now()

# Set the completed date to 09/19/2025
completed_date = datetime(2025, 9, 17).date()

# Find the Pangani Centre
pangani_centre = Centre.objects.filter(name__iexact='Pangani').first()
if not pangani_centre:
    print("Error: Pangani Centre not found. Please ensure the centre exists.")
    exit(1)

# Get all devices assigned to Pangani Centre
devices = Import.objects.filter(centre=pangani_centre)

# Get the active PPM period
active_period = PPMPeriod.objects.filter(is_active=True).first()
if not active_period:
    print("Error: No active PPM period found. Please ensure an active period is set.")
    exit(1)

# Get the specific activities
try:
    # Base activities (1, 2, 6, 7) for non-laptop hardware
    base_activities = PPMActivity.objects.filter(id__in=[1, 2, 6, 7])
    # Extended activities (1, 2, 3, 4, 5, 6, 7, 8, 10) for laptops
    laptop_activities = PPMActivity.objects.filter(id__in=[1, 2, 3, 4, 5, 6, 7, 8, 10])
    if not base_activities.exists() or not laptop_activities.exists():
        print("Error: One or more specified activities not found. Please ensure these activities exist.")
        exit(1)
except PPMActivity.DoesNotExist:
    print("Error: One or more specified activities not found.")
    exit(1)

# Get the current user (e.g., admin user for created_by)
created_by_user = CustomUser.objects.filter(is_superuser=True).first()
if not created_by_user:
    print("Error: No superuser found for created_by. Please ensure an admin user exists.")
    exit(1)

# Populate or update PPM tasks for each device
updated_tasks = 0
created_tasks = 0
for device in devices:
    # Determine activities based on hardware
    activities = laptop_activities if device.hardware.lower() == 'laptop' else base_activities
    
    # Check if a PPM task already exists for this device and period
    existing_task = PPMTask.objects.filter(device=device, period=active_period).first()
    if existing_task:
        # Update only the completed_date if it differs
        if existing_task.completed_date != completed_date:
            existing_task.completed_date = completed_date
            existing_task.remarks = "device is in good condition"
            existing_task.save()
            # Update activities if they differ
            current_activity_ids = [a.id for a in existing_task.activities.all()]
            if sorted(current_activity_ids) != sorted([a.id for a in activities]):
                existing_task.activities.set(activities)
                print(f"Updated completed_date to {completed_date}, remarks to 'device is in good condition', and activities to {', '.join(a.name for a in activities)} for device {device.serial_number}")
            else:
                print(f"Updated completed_date to {completed_date} and remarks to 'device is in good condition' for device {device.serial_number}")
            updated_tasks += 1
        else:
            # Check if activities need updating
            current_activity_ids = [a.id for a in existing_task.activities.all()]
            if sorted(current_activity_ids) != sorted([a.id for a in activities]):
                existing_task.activities.set(activities)
                print(f"Updated activities to {', '.join(a.name for a in activities)} for device {device.serial_number}")
            else:
                print(f"Completed date and activities for device {device.serial_number} are already correct. Skipping...")
    else:
        # Create a new PPM task with completed_date, remarks, and appropriate activities
        ppm_task = PPMTask.objects.create(
            device=device,
            period=active_period,
            created_by=created_by_user,
            completed_date=completed_date,
            remarks="device is in good condition"
        )
        # Assign the appropriate activities
        ppm_task.activities.set(activities)
        created_tasks += 1
        print(f"Created PPM task for device {device.serial_number} with activities {', '.join(a.name for a in activities)} and completed on {completed_date} with remarks 'device is in good condition'")

print(f"Total PPM tasks created: {created_tasks}")
print(f"Total PPM tasks updated: {updated_tasks}")
print(f"Script completed at {current_datetime.strftime('%Y-%m-%d %H:%M:%S')} EAT")