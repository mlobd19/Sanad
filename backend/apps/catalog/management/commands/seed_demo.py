"""Catalogue auto de démonstration : NASR, MAR, MEDINA Assurances, IMAN Assurance.

Compagnies choisies par l'équipe Sanad parmi les sociétés agréées listées dans
le « Rapport sur le marché des assurances en Mauritanie » (ministère des
Finances, exercice 2022, publié en déc. 2023).

ATTENTION : les primes ci-dessous sont FICTIVES. Chaque produit est marqué
`is_indicative` et l'application affiche « tarif indicatif ». Elles seront
remplacées par les grilles officielles une fois les partenariats signés.
Seule la RC automobile a un tarif homologué par l'État : elle est donc
identique d'une compagnie à l'autre (montant de démonstration ici aussi).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.catalog.models import Insurer, Product, TariffFactor

FORMULAS = {
    "rc": ("RC obligatoire", ["Responsabilité civile"]),
    "tiers-etendu": ("Tiers étendu", ["Responsabilité civile", "Vol et incendie", "Bris de glace"]),
    "tous-risques": ("Tous risques", ["Tiers étendu", "Dommages au véhicule", "Assistance"]),
}
TIERS, TOUS = "tiers-etendu", "tous-risques"

RC_DEMO_PREMIUM = 10000  # identique partout : tarif RC homologué (montant fictif)

# slug, nom court, raison sociale, n° agent démo, primes fictives {formule: prime annuelle de base}
COMPANIES = [
    ("nasr", "NASR", "Nationale d'Assurance et de Réassurance", "+22220000001",
     {TIERS: 19000, TOUS: 34000}),
    ("mar", "MAR", "Mauritanienne d'Assurance et de Réassurance", "+22220000002",
     {TIERS: 18000, TOUS: 33000}),
    ("medina", "MEDINA Assurances", "MEDINA Assurances", "+22220000003",
     {TIERS: 17500}),
    ("iman", "IMAN Assurance", "IMAN Assurance", "+22220000004",
     {TIERS: 18500}),
]

FACTORS = [
    ("fiscal_power", None, Decimal("0"), Decimal("6"), Decimal("1.0000")),
    ("fiscal_power", None, Decimal("7"), Decimal("10"), Decimal("1.2500")),
    ("fiscal_power", None, Decimal("11"), None, Decimal("1.6000")),
    ("usage", "commercial", None, None, Decimal("1.4000")),
    ("usage", "taxi", None, None, Decimal("1.8000")),
]

# Compagnies des catalogues de démo précédents, à retirer
OLD_DEMO_SLUGS = ["assureur-a", "assureur-b", "assureur-c", "damane", "cna", "car"]


class Command(BaseCommand):
    help = "Crée le catalogue auto de démonstration (4 compagnies, tarifs fictifs) et un agent démo par compagnie."

    @transaction.atomic
    def handle(self, *args, **options):
        self._retire_old_demo()
        for slug, name, legal, agent_phone, offers in COMPANIES:
            insurer, _ = Insurer.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "legal_name": legal, "commission_rate": Decimal("0.1500"),
                          "auto_validate": False, "integration": Insurer.Integration.PORTAL, "is_active": True},
            )
            for code, premium in [("rc", RC_DEMO_PREMIUM), *offers.items()]:
                label, coverages = FORMULAS[code]
                product, _ = Product.objects.update_or_create(
                    insurer=insurer, code=code,
                    defaults={"name": label, "coverages": coverages, "base_premium": premium, "branch": "auto",
                              "is_indicative": True, "tariff_version": "demo-2026", "is_active": True},
                )
                product.factors.all().delete()
                TariffFactor.objects.bulk_create(
                    TariffFactor(product=product, attribute=a, equals=eq or "", min_value=lo, max_value=hi, multiplier=m)
                    for a, eq, lo, hi, m in FACTORS
                )
            agent = User.objects.filter(phone=agent_phone).first()
            if agent is None:
                User.objects.create_user(agent_phone, role=User.Role.INSURER_AGENT, insurer=insurer,
                                         full_name=f"Agent {name} (démo)")
            elif agent.insurer_id != insurer.pk:
                agent.insurer, agent.role, agent.full_name = insurer, User.Role.INSURER_AGENT, f"Agent {name} (démo)"
                agent.save()
        self.stdout.write(self.style.SUCCESS(
            "Catalogue auto prêt : NASR, MAR, MEDINA, IMAN (tarifs fictifs). "
            "Agents démo : +22220000001 à +22220000004."
        ))

    def _retire_old_demo(self):
        """Retire les compagnies des anciens catalogues ; les désactive si elles ont déjà des contrats."""
        for insurer in Insurer.objects.filter(slug__in=OLD_DEMO_SLUGS):
            try:
                with transaction.atomic():
                    insurer.agents.all().delete()
                    insurer.products.all().delete()
                    insurer.delete()
            except ProtectedError:
                insurer.is_active = False
                insurer.save(update_fields=["is_active"])
                insurer.products.update(is_active=False)
                insurer.agents.update(is_active=False)  # plus d'accès au portail pour une compagnie retirée
