from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attestations.models import Attestation

from . import registration_scan, services
from .models import Claim, Commission, InsuredAsset, Policy, Quote


def django_errors(fn):
    """Convertit les erreurs métier Django en réponses API lisibles."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=400)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc

    return wrapper


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuredAsset
        fields = ["id", "kind", "reference", "attributes", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_reference(self, value):
        return value.strip().upper()

    def validate_attributes(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Objet attendu.")
        return value


class IsCustomer(BasePermission):
    """Espace particulier : les comptes pro (agents, entreprises) ont leurs propres API."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not user.is_pro)


def logo_url(insurer):
    return insurer.logo.url if insurer.logo else None


class QuoteSerializer(serializers.ModelSerializer):
    insurer = serializers.CharField(source="product.insurer.name")
    insurer_legal_name = serializers.CharField(source="product.insurer.legal_name")
    insurer_slug = serializers.CharField(source="product.insurer.slug")
    product = serializers.CharField(source="product.name")
    product_code = serializers.CharField(source="product.code")
    coverages = serializers.JSONField(source="product.coverages")
    indicative = serializers.BooleanField(source="product.is_indicative")
    insurer_logo = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "id", "insurer", "insurer_legal_name", "insurer_slug", "insurer_logo", "product", "product_code",
            "coverages", "indicative", "premium", "duration_months", "expires_at",
        ]

    def get_insurer_logo(self, quote):
        return logo_url(quote.product.insurer)


class AttestationSerializer(serializers.ModelSerializer):
    verify_url = serializers.CharField(read_only=True)

    class Meta:
        model = Attestation
        fields = ["id", "number", "status", "issued_at", "verify_url"]


