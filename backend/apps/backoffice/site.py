"""Site d'administration de Sanad : accueil « À traiter » et menu organisé par métier."""
from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .ui import mru

# Menu : sections métier → modèles (app_label.ModelName), dans l'ordre d'affichage.
SECTIONS = [
    ("clients", _("Clients"), ["accounts.User"]),
    ("companies", _("Entreprises"), ["companies.Company"]),
    ("contracts", _("Contrats"), ["policies.Policy", "policies.Order", "attestations.Attestation", "policies.Claim",
                                  "policies.InsuredAsset"]),
    ("money", _("Paiements"), ["payments.Payment", "payments.Refund", "policies.Commission"]),
    ("catalog", _("Catalogue"), ["catalog.Insurer", "catalog.Product"]),
    ("technical", _("Technique"), ["audit.AuditEvent", "payments.CallbackLog", "policies.Quote", "auth.Group",
                                   "authtoken.TokenProxy"]),
]


class SanadAdminSite(admin.AdminSite):
    site_header = _("Sanad · back-office")
    site_title = _("Sanad · back-office")
    index_title = _("Tableau de bord")
    index_template = "admin/sanad_index.html"
    enable_nav_sidebar = False  # l'accueil et le fil d'Ariane suffisent : toute la largeur pour les tableaux

    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        if app_label:  # page d'une app Django : on garde le comportement standard
            return apps
        models = {f"{a['app_label']}.{m['object_name']}": m for a in apps for m in a["models"]}
        sections, placed = [], set()
        for key, name, wanted in SECTIONS:
            items = [models[w] for w in wanted if w in models]
            placed.update(w for w in wanted if w in models)
            if items:
                sections.append({"name": name, "app_label": f"sn-{key}", "app_url": items[0]["admin_url"],
                                 "has_module_perms": True, "models": items, "section": key})
        rest = [m for k, m in models.items() if k not in placed]
        if rest:  # tout modèle oublié reste accessible
            sections.append({"name": _("Autres"), "app_label": "sn-other", "app_url": rest[0]["admin_url"],
                             "has_module_perms": True, "models": rest, "section": "other"})
        return sections

    def index(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "todo": self._todo(), "today": self._today()}
        return super().index(request, extra_context)

    # --- Accueil -----------------------------------------------------------------------

    @staticmethod
    def _url(name: str, query: str = "") -> str:
        try:
            return reverse(f"admin:{name}") + (f"?{query}" if query else "")
        except NoReverseMatch:
            return ""

    def _todo(self) -> list[dict]:
        from apps.accounts.models import User
        from apps.companies.models import Company
        from apps.payments.models import Refund
        from apps.policies.models import Claim, Policy

        pending = Company.objects.filter(status=Company.Status.PENDING).annotate(
            kinds=Count("documents__kind", distinct=True))
        ready = pending.filter(kinds__gte=2).count()
        waiting_docs = pending.filter(kinds__lt=2).count()
        paid = Policy.objects.filter(status=Policy.Status.PAID)
        late = paid.filter(updated_at__lt=timezone.now() - timedelta(hours=24)).count()
        return [
            {"count": ready, "label": _("Entreprises à vérifier"),
             "hint": _("NIF et Registre du Commerce déposés"),
             "extra": _("%(n)s en attente de pièces") % {"n": waiting_docs} if waiting_docs else "",
             "url": self._url("companies_company_changelist", "status__exact=pending"), "tone": "warn"},
            {"count": paid.count(), "label": _("Polices payées, en attente de l'assureur"),
             "hint": _("Les compagnies les valident depuis leur portail"),
             "extra": _("%(n)s depuis plus de 24 h") % {"n": late} if late else "",
             "url": self._url("policies_policy_changelist", "status__exact=paid"), "tone": "bad" if late else "warn"},
            {"count": Refund.objects.filter(status=Refund.Status.FAILED).count(), "label": _("Remboursements en échec"),
             "hint": _("À reprendre à la main avec l'opérateur"),
             "url": self._url("payments_refund_changelist", "status__exact=failed"), "tone": "bad"},
            {"count": User.objects.filter(kyc_status=User.KycStatus.PENDING).count(),
             "label": _("Identités (KYC) à vérifier"), "hint": _("Pièces d'identité déposées par des clients"),
             "url": self._url("accounts_user_changelist", "kyc_status__exact=pending"), "tone": "warn"},
            {"count": Claim.objects.filter(status=Claim.Status.SUBMITTED).count(), "label": _("Sinistres déclarés"),
             "hint": _("À transmettre à l'assureur"),
             "url": self._url("policies_claim_changelist", "status__exact=submitted"), "tone": "warn"},
        ]

    def _today(self) -> list[dict]:
        from apps.companies.models import Company
        from apps.payments.models import Payment
        from apps.policies.models import Policy

        today = timezone.localdate()
        cashed = Payment.objects.filter(
            Q(status=Payment.Status.SUCCEEDED) | Q(status=Payment.Status.REFUNDED), confirmed_at__date=today
        ).aggregate(total=Sum("amount"))["total"] or 0
        return [
            {"value": Policy.objects.filter(status=Policy.Status.ACTIVE, decided_at__date=today).count(),
             "label": _("Polices activées aujourd'hui")},
            {"value": mru(cashed), "label": _("Encaissé aujourd'hui")},
            {"value": Company.objects.filter(created_at__date=today).count(),
             "label": _("Entreprises inscrites aujourd'hui")},
        ]
