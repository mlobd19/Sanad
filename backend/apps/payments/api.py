import json

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.policies.api import django_errors
from apps.policies.models import Policy

from .models import Payment
from .providers import InvalidCallback, SimulatedProvider, available_providers
from .services import handle_callback, initiate_payment


class ProviderListView(APIView):
    def get(self, request):
        return Response(available_providers())


class PayPolicyView(APIView):
    @django_errors
    def post(self, request, policy_id):
        policy = get_object_or_404(Policy, pk=policy_id, customer=request.user)
        payment, instructions = initiate_payment(
            request.user, policy, request.data.get("provider", ""), request.data.get("payer_phone", "")
        )
        return Response(
            {"payment_id": str(payment.id), "reference": payment.external_ref, "amount": payment.amount,
             "instructions": instructions},
            status=201,
        )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def callback(request, provider):
    """Appelé par l'opérateur. Authentifié par signature HMAC, pas par session."""
    try:
        outcome = handle_callback(provider, request.body, request.headers)
    except (KeyError, InvalidCallback):
        return Response({"detail": "Callback refusé."}, status=400)
    return Response({"outcome": outcome})


class SimulateConfirmView(APIView):
    """Développement : joue le rôle de l'opérateur et confirme un paiement simulé."""

    def post(self, request, payment_id):
        if not settings.ENABLE_PAYMENT_SIMULATOR:
            raise Http404
        payment = get_object_or_404(Payment, pk=payment_id, provider="simulated", policy__customer=request.user)
        body = json.dumps({"reference": payment.external_ref, "status": "success", "amount": payment.amount}).encode()
        outcome = handle_callback("simulated", body, {"X-Signature": SimulatedProvider.sign(body)})
        return Response({"outcome": outcome})
