from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.audit.models import record
from apps.backoffice.actions import reason_page
from apps.backoffice.ui import pill, status_pill

from .models import KycDocument, User
from .services import send_password_email


class KycDocumentInline(admin.TabularInline):
    model = KycDocument
    fk_name = "user"
    extra = 0
    can_delete = False
    fields = ("kind", "open_file", "status_display", "review_note", "uploaded_at")
    readonly_fields = ("kind", "open_file", "status_display", "review_note", "uploaded_at")

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("fichier"))
    def open_file(self, doc):
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', doc.file.url, gettext("Ouvrir"))

    @admin.display(description=_("statut"))
    def status_display(self, doc):
        return status_pill(doc)


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
    inlines = [KycDocumentInline]
    fieldsets = (
        (_("Identité"), {"fields": ("full_name", "phone", "email", "nni", "language")}),
        (_("Rôle et accès"), {
            "fields": ("role", "insurer", "is_active", "is_staff", "is_superuser", "groups"),
            "description": _("Agent assureur : choisir la compagnie, renseigner l'email, puis envoyer l'invitation "
                             "depuis la liste (action « Envoyer l'invitation »)."),
        }),
        (_("Vérification d'identité"), {"fields": ("kyc_status",)}),
        (_("Sécurité"), {"fields": ("password", "last_login", "failed_logins", "locked_until"),
                         "classes": ("collapse",)}),
    )
    add_fieldsets = ((None, {
        "classes": ("wide",),
        "fields": ("phone", "full_name", "email", "role", "insurer", "password1", "password2"),
        "description": _("Pour un agent assureur : laissez le mot de passe vide si le formulaire le permet, "
                         "puis envoyez l'invitation : l'agent choisira lui-même son mot de passe."),
    }),)
    readonly_fields = ("last_login", "failed_logins")
    actions = ["mark_kyc_verified", "reject_kyc", "send_invitation"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("insurer", "membership__company")

    @admin.display(description=_("téléphone"), ordering="phone")
    def phone_display(self, user):
        return format_html('<span class="sn-mono">{}</span>', user.phone)

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

    @admin.action(description=_("Valider l'identité (KYC)"))
    def mark_kyc_verified(self, request, queryset):
        for user in queryset:
            user.kyc_status = User.KycStatus.VERIFIED
            user.save(update_fields=["kyc_status"])
            user.documents.filter(status=KycDocument.Status.PENDING).update(
                status=KycDocument.Status.ACCEPTED, reviewed_by=request.user
            )
            record("kyc.verified", user, actor=request.user)
        self.message_user(request, gettext("Identité validée pour %(n)s compte(s).") % {"n": queryset.count()},
                          messages.SUCCESS)

    @admin.action(description=_("Refuser l'identité (KYC)…"))
    def reject_kyc(self, request, queryset):
        def apply(user, reason):
            user.kyc_status = User.KycStatus.REJECTED
            user.save(update_fields=["kyc_status"])
            user.documents.filter(status=KycDocument.Status.PENDING).update(
                status=KycDocument.Status.REJECTED, reviewed_by=request.user, review_note=reason[:255]
            )
            record("kyc.rejected", user, actor=request.user, reason=reason)

        return reason_page(
            request, self, objects=list(queryset), action="reject_kyc",
            title=gettext("Refuser l'identité"),
            intro=gettext("Le client ne pourra plus souscrire tant qu'il n'aura pas déposé de pièce valable."),
            label=gettext("Motif du refus (obligatoire)"), submit=gettext("Refuser l'identité"), apply=apply,
            done_message=gettext("Identité refusée pour %(n)s compte(s)."),
        )

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
