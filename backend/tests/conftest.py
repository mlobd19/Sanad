import json
import re

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Insurer
from apps.notifications.backends import MemoryBackend
from apps.attestations.signing import generate_seed_b64
from apps.payments.providers import SimulatedProvider

TEST_SIGNING_KEY = generate_seed_b64()


@pytest.fixture(autouse=True)
def _settings(settings, tmp_path):
    settings.NOTIFICATION_BACKEND = "apps.notifications.backends.MemoryBackend"
    settings.PAYMENT_PROVIDERS = ["simulated"]
    settings.MEDIA_ROOT = tmp_path
    settings.ATTESTATION_SIGNING_KEY = TEST_SIGNING_KEY
    settings.ANTHROPIC_API_KEY = ""  # jamais d'appel réel à l'API Claude pendant les tests
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    MemoryBackend.outbox.clear()


@pytest.fixture
def demo(db):
    call_command("seed_demo", verbosity=0)
    return {i.slug: i for i in Insurer.objects.all()}


@pytest.fixture
def auto_insurer(demo):
    """IMAN passe en validation automatique, comme un assureur intégré par API."""
    iman = demo["iman"]
    iman.auto_validate = True
    iman.save()
    return iman


@pytest.fixture
def outbox():
    return MemoryBackend.outbox


def login(client: APIClient, phone: str) -> dict:
    client.post("/api/auth/otp/request", {"phone": phone}, format="json")
    sms = [m for m in MemoryBackend.outbox if m["channel"] == "sms"][-1]
    code = re.search(r"\b(\d{6})\b", sms["body"]).group(1)
    resp = client.post("/api/auth/otp/verify", {"phone": phone, "code": code}, format="json")
    assert resp.status_code == 200, resp.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {resp.data['token']}")
    return resp.data


@pytest.fixture
def customer_client(demo):
    client = APIClient()
    login(client, "+22236000001")
    client.patch("/api/me", {"full_name": "Sidi Mohamed", "nni": "1234567890"}, format="json")
    return client


@pytest.fixture
def agent_client(demo):
    client = APIClient()
    agent = User.objects.get(phone="+22220000002")
    client.force_authenticate(agent)
    return client


def simulate_callback(client, reference, amount, status="success", tamper=False):
    body = json.dumps({"reference": reference, "status": status, "amount": amount}).encode()
    signature = SimulatedProvider.sign(body)
    if tamper:
        signature = "0" * len(signature)
    return client.generic(
        "POST", "/api/payments/callback/simulated", body, content_type="application/json", HTTP_X_SIGNATURE=signature
    )


def buy(client, plate="1234AB00", fiscal_power=8, usage="personal", product_code="tiers-etendu", insurer="mar"):
    """Parcours client jusqu'au paiement initié. Renvoie (police, paiement)."""
    asset = client.post(
        "/api/assets", {"reference": plate, "attributes": {"fiscal_power": fiscal_power, "usage": usage}},
        format="json",
    ).data
    quotes = client.post(f"/api/assets/{asset['id']}/quotes").data
    quote = next(q for q in quotes if q["product_code"] == product_code and q["insurer_slug"] == insurer)
    policy = client.post("/api/policies", {"quote_id": quote["id"]}, format="json")
    assert policy.status_code == 201, policy.data
    payment = client.post(f"/api/policies/{policy.data['id']}/pay", {"provider": "simulated"}, format="json")
    assert payment.status_code == 201, payment.data
    return policy.data, payment.data
