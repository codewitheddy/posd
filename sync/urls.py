from django.urls import path
from sync import views

urlpatterns = [
    path('events/', views.SyncEventsView.as_view(), name='sync_events'),
    path('status/', views.SyncStatusView.as_view(), name='sync_status'),
]
