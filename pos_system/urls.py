"""
URL configuration for pos_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import user_passes_test

# Restrict admin to superusers only
admin.site.login = user_passes_test(lambda u: u.is_superuser, login_url='/login/')(admin.site.login)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('pos.api_urls')),  # REST API endpoints
    path('api/v1/sync/', include('sync.urls')),
    path('api/v1/backup/', include('backup.urls')),
    path('api/v1/restore/', include('restore.urls')),
    path('settings/backup/', include('backup.web_urls')),
    path('b/<slug:slug>/hr/', include('hr.urls')),  # HR module web + API
    path('', include('pos.urls_multitenant')),  # Multi-tenant web interface
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
