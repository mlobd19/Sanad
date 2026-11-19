"""Données de démonstration : 3 assureurs FICTIFS et leurs grilles auto.

Les montants ne sont pas des tarifs réels : ils servent à faire tourner
le parcours en local, avant d'importer les grilles des assureurs partenaires.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.catalog.models import Insurer, Product, TariffFactor

DEMO = [
    ("Assureur A (démo)", "assureur-a", Decimal("0.1500"), False, [
        ("rc", "RC seule", ["Responsabilité civile"], 10000),
    ]),
    ("Assureur B (démo)", "assureur-b", Decimal("0.1500"), False, [
        ("tiers-etendu", "Tiers étendu", ["Responsabilité civile", "Vol et incendie", "Bris de glace"], 18000),
    ]),
    ("Assureur C (démo)", "assureur-c", Decimal("0.1200"), True, [
        ("tous-risques", "Tous risques", ["Tiers étendu", "Dommages au véhicule"], 32000),
    ]),
]

FACTORS = [
    ("fiscal_power", None, Decimal("0"), Decimal("6"), Decimal("1.0000")),
    ("fiscal_power", None, Decimal("7"), Decimal("10"), Decimal("1.2500")),
    ("fiscal_power", None, Decimal("11"), None, Decimal("1.6000")),
    ("usage", "commercial", None, None, Decimal("1.4000")),
    ("usage", "taxi", None, None, Decimal("1.8000")),
]


class Command(BaseCommand):
    help = "Crée des assureurs, produits et comptes de démonstration."

    @transaction.atomic
    def handle(self, *args, **options):
        for name, slug, rate, auto, products in DEMO:
            insurer, _ = Insurer.objects.update_or_create(
                slug=slug, defaults={"name": name, "commission_rate": rate, "auto_validate": auto,
                                     "integration": Insurer.Integration.API if auto else Insurer.Integration.PORTAL},
            )
            for code, label, coverages, base in products:
                product, _ = Product.objects.update_or_create(
                    insurer=insurer, code=code,
                    defaults={"name": label, "coverages": coverages, "base_premium": base, "branch": "auto"},
                )
                product.factors.all().delete()
                TariffFactor.objects.bulk_create(
                    TariffFactor(product=product, attribute=a, equals=eq or "", min_value=lo, max_value=hi, multiplier=m)
                    for a, eq, lo, hi, m in FACTORS
                )
        b = Insurer.objects.get(slug="assureur-b")
        if not User.objects.filter(phone="+22220000002").exists():
            User.objects.create_user("+22220000002", role=User.Role.INSURER_AGENT, insurer=b, full_name="Agent B (démo)")
        self.stdout.write(self.style.SUCCESS("Données de démonstration prêtes (agent assureur B : +22220000002)."))
