from django.urls import path
from restore import views

urlpatterns = [
    path('', views.RestoreView.as_view(), name='restore'),
]
