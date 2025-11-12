# ticketing/views.py

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Count, Avg
from .models import Ticket
from django.db.models.functions import TruncDate


@staff_member_required
def dashboard_view(request):
    """
    The view function for our custom admin dashboard.
    Only accessible to staff members (i.e., logged-in admins).
    """
    # --- Calculate Key Performance Indicators (KPIs) ---
    total_tickets = Ticket.objects.count()
    processing_tickets = Ticket.objects.filter(status='Processing').count()
    attention_needed_tickets = Ticket.objects.filter(status='Attention Needed').count()
    solution_proposed_tickets = Ticket.objects.filter(status='Solution Proposed').count()
    closed_tickets = Ticket.objects.filter(status='Closed').count()

    # --- Prepare Data for Charts ---

    # 1. Tickets by Status (Pie Chart)
    # This query groups tickets by status and counts them.
    status_counts = Ticket.objects.values('status').annotate(count=Count('status'))
    status_labels = [item['status'] or 'N/A' for item in status_counts] # Handle possible None status
    status_data = [item['count'] for item in status_counts]

    # 2. Tickets by Alert Type (Bar Chart)
    # This query groups tickets by alert_type and counts them, ordered by the most frequent.
    alert_type_counts = Ticket.objects.values('alert_type').annotate(count=Count('alert_type')).order_by('-count')
    alert_type_labels = [item['alert_type'] or 'N/A' for item in alert_type_counts] # Handle possible None alert_type
    alert_type_data = [item['count'] for item in alert_type_counts]

    # This context dictionary passes all the calculated data to the HTML template.
    context = {
        'title': 'AINIT Dashboard',
        'total_tickets': total_tickets,
        'processing_tickets': processing_tickets,
        'attention_needed_tickets': attention_needed_tickets,
        'solution_proposed_tickets': solution_proposed_tickets,
        'closed_tickets': closed_tickets,
        'status_labels': status_labels,
        'status_data': status_data,
        'alert_type_labels': alert_type_labels,
        'alert_type_data': alert_type_data,
    }
    
    # Render the HTML template with our calculated data
    return render(request, 'admin/dashboard.html', context)

# ticketing/views.py
# (make sure all the imports from Step 1 are there)

