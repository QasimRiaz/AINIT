import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from ticketing.models import Ticket

STATUSES_OPEN = ["Open", "In Progress", "Pending", "Reopened", "Assigned"]
STATUSES_CLOSED = ["Resolved", "Closed"]
ALERT_TYPES = [
    "SNMP CPU Load", "Host Unreachable", "Disk Space Low",
    "High Memory Usage", "Interface Errors", "Packet Loss",
]
DEVICES = [
    "Firewall-HQ", "Core-Router-SF", "Switch-3F", "VPN-Gateway-1",
    "DB-Server-01", "Web-Edge-02",
]
AGENTS = ["Alice", "Bob", "Carlos", "Dana", "Eva", "Faraz"]

def rand_sentence(alert, device):
    samples = [
        f"{alert}: threshold exceeded.",
        f"{alert}: transient spike detected.",
        f"{alert}: device {device} reported abnormal value.",
        f"{alert}: watchdog triggered.",
        f"{alert}: please investigate.",
    ]
    return random.choice(samples)

class Command(BaseCommand):
    help = "Seed 15 days of dummy tickets for the reporting dashboard"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=15)
        parser.add_argument("--per-day-min", type=int, default=5)
        parser.add_argument("--per-day-max", type=int, default=12)
        parser.add_argument("--force", action="store_true",
                            help="Create data even if tickets already exist")

    def handle(self, *args, **opts):
        if Ticket.objects.exists() and not opts["force"]:
            self.stdout.write(self.style.WARNING(
                "Tickets already exist. Use --force to add more."))
            return

        today = timezone.localdate()
        uid_base = random.randint(10_000, 99_999)

        created = 0
        for i in range(opts["days"]):
            day = today - timedelta(days=(opts["days"] - 1 - i))
            n = random.randint(opts["per_day_min"], opts["per_day_max"])

            for j in range(n):
                device = random.choice(DEVICES)
                alert = random.choice(ALERT_TYPES)
                is_closed = random.random() < 0.55
                status = random.choice(STATUSES_CLOSED if is_closed else STATUSES_OPEN)

                # 70% have a rating when closed
                rating = None
                if is_closed and random.random() < 0.7:
                    rating = random.randint(1, 5)

                # 75% solution feedback when closed; mostly correct
                feedback = None
                if is_closed and random.random() < 0.75:
                    feedback = "Correct" if random.random() < 0.8 else "Wrong"

                t = Ticket.objects.create(
                    alert_type=alert,
                    ticket_uid=uid_base,
                    device_name=device,
                    issue_description=rand_sentence(alert, device),
                    history={"events": []},
                    status=status,
                    assigned_agent=random.choice(AGENTS) if random.random() < 0.9 else None,
                    llm_questions="",
                    llm_solution="",
                    resolution_feedback=feedback,
                    solution_rating=rating,
                    sensor=alert,
                    prtg_status="Unusual" if not is_closed else "OK",
                    prtg_message=rand_sentence(alert, device),
                )
                uid_base += 1

                # Put it on the target day (keep updated_at the same)
                Ticket.objects.filter(pk=t.pk).update(
                    created_at=timezone.make_aware(
                        timezone.datetime.combine(day, timezone.datetime.min.time())
                    ),
                    updated_at=timezone.make_aware(
                        timezone.datetime.combine(day, timezone.datetime.min.time())
                    ),
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} dummy tickets."))
