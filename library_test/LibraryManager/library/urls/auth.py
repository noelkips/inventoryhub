from django.urls import path
from .. import views

auth_urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('login/', views.login_view, name='login_view'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('user/add/', views.user_add, name='user_add'),
    path('user/<int:pk>/update/', views.user_update, name='user_update'),
    path('user/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('user/<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),
]

urlpatterns = auth_urlpatterns
