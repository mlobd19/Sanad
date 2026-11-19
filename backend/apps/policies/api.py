from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attestations.models import Attestation

from . import services
from .models import Claim, InsuredAsset, Policy, Quote


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


class QuoteSerializer(serializers.ModelSerializer):
    insurer = serializers.CharField(source="product.insurer.name")
    product = serializers.CharField(source="product.name")
    product_code = serializers.CharField(source="product.code")
    coverages = serializers.JSONField(source="product.coverages")

    class Meta:
        model = Quote
        fields = ["id", "insurer", "product", "product_code", "coverages", "premium", "expires_at"]


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

    class Meta:
        model = Policy
        fields = [
            "id", "insurer", "product", "plate", "premium", "status", "status_label",
            "starts_on", "ends_on", "refusal_reason", "attestation", "asset_id", "renewed", "created_at",
        ]

    def get_renewed(self, policy):
        return policy.renewals.exclude(status__in=["refused", "cancelled"]).exists()

    def get_attestation(self, policy):
        att = policy.attestations.filter(status=Attestation.Status.VALID).first()
        return AttestationSerializer(att).data if att else None


class AssetListView(APIView):
    def get(self, request):
        return Response(AssetSerializer(request.user.assets.all(), many=True).data)

    def post(self, request):
        serializer = AssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = serializer.save(owner=request.user)
        return Response(AssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class QuoteView(APIView):
    @django_errors
    def post(self, request, asset_id):
        asset = get_object_or_404(InsuredAsset, pk=asset_id, owner=request.user)
        quotes = services.compute_quotes(request.user, asset)
        return Response(QuoteSerializer(quotes, many=True).data, status=status.HTTP_201_CREATED)


class PolicyListView(APIView):
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
    def get(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        return Response(PolicySerializer(policy).data)


class ClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ["id", "occurred_on", "description", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class ClaimView(APIView):
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


class IsInsurerAgent(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.INSURER_AGENT and user.insurer_id)


class InsurerPolicySerializer(PolicySerializer):
    customer = serializers.SerializerMethodField()
    payment_provider = serializers.SerializerMethodField()
    kyc_status = serializers.CharField(source="customer.kyc_status", read_only=True)

    class Meta(PolicySerializer.Meta):
        fields = PolicySerializer.Meta.fields + ["customer", "payment_provider", "kyc_status"]

    def get_customer(self, policy):
        return {"full_name": policy.customer.full_name, "phone": policy.customer.phone, "nni": policy.customer.nni}

    def get_payment_provider(self, policy):
        paid = policy.payments.filter(status="succeeded").first()
        return paid.provider if paid else None


class InsurerPolicyListView(APIView):
    permission_classes = [IsInsurerAgent]

    def get(self, request):
        qs = Policy.objects.filter(product__insurer_id=request.user.insurer_id).select_related(
            "product__insurer", "asset", "customer"
        )
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response(InsurerPolicySerializer(qs, many=True).data)


class InsurerDecisionView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def post(self, request, policy_id, decision):
        policy = get_object_or_404(Policy, pk=policy_id, product__insurer_id=request.user.insurer_id)
        if decision == "validate":
            policy = services.validate_policy(policy, request.user, request.data.get("insurer_reference", ""))
        elif decision == "refuse":
            policy = services.refuse_policy(policy, request.user, request.data.get("reason", ""))
        else:
            return Response({"detail": "Décision inconnue."}, status=404)
        return Response(InsurerPolicySerializer(policy).data)
