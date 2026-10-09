"""Apply the reviewed printed menu without rewriting historical bookings."""
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from spa.models import Service, ServiceCategory, ServiceOption


def normalized_name(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


class Command(BaseCommand):
    help = "Sync service names and prices from the reviewed Sukoon rate card. Default is preview; use --apply to save."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        source = Path(__file__).resolve().parents[2] / "data" / "sukoon_rate_card.json"
        menu = json.loads(source.read_text(encoding="utf-8"))["services"]
        existing = defaultdict(list)
        for service in Service.objects.select_for_update().order_by("pk"):
            existing[normalized_name(service.name)].append(service)
        for entry in menu:
            if len(existing[normalized_name(entry["name"])]) > 1:
                raise CommandError(f"Ambiguous service name: {entry['name']}. Resolve duplicates before syncing.")

        new_services = new_options = updated_options = 0
        for entry in menu:
            matches = existing[normalized_name(entry["name"])]
            service = matches[0] if matches else Service(name=entry["name"])
            desired = {duration: Decimal(str(price)) for duration, price in entry.get("options", [])}
            current = {o.duration: o for o in service.options.all()} if service.pk else {}
            new_services += not bool(service.pk)
            new_options += len(desired.keys() - current.keys())
            updated_options += sum(duration in current and (current[duration].price != price or not current[duration].is_active) for duration, price in desired.items())
            rates = ", ".join(f"{duration} min = INR {price}" for duration, price in desired.items()) or f"INR {entry['menu_price']} (no fixed duration)"
            self.stdout.write(f"{entry['name']}: {rates}")
            if not options["apply"]:
                continue
            category, _ = ServiceCategory.objects.get_or_create(name=entry["category"], defaults={"is_active": True})
            service.name = entry["name"]
            service.category = category
            service.is_active = True
            service.menu_price = Decimal(str(entry["menu_price"])) if "menu_price" in entry else None
            if "description" in entry:
                service.description = entry["description"]
                service.short_description = entry["description"]
            service.full_clean()
            service.save()
            for duration, price in desired.items():
                ServiceOption.objects.update_or_create(service=service, duration=duration, defaults={"price": price, "is_active": True})
            # Keep old options for history but stop offering rates absent from this menu.
            service.options.exclude(duration__in=desired).update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f"{'Applied' if options['apply'] else 'Preview'}: {len(menu)} menu entries; "
            f"{new_services} new services, {new_options} new duration options, {updated_options} changed options. Historical bookings unchanged."
        ))
