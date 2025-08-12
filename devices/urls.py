# urls.py
from django.urls import path
from . import views
from .views import display_csv



urlpatterns = [
    path('upload/', views.upload_csv, name='upload_csv'),
    path('displaycsv/', views.display_csv, name='display_csv'),
    path('exportpdf/', views.export_to_pdf, name='export_to_pdf'),
    path('exportexcel/', views.export_to_excel, name='export_to_excel'),
    path('displayreport/', display_csv, name='import_displaycsv'), 
    
]
    
    











