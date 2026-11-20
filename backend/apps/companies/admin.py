from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.accounts.storage import private_file_response
from apps.audit.models import record
from apps.backoffice.actions import reason_page
from apps.backoffice.ui import pill, status_pill

from . import services
from .models import Company, CompanyDocument, Membership


class DocumentInline(admin.TabularInline):
    model = CompanyDocument
    extra = 0
    can_delete = False
    fields = ("kind", "open_file", "uploaded_by", "uploaded_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("fichier"))
    def open_file(self, doc):
        # Fichier privé : ouvert par une vue réservée à l'équipe, jamais par une URL publique.
        url = reverse("admin:companies_companydocument_file", args=[doc.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, gettext("Ouvrir"))


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "company"
    extra = 0
    can_delete = False
    fields = ("member", "email", "phone", "role", "invited_by", "created_at")
    readonly_fields = ("member", "email", "phone", "invited_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False  # les membres sont invités par l'administrateur de l'entreprise

    @admin.display(description=_("membre"))
    def member(self, m):
        url = reverse("admin:accounts_user_change", args=[m.user_id])
        return format_html('<a href="{}">{}</a>', url, m.user.full_name or m.user.email)

    @admin.display(description=_("email"))
    def email(self, m):
        return m.user.email

    @admin.display(description=_("téléphone"))
    def phone(self, m):
        return m.user.phone


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "nif", "rc_number", "status_display", "documents_display", "members", "created_at")
    list_filter = ("status",)
    search_fields = ("legal_name", "nif", "rc_number")
    readonly_fields = ("status_display", "rejection_reason", "verified_by", "verified_at", "created_at")
    fieldsets = (
        (_("Entreprise"), {"fields": ("legal_name", "nif", "rc_number", "address")}),
        (_("Vérification"), {"fields": ("status_display", "rejection_reason", "verified_by", "verified_at",
                                        "created_at")}),
    )
    inlines = [DocumentInline, MembershipInline]
    actions = ["verify"]
    change_form_template = "admin/companies/company/change_form.html"
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_kinds=Count("documents__kind", distinct=True), n_members=Count("memberships", distinct=True))

    def has_add_permission(self, request):
        return False  # les entreprises s'inscrivent elles-mêmes en ligne

    def has_delete_permission(self, request, obj=None):
        return False  # contrats et paiements y sont rattachés : on refuse, on ne supprime pas

    @admin.display(description=_("statut"), ordering="status")
    def status_display(self, company):
        return status_pill(company)

    @admin.display(description=_("pièces"), ordering="n_kinds")
    def documents_display(self, company):
        n = getattr(company, "n_kinds", None)
        if n is None:
            n = company.documents.values("kind").distinct().count()
        return pill("ok" if n >= 2 else "warn", f"{n}/2", "ok" if n >= 2 else "warn")

    @admin.display(description=_("membres"), ordering="n_members")
    def members(self, company):
        return company.n_members

    # --- Décision : vérifier ou refuser --------------------------------------------------------

    def get_urls(self):
        return [
            path("<int:pk>/verifier/", self.admin_site.admin_view(self.verify_view), name="companies_company_verify"),
            path("<int:pk>/refuser/", self.admin_site.admin_view(self.reject_view), name="companies_company_reject"),
            path("piece/<int:doc_id>/", self.admin_site.admin_view(self.document_file_view),
                 name="companies_companydocument_file"),
            *super().get_urls(),
        ]

    def document_file_view(self, request, doc_id):
        """Affiche une pièce NIF / RC à l'équipe ; chaque consultation est journalisée."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        doc = get_object_or_404(CompanyDocument, pk=doc_id)
        response = private_file_response(doc.file)
        record("company.document_viewed", doc.company, actor=request.user, kind=doc.kind, document_id=doc.pk)
        return response

    def change_view(self, request, object_id, form_url="", extra_context=None):
        company = self.get_object(request, object_id)
        extra = {}
        if company is not None:
            missing = services.missing_documents(company)
            labels = dict(CompanyDocument.Kind.choices)
            extra = {
                "sn_company": company,
                "sn_documents": company.documents.all(),
                "sn_missing": [labels[k] for k in missing],
                "sn_can_decide": self.has_change_permission(request, company),
            }
        return super().change_view(request, object_id, form_url, {**(extra_context or {}), **extra})

    def verify_view(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        if request.method == "POST" and self.has_change_permission(request, company):
            try:
                services.verify_company(company, request.user)
                self.message_user(request, gettext("%(company)s est vérifiée : elle peut maintenant payer.")
                                  % {"company": company}, messages.SUCCESS)
            except ValidationError as exc:
                self.message_user(request, exc.messages[0], messages.ERROR)
        return redirect("admin:companies_company_change", pk)

    def reject_view(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        back = reverse("admin:companies_company_change", args=[pk])
        response = reason_page(
            request, self, objects=[company], back=back,
            title=gettext("Refuser l'entreprise"),
            intro=gettext("L'administrateur de l'entreprise reçoit ce motif par email et peut déposer une pièce "
                          "corrigée : la vérification reprendra alors."),
            label=gettext("Motif du refus (obligatoire)"), submit=gettext("Refuser l'entreprise"),
            apply=lambda c, reason: services.reject_company(c, request.user, reason),
            done_message=gettext("Entreprise refusée."),
        )
        return response or redirect(back)

    @admin.action(description=_("Vérifier les entreprises sélectionnées (NIF et RC contrôlés)"))
    def verify(self, request, queryset):
        for company in queryset:
            try:
                services.verify_company(company, request.user)
                self.message_user(request, gettext("%(company)s : vérifiée.") % {"company": company}, messages.SUCCESS)
            except ValidationError as exc:
                self.message_user(request, f"{company} : {exc.messages[0]}", messages.ERROR)
