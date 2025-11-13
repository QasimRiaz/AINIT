from django.db import models

class Dashboard(models.Model):
    class Meta:
        managed = False                 # no DB table or migrations
        default_permissions = ()        # hides add/change/delete perms
        verbose_name = "Dashboard"
        verbose_name_plural = "Dashboard"
