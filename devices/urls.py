from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('logout/', views.logout_view, name='logout'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    path('upload/', views.upload_csv, name='upload_csv'),
    path('displaycsv/', views.display_csv, name='display_csv'),
    path('exportpdf/', views.export_to_pdf, name='export_to_pdf'),
    path('exportexcel/', views.export_to_excel, name='export_to_excel'),
    path('displayreport/', views.display_csv, name='import_displaycsv'),
    
    path('import/add/', views.import_add, name='import_add'),
    path('import/update/<int:pk>/', views.import_update, name='import_update'),
    path('import/delete/<int:pk>/', views.import_delete, name='import_delete'),
    path('import/approve/<int:pk>/', views.import_approve, name='import_approve'),
    path('import/approve_all/', views.import_approve_all, name='import_approve_all'),
    
    path('imports/add/', views.imports_add, name='imports_add'),
    path('imports/view/', views.imports_view, name='imports_view'),
    
    path('manage-users/', views.manage_users, name='manage_users'),
    path('user/add/', views.user_add, name='user_add'),
    path('user/update/<int:pk>/', views.user_update, name='user_update'),
    path('user/delete/<int:pk>/', views.user_delete, name='user_delete'),
    path('manage-groups/', views.manage_groups, name='manage_groups'),
    path('delete-group/', views.delete_group, name='delete_group'),
    path('update-group-permissions/', views.update_group_permissions, name='update_group_permissions'),
]


# from django.urls import path
# from . import views
# from django.contrib.auth import views as auth_views

# urlpatterns = [
#     path('', views.login_view, name='login'),
#     path('dashboard/', views.dashboard_view, name='dashboard'),
#     path('logout/', views.logout_view, name='logout'),
#     path('import/uploadcsv/', views.upload_csv, name='import_uploadcsv'),
#     path('imports/add/', views.imports_add, name='import_add'),
#     path('imports/', views.imports_view, name='import_displaycsv'),
#     path('display_csv/', views.display_csv, name='display_csv'),
#     path('import/update/<int:pk>/', views.import_update, name='import_update'),
#     path('import/delete/<int:pk>/', views.import_delete, name='import_delete'),
#     path('import/approve/<int:pk>/', views.import_approve, name='import_approve'),
#     path('import/approve_all/', views.import_approve_all, name='import_approve_all'),
#     path('export/pdf/', views.export_to_pdf, name='export_to_pdf'),
#     path('export/excel/', views.export_to_excel, name='export_to_excel'),
#     path('profile/', views.profile, name='profile'),
#     path('change_password/', views.change_password, name='change_password'),
#     path('manage_users/', views.manage_users, name='manage_users'),
#     path('user/add/', views.user_add, name='user_add'),
#     path('user/update/<int:pk>/', views.user_update, name='user_update'),
#     path('user/delete/<int:pk>/', views.user_delete, name='user_delete'),
#     path('manage_groups/', views.manage_groups, name='manage_groups'),
#     path('delete_group/', views.delete_group, name='delete_group'),
#     path('update_group_permissions/', views.update_group_permissions, name='update_group_permissions'),
# ]