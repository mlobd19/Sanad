from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts import api as accounts
from apps.attestations import api as attestations
from apps.companies import api as companies
from apps.payments import api as payments
from apps.policies import api as policies

from .meta import MetaView


api = [
    path("meta", MetaView.as_view()),  # mode démo (bandeau de l'app)
    # Compte et KYC
    path("auth/otp/request", accounts.OtpRequestView.as_view()),
    path("auth/otp/verify", accounts.OtpVerifyView.as_view()),
    path("auth/pro/login", accounts.ProLoginView.as_view()),
    path("auth/pro/verify", accounts.ProVerifyView.as_view()),
    path("auth/pro/password/forgot", accounts.PasswordForgotView.as_view()),
    path("auth/pro/password/reset", accounts.PasswordResetView.as_view()),
    path("me", accounts.MeView.as_view()),
    path("me/documents", accounts.KycDocumentView.as_view()),
    path("me/identity", accounts.IdentityCheckView.as_view()),
    # Biens, devis, polices
    path("assets", policies.AssetListView.as_view()),
    path("assets/scan", policies.RegistrationScanView.as_view()),
    path("assets/<int:asset_id>/quotes", policies.QuoteView.as_view()),
    path("policies", policies.PolicyListView.as_view()),
    path("policies/<int:policy_id>", policies.PolicyDetailView.as_view()),
    path("policies/<int:policy_id>/claims", policies.ClaimView.as_view()),
    # Paiements
    path("payments/providers", payments.ProviderListView.as_view()),
    path("policies/<int:policy_id>/pay", payments.PayPolicyView.as_view()),
    path("payments/callback/<str:provider>", payments.callback),
    path("payments/<uuid:payment_id>/simulate-confirm", payments.SimulateConfirmView.as_view()),
    # Attestations
    path("attestations/<int:attestation_id>/qr.png", attestations.QrCodeView.as_view()),
    path("attestations/<int:attestation_id>/pdf", attestations.AttestationPdfView.as_view()),
    path("verify/public-key", attestations.PublicKeyView.as_view()),
    path("verify/<str:token>", attestations.VerifyView.as_view()),
    # Portail assureur
    # Espace entreprise
    path("company/signup", companies.SignupView.as_view()),
    path("company/signup/verify", companies.SignupVerifyView.as_view()),
    path("company/me", companies.CompanyMeView.as_view()),
    path("company/documents", companies.DocumentView.as_view()),
    path("company/members", companies.MemberView.as_view()),
    path("company/fleet", companies.FleetView.as_view()),
    path("company/fleet/import", companies.FleetImportView.as_view()),
    path("company/quotes", companies.QuoteSelectionView.as_view()),
    path("company/orders", companies.OrderView.as_view()),
    path("company/orders/<int:order_id>", companies.OrderDetailView.as_view()),
    path("company/orders/<int:order_id>/pay", companies.OrderPayView.as_view()),
    path("company/policies", companies.CompanyPolicyView.as_view()),
    path("company/attestations.zip", companies.AttestationZipView.as_view()),
    path("company/claims", companies.FleetClaimListView.as_view()),
    path("company/policies/<int:policy_id>/claims", companies.FleetClaimView.as_view()),
    # Portail assureur
    path("insurer/me", policies.InsurerMeView.as_view()),
    path("insurer/policies", policies.InsurerPolicyListView.as_view()),
    path("insurer/commissions", policies.InsurerCommissionView.as_view()),
    path("insurer/policies/<int:policy_id>/<str:decision>", policies.InsurerDecisionView.as_view()),
    path("insurer/claims", policies.InsurerClaimListView.as_view()),
    path("insurer/claims/<int:claim_id>/photos/<int:photo_id>", policies.InsurerClaimPhotoView.as_view()),
    path("insurer/claims/<int:claim_id>/<str:action>", policies.InsurerClaimActionView.as_view()),
]

urlpatterns = [
    path("admin/i18n/", include("django.conf.urls.i18n")),  # choix de la langue (français / arabe)
    path("admin/", admin.site.urls),
    path("v/<str:token>", attestations.verify_page, name="verify-page"),
    path("api/", include(api)),
]

# Développement : Django sert les logos ; en production, le stockage objet ou le serveur web s'en charge.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
