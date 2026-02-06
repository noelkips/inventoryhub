"""
Simple Device Assignment Script - Match Only (No Employee Creation)

This script ONLY matches existing Import devices to existing Employee records.
It will NOT create new Employee records.

Run in Django shell:
    python manage.py shell
    exec(open('assign_devices_match_only.py').read())
"""

from devices.models import Import, Employee
from django.db.models import Q

print('='*70)
print('DEVICE ASSIGNMENT SCRIPT - MATCH EXISTING EMPLOYEES ONLY')
print('='*70)
print()

# Step 1: Count devices without names (will be skipped)
devices_without_names = Import.objects.filter(
    assignee__isnull=True
).filter(
    Q(assignee_first_name__isnull=True) | 
    Q(assignee_first_name='') |
    Q(assignee_last_name__isnull=True) | 
    Q(assignee_last_name='')
).count()

print(f'ℹ️  {devices_without_names} devices have no first/last name - will remain unassigned')
print()

# Step 2: Get devices to process (must have both first and last name)
devices_to_assign = Import.objects.filter(
    assignee__isnull=True,
    assignee_first_name__isnull=False,
    assignee_last_name__isnull=False,
).exclude(
    Q(assignee_first_name='') | Q(assignee_last_name='')
)

total = devices_to_assign.count()
print(f'📦 Found {total} devices with names to process')
print()

if total == 0:
    print('✅ No devices need assignment!')
    print('='*70)
else:
    print('Starting matching process...')
    print('-'*70)
    
    matched = 0
    unmatched = 0
    unmatched_list = []
    
    for device in devices_to_assign:
        first = device.assignee_first_name.strip()
        last = device.assignee_last_name.strip()
        
        # Skip if empty after stripping
        if not first or not last:
            continue
        
        # Build expected email
        expected_email = f"{first.lower()}.{last.lower()}@mohiafrica.org"
        old_email = device.assignee_email_address
        
        employee = None
        
        # Try 1: Match by expected email pattern
        try:
            employee = Employee.objects.get(email__iexact=expected_email)
            print(f'✅ {first} {last} → {employee.email}')
        except Employee.DoesNotExist:
            pass
        except Employee.MultipleObjectsReturned:
            print(f'⚠️  Multiple employees with email: {expected_email}')
            continue
        
        # Try 2: Match by old email (if it exists)
        if not employee and old_email:
            try:
                employee = Employee.objects.get(email__iexact=old_email)
                print(f'✅ {first} {last} → {employee.email} [old email]')
            except Employee.DoesNotExist:
                pass
            except Employee.MultipleObjectsReturned:
                print(f'⚠️  Multiple employees with email: {old_email}')
                continue
        
        # Try 3: Match by name only
        if not employee:
            try:
                employee = Employee.objects.get(
                    first_name__iexact=first,
                    last_name__iexact=last
                )
                print(f'✅ {first} {last} → {employee.email} [name match]')
            except Employee.DoesNotExist:
                pass
            except Employee.MultipleObjectsReturned:
                print(f'⚠️  Multiple employees named: {first} {last}')
                continue
        
        # Assign if found
        if employee:
            # Check if email already exists (safety check)
            if Employee.objects.filter(email=employee.email).count() == 1:
                device.assignee = employee
                device.save(update_fields=['assignee', 'assignee_cache'])
                matched += 1
            else:
                print(f'⚠️  Duplicate email issue: {employee.email}')
        else:
            print(f'❌ No employee found: {first} {last} (expected: {expected_email})')
            unmatched += 1
            unmatched_list.append({
                'name': f'{first} {last}',
                'expected_email': expected_email,
                'old_email': old_email or 'N/A',
                'serial': device.serial_number or 'N/A'
            })
    
    # Summary
    print()
    print('='*70)
    print('SUMMARY')
    print('='*70)
    print(f'Total devices processed:  {total}')
    print(f'✅ Successfully matched:  {matched}')
    print(f'❌ Unmatched:             {unmatched}')
    print(f'⏭️  Skipped (no names):    {devices_without_names}')
    print()
    
    # Show unmatched details
    if unmatched_list:
        print('='*70)
        print('UNMATCHED DEVICES - CREATE THESE EMPLOYEES MANUALLY:')
        print('='*70)
        for item in unmatched_list:
            print(f"\n📋 {item['name']}")
            print(f"   Serial: {item['serial']}")
            print(f"   Expected Email: {item['expected_email']}")
            print(f"   Old Email: {item['old_email']}")
            print(f"\n   Create employee with:")
            print(f"   Employee.objects.create(")
            parts = item['name'].split()
            if len(parts) >= 2:
                print(f"       first_name='{parts[0]}',")
                print(f"       last_name='{parts[1]}',")
            print(f"       email='{item['expected_email']}'")
            print(f"   )")
        print()
    
    print('='*70)
    print('✅ Assignment complete!')
    print('='*70)
    
    if unmatched > 0:
        print(f'\nℹ️  {unmatched} devices still need employees created.')
        print('   Create the missing employees, then run this script again.')
