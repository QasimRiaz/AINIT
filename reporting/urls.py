from django.urls import path
from .views import reporting_dashboard_view 

app_name = "reporting"

urlpatterns = [
    path("dashboard/", reporting_dashboard_view, name="dashboard"),
]
