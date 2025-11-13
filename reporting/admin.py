from django.contrib import admin
from django.template.response import TemplateResponse
from .models import Dashboard

@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    # Hide CRUD
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    # Make the changelist render your dashboard
    def changelist_view(self, request, extra_context=None):
        context = dict(self.admin_site.each_context(request))
        # add your dashboard data to context if needed
        return TemplateResponse(request, "admin/reporting_dashboard.html", context)
