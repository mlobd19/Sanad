from django.contrib import admin
from django.urls import include, path

from apps.accounts import api as accounts
from apps.attestations import api as attestations
from apps.payments import api as payments
from apps.policies import api as policies

admin.site.site_header = "Sanad · back-office"
admin.site.site_title = "Sanad"

api = [
    # Compte et KYC
    path("auth/otp/request", accounts.OtpRequestView.as_view()),
    path("auth/otp/verify", accounts.OtpVerifyView.as_view()),
    path("me", accounts.MeView.as_view()),
    path("me/documents", accounts.KycDocumentView.as_view()),
    # Biens, devis, polices
    path("assets", policies.AssetListView.as_view()),
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
    path("verify/public-key", attestations.PublicKeyView.as_view()),
    path("verify/<str:token>", attestations.VerifyView.as_view()),
    # Portail assureur
    path("insurer/policies", policies.InsurerPolicyListView.as_view()),
    path("insurer/policies/<int:policy_id>/<str:decision>", policies.InsurerDecisionView.as_view()),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("v/<str:token>", attestations.verify_page, name="verify-page"),
    path("api/", include(api)),
]
