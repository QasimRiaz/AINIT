# reporting/views.py

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate
from ticketing.models import Ticket

@staff_member_required
def reporting_dashboard_view(request):
    raise Exception("HIT REPORTING_DASHBOARD_VIEW")
    """
    Calculates and provides all necessary data for the NexusAI Reporting Dashboard,
    with added debugging print statements.
    """
    print("\n--- REPORTING VIEW: STARTING DATA CALCULATION ---")
    today = timezone.localdate()

    # --- 1. Calculate KPIs ---
    total_tickets = Ticket.objects.count()
    closed_tickets = Ticket.objects.filter(status__iexact='Closed').count()
    open_tickets = total_tickets - closed_tickets
    today_tickets = Ticket.objects.filter(created_at__date=today).count()
    correct_solutions = Ticket.objects.filter(resolution_feedback__iexact='correct').count()
    incorrect_solutions = Ticket.objects.filter(resolution_feedback__iexact='incorrect').count()
    avg_rating_result = Ticket.objects.filter(solution_rating__isnull=False).aggregate(avg_val=Avg('solution_rating'))
    average_rating = avg_rating_result['avg_val'] or 0
    
    kpis = {
        "total": total_tickets,
        "open": open_tickets,
        "closed": closed_tickets,
        "today": today_tickets,
        "avg_rating": round(average_rating, 2),
    }
    print(f"1. KPIs Calculated: {kpis}")

    # --- 2. Prepare Data for Charts ---
    
    # Daily Data
    start_date = today - timezone.timedelta(days=13)
    daily_series = list(Ticket.objects.filter(created_at__date__gte=start_date).annotate(date=TruncDate('created_at')).values('date').annotate(c=Count('id')).order_by('date'))
    daily_map = {d['date']: d['c'] for d in daily_series}
    days_range = [(start_date + timezone.timedelta(days=i)) for i in range(14)]
    
    # Status Data
    status_series = list(Ticket.objects.values('status').annotate(c=Count('id')).order_by('-c'))

    # Alert Data
    alert_series = list(Ticket.objects.values('alert_type').annotate(c=Count('id')).order_by('-c')[:5])

    # Correctness Data
    correctness_labels = ['Correct', 'Incorrect']
    correctness_counts = [correct_solutions, incorrect_solutions]
    
    # Ratings Data
    ratings_series = list(Ticket.objects.filter(solution_rating__isnull=False).values('solution_rating').annotate(c=Count('id')).order_by('solution_rating'))
    
    # Agent Data
    agent_series = list(Ticket.objects.exclude(assigned_agent__isnull=True).exclude(assigned_agent='').values('assigned_agent').annotate(c=Count('id')).order_by('-c'))
    
    chart_data = {
        "daily_labels": [d.strftime('%b %d') for d in days_range],
        "daily_counts": [daily_map.get(d, 0) for d in days_range],
        "status_labels": [s['status'] or 'N/A' for s in status_series],
        "status_counts": [s['c'] for s in status_series],
        "alert_labels": [a['alert_type'] or 'N/A' for a in alert_series],
        "alert_counts": [a['c'] for a in alert_series],
        "correctness_labels": correctness_labels,
        "correctness_counts": correctness_counts,
        "rating_labels": [f"{r['solution_rating']} Star(s)" for r in ratings_series],
        "rating_counts": [r['c'] for r in ratings_series],
        "agent_labels": [a['assigned_agent'] for a in agent_series],
        "agent_counts": [a['c'] for a in agent_series],
    }
    print(f"2. Chart Data Assembled: {chart_data}")

    context = {
        'kpis': kpis,
        'chart_data': chart_data,
    }
    print("--- REPORTING VIEW: DATA CALCULATION COMPLETE ---")
    return render(request, "admin/reporting_dashboard.html", context)