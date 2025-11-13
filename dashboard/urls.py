# config/urls.py  (or whatever your root urls module is called)
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin/reporting/", include("reporting.urls")),  # <-- add this
]
