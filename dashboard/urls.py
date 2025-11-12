# dashboard/urls.py
from django.contrib import admin
from django.urls import path
from reporting.views import reporting_dashboard_view

urlpatterns = [
    path("admin/", admin.site.urls),
   
    path("admin/reporting/", admin.site.admin_view(reporting_dashboard_view), name="reporting"),
]
