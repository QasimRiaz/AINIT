# ticketing/admin.py

import requests
from django import forms
from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.utils.safestring import mark_safe
from .models import Ticket, TicketMessage

class TicketReplyForm(forms.ModelForm):
    """A custom form that includes a non-database field for user replies."""
    user_reply = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label="Your Reply",
        help_text="Type your response to the AI here and click 'Save'."
    )

    class Meta:
        model = Ticket
        fields = '__all__'

@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    """
    Customizes the Django admin interface for the Ticket model, enabling an asynchronous,
    conversational workflow with the AI backend.
    """
    form = TicketReplyForm

    # Configure the main list view to show the new ticket_uid
    list_display = ('ticket_uid', 'device_name', 'alert_type', 'status', 'assigned_agent', 'created_at')
    list_filter = ('status', 'device_name', 'alert_type', 'assigned_agent')
    search_fields = ('ticket_uid', 'device_name', 'issue_description', 'prtg_message')
    ordering = ('-created_at',)

    # All fields that are populated by the system should be read-only
    readonly_fields = (
        'id', 'ticket_uid', 'created_at', 'updated_at', 'assigned_agent', 'display_conversation',
        'llm_solution', 'sensor', 'prtg_status', 'prtg_message'
    )

    # Organize the ticket detail page into logical, collapsible sections
    fieldsets = (
        ('Ticket Details', {
            'fields': ('id', 'ticket_uid', 'status', 'device_name', 'alert_type', 'issue_description')
        }),
        ('PRTG Alert Data', {
            'classes': ('collapse',),
            'fields': ('sensor', 'prtg_status', 'prtg_message'),
            'description': 'This is the raw alert information received from the PRTG monitoring system.'
        }),
        ('AI Conversation', {
            'fields': ('assigned_agent', 'display_conversation', 'user_reply')
        }),
        ('AI Final Solution', {
            'fields': ('llm_solution',)
        }),
        ('Metadata', {
            'fields': ('history', 'resolution_feedback', 'created_at', 'updated_at')
        }),
    )

    def display_conversation(self, obj):
        """Renders the back-and-forth conversation history as clean HTML."""
        messages = TicketMessage.objects.filter(ticket=obj).order_by('created_at')
        if not messages:
            return "No conversation has started yet."
        
        html = '<div style="border: 1px solid #e1e1e1; border-radius: 5px; padding: 15px; height: 350px; overflow-y: scroll; background: #fdfdfd;">'
        for msg in messages:
            sender_style = "font-weight: bold; color: #0056b3;" if msg.sender == 'user' else "font-weight: bold; color: #6a0dad;"
            formatted_message = mark_safe(msg.message.replace('\n', '<br>'))
            html += f'<div style="margin-bottom: 12px;"><strong style="{sender_style}">{msg.sender.upper()}:</strong><br>{formatted_message}</div>'
        html += '</div>'
        return mark_safe(html)
    display_conversation.short_description = 'Conversation History'

    def save_model(self, request, obj, form, change):
        """
        Overrides the save action to send the user's reply to the FastAPI backend.
        This now returns instantly as the AI processing is a background job.
        """
        super().save_model(request, obj, form, change)

        user_reply_message = form.cleaned_data.get('user_reply')

        if user_reply_message:
            print("---DJANGO ADMIN---")
            print(f"✅ Captured reply for ticket {obj.id}: '{user_reply_message}'")
            
            fastapi_url = f"http://127.0.0.1:8000/api/v1/ticket/{obj.id}/continue"
            payload = {"message": user_reply_message}
            
            print(f"🚀 Sending POST request to: {fastapi_url}")

            try:
                # Use a short timeout because the background-task-enabled FastAPI endpoint should respond instantly.
                response = requests.post(fastapi_url, json=payload, timeout=10)
                response.raise_for_status()
                
                messages.success(request, "Reply submitted successfully! The AI is processing in the background. Refresh the page in a moment to see updates.")

            except requests.exceptions.RequestException as e:
                error_message = f"CRITICAL ERROR: Could not send reply to the AI backend. Details: {e}"
                print(f"❌❌❌ DJANGO ERROR: {error_message} ❌❌❌")
                messages.error(request, error_message)