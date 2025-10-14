from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.utils.crypto import get_random_string
from django.contrib.auth.models import Group, Permission
from .models import CustomUser, Centre


def is_authorized_for_manage_users(user):
    return user.is_superuser or user.is_site_admin or user.is_staff


def can_reset_password(current_user, target_user):
    if current_user.is_superuser:
        return True
    if current_user.is_site_admin:
        return not target_user.is_superuser
    return False


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'auth/landing.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.email}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid email or password.')
    
    return render(request, 'auth/login.html')


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('landing_page')


@login_required
def dashboard(request):
    context = {
        'user': request.user,
    }
    return render(request, 'auth/dashboard.html', context)


@login_required
def profile(request):
    return render(request, 'auth/profile.html')


@login_required
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not request.user.check_password(current_password):
            messages.error(request, 'Current password is incorrect.')
        elif new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
        elif len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        else:
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, 'Password changed successfully. Please log in again.')
            logout(request)
            return redirect('login_view')
    
    return render(request, 'auth/change_password.html')



def book_list(request):
    return render(request, 'books/book_list.html')


def book_add(request):
    return render(request, 'books/book_add.html')
