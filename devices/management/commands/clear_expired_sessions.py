"""
Management Command to Clear Expired Sessions

Location: devices/management/commands/clear_expired_sessions.py

Run this command periodically (via cron or task scheduler):
python manage.py clear_expired_sessions

Or set up a cron job:
0 */6 * * * cd /path/to/project && python manage.py clear_expired_sessions
"""

from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone


class Command(BaseCommand):
    help = 'Clears expired sessions from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get expired sessions
        expired_sessions = Session.objects.filter(expire_date__lt=timezone.now())
        count = expired_sessions.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would delete {count} expired sessions')
            )
        else:
            # Delete expired sessions
            expired_sessions.delete()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully deleted {count} expired sessions')
            )
        
        # Show current active sessions
        active_sessions = Session.objects.filter(expire_date__gte=timezone.now()).count()
        self.stdout.write(
            self.style.SUCCESS(f'Active sessions remaining: {active_sessions}')
        )