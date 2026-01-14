import random
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction


from devices.models import (
    Centre, 
    Department
)
from it_operations.models import (
    WorkPlan, 
    WorkPlanTask, 
    PublicHoliday, 
)
User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds Work Plans with Tasks, random Collaborators, and Other Parties'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('Starting ADVANCED data seeding process...'))

        # 1. CONFIGURATION
        # ---------------------------------------------------------
        current_year = 2025
        today = timezone.now().date()
        
        start_date = date(current_year, 10, 1)   
        end_date = date(current_year, 12, 31)    

        # 2. HOLIDAY SETUP
        # ---------------------------------------------------------
        holidays_data = [
            {"name": "Mazingira Day", "date": date(current_year, 10, 10)},
            {"name": "Mashujaa Day", "date": date(current_year, 10, 20)},
            {"name": "Jamhuri Day", "date": date(current_year, 12, 12)},
            {"name": "Christmas Day", "date": date(current_year, 12, 25)},
        ]

        holiday_dates = []
        for h in holidays_data:
            PublicHoliday.objects.get_or_create(date=h['date'], defaults={'name': h['name']})
            holiday_dates.append(h['date'])

        # 3. DATA POOLS
        # ---------------------------------------------------------
        
        # IT Tasks
        it_tasks_pool = [
            "Troubleshoot network connectivity", "Re-imaging lab computers",
            "Install QuickBooks update", "Replace faulty HDMI cables",
            "Server Room log check", "Configure Outlook for new staff",
            "Weekly Data Backup", "Printer maintenance (Kyocera)",
            "Update Anti-virus definitions", "Biometric system troubleshooting",
            "Cabling organization", "Resetting domain passwords",
            "Inventory audit", "Setup projector for training",
            "Crimping LAN cables", "Troubleshoot internet speeds",
            "Patch Management", "Cleaning System Units",
            "Configuring Firewall rules", "IT Asset tagging"
        ]

        # Other Parties (External or Non-IT)
        other_parties_pool = [
            "HR Manager", "Safaricom Technical Team", "Office Administrator",
            "Finance Dept Head", "External Auditor", "Power Technicians",
            "Procurement Officer", "Training Facilitator", 
            None, None, None, None, None # Added None multiple times to make it occasional
        ]

        # Fetch DB Objects
        # We convert users to a list so we can use random.sample easily
        all_users = list(User.objects.all())
        centres = list(Centre.objects.all())
        departments = list(Department.objects.all())

        if not all_users:
            self.stdout.write(self.style.ERROR("No users found."))
            return

        # 4. CLEANUP
        # ---------------------------------------------------------
        self.stdout.write("Cleaning up existing tasks for this period...")
        WorkPlanTask.objects.filter(date__range=[start_date, end_date]).delete()

        # 5. GENERATION LOOP
        # ---------------------------------------------------------
        total_tasks_created = 0

        with transaction.atomic():
            for user in all_users:
                self.stdout.write(f"Generating data for: {user.username}...")

                current_loop_date = start_date
                while current_loop_date <= end_date:
                    
                    # Skip Logic (Sundays & Holidays)
                    if current_loop_date.weekday() == 6 or current_loop_date in holiday_dates:
                        current_loop_date += timedelta(days=1)
                        continue

                    # WorkPlan Container
                    monday_of_week = current_loop_date - timedelta(days=current_loop_date.weekday())
                    work_plan, _ = WorkPlan.objects.get_or_create(
                        user=user,
                        week_start_date=monday_of_week,
                        defaults={'week_end_date': monday_of_week + timedelta(days=5)}
                    )

                    # Status Logic
                    if current_loop_date < today:
                        status_choice = random.choices(['Completed', 'Not Done'], weights=[85, 15], k=1)[0]
                    else:
                        status_choice = random.choices(['Pending', 'Rescheduled'], weights=[90, 10], k=1)[0]

                    # Pick "Other Parties"
                    selected_party = random.choice(other_parties_pool)

                    # --- CREATE THE TASK OBJECT FIRST ---
                    task = WorkPlanTask.objects.create(
                        work_plan=work_plan,
                        date=current_loop_date,
                        is_leave=False,
                        task_name=random.choice(it_tasks_pool),
                        centre=random.choice(centres) if centres else None,
                        department=random.choice(departments) if departments else None,
                        other_parties=selected_party,  # <--- Added here
                        resources_needed="Standard Toolkit",
                        target="Resolution",
                        comments="Routine task" if status_choice == 'Completed' else None,
                        status=status_choice,
                        created_by=user
                    )

                    # --- ADD COLLABORATORS (Many-to-Many) ---
                    # Logic: Pick 0, 1, or 2 collaborators.
                    # We filter the list to ensure the user doesn't collaborate with themselves.
                    
                    possible_collabs = [u for u in all_users if u.id != user.id]
                    
                    if possible_collabs:
                        # 70% chance of 0 collaborators, 20% chance of 1, 10% chance of 2
                        num_collabs = random.choices([0, 1, 2], weights=[70, 20, 10], k=1)[0]
                        
                        if num_collabs > 0:
                            selected_collabs = random.sample(possible_collabs, k=min(num_collabs, len(possible_collabs)))
                            # Django M2M .add() accepts a list of objects using *args
                            task.collaborators.add(*selected_collabs)

                    total_tasks_created += 1
                    current_loop_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f'Done! Created {total_tasks_created} tasks with collaborators.'))