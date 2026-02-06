"""
Django management command to migrate legacy device assignee data to Employee model.

This script:
1. Reads assignee data from Import (device) records
2. Creates Employee records from legacy first_name, last_name, email fields
3. Links devices to their respective Employee records
4. Handles duplicate emails by reusing existing employees
5. Generates email addresses for missing data (firstname.lastname@mohiafrica.org)
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from devices.models import Import, Employee  
import re


class Command(BaseCommand):
    help = 'Migrate legacy device assignee data to Employee model'

    def __init__(self):
        super().__init__()
        self.stats = {
            'devices_processed': 0,
            'devices_skipped': 0,
            'employees_created': 0,
            'employees_reused': 0,
            'devices_assigned': 0,
            'errors': []
        }

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making any changes to the database',
        )

    def normalize_email(self, email):
        """Normalize email to lowercase and strip whitespace"""
        if email:
            return email.strip().lower()
        return None

    def generate_email(self, first_name, last_name):
        """Generate email from first and last name"""
        if not first_name or not last_name:
            return None
        
        # Clean names: remove special characters, convert to lowercase
        first_clean = re.sub(r'[^a-zA-Z]', '', first_name).lower()
        last_clean = re.sub(r'[^a-zA-Z]', '', last_name).lower()
        
        if not first_clean or not last_clean:
            return None
            
        return f"{first_clean}.{last_clean}@mohiafrica.org"

    def clean_name(self, name):
        """Clean and normalize a name field"""
        if name:
            return name.strip()
        return None

    def should_skip_device(self, device):
        """Determine if a device should be skipped"""
        first_name = self.clean_name(device.assignee_first_name)
        last_name = self.clean_name(device.assignee_last_name)
        email = self.normalize_email(device.assignee_email_address)
        
        # Skip if both first and last name are blank
        if not first_name and not last_name:
            return True, "Both first and last name are blank"
        
        # Skip if either first or last name is blank (but not both)
        if not first_name or not last_name:
            return True, f"Missing {'first' if not first_name else 'last'} name"
        
        return False, None

    def get_or_create_employee(self, device, dry_run=False):
        """
        Get existing employee or create new one from device data.
        Returns (employee, created) tuple.
        """
        first_name = self.clean_name(device.assignee_first_name)
        last_name = self.clean_name(device.assignee_last_name)
        email = self.normalize_email(device.assignee_email_address)
        
        # Generate email if not provided
        if not email:
            email = self.generate_email(first_name, last_name)
        
        if not email:
            return None, False
        
        # Try to find existing employee by email
        try:
            employee = Employee.objects.get(email=email)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ Found existing employee: {employee.full_name} ({email})"
                )
            )
            self.stats['employees_reused'] += 1
            return employee, False
        except Employee.DoesNotExist:
            pass
        
        # Create new employee
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"  → Would create employee: {first_name} {last_name} ({email})"
                )
            )
            return None, True
        
        employee = Employee.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            centre=device.centre,
            department=device.department,
            is_active=True
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ Created employee: {employee.full_name} ({email})"
            )
        )
        self.stats['employees_created'] += 1
        return employee, True

    def assign_device_to_employee(self, device, employee, dry_run=False):
        """Assign a device to an employee"""
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"  → Would assign device {device.serial_number} to {employee.full_name if employee else 'new employee'}"
                )
            )
            return False
        
        device.assignee = employee
        device.save(update_fields=['assignee', 'assignee_cache'])
        
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ Assigned device {device.serial_number} to {employee.full_name}"
            )
        )
        self.stats['devices_assigned'] += 1
        return True

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\n=== DRY RUN MODE - No changes will be made ===\n')
            )
        
        self.stdout.write(self.style.MIGRATE_HEADING('Starting device assignee migration...\n'))
        
        # Get all devices that haven't been migrated yet
        devices = Import.objects.filter(assignee__isnull=True).select_related(
            'centre', 'department'
        )
        
        total_devices = devices.count()
        self.stdout.write(f"Found {total_devices} devices to process\n")
        
        if total_devices == 0:
            self.stdout.write(self.style.SUCCESS('No devices to migrate!'))
            return
        
        # Process devices
        with transaction.atomic():
            for i, device in enumerate(devices, 1):
                self.stdout.write(
                    self.style.MIGRATE_LABEL(
                        f"\n[{i}/{total_devices}] Processing device: {device.serial_number}"
                    )
                )
                
                self.stats['devices_processed'] += 1
                
                # Check if device should be skipped
                should_skip, skip_reason = self.should_skip_device(device)
                if should_skip:
                    self.stdout.write(
                        self.style.WARNING(f"  ⊗ Skipped: {skip_reason}")
                    )
                    self.stats['devices_skipped'] += 1
                    continue
                
                try:
                    # Get or create employee
                    employee, created = self.get_or_create_employee(device, dry_run)
                    
                    if not employee and dry_run:
                        # In dry run, still count the would-be assignment
                        self.stats['devices_assigned'] += 1
                        continue
                    
                    if employee:
                        # Assign device to employee
                        self.assign_device_to_employee(device, employee, dry_run)
                    
                except Exception as e:
                    error_msg = f"Error processing device {device.serial_number}: {str(e)}"
                    self.stdout.write(self.style.ERROR(f"  ✗ {error_msg}"))
                    self.stats['errors'].append(error_msg)
                    
            # Rollback if dry run
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING('\n=== DRY RUN - Transaction rolled back ===')
                )
        
        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print migration summary statistics"""
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.MIGRATE_HEADING('MIGRATION SUMMARY'))
        self.stdout.write('=' * 60)
        
        self.stdout.write(f"\n📊 Devices:")
        self.stdout.write(f"  • Processed: {self.stats['devices_processed']}")
        self.stdout.write(f"  • Skipped: {self.stats['devices_skipped']}")
        self.stdout.write(f"  • Assigned: {self.stats['devices_assigned']}")
        
        self.stdout.write(f"\n👥 Employees:")
        self.stdout.write(f"  • Created: {self.stats['employees_created']}")
        self.stdout.write(f"  • Reused (existing): {self.stats['employees_reused']}")
        
        if self.stats['errors']:
            self.stdout.write(
                self.style.ERROR(f"\n⚠️  Errors: {len(self.stats['errors'])}")
            )
            for error in self.stats['errors']:
                self.stdout.write(f"  • {error}")
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ No errors!"))
        
        self.stdout.write('\n' + '=' * 60 + '\n')