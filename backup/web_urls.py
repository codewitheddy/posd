from django.urls import path
from backup import web_views

urlpatterns = [
    path('', web_views.backup_settings_view, name='backup_settings'),
]
