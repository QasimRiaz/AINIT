# ticketing/models.py

from django.db import models



class Ticket(models.Model):
    # Field definitions that match our database columns
    alert_type = models.CharField(max_length=255, blank=True, null=True)
    ticket_uid = models.BigIntegerField(unique=True, blank=True, null=True)
    device_name = models.CharField(max_length=255, blank=True, null=True)
    issue_description = models.TextField(blank=True, null=True)
    history = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    assigned_agent = models.CharField(max_length=100, blank=True, null=True)
    llm_questions = models.TextField(blank=True, null=True)
    llm_solution = models.TextField(blank=True, null=True)
    resolution_feedback = models.CharField(max_length=50, blank=True, null=True)
    solution_rating = models.IntegerField(blank=True, null=True)

    ready_for_fix = models.JSONField(blank=True, null=True)
    inventory_host = models.TextField(blank=True, null=True)
    auto_apply = models.BooleanField(default=False)

    # ADD THESE NEW FIELDS
    sensor = models.CharField(max_length=255, blank=True, null=True)
    prtg_status = models.CharField(max_length=255, blank=True, null=True)
    prtg_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True) # auto_now_add is suitable here
    updated_at = models.DateTimeField(auto_now=True) # auto_now is suitable here

    class Meta:
        managed = False  # VERY IMPORTANT: Tells Django not to manage this table's schema
        db_table = 'tickets'  # VERY IMPORTANT: Links this model to our existing table

# ticketing/models.py
# ... (keep the Ticket model) ...

class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=50)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False # Django will not manage this table
        db_table = 'ticket_messages'
        ordering = ['created_at'] # Always show oldest messages first

    def __str__(self):
        return f"Ticket {self.id} - {self.device_name} ({self.alert_type})"