from django.urls import path
from . import views

urlpatterns = [
    # Mission Critical Assets
    path('mission-critical/', views.mission_critical_list, name='mission_critical_list'),
    path('mission-critical/<int:pk>/', views.mission_critical_detail, name='mission_critical_detail'),
    path('mission-critical/add/', views.mission_critical_create, name='mission_critical_create'),
    path('mission-critical/<int:pk>/edit/', views.mission_critical_update, name='mission_critical_update'),
    path('mission-critical/<int:pk>/delete/', views.mission_critical_delete, name='mission_critical_delete'),
    
    # Backup Registry
    path('backup-registry/', views.backup_registry_list, name='backup_registry_list'),
    path('backup-registry/add/', views.backup_registry_create, name='backup_registry_create'),
    path('backup-registry/<int:pk>/edit/', views.backup_registry_update, name='backup_registry_update'),
    path('backup-registry/<int:pk>/delete/', views.backup_registry_delete, name='backup_registry_delete'),
    
    # Work Plan
    path('work-plan/', views.work_plan_list, name='work_plan_list'),
    path('work-plan/<int:pk>/', views.work_plan_detail, name='work_plan_detail'),
    path('work-plan/add/', views.work_plan_create, name='work_plan_create'),
    path('work-plan/<int:pk>/edit/', views.work_plan_update, name='work_plan_update'),
    path('work-plan/<int:pk>/comment/', views.work_plan_add_task_comment, name='work_plan_add_comment'),
    path('work-plan/calendar/', views.work_plan_calendar, name='work_plan_calendar'),
    path('work-plan/calendar/<int:user_id>/', views.work_plan_calendar, name='work_plan_calendar_user'),
]
