from django.core.management.base import BaseCommand
from django.db import transaction
from spa.models import Service, PackageComponent


class Command(BaseCommand):
    help = "Configure reviewed package credits, couple requirements and homepage features without changing prices or room capacity."

    @transaction.atomic
    def handle(self, *args, **options):
        names = {s.name:s for s in Service.objects.all()}
        for name in ["SWEDISH MASSAGE", "AROMA THERAPY", "DEEP TISSUE MASSAGE", "BALINESE MASSAGE"]:
            if name in names:
                Service.objects.filter(pk=names[name].pk).update(is_featured=True)
        if "COUPLE MASSAGE" in names:
            Service.objects.filter(pk=names["COUPLE MASSAGE"].pk).update(staff_required=2, requires_couple_room=True)
        recipes = {
            "SILVER PACKAGE": [("AROMA THERAPY",1,None),("BALINESE MASSAGE",1,"SWEDISH MASSAGE"),("DEEP TISSUE MASSAGE",1,None)],
            "SILVER PLUS PACKAGE": [("AROMA THERAPY",2,None),("SWEDISH MASSAGE",1,None),("BALINESE MASSAGE",1,None)],
            "GOLD PACKAGE": [("DEEP TISSUE MASSAGE",2,None),("AROMA THERAPY",1,None),("SWEDISH MASSAGE",1,None),("BALINESE MASSAGE",1,None)],
            "GOLD PLUS PACKAGE": [("AROMA THERAPY",2,None),("SWEDISH MASSAGE",2,None),("BALINESE MASSAGE",1,None),("DEEP TISSUE MASSAGE",1,None)],
            "PLATINUM PACKAGE": [("AROMA THERAPY",2,None),("DEEP TISSUE MASSAGE",2,None),("BALINESE MASSAGE",1,None),("SWEDISH MASSAGE",3,None)],
            "PLATINUM PLUS PACKAGE": [("AROMA THERAPY",2,None),("SWEDISH MASSAGE",2,None),("BALINESE MASSAGE",2,None),("DEEP TISSUE MASSAGE",2,None),("THAI DRY THERAPY",1,None)],
        }
        for package, rules in recipes.items():
            if package not in names or any(n not in names or alt and alt not in names for n,_,alt in rules):
                continue
            p=names[package]
            Service.objects.filter(pk=p.pk).update(is_package=True)
            for name, count, alternative in rules:
                PackageComponent.objects.update_or_create(package=p,treatment=names[name],defaults={"sessions":count,"alternative":names[alternative] if alternative else None})
        self.stdout.write("Package recipes and featured treatments ready. Mark the actual couple room in Rooms; room capacity was not invented.")
