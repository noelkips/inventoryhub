from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from centre.models import Centre, Department
from .models import MissionCriticalAsset, BackupRegistry, WorkPlan, WorkPlanActivity

User = get_user_model()

class MissionCriticalAssetTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.dept = Department.objects.create(name='IT', department_code='IT001')
        
    def test_create_mission_critical_asset(self):
        asset = MissionCriticalAsset.objects.create(
            name='Test Asset',
            category='Infrastructure',
            location_scope='HQ',
            purpose_function='Test Purpose',
            backup_recovery_method='Test Method',
            department=self.dept,
            criticality_level='High',
            created_by=self.user
        )
        self.assertEqual(asset.name, 'Test Asset')
        self.assertEqual(asset.criticality_level, 'High')


class WorkPlanTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        today = timezone.now().date()
        self.monday = today - timedelta(days=today.weekday())
        self.sunday = self.monday + timedelta(days=6)
        
    def test_create_work_plan(self):
        plan = WorkPlan.objects.create(
            user=self.user,
            week_start_date=self.monday,
            week_end_date=self.sunday
        )
        self.assertEqual(plan.user, self.user)
        self.assertFalse(plan.is_submitted())
        
    def test_work_plan_with_activities(self):
        plan = WorkPlan.objects.create(
            user=self.user,
            week_start_date=self.monday,
            week_end_date=self.sunday
        )
        WorkPlanActivity.objects.create(
            work_plan=plan,
            day='Monday',
            activity='Test Activity'
        )
        self.assertTrue(plan.is_submitted())
