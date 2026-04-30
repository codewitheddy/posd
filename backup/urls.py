from django.urls import path
from backup import views

urlpatterns = [
    path('manual/', views.ManualBackupView.as_view(), name='backup_manual'),
    path('versions/', views.BackupVersionsView.as_view(), name='backup_versions'),
]
