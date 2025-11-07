# dashboard/urls.py

from django.contrib import admin
from django.urls import path

# Import our dashboard_view from the ticketing app
from ticketing.views import dashboard_view

urlpatterns = [
    path('admin/', admin.site.urls),

    # Restore the correct path for our dashboard
    path('admin/dashboard/', dashboard_view, name='dashboard'),
]