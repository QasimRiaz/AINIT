from django.urls import path
from .views import reporting_dashboard
urlpatterns = [ path("dashboard/", reporting_dashboard, name="reporting_dashboard") ]
