from django.urls import path
from . import views

urlpatterns = [
    # Authentication and User Management
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
     path('accounts/password_reset/', 
         views.password_reset_request, 
         name='password_reset_request'),
         
    path('accounts/password_reset/sent/', 
         views.password_reset_sent, 
         name='password_reset_sent'),
         
    path('accounts/reset/<str:uidb64>/<str:token>/', 
         views.password_reset_confirm, 
         name='password_reset_confirm'),
     path('session-ping/', views.session_ping, name='session_ping'),
     
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/filter/<str:list_type>/', views.filtered_list_view, name='filtered_list'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('user/add/', views.user_add, name='user_add'),
    path('user/update/<int:pk>/', views.user_update, name='user_update'),
    path('user/delete/<int:pk>/', views.user_delete, name='user_delete'),
    path('manage-groups/', views.manage_groups, name='manage_groups'),
    path('delete-group/', views.delete_group, name='delete_group'),
    path('update-group-permissions/', views.update_group_permissions, name='update_group_permissions'),

    # Device Management
    path('import/add/', views.import_add, name='import_add'),
    path('import/update/<int:pk>/', views.import_update, name='import_update'),
    path('import/delete/<int:pk>/', views.import_delete, name='import_delete'),
    path('import/approve/<int:pk>/', views.import_approve, name='import_approve'),
    path('import/reject/<int:pk>/', views.import_reject, name='import_reject'),  # New: Added reject URL
    path('import/approve_all/', views.import_approve_all, name='import_approve_all'),
    path('import/download-template/', views.download_csv_template, name='download_csv_template'),
    path('devices/<int:device_id>/clear/', views.clear_user, name='clear_user'),
    path('devices/<int:device_id>/download_clearance/', views.download_clearance_form, name='download_clearance_form'),
    path('dispose/<int:device_id>/', views.dispose_device, name='dispose_device'),
    path('import/history/<int:pk>/', views.device_history, name='device_history'),

    path('dispose/add/', views.dispose_add, name='dispose_add'),
    path('dispose/template/', views.download_dispose_template, name='download_dispose_template'),

    # Reporting and Display
    path('displaycsv/', views.display_approved_imports, name='display_csv'),  # Legacy URL, consider deprecating
    path('displayreport/approved/', views.display_approved_imports, name='display_approved_imports'),
    path('displayreport/unapproved/', views.display_unapproved_imports, name='display_unapproved_imports'),
    path('displayreport/disposed/', views.display_disposed_imports, name='display_disposed_imports'),
    path('exportpdf/', views.export_to_pdf, name='export_to_pdf'),
    path('exportexcel/', views.export_to_excel, name='export_to_excel'),

  

    # Notifications
    path('notifications/', views.notifications_view, name='notifications_view'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/clear-all/', views.clear_all_notifications, name='clear_all_notifications'),  # New: Added clear all notifications URL
]