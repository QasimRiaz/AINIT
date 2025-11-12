from django.db import models

class ReportingRoot(models.Model):
    class Meta:
        managed = False                 # no DB table or migrations
        default_permissions = ()        # hides add/change/delete perms
        verbose_name = "Reporting"
        verbose_name_plural = "Reporting"
