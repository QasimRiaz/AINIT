# ticketing/admin.py
import requests
from django import forms
from django.contrib.admin import ModelAdmin
from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from .models import Ticket, TicketMessage

class TicketReplyForm(forms.ModelForm):
    user_reply = forms.CharField(widget=forms.Textarea, required=False, label="Your Reply")

    class Meta:
        model = Ticket
        fields = '__all__'

@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    # ... (all the other settings like list_display, etc., stay the same) ...
    form = TicketReplyForm
    list_display = ('id', 'device_name', 'alert_type', 'status', 'created_at')
    list_filter = ('status', 'device_name', 'alert_type')
    search_fields = ('device_name', 'issue_description')
    readonly_fields = ('id', 'created_at', 'updated_at', 'assigned_agent', 'display_conversation', 'llm_solution')

    fieldsets = (
        ('Ticket Details', {'fields': ('id', 'status', 'device_name', 'alert_type', 'issue_description')}),
        ('AI Conversation', {'fields': ('assigned_agent', 'display_conversation', 'user_reply')}),
        ('AI Final Solution', {'fields': ('llm_solution',)}),
        ('Metadata', {'fields': ('history', 'resolution_feedback', 'created_at', 'updated_at')}),
    )

    def display_conversation(self, obj):
        messages = TicketMessage.objects.filter(ticket=obj).order_by('created_at')
        if not messages:
            return "No conversation has started yet."
        html = '<div style="border: 1px solid #ccc; padding: 10px; height: 300px; overflow-y: scroll; background: #f9f9f9; border-radius: 5px;">'
        for msg in messages:
            sender_style = "font-weight: bold; color: #0056b3;" if msg.sender == 'user' else "font-weight: bold; color: #8a2be2;"
            formatted_message = mark_safe(msg.message.replace('\n', '<br>'))
            html += f'<div style="margin-bottom: 10px;"><strong style="{sender_style}">{msg.sender.upper()}:</strong><br>{formatted_message}</div>'
        html += '</div>'
        return mark_safe(html)
    display_conversation.short_description = 'Conversation History'

    # *** THIS IS THE UPDATED FUNCTION ***
    def save_model(self, request, obj, form, change):
        """
        Overridden to capture the user's reply and trigger the FastAPI backend.
        """
        # First, save any changes to the ticket object itself (e.g., if you manually edit a field)
        super().save_model(request, obj, form, change)

        user_reply_message = form.cleaned_data.get('user_reply')

        # Only proceed if the user actually typed something in the reply box
        if user_reply_message:
            print("---DJANGO ADMIN---")
            print(f"✅ Captured reply for ticket {obj.id}: '{user_reply_message}'")
            
            fastapi_url = f"http://127.0.0.1:8000/api/v1/ticket/{obj.id}/continue"
            payload = {"message": user_reply_message}
            
            print(f"🚀 About to send POST request to: {fastapi_url}")
            print(f"📦 With payload: {payload}")

            try:
                # Set a timeout to prevent it from hanging indefinitely
                response = requests.post(fastapi_url, json=payload, timeout=5000)
                
                print(f"🚦 FastAPI response status code: {response.status_code}")
                print(f"📄 FastAPI response body: {response.text}")

                # This will raise an error if the status code is 4xx or 5xx
                response.raise_for_status()
                
                # Use the more robust Django messages framework
                messages.success(request, "Your reply was sent to the AI. Please refresh the page in a few moments to see the response.")

            except requests.exceptions.RequestException as e:
                print(f"❌❌❌ DJANGO ERROR: Failed to communicate with FastAPI. ❌❌❌")
                print(f"Error details: {e}")
                messages.error(request, f"CRITICAL ERROR: Could not send reply to the AI backend. Details: {e}")