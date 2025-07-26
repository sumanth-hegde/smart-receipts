"""
URL configuration for receipt_reader project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from reader.views import home_view

urlpatterns = [
    # Root URL now points to the home_view to render index.html
    path('', home_view, name='home'),

    path('admin/', admin.site.urls),

    # All API endpoints are now under /api/
    path('api/', include('reader.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)