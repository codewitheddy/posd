"""
Celery application configuration for background task processing.
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')

app = Celery('pos_system')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
