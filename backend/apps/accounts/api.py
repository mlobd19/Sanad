from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import record

from .models import KycDocument, User
from .services import OtpError, request_otp, verify_otp

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "full_name", "nni", "language", "kyc_status", "role"]
        read_only_fields = ["id", "phone", "kyc_status", "role"]


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        try:
            request_otp(request.data.get("phone", ""))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=400)
        return Response({"detail": "Code envoyé par SMS."}, status=202)


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        try:
            user, created = verify_otp(request.data.get("phone", ""), request.data.get("code", ""))
        except (OtpError, DjangoValidationError) as exc:
            message = exc.messages[0] if isinstance(exc, DjangoValidationError) else str(exc)
            return Response({"detail": message}, status=400)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "created": created, "user": UserSerializer(user).data})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class KycDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycDocument
        fields = ["id", "kind", "file", "status", "uploaded_at"]
        read_only_fields = ["id", "status", "uploaded_at"]
        extra_kwargs = {"file": {"write_only": True}}

    def validate_file(self, f):
        if f.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("Fichier trop lourd (8 Mo maximum).")
        if getattr(f, "content_type", None) not in ALLOWED_TYPES:
            raise serializers.ValidationError("Formats acceptés : JPEG, PNG, PDF.")
        return f


class KycDocumentView(APIView):
    def get(self, request):
        return Response(KycDocumentSerializer(request.user.documents.all(), many=True).data)

    def post(self, request):
        serializer = KycDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = serializer.save(user=request.user)
        if request.user.kyc_status == User.KycStatus.NONE:
            request.user.kyc_status = User.KycStatus.PENDING
            request.user.save(update_fields=["kyc_status"])
        record("kyc.document_uploaded", doc, actor=request.user, kind=doc.kind)
        return Response(KycDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)
