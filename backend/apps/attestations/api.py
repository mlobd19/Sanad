import base64

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import signing
from .models import Attestation
from .services import check, qr_png


class VerifyView(APIView):
    """Vérification publique : ce que voit l'agent de contrôle. Données personnelles masquées."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "verify"

    def get(self, request, token):
        return Response(check(token))


class PublicKeyView(APIView):
    """Clé publique pour la vérification hors ligne dans l'app de contrôle."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        vk = signing.public_key()
        return Response({"algorithm": "Ed25519", "key_id": signing.key_id(vk),
                         "public_key": base64.b64encode(bytes(vk)).decode()})


class QrCodeView(APIView):
    def get(self, request, attestation_id):
        att = get_object_or_404(Attestation, pk=attestation_id, policy__customer=request.user)
        return HttpResponse(qr_png(att), content_type="image/png")


def verify_page(request, token):
    """Page web ouverte en scannant le QR avec n'importe quel téléphone."""
    return render(request, "attestations/verify.html", {"result": check(token)})