class PolicySerializer(serializers.ModelSerializer):
    insurer = serializers.CharField(source="product.insurer.name", read_only=True)
    product = serializers.CharField(source="product.name", read_only=True)
    plate = serializers.CharField(source="asset.reference", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    attestation = serializers.SerializerMethodField()
    renewed = serializers.SerializerMethodField()
    insurer_logo = serializers.SerializerMethodField()
    duration_months = serializers.IntegerField(source="quote.duration_months", read_only=True)

    class Meta:
        model = Policy
        fields = [
            "id", "insurer", "insurer_logo", "product", "plate", "premium", "status", "status_label",
            "starts_on", "ends_on", "duration_months", "refusal_reason", "attestation", "asset_id", "renewed", "created_at",
        ]

    def get_insurer_logo(self, policy):
        return logo_url(policy.product.insurer)

    def get_renewed(self, policy):
        return policy.renewals.exclude(status__in=["refused", "cancelled"]).exists()

    def get_attestation(self, policy):
        att = policy.attestations.filter(status=Attestation.Status.VALID).first()
        return AttestationSerializer(att).data if att else None


class AssetListView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return Response(AssetSerializer(request.user.assets.all(), many=True).data)

    def post(self, request):
        serializer = AssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = serializer.save(owner=request.user)
        return Response(AssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class CanScanRegistration(BasePermission):
    """Particuliers et membres d'entreprise (flotte) ; pas les agents assureurs."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role != user.Role.INSURER_AGENT)


class RegistrationScanView(APIView):
    """Lit une photo de carte grise et renvoie les champs pour pré-remplir le formulaire.

    Chaque erreur porte un « code » que l'app traduit (français / arabe).
    """

    permission_classes = [CanScanRegistration]
    parser_classes = [MultiPartParser]
    throttle_scope = "scan"

    def post(self, request):
        try:
            fields = services.scan_registration_card(request.user, request.FILES.get("image"))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0], "code": exc.error_list[0].code or "invalid"}, status=400)
        except registration_scan.ScanUnavailable:
            return Response({"detail": "La lecture automatique n'est pas disponible.", "code": "unavailable"},
                            status=503)
        except registration_scan.ScanFailed:
            return Response({"detail": "La carte grise n'a pas pu être lue.", "code": "failed"}, status=502)
        return Response(fields)


class QuoteView(APIView):
    permission_classes = [IsCustomer]

    @django_errors
    def post(self, request, asset_id):
        asset = get_object_or_404(InsuredAsset, pk=asset_id, owner=request.user)
        months = services.parse_duration(request.data.get("months"))
        quotes = services.compute_quotes(request.user, asset, months=months)
        return Response(QuoteSerializer(quotes, many=True).data, status=status.HTTP_201_CREATED)


class PolicyListView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        qs = request.user.policies.select_related("product__insurer", "asset").prefetch_related("attestations")
        return Response(PolicySerializer(qs, many=True).data)

    @django_errors
    def post(self, request):
        quote = get_object_or_404(Quote, pk=request.data.get("quote_id"), customer=request.user)
        starts_on = serializers.DateField(required=False, allow_null=True).run_validation(
            request.data.get("starts_on")
        ) if request.data.get("starts_on") else None
        renewal_of = None
        if request.data.get("renewal_of"):
            renewal_of = get_object_or_404(Policy, pk=request.data["renewal_of"], customer=request.user)
        policy = services.create_policy(request.user, quote, starts_on=starts_on, renewal_of=renewal_of)
        return Response(PolicySerializer(policy).data, status=status.HTTP_201_CREATED)


class PolicyDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        return Response(PolicySerializer(policy).data)


class ClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ["id", "occurred_on", "description", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class ClaimView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        return Response(ClaimSerializer(policy.claims.all(), many=True).data)

    def post(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        if policy.status != Policy.Status.ACTIVE:
            return Response({"detail": "Un sinistre se déclare sur une police active."}, status=400)
        serializer = ClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        claim = serializer.save(policy=policy)
        return Response(ClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


# --- Portail assureur ---------------------------------------------------------
# Chaque lecture et chaque décision passe par services.insurer_* : la compagnie
# vient toujours du compte de l'agent, jamais de la requête.


class IsInsurerAgent(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.INSURER_AGENT and user.insurer_id)


class InsurerPolicySerializer(PolicySerializer):
    customer = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    payment_provider = serializers.SerializerMethodField()
    kyc_status = serializers.CharField(source="customer.kyc_status", read_only=True)
    indicative = serializers.BooleanField(source="product.is_indicative", read_only=True)

    class Meta(PolicySerializer.Meta):
        fields = PolicySerializer.Meta.fields + [
            "customer", "company", "vehicle", "payment_provider", "kyc_status", "indicative", "insurer_reference", "decided_at",
        ]

    def get_customer(self, policy):
        return {"full_name": policy.customer.full_name, "phone": policy.customer.phone, "nni": policy.customer.nni}

    def get_company(self, policy):
        company = policy.company
        if company is None:
            return None
        return {"legal_name": company.legal_name, "nif": company.nif, "rc_number": company.rc_number,
                "status": company.status}

    def get_vehicle(self, policy):
        attrs = policy.asset.attributes
        return {"make": attrs.get("make", ""), "fiscal_power": attrs.get("fiscal_power"), "usage": attrs.get("usage", "")}

    def get_payment_provider(self, policy):
        payments = list(policy.payments.all()) + (list(policy.order.payments.all()) if policy.order_id else [])
        paid = next((p for p in payments if p.status in ("succeeded", "refunded")), None)
        return paid.provider if paid else None

    def get_renewed(self, policy):
        return any(r.status not in ("refused", "cancelled") for r in policy.renewals.all())

    def get_attestation(self, policy):
        att = next((a for a in policy.attestations.all() if a.status == Attestation.Status.VALID), None)
        return AttestationSerializer(att).data if att else None


class InsurerMeView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def get(self, request):
        insurer = services.agent_insurer(request.user)
        return Response({
            "agent": {"full_name": request.user.full_name, "phone": request.user.phone},
            "insurer": {
                "name": insurer.name,
                "legal_name": insurer.legal_name,
                "slug": insurer.slug,
                "logo": logo_url(insurer),
            },
        })


class InsurerPolicyListView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def get(self, request):
        statuses = services.parse_statuses(request.query_params.get("status"))
        qs = services.insurer_policies(request.user, statuses)
        return Response(InsurerPolicySerializer(qs, many=True).data)


class InsurerDecisionView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def post(self, request, policy_id, decision):
        if decision not in ("validate", "refuse"):
            return Response({"detail": "Décision inconnue."}, status=404)
        try:
            policy = services.insurer_policy(request.user, policy_id)
        except Policy.DoesNotExist:
            raise Http404 from None
        if decision == "validate":
            policy = services.validate_policy(policy, request.user, request.data.get("insurer_reference", ""))
        else:
            policy = services.refuse_policy(policy, request.user, request.data.get("reason", ""))
        policy = services.insurer_policy(request.user, policy.pk)  # relu avec l'attestation émise
        return Response(InsurerPolicySerializer(policy).data)


class CommissionSerializer(serializers.ModelSerializer):
    policy_id = serializers.IntegerField(source="policy.id")
    plate = serializers.CharField(source="policy.asset.reference")
    product = serializers.CharField(source="policy.product.name")
    premium = serializers.IntegerField(source="policy.premium")

    class Meta:
        model = Commission
        fields = ["id", "policy_id", "plate", "product", "premium", "rate", "amount", "period", "is_paid", "created_at"]


class InsurerCommissionView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def get(self, request):
        data = services.insurer_commissions(request.user)
        return Response({
            "indicative": data["indicative"],
            "months": data["months"],
            "items": CommissionSerializer(data["items"], many=True).data,
        })
