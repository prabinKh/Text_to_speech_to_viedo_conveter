from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_file, name='upload_file'),
    path('files/', views.file_list, name='file_list'),
    path('process/<int:file_id>/', views.process_file, name='process_file'),
    path('delete/<int:file_id>/', views.delete_file, name='delete_file'),
    path('download/<int:file_id>/', views.download_file, name='download_file'),
]