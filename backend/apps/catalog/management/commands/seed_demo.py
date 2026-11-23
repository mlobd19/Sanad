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

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Insurer, Product, TariffFactor

FORMULAS = {
    "rc": ("RC obligatoire", ["Responsabilité civile"]),
    "tiers-etendu": ("Tiers étendu", ["Responsabilité civile", "Vol et incendie", "Bris de glace"]),
    "tous-risques": ("Tous risques", ["Tiers étendu", "Dommages au véhicule", "Assistance"]),
}
TIERS, TOUS = "tiers-etendu", "tous-risques"

# Comptes démo : seulement avec DEMO_MODE ; mot de passe lu dans DEMO_PASSWORD (jamais dans le code).
DEMO_STAFF_PHONE = "+22230000000"  # back-office (DEMO_MODE)
DEMO_COMPANY_NIF, DEMO_COMPANY_EMAIL, DEMO_COMPANY_PHONE = "DEMO00001", "entreprise@demo.test", "+22240000001"
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
    ("usage", "commercial", None, None, Decimal("1.4000")),  # deux usages : personnel (1) et commercial
]

# Compagnies des catalogues de démo précédents, à retirer
OLD_DEMO_SLUGS = ["assureur-a", "assureur-b", "assureur-c", "damane", "cna", "car"]


def demo_password() -> str:
    """Mot de passe des comptes démo : DEMO_PASSWORD, et seulement en DEMO_MODE."""
    return settings.DEMO_PASSWORD if settings.DEMO_MODE else ""


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
            # Le numéro peut aussi porter un compte particulier : on cherche le compte agent.
            agent = (User.objects.filter(email=f"agent@{slug}.test").first()
                     or User.objects.filter(phone=agent_phone, role=User.Role.INSURER_AGENT).first())
            if agent is None:
                agent = User.objects.create_user(agent_phone, role=User.Role.INSURER_AGENT, insurer=insurer,
                                                 full_name=f"Agent {name} (démo)")
            elif agent.insurer_id != insurer.pk:
                agent.insurer, agent.role, agent.full_name = insurer, User.Role.INSURER_AGENT, f"Agent {name} (démo)"
            self._demo_login(agent, slug)
        self.stdout.write(self.style.SUCCESS(
            "Catalogue auto prêt : NASR, MAR, MEDINA, IMAN (tarifs fictifs). "
            "Agents démo : agent@nasr.test, agent@mar.test, agent@medina.test, agent@iman.test "
            "(+22220000001 à +22220000004)."
        ))
        if settings.DEMO_MODE:
            self._demo_staff_and_company()
            self.stdout.write(
                f"Back-office (démo) : {DEMO_STAFF_PHONE} puis code SMS · Entreprise démo vérifiée : {DEMO_COMPANY_EMAIL}"
            )
            if demo_password():
                self.stdout.write("Mot de passe des comptes démo : la valeur de DEMO_PASSWORD.")
            else:
                self.stdout.write(self.style.WARNING(
                    "DEMO_PASSWORD vide : comptes démo sans mot de passe (invitation depuis le back-office)."))
        else:
            self.stdout.write("Hors DEMO_MODE : pas de comptes démo ni de mot de passe. "
                              "Envoyez l'invitation depuis le back-office.")

    def _demo_login(self, agent, slug):
        """Email agent@<code>.test ; mot de passe démo seulement en DEMO_MODE, sans écraser un mot de passe choisi."""
        agent.email = agent.email or f"agent@{slug}.test"
        if demo_password() and not agent.has_usable_password():
            agent.set_password(demo_password())
        agent.save()

    def _demo_staff_and_company(self):
        """DEMO_MODE uniquement : un compte équipe (back-office) et une entreprise vérifiée, pour tout essayer.

        Le compte équipe n'est pas superutilisateur : il reçoit le groupe « Équipe Sanad » (droits métier).
        """
        from apps.backoffice.permissions import staff_group
        from apps.companies.models import Company, Membership

        staff = User.objects.filter(phone=DEMO_STAFF_PHONE).exclude(role__in=User.PRO_ROLES).first()
        if staff is None:
            staff = User.objects.create_user(DEMO_STAFF_PHONE, role=User.Role.STAFF, full_name="Équipe Sanad (démo)")
        staff.role, staff.is_staff, staff.is_superuser = User.Role.STAFF, True, False
        if demo_password() and not staff.has_usable_password():
            staff.set_password(demo_password())
        staff.save()
        staff.groups.add(staff_group())

        company, _ = Company.objects.get_or_create(
            nif=DEMO_COMPANY_NIF,
            defaults={"legal_name": "Entreprise démo SARL", "rc_number": "NKC-DEMO-0001",
                      "address": "Tevragh Zeina, Nouakchott"},
        )
        if company.status != Company.Status.VERIFIED:
            company.status, company.verified_by, company.verified_at = Company.Status.VERIFIED, staff, timezone.now()
            company.save()
        admin = User.objects.filter(email=DEMO_COMPANY_EMAIL).first()
        if admin is None:
            admin = User.objects.create_user(DEMO_COMPANY_PHONE, role=User.Role.COMPANY_MEMBER,
                                             email=DEMO_COMPANY_EMAIL, full_name="Admin Entreprise démo")
        if demo_password() and not admin.has_usable_password():
            admin.set_password(demo_password())
            admin.save()
        Membership.objects.get_or_create(user=admin, defaults={"company": company, "role": Membership.Role.ADMIN})

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
