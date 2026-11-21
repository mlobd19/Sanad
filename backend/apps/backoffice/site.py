"""Site d'administration de Sanad : connexion en deux étapes (mot de passe puis code SMS),
accueil « À traiter » et menu organisé par métier."""
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

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


# Connexion en attente du code SMS : {"user": pk, "at": envoi du code, "next": page demandée}.
PENDING_LOGIN = "sn_backoffice_login"
RESEND_DELAY = 60  # secondes entre deux envois de code


class PasswordThenSmsLoginView(LoginView):
    """1re étape : téléphone et mot de passe corrects → code SMS envoyé, pas encore de session ouverte."""

    def form_valid(self, form):
        if not settings.BACKOFFICE_SMS_CODE:  # développement uniquement (interdit en production)
            return super().form_valid(form)
        from apps.accounts.services import staff_send_code

        user = form.get_user()
        staff_send_code(user)
        self.request.session[PENDING_LOGIN] = {"user": user.pk, "at": int(time.time()), "next": self.get_success_url()}
        return HttpResponseRedirect(reverse("admin:login_code"))


class SanadAdminSite(admin.AdminSite):
    site_header = _("Sanad · back-office")
    site_title = _("Sanad · back-office")
    index_title = _("Tableau de bord")
    index_template = "admin/sanad_index.html"
    login_template = "admin/sanad_login.html"  # connexion Django + lien « Retour à Sanad »
    enable_nav_sidebar = False  # l'accueil et le fil d'Ariane suffisent : toute la largeur pour les tableaux

    # --- Connexion : mot de passe, puis code SMS ------------------------------------------

    def get_urls(self):
        return [path("login/code/", self.login_code, name="login_code"), *super().get_urls()]

    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        """Comme AdminSite.login, avec une 2e étape par code SMS (PasswordThenSmsLoginView)."""
        if request.method == "GET" and self.has_permission(request):
            return HttpResponseRedirect(reverse("admin:index", current_app=self.name))
        from django.contrib.admin.forms import AdminAuthenticationForm

        context = {**self.each_context(request), "title": gettext("Connexion"), "subtitle": None,
                   "app_path": request.get_full_path(), "username": request.user.get_username()}
        if REDIRECT_FIELD_NAME not in request.GET and REDIRECT_FIELD_NAME not in request.POST:
            context[REDIRECT_FIELD_NAME] = reverse("admin:index", current_app=self.name)
        context.update(extra_context or {})
        request.current_app = self.name
        return PasswordThenSmsLoginView.as_view(
            extra_context=context, authentication_form=self.login_form or AdminAuthenticationForm,
            template_name=self.login_template or "admin/login.html",
        )(request)

    @method_decorator(never_cache)
    def logout(self, request, extra_context=None):
        """Déconnexion : retour à l'accueil de Sanad (lien « Espace admin »), pas la page générique de Django."""
        from django.contrib.auth.views import LogoutView

        request.current_app = self.name
        return LogoutView.as_view(next_page="/")(request)

    @method_decorator(never_cache)
    def login_code(self, request):
        """2e étape : code reçu par SMS. Valable OTP_TTL_SECONDS ; renvoi possible après une minute."""
        from apps.accounts.models import User
        from apps.accounts.services import LoginError, mask_phone, staff_send_code, staff_verify_code

        pending = request.session.get(PENDING_LOGIN)
        user = User.objects.filter(pk=pending["user"], is_active=True, is_staff=True).first() if pending else None
        if user is None or time.time() - pending["at"] > settings.OTP_TTL_SECONDS * 3:
            request.session.pop(PENDING_LOGIN, None)
            return HttpResponseRedirect(reverse("admin:login", current_app=self.name))

        error = notice = ""
        if request.method == "POST" and "resend" in request.POST:
            wait = RESEND_DELAY - int(time.time() - pending["at"])
            if wait > 0:
                error = gettext("Patientez %(n)s secondes avant de demander un nouveau code.") % {"n": wait}
            else:
                staff_send_code(user)
                request.session[PENDING_LOGIN] = {**pending, "at": int(time.time())}
                notice = gettext("Nouveau code envoyé.")
        elif request.method == "POST":
            try:
                user = staff_verify_code(user.pk, request.POST.get("code", ""))
            except LoginError:
                error = gettext("Code incorrect ou expiré. Vérifiez le SMS ou demandez un nouveau code.")
            else:
                request.session.pop(PENDING_LOGIN, None)
                auth_login(request, user, backend="apps.accounts.backends.PhonePasswordBackend")
                return HttpResponseRedirect(pending.get("next") or reverse("admin:index", current_app=self.name))

        request.current_app = self.name
        return TemplateResponse(request, "admin/sanad_login_code.html", {
            **self.each_context(request), "title": gettext("Code de connexion"), "subtitle": None,
            "phone": mask_phone(user.phone), "error": error, "notice": notice,
        })

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
