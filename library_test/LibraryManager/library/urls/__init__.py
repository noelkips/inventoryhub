from django.urls import path, include
from .. import views

urlpatterns = [
    path('auth/', include('library.urls.auth')),
    path('books/', views.book_list, name='book_list'),
    path('books/add/', views.book_add, name='book_add'),
]
