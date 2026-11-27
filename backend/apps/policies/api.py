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

from apps.accounts.storage import private_file_response
from apps.attestations.models import Attestation
from apps.audit.models import record

from . import registration_scan, services, travel
from .body_types import body_type
from .models import Claim, Commission, InsuredAsset, Policy, Quote, Traveler, Trip, VehicleUsage, normalize_plate


def django_errors(fn):
    """Convertit les erreurs métier Django en réponses API lisibles."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DjangoValidationError as exc:
            body = {"detail": exc.messages[0]}
            code = getattr(exc, "error_list", [None])[0]
            if code is not None and code.code:
                body["code"] = code.code  # traduit par l'app (ex. kyc_required)
            return Response(body, status=400)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc

    return wrapper


class AssetSerializer(serializers.ModelSerializer):
    # Carrosserie déduite de « marque et modèle », pour l'illustration (aucune question de plus à l'utilisateur).
    body_type = serializers.SerializerMethodField()

    class Meta:
        model = InsuredAsset
        fields = ["id", "kind", "reference", "attributes", "body_type", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_body_type(self, asset):
        return body_type((asset.attributes or {}).get("make"))

    def validate_reference(self, value):
        plate = normalize_plate(value)
        if not plate:
            raise serializers.ValidationError("Indiquez l'immatriculation.")
        return plate

    def validate_attributes(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Objet attendu.")
        # Personnel ou commercial ; « taxi » n'existe plus. Un usage absent est signalé au devis.
        if "usage" in value and value["usage"] not in VehicleUsage.values:
            raise serializers.ValidationError(services.USAGE_ERROR)
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
    branch = serializers.CharField(source="product.branch")
    limits = serializers.JSONField(source="product.limits")
    days = serializers.SerializerMethodField()
    travelers = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "id", "insurer", "insurer_legal_name", "insurer_slug", "insurer_logo", "product", "product_code",
            "coverages", "indicative", "premium", "duration_months", "expires_at", "branch", "limits", "days",
            "travelers",
        ]

    def get_days(self, quote):
        return quote.attributes_snapshot.get("days")

    def get_travelers(self, quote):
        """Voyage : nombre de voyageurs du devis (la prime est leur total)."""
        travelers = quote.attributes_snapshot.get("travelers")
        return len(travelers) if travelers is not None else None

    def get_insurer_logo(self, quote):
        return logo_url(quote.product.insurer)


class AttestationSerializer(serializers.ModelSerializer):
    verify_url = serializers.CharField(read_only=True)

    class Meta:
        model = Attestation
        fields = ["id", "number", "status", "issued_at", "verify_url"]


class TravelerSerializer(serializers.ModelSerializer):
    attestation = serializers.SerializerMethodField()

    class Meta:
        model = Traveler
        fields = ["id", "nni", "full_name", "full_name_ar", "passport_number", "birth_date", "verification",
                  "attestation"]

    def get_attestation(self, traveler):
        att = next((a for a in traveler.attestations.all() if a.status == Attestation.Status.VALID), None)
        return AttestationSerializer(att).data if att else None


class TripSerializer(serializers.ModelSerializer):
    days = serializers.IntegerField(read_only=True)
    travelers = TravelerSerializer(many=True, read_only=True)
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = ["id", "asset_id", "destinations", "departure_on", "return_on", "days", "travelers", "locked"]

    def get_locked(self, trip):
        return travel.is_locked(trip)


class PolicySerializer(serializers.ModelSerializer):
    insurer = serializers.CharField(source="product.insurer.name", read_only=True)
    product = serializers.CharField(source="product.name", read_only=True)
    plate = serializers.CharField(source="asset.reference", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    attestation = serializers.SerializerMethodField()
    renewed = serializers.SerializerMethodField()
    insurer_logo = serializers.SerializerMethodField()
    duration_months = serializers.IntegerField(source="quote.duration_months", read_only=True)
    body_type = serializers.SerializerMethodField()
    branch = serializers.CharField(source="product.branch", read_only=True)
    trip = serializers.SerializerMethodField()
    limits = serializers.JSONField(source="product.limits", read_only=True)
    assistance_phone = serializers.CharField(source="product.insurer.assistance_phone", read_only=True)

    class Meta:
        model = Policy
        fields = [
            "id", "insurer", "insurer_logo", "product", "plate", "body_type", "premium", "status", "status_label",
            "starts_on", "ends_on", "duration_months", "refusal_reason", "attestation", "asset_id", "renewed", "created_at",
            "branch", "trip", "limits", "assistance_phone",
        ]

    def get_trip(self, policy):
        """Voyage : destinations, dates et voyageurs (chacun avec son attestation). Auto : null."""
        if not policy.is_travel:
            return None
        trip = policy.asset.trip
        return {"id": trip.pk, "destinations": trip.destinations, "departure_on": trip.departure_on,
                "return_on": trip.return_on, "days": trip.days,
                "travelers": TravelerSerializer(trip.travelers.all(), many=True).data}

    def get_insurer_logo(self, policy):
        return logo_url(policy.product.insurer)

    def get_body_type(self, policy):
        if policy.is_travel:
            return None
        return body_type((policy.asset.attributes or {}).get("make"))

    def get_renewed(self, policy):
        return policy.renewals.exclude(status__in=["refused", "cancelled"]).exists()

    def get_attestation(self, policy):
        att = policy.attestations.filter(status=Attestation.Status.VALID).first()
        return AttestationSerializer(att).data if att else None


class AssetListView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        # Véhicules seulement : les voyages ont leur propre parcours (/api/trips).
        return Response(AssetSerializer(request.user.assets.filter(kind=InsuredAsset.Kind.VEHICLE), many=True).data)

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

    def get_throttles(self):
        # Seule la lecture (payante) est limitée ; la question « disponible ? » est gratuite.
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request):
        """L'app n'affiche le bouton que si la lecture est configurée (clé API présente)."""
        return Response({"available": registration_scan.is_available()})

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
        asset = get_object_or_404(InsuredAsset, pk=asset_id, owner=request.user, kind=InsuredAsset.Kind.VEHICLE)
        months = services.parse_duration(request.data.get("months"))
        quotes = services.compute_quotes(request.user, asset, months=months)
        return Response(QuoteSerializer(quotes, many=True).data, status=status.HTTP_201_CREATED)


class PolicyListView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        qs = request.user.policies.select_related("product__insurer", "asset__trip").prefetch_related(
            "attestations", "asset__trip__travelers__attestations")
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
    number = serializers.CharField(read_only=True)
    photos = serializers.SerializerMethodField()
    traveler = serializers.CharField(source="traveler.full_name", default=None, read_only=True)

    class Meta:
        model = Claim
        fields = ["id", "number", "kind", "occurred_on", "place", "description", "third_party_plate", "injuries",
                  "status", "closing_note", "photos", "traveler", "created_at", "updated_at"]

    def get_photos(self, claim):
        return len(claim.photos.all())  # nombre seulement : les fichiers restent privés


def claim_error(exc: DjangoValidationError) -> Response:
    return Response({"detail": exc.messages[0], "code": exc.error_list[0].code or "invalid"}, status=400)


def truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


class ClaimView(APIView):
    """Sinistres d'un contrat du client : liste et déclaration (multipart, champ « photos » répété)."""

    permission_classes = [IsCustomer]

    def get(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        return Response(ClaimSerializer(policy.claims.prefetch_related("photos"), many=True).data)

    def post(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        data = {key: request.data.get(key)
                for key in ("kind", "occurred_on", "place", "description", "third_party_plate", "traveler")}
        data["injuries"] = truthy(request.data.get("injuries"))
        try:
            claim = services.declare_claim(request.user, policy, data, request.FILES.getlist("photos"))
        except DjangoValidationError as exc:
            return claim_error(exc)
        return Response(ClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


# --- Voyage ------------------------------------------------------------------------
# Parcours : voyage (destinations, dates) → voyageurs → devis → contrat (POST /api/policies) →
# paiement. Mêmes vues pour l'espace entreprise, avec `company` (companies/api.py).


def trip_error(exc: DjangoValidationError) -> Response:
    """Erreur métier avec son code, traduit par l'app (français / arabe)."""
    return Response({"detail": exc.messages[0], "code": exc.error_list[0].code or "invalid"}, status=400)


class TripViews:
    """Logique commune particulier / entreprise : `company_for(request)` donne l'entreprise ou None."""

    @staticmethod
    def company_for(request):
        return None

    def trip(self, request, trip_id):
        try:
            return travel.trip_for(request.user, trip_id, company=self.company_for(request))
        except Trip.DoesNotExist:
            raise Http404 from None


class TripListView(TripViews, APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        try:
            trip = travel.create_trip(request.user, request.data.get("destinations"), request.data.get("departure_on"),
                                      request.data.get("return_on"), company=self.company_for(request))
        except DjangoValidationError as exc:
            return trip_error(exc)
        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)


class TripDetailView(TripViews, APIView):
    permission_classes = [IsCustomer]

    def get(self, request, trip_id):
        return Response(TripSerializer(self.trip(request, trip_id)).data)


class TravelerCheckView(APIView):
    """Nom officiel d'un voyageur d'après son NNI (eID), avant de l'ajouter. Limité par compte."""

    permission_classes = [IsCustomer]
    throttle_scope = "traveler_check"

    def post(self, request):
        try:
            result = travel.check_traveler(request.user, request.data.get("nni"))
        except DjangoValidationError as exc:
            return trip_error(exc)
        return Response({k: result[k] for k in ("status", "full_name", "full_name_ar")})


class TravelerListView(TripViews, APIView):
    permission_classes = [IsCustomer]
    throttle_scope = "traveler_check"

    def post(self, request, trip_id):
        trip = self.trip(request, trip_id)
        d = request.data
        try:
            travel.add_traveler(request.user, trip, nni=d.get("nni"), passport_number=d.get("passport_number"),
                                birth_date=d.get("birth_date"), full_name=d.get("full_name", ""),
                                company=self.company_for(request))
        except DjangoValidationError as exc:
            return trip_error(exc)
        return Response(TripSerializer(self.trip(request, trip_id)).data, status=status.HTTP_201_CREATED)


class TravelerDetailView(TripViews, APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, trip_id, traveler_id):
        trip = self.trip(request, trip_id)
        try:
            travel.remove_traveler(request.user, trip, traveler_id)
        except Traveler.DoesNotExist:
            raise Http404 from None
        except DjangoValidationError as exc:
            return trip_error(exc)
        return Response(TripSerializer(self.trip(request, trip_id)).data)


class TripQuoteView(TripViews, APIView):
    permission_classes = [IsCustomer]

    def post(self, request, trip_id):
        trip = self.trip(request, trip_id)
        try:
            quotes = travel.build_travel_quotes(request.user, trip)
        except DjangoValidationError as exc:
            return trip_error(exc)
        return Response(QuoteSerializer(quotes, many=True).data, status=status.HTTP_201_CREATED)


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
        qs = services.insurer_policies(request.user, statuses, services.parse_branch(request.query_params.get("branch")))
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
    plate = serializers.CharField(source="policy.asset.reference")  # voyage : codes des pays
    product = serializers.CharField(source="policy.product.name")
    branch = serializers.CharField(source="policy.product.branch")
    premium = serializers.IntegerField(source="policy.premium")

    class Meta:
        model = Commission
        fields = ["id", "policy_id", "plate", "product", "branch", "premium", "rate", "amount", "period", "is_paid",
                  "created_at"]


class InsurerCommissionView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def get(self, request):
        data = services.insurer_commissions(request.user, services.parse_branch(request.query_params.get("branch")))
        return Response({
            "indicative": data["indicative"],
            "months": data["months"],
            "items": CommissionSerializer(data["items"], many=True).data,
        })


class InsurerClaimSerializer(ClaimSerializer):
    policy = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    photo_ids = serializers.SerializerMethodField()
    handled_by = serializers.CharField(source="handled_by.full_name", default=None, read_only=True)

    class Meta(ClaimSerializer.Meta):
        fields = ClaimSerializer.Meta.fields + ["policy", "customer", "photo_ids", "handled_by"]

    def get_policy(self, claim):
        policy = claim.policy
        return {"id": policy.pk, "plate": policy.asset.reference, "product": policy.product.name,
                "branch": policy.product.branch, "make": policy.asset.attributes.get("make", ""),
                "starts_on": policy.starts_on, "ends_on": policy.ends_on, "insurer_reference": policy.insurer_reference}

    def get_customer(self, claim):
        # Le contact du dossier est le déclarant ; pour une flotte, on indique aussi l'entreprise titulaire.
        person = claim.declared_by or claim.policy.customer
        company = claim.policy.company
        return {"full_name": person.full_name, "phone": person.phone,
                "company": company.legal_name if company else None}

    def get_photo_ids(self, claim):
        return [photo.pk for photo in claim.photos.all()]


class InsurerClaimListView(APIView):
    permission_classes = [IsInsurerAgent]

    @django_errors
    def get(self, request):
        statuses = services.parse_claim_statuses(request.query_params.get("status"))
        return Response(InsurerClaimSerializer(services.insurer_claims(request.user, statuses), many=True).data)


class InsurerClaimActionView(APIView):
    """Prise en charge (« take ») ou clôture avec note (« close ») d'un sinistre de la compagnie."""

    permission_classes = [IsInsurerAgent]

    @django_errors
    def post(self, request, claim_id, action):
        if action not in ("take", "close"):
            return Response({"detail": "Action inconnue."}, status=404)
        try:
            claim = services.insurer_claim(request.user, claim_id)
        except Claim.DoesNotExist:
            raise Http404 from None
        if action == "take":
            services.take_claim(claim, request.user)
        else:
            services.close_claim(claim, request.user, str(request.data.get("note") or ""))
        return Response(InsurerClaimSerializer(services.insurer_claim(request.user, claim_id)).data)


class InsurerClaimPhotoView(APIView):
    """Photo d'un sinistre de la compagnie de l'agent (fichier privé) ; consultation journalisée."""

    permission_classes = [IsInsurerAgent]

    def get(self, request, claim_id, photo_id):
        try:
            claim = services.insurer_claim(request.user, claim_id)
        except Claim.DoesNotExist:
            raise Http404 from None
        photo = get_object_or_404(claim.photos, pk=photo_id)
        response = private_file_response(photo.file)
        record("claim.photo_viewed", claim, actor=request.user, photo_id=photo.pk)
        return response
