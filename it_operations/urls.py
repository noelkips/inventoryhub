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
    
    # Work plan Core
    path('workplans/', views.work_plan_list, name='work_plan_list'),
    path('workplans/create/', views.work_plan_create, name='work_plan_create'),
    path('workplans/<int:pk>/', views.work_plan_detail, name='work_plan_detail'),
    
    # Task Actions (POST)
    path('workplans/task/<int:pk>/delete/', views.work_plan_task_delete, name='work_plan_task_delete'),
    path('workplans/task/<int:pk>/status/', views.work_plan_task_status_update, name='work_plan_task_status_update'),
    path('workplans/task/<int:pk>/edit/', views.work_plan_task_edit, name='work_plan_task_edit'),
    path('workplans/task/<int:pk>/comment/', views.work_plan_task_add_comment, name='work_plan_task_add_comment'),
    
    # Reschedule URL
    path('workplans/task/<int:pk>/reschedule/', views.work_plan_task_reschedule, name='work_plan_task_reschedule'),

    # API for Calendar Modal (NEW)
    path('workplans/api/task/<int:pk>/', views.get_task_details_json, name='get_task_details_json'),
    # Reporting & Calendar
    path('workplans/calendar/', views.work_plan_calendar, name='work_plan_calendar'),
    path('workplans/create_from_calendar/', views.work_plan_create_task_from_calendar, name='work_plan_create_task_from_calendar'),
    path('workplans/<int:pk>/pdf/', views.download_workplan_pdf, name='download_workplan_pdf'),
    path('workplans/export/excel/', views.download_bulk_excel_report, name='download_bulk_excel_report'),
    path('workplans/bulk-pdf/', views.download_bulk_pdf_report, name='download_bulk_pdf_report'),

    path('incident-reports/', views.incident_report_list, name='incident_report_list'),
    path('incident-reports/create/', views.incident_report_create, name='incident_report_create'),
    path('incident-reports/<int:pk>/', views.incident_report_detail, name='incident_report_detail'),
    path('incident-reports/<int:pk>/update/', views.incident_report_update, name='incident_report_update'),
    path('incident-reports/<int:pk>/delete/', views.incident_report_delete, name='incident_report_delete'),
    path('incident-reports/<int:pk>/download-pdf/', views.download_incident_report_pdf, name='download_incident_report_pdf'),
]

