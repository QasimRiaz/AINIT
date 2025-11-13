# ticketing/views.py

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate

from .models import Ticket

@staff_member_required
def reporting_dashboard_view(request):
    """
    Calculates and provides all necessary data for the NexusAI Reporting Dashboard.
    """
    today = timezone.localdate()

    # --- 1. Calculate KPIs ---
    total_tickets = Ticket.objects.count()
    closed_tickets = Ticket.objects.filter(status='Closed').count()
    open_tickets = total_tickets - closed_tickets
    
    # Tickets created today
    today_tickets = Ticket.objects.filter(created_at__date=today).count()

    # Solution Correctness (based on feedback)
    correct_solutions = Ticket.objects.filter(resolution_feedback='correct').count()
    incorrect_solutions = Ticket.objects.filter(resolution_feedback='incorrect').count()

    # Average solution rating
    avg_rating_result = Ticket.objects.filter(solution_rating__isnull=False).aggregate(avg_val=Avg('solution_rating'))
    average_rating = avg_rating_result['avg_val'] or 0

    # --- 2. Prepare Data for Charts ---
    
    # Tickets per Day (last 14 days)
    start_date = today - timezone.timedelta(days=13)
    daily_series = (
        Ticket.objects.filter(created_at__date__gte=start_date)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(c=Count('id'))
        .order_by('date')
    )
    daily_map = {d['date']: d['c'] for d in daily_series}
    days = [(start_date + timezone.timedelta(days=i)) for i in range(14)]
    
    # Tickets by Status
    status_series = Ticket.objects.values('status').annotate(c=Count('id')).order_by('-c')

    # Top Alert Types
    alert_series = Ticket.objects.values('alert_type').annotate(c=Count('id')).order_by('-c')[:5]

    # Solution Correctness
    correctness_labels = ['Correct', 'Incorrect']
    correctness_counts = [correct_solutions, incorrect_solutions]
    
    # Ratings Distribution
    ratings_series = Ticket.objects.filter(solution_rating__isnull=False).values('solution_rating').annotate(c=Count('id')).order_by('solution_rating')
    rating_labels = [f"{r['solution_rating']} Star" for r in ratings_series]
    rating_counts = [r['c'] for r in ratings_series]
    
    # Agent Workload
    agent_series = Ticket.objects.exclude(assigned_agent__isnull=True).exclude(assigned_agent='').values('assigned_agent').annotate(c=Count('id')).order_by('-c')

    context = {
        'kpis': {
            "total": total_tickets,
            "open": open_tickets,
            "closed": closed_tickets, # Using closed instead of unsolved
            "today": today_tickets,
            "avg_rating": round(average_rating, 2),
        },
        'charts': {
            "days": [d.strftime('%b %d') for d in days],
            "day_counts": [daily_map.get(d, 0) for d in days],
            "status_labels": [s['status'] or 'N/A' for s in status_series],
            "status_counts": [s['c'] for s in status_series],
            "alert_labels": [a['alert_type'] or 'N/A' for a in alert_series],
            "alert_counts": [a['c'] for a in alert_series],
            "correctness_labels": correctness_labels,
            "correctness_counts": correctness_counts,
            "rating_labels": rating_labels,
            "rating_counts": rating_counts,
            "agent_labels": [a['assigned_agent'] for a in agent_series],
            "agent_totals": [a['c'] for a in agent_series],
            # We will simplify the agent chart to show total tickets per agent
        },
    }
    return render(request, "admin/reporting_dashboard.html", context)