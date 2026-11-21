"""API de l'espace entreprise (/api/company/…). La logique métier est dans services.py."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponse
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import UserSerializer
from apps.accounts.services import LoginError
from apps.policies.api import ClaimSerializer, PolicySerializer, claim_error, django_errors, logo_url, truthy
from apps.policies.body_types import body_type
from apps.policies.models import Order, Policy
from apps.policies.services import parse_duration, parse_statuses

from . import services
from .models import CompanyDocument, Membership


class IsCompanyMember(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.COMPANY_MEMBER
                    and hasattr(user, "membership"))


# --- Inscription ------------------------------------------------------------------------------


class SignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "pro_login"

    @django_errors
    def post(self, request):
        d = request.data
        challenge, phone = services.signup(
            legal_name=d.get("legal_name", ""), nif=d.get("nif", ""), rc_number=d.get("rc_number", ""),
            address=d.get("address", ""), full_name=d.get("full_name", ""), email=d.get("email", ""),
            phone=d.get("phone", ""), password=d.get("password", ""), language=d.get("language", "fr"),
        )
        return Response({"challenge": challenge, "phone": phone}, status=status.HTTP_201_CREATED)


class SignupVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "pro_login"

    def post(self, request):
        try:
            user = services.verify_signup(request.data.get("challenge", ""), request.data.get("code", ""))
        except LoginError as exc:
            return Response({"detail": str(exc)}, status=400)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


# --- Entreprise, pièces, membres ------------------------------------------------------------------


class DocumentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display")

    class Meta:
        model = CompanyDocument
        fields = ["id", "kind", "kind_label", "uploaded_at"]


class MemberSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name")
    email = serializers.CharField(source="user.email")
    phone = serializers.CharField(source="user.phone")
    active = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["id", "full_name", "email", "phone", "role", "active", "created_at"]

    def get_active(self, m):
        return m.user.is_active and m.user.has_usable_password()


class CompanyMeView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request):
        company, membership = services.member_company(request.user)
        return Response({
            "company": {
                "legal_name": company.legal_name, "nif": company.nif, "rc_number": company.rc_number,
                "address": company.address, "status": company.status, "rejection_reason": company.rejection_reason,
                "missing_documents": services.missing_documents(company),
                "documents": DocumentSerializer(company.documents.all(), many=True).data,
            },
            "member": {"full_name": request.user.full_name, "email": request.user.email, "phone": request.user.phone,
                       "role": membership.role},
        })


class DocumentView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def post(self, request):
        doc = services.add_document(request.user, request.data.get("kind", ""), request.FILES.get("file"))
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class MemberView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request):
        company, _ = services.member_company(request.user)
        return Response(MemberSerializer(company.memberships.select_related("user"), many=True).data)

    @django_errors
    def post(self, request):
        d = request.data
        user = services.invite_member(request.user, full_name=d.get("full_name", ""), email=d.get("email", ""),
                                      phone=d.get("phone", ""), role=d.get("role", Membership.Role.MANAGER))
        return Response(MemberSerializer(user.membership).data, status=status.HTTP_201_CREATED)


# --- Flotte ------------------------------------------------------------------------------------------


class VehicleSerializer(serializers.Serializer):
    def to_representation(self, asset):
        # Contrat en cours : actif, sinon payé en attente de l'assureur (les brouillons non payés sont ignorés).
        current = next(
            (p for p in sorted(asset.policies.all(), key=lambda p: (p.status == "active", p.ends_on), reverse=True)
             if p.status in ("paid", "active")), None)
        return {
            "id": asset.pk,
            "reference": asset.reference,
            "attributes": asset.attributes,
            "body_type": body_type((asset.attributes or {}).get("make")),
            "policy": None if current is None else {
                "id": current.pk, "status": current.status, "insurer": current.product.insurer.name,
                "product": current.product.name, "ends_on": current.ends_on,
            },
        }


class FleetView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request):
        return Response(VehicleSerializer(services.fleet(request.user), many=True).data)

    @django_errors
    def post(self, request):
        asset = services.add_vehicle(request.user, request.data.get("reference", ""),
                                     request.data.get("attributes") or {})
        return Response(VehicleSerializer(asset).data, status=status.HTTP_201_CREATED)


class FleetImportView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def post(self, request):
        file = request.FILES.get("file")
        if file is None or file.size > services.MAX_UPLOAD_BYTES:
            raise DjangoValidationError("Joignez un fichier CSV de 8 Mo au plus.")
        return Response(services.import_fleet(request.user, file.read()))


# --- Devis, commandes, paiement -------------------------------------------------------------------------


class QuoteSelectionView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def post(self, request):
        months = parse_duration(request.data.get("months"))
        offers = services.quote_selection(request.user, request.data.get("asset_ids") or [], months=months)
        return Response([{
            "insurer": o["product"].insurer.name,
            "insurer_legal_name": o["product"].insurer.legal_name,
            "insurer_logo": logo_url(o["product"].insurer),
            "product": o["product"].name,
            "product_code": o["product"].code,
            "coverages": o["product"].coverages,
            "indicative": o["product"].is_indicative,
            "total": o["total"],
            "duration_months": months,
            "lines": o["lines"],
        } for o in offers])


def order_data(order: Order) -> dict:
    policies = list(order.policies.select_related("product__insurer", "asset").prefetch_related(
        "attestations", "renewals"))
    return {"id": order.pk, "total": sum(p.premium for p in policies), "created_at": order.created_at,
            "policies": PolicySerializer(policies, many=True).data}


class OrderView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def post(self, request):
        starts_on = None
        if request.data.get("starts_on"):
            starts_on = serializers.DateField().run_validation(request.data["starts_on"])
        order = services.create_order(request.user, request.data.get("quote_ids") or [], starts_on=starts_on)
        return Response(order_data(order), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request, order_id):
        try:
            return Response(order_data(services.company_order(request.user, order_id)))
        except Order.DoesNotExist:
            raise Http404 from None


class OrderPayView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def post(self, request, order_id):
        try:
            order = services.company_order(request.user, order_id)
        except Order.DoesNotExist:
            raise Http404 from None
        payment, instructions = services.pay_order(request.user, order, request.data.get("provider", ""),
                                                   request.data.get("payer_phone", ""))
        return Response({"payment_id": str(payment.id), "reference": payment.external_ref, "amount": payment.amount,
                         "instructions": instructions}, status=status.HTTP_201_CREATED)


# --- Contrats -------------------------------------------------------------------------------------------


class CompanyPolicyView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def get(self, request):
        qs = services.company_policies(request.user, parse_statuses(request.query_params.get("status")))
        return Response(PolicySerializer(qs, many=True).data)


class AttestationZipView(APIView):
    permission_classes = [IsCompanyMember]

    @django_errors
    def get(self, request):
        company, _ = services.member_company(request.user)
        content = services.attestations_zip(request.user)
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="attestations-{company.nif}.zip"'
        return response



# --- Sinistres de la flotte ----------------------------------------------------------------------------


class FleetClaimSerializer(ClaimSerializer):
    policy_id = serializers.IntegerField(source="policy.pk", read_only=True)
    plate = serializers.CharField(source="policy.asset.reference", read_only=True)
    insurer = serializers.CharField(source="policy.product.insurer.name", read_only=True)
    declared_by = serializers.CharField(source="declared_by.full_name", default="", read_only=True)

    class Meta(ClaimSerializer.Meta):
        fields = ClaimSerializer.Meta.fields + ["policy_id", "plate", "insurer", "declared_by"]


class FleetClaimListView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request):
        return Response(FleetClaimSerializer(services.company_claims(request.user), many=True).data)


class FleetClaimView(APIView):
    """Déclaration d'un sinistre sur un contrat de la flotte (multipart, champ « photos » répété)."""

    permission_classes = [IsCompanyMember]

    def post(self, request, policy_id):
        data = {key: request.data.get(key) for key in ("kind", "occurred_on", "place", "description", "third_party_plate")}
        data["injuries"] = truthy(request.data.get("injuries"))
        try:
            claim = services.declare_fleet_claim(request.user, policy_id, data, request.FILES.getlist("photos"))
        except Policy.DoesNotExist:
            raise Http404 from None
        except DjangoValidationError as exc:
            return claim_error(exc)
        return Response(FleetClaimSerializer(claim).data, status=status.HTTP_201_CREATED)
