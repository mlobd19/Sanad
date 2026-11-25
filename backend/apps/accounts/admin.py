from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.audit.models import record
from apps.backoffice.ui import pill, status_pill

from .models import AuthToken, IdentityCheck, User, format_phone
from .services import send_password_email


class IdentityCheckInline(admin.TabularInline):
    """Historique des vérifications d'identité numérique (eID) auprès de l'ANRPTS : lecture seule."""

    model = IdentityCheck
    extra = 0
    can_delete = False
    fields = ("created_at", "provider", "nni", "outcome_display", "reference")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("résultat"))
    def outcome_display(self, check):
        return status_pill(check, "outcome")


class RoleFilter(admin.SimpleListFilter):
    title = _("type de compte")
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return [("customer", _("Particuliers")), ("pro", _("Comptes professionnels")), ("staff", _("Équipe Sanad"))]

    def queryset(self, request, queryset):
        if self.value() == "customer":
            return queryset.filter(role=User.Role.CUSTOMER)
        if self.value() == "pro":
            return queryset.filter(role__in=User.PRO_ROLES)
        if self.value() == "staff":
            return queryset.filter(role=User.Role.STAFF)
        return queryset


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("phone_display", "full_name", "email", "role_display", "organisation", "kyc_display", "is_active",
                    "date_joined")
    list_display_links = ("phone_display", "full_name")
    list_filter = (RoleFilter, "kyc_status", "insurer", "is_active")
    search_fields = ("phone", "email", "full_name", "nni")
    inlines = [IdentityCheckInline]
    fieldsets = (
        (_("Identité"), {"fields": ("full_name", "full_name_ar", "phone", "email", "nni", "language")}),
        (_("Rôle et accès"), {
            "fields": ("role", "insurer", "is_active", "is_staff", "is_superuser", "groups"),
            "description": _("Agent assureur : choisir la compagnie, renseigner l'email, puis envoyer l'invitation "
                             "depuis la liste (action « Envoyer l'invitation »)."),
        }),
        (_("Vérification d'identité"), {
            "fields": ("kyc_status",),
            "description": _("Vérifiée uniquement par l'identité numérique (eID Houwiyeti) auprès de l'ANRPTS, "
                             "depuis le profil du client. Aucune pièce d'identité n'est demandée."),
        }),
        (_("Sécurité"), {"fields": ("password", "last_login", "failed_logins", "locked_until"),
                         "classes": ("collapse",)}),
    )
    add_fieldsets = ((None, {
        "classes": ("wide",),
        "fields": ("phone", "full_name", "email", "role", "insurer", "password1", "password2"),
        "description": _("Pour un agent assureur : laissez le mot de passe vide si le formulaire le permet, "
                         "puis envoyez l'invitation : l'agent choisira lui-même son mot de passe."),
    }),)
    readonly_fields = ("last_login", "failed_logins", "kyc_status")
    actions = ["send_invitation"]
    # Particulier : nom renvoyé par l'ANRPTS avec l'eID, jamais modifié à la main.
    CUSTOMER_IDENTITY_FIELDS = ("full_name", "full_name_ar")

    # Un compte équipe ordinaire (groupe « Équipe Sanad ») ne peut ni s'accorder plus de droits,
    # ni modifier un superutilisateur : seuls les superutilisateurs gèrent les accès.
    ACCESS_FIELDS = ("is_staff", "is_superuser", "groups", "user_permissions")

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        if obj is not None and obj.role == User.Role.CUSTOMER:
            fields = (*fields, *self.CUSTOMER_IDENTITY_FIELDS)
        return fields if request.user.is_superuser else (*fields, *self.ACCESS_FIELDS)

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("insurer", "membership__company")

    @admin.display(description=_("téléphone"), ordering="phone")
    def phone_display(self, user):
        return format_html('<span class="sn-mono">{}</span>', format_phone(user.phone))

    @admin.display(description=_("rôle"), ordering="role")
    def role_display(self, user):
        tone = {"customer": "quiet", "insurer_agent": "ok", "company_member": "ok", "staff": "warn"}.get(user.role)
        return pill(user.role, user.get_role_display(), tone)

    @admin.display(description=_("organisation"))
    def organisation(self, user):
        if user.insurer_id:
            return user.insurer.name
        membership = getattr(user, "membership", None)
        return membership.company.legal_name if membership else "—"

    @admin.display(description=_("identité"), ordering="kyc_status")
    def kyc_display(self, user):
        return status_pill(user, "kyc_status")

    @admin.action(description=_("Envoyer l'invitation par email (choix du mot de passe)"))
    def send_invitation(self, request, queryset):
        sent = 0
        for user in queryset:
            if not user.is_pro:
                self.message_user(request, gettext("%(user)s : pas un compte professionnel, ignoré.") % {"user": user},
                                  messages.WARNING)
                continue
            try:
                send_password_email(user, "invite", actor=request.user)
                sent += 1
            except ValidationError as exc:
                self.message_user(request, f"{user} : {exc.messages[0]}", messages.ERROR)
        if sent:
            self.message_user(request, gettext("Invitation envoyée à %(n)s compte(s).") % {"n": sent}, messages.SUCCESS)


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    """Connexions ouvertes à l'app (un appareil chacune). Lecture seule ; « Fermer » révoque le jeton."""

    list_display = ("user", "created_at", "last_used_at", "expires_at", "user_agent")
    list_filter = ("user__role",)
    search_fields = ("user__phone", "user__email", "user__full_name")
    fields = ("user", "created_at", "last_used_at", "expires_at", "user_agent")
    readonly_fields = fields
    actions = ["close_sessions"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description=_("Fermer les connexions sélectionnées"))
    def close_sessions(self, request, queryset):
        for token in queryset.select_related("user"):
            record("user.session_closed", token.user, actor=request.user)
        count = queryset.delete()[0]
        self.message_user(request, gettext("%(n)s connexion(s) fermée(s).") % {"n": count}, messages.SUCCESS)


# Ancien jeton DRF (sans fin) : remplacé par AuthToken, plus affiché.
try:
    from rest_framework.authtoken.models import TokenProxy

    admin.site.unregister(TokenProxy)
except (ImportError, admin.sites.NotRegistered):
    pass
