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
    
    #Work plan
    path('calendar/', views.work_plan_calendar, name='calendar'),
    path('calendar/<int:year>/<int:month>/', views.work_plan_calendar, name='calendar_month'),
    path('<int:pk>/', views.work_plan_detail, name='work_plan_detail'),
    path('list/', views.work_plan_list, name='work_plan_list'),
    
    path('<int:pk>/add-task/', views.add_task, name='add_task'),
    path('task/<int:pk>/status/', views.update_task_status, name='update_task_status'),
    path('task/<int:pk>/delete/', views.delete_task, name='delete_task'),
]
