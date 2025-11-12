# ticketing/views.py
from django.shortcuts import render
from django.contrib import admin
from django.utils import timezone
from django.db.models import Count, Avg, Q, IntegerField, Case, When
from django.db.models.functions import TruncDate
import json

from ticketing.models import Ticket, TicketMessage


def reporting_dashboard_view(request):
    today = timezone.localdate()

    # --- KPIs ---
    total_tickets = Ticket.objects.count()
    open_tickets = Ticket.objects.exclude(status__in=["Resolved", "Closed"]).count()
    unsolved_tickets = Ticket.objects.filter(
        Q(solution_rating__isnull=True) | Q(resolution_feedback__isnull=True) |
        ~Q(resolution_feedback__iexact="correct")
    ).count()
    todays_tickets = Ticket.objects.filter(created_at__date=today).count()

    avg_rating = Ticket.objects.filter(solution_rating__isnull=False)\
        .aggregate(avg=Avg("solution_rating"))["avg"] or 0

    # --- Time series: last 14 days ---
    start = today - timezone.timedelta(days=13)
    by_day = (
        Ticket.objects.filter(created_at__date__gte=start, created_at__date__lte=today)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(c=Count("id"))
        .order_by("day")
    )
    days = []
    day_counts = []
    d = start
    counts_map = {row["day"]: row["c"] for row in by_day}
    while d <= today:
        days.append(d.isoformat())
        day_counts.append(counts_map.get(d, 0))
        d += timezone.timedelta(days=1)

    # --- Tickets by status ---
    by_status = (
        Ticket.objects.values("status")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    status_labels = [row["status"] or "Unknown" for row in by_status]
    status_counts = [row["c"] for row in by_status]

    # --- Tickets by alert type (top 10) ---
    by_alert = (
        Ticket.objects.values("alert_type")
        .annotate(c=Count("id"))
        .order_by("-c")[:10]
    )
    alert_labels = [row["alert_type"] or "Unknown" for row in by_alert]
    alert_counts = [row["c"] for row in by_alert]

    # --- Solution correctness (based on resolution_feedback) ---
    correctness = Ticket.objects.aggregate(
        correct=Count(Case(When(resolution_feedback__iexact="correct", then=1))),
        wrong=Count(Case(When(~Q(resolution_feedback__iexact="correct") &
                              Q(resolution_feedback__isnull=False), then=1))),
        unknown=Count(Case(When(resolution_feedback__isnull=True, then=1))),
    )
    correctness_labels = ["Correct", "Wrong", "Unknown"]
    correctness_counts = [
        correctness["correct"] or 0,
        correctness["wrong"] or 0,
        correctness["unknown"] or 0,
    ]

    # --- Ratings distribution (1..5) ---
    rating_buckets = (
        Ticket.objects
        .filter(solution_rating__isnull=False)
        .values("solution_rating")
        .annotate(c=Count("id"))
        .order_by("solution_rating")
    )
    rating_map = {row["solution_rating"]: row["c"] for row in rating_buckets}
    rating_labels = [1, 2, 3, 4, 5]
    rating_counts = [rating_map.get(i, 0) for i in rating_labels]

    # --- Agent workload (top 10) ---
    by_agent = (
        Ticket.objects.values("assigned_agent")
        .annotate(
            open=Count(Case(When(~Q(status__in=["Resolved", "Closed"]), then=1))),
            total=Count("id"),
        )
        .order_by("-total")[:10]
    )
    agent_labels = [row["assigned_agent"] or "Unassigned" for row in by_agent]
    agent_totals = [row["total"] for row in by_agent]
    agent_opens = [row["open"] for row in by_agent]

    context = admin.site.each_context(request)
    context.update(
        kpis={
            "total": total_tickets,
            "open": open_tickets,
            "unsolved": unsolved_tickets,
            "today": todays_tickets,
            "avg_rating": round(avg_rating, 2),
        },
        charts={
            "days": json.dumps(days),
            "day_counts": json.dumps(day_counts),
            "status_labels": json.dumps(status_labels),
            "status_counts": json.dumps(status_counts),
            "alert_labels": json.dumps(alert_labels),
            "alert_counts": json.dumps(alert_counts),
            "correctness_labels": json.dumps(correctness_labels),
            "correctness_counts": json.dumps(correctness_counts),
            "rating_labels": json.dumps(rating_labels),
            "rating_counts": json.dumps(rating_counts),
            "agent_labels": json.dumps(agent_labels),
            "agent_totals": json.dumps(agent_totals),
            "agent_opens": json.dumps(agent_opens),
        },
    )
    return render(request, "admin/reporting_dashboard.html", context)
