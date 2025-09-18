from django.urls import path
from . import views

urlpatterns = [
    path('ppm/devices/', views.ppm_device_list, name='ppm_device_list'),
    path('ppm/devices/<int:device_id>/task/create/', views.ppm_task_create, name='ppm_task_create'),
    path('ppm/devices/<int:device_id>/task/get/', views.get_ppm_task, name='get_ppm_task'),
    path('ppm/history/', views.ppm_history, name='ppm_history'),
    path('ppm/history/<int:device_id>/', views.ppm_history, name='ppm_history_device'),
    path('ppm/manage_activities/', views.manage_activities, name='manage_activities'),
    path('ppm/activity_edit/<int:activity_id>/', views.activity_edit, name='activity_edit'),
    path('ppm/activity_delete/<int:activity_id>/', views.activity_delete, name='activity_delete'),
    path('ppm/manage_periods/', views.manage_periods, name='manage_periods'),
    path('ppm/period_edit/<int:period_id>/', views.period_edit, name='period_edit'),
    path('ppm/period_delete/<int:period_id>/', views.period_delete, name='period_delete'),
    path('ppm/report/', views.ppm_report, name='ppm_report'),
]