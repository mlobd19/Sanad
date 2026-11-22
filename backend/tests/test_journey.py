import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import OtpCode, User, normalize_phone
from apps.attestations.models import Attestation
from apps.audit.models import AuditEvent
from apps.payments.models import Payment, Refund
from apps.policies.models import Commission, Policy

from .conftest import buy, login, simulate_callback

pytestmark = pytest.mark.django_db


# --- Compte -------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["36000001", "+222 36 00 00 01", "0022236000001", "22236000001"])
def test_phone_normalization(raw):
    assert normalize_phone(raw) == "+22236000001"


@pytest.mark.parametrize("raw", ["", "1234", "+33612345678", "+2223600000"])
def test_phone_rejected(raw):
    with pytest.raises(ValidationError):
        normalize_phone(raw)


def test_otp_login_creates_account(demo, outbox):
    data = login(APIClient(), "36000009")
    assert data["created"] is True
    assert data["user"]["phone"] == "+22236000009"
    assert "Ne le partagez" in outbox[0]["body"]
    assert OtpCode.objects.get().code_hash not in outbox[0]["body"]  # le code n'est jamais stocké en clair


def test_otp_wrong_code_then_lockout(demo, settings):
    client = APIClient()
    client.post("/api/auth/otp/request", {"phone": "36000010"}, format="json")
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        assert client.post("/api/auth/otp/verify", {"phone": "36000010", "code": "000000"}, format="json").status_code == 400
    resp = client.post("/api/auth/otp/verify", {"phone": "36000010", "code": "000000"}, format="json")
    assert "Trop de tentatives" in resp.data["detail"]


# --- Parcours complet ---------------------------------------------------------


def test_full_auto_journey(customer_client, agent_client, outbox, django_capture_on_commit_callbacks):
    quotes_asset = customer_client.post(
        "/api/assets", {"reference": "5678 ab 00", "attributes": {"fiscal_power": 8, "usage": "personal"}}, format="json"
    ).data
    assert quotes_asset["reference"] == "5678AB00"  # enregistrée sans espaces
    quotes = customer_client.post(f"/api/assets/{quotes_asset['id']}/quotes").data
    assert [q["premium"] for q in quotes] == sorted(q["premium"] for q in quotes)
    b = next(q for q in quotes if q["product_code"] == "tiers-etendu" and q["insurer_slug"] == "mar")
    assert b["premium"] == 22500  # 18 000 × 1,25 (puissance 7–10 CV)
    assert b["indicative"] is True and b["insurer_legal_name"] == "Mauritanienne d'Assurance et de Réassurance"
    rc_prices = {q["premium"] for q in quotes if q["product_code"] == "rc"}
    assert len(rc_prices) == 1  # RC à tarif homologué : identique chez tous les assureurs

    policy = customer_client.post("/api/policies", {"quote_id": b["id"]}, format="json").data
    assert policy["status"] == "draft"
    pay = customer_client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json").data

    assert simulate_callback(APIClient(), pay["reference"], 22500).data["outcome"] == "succeeded"
    assert Policy.objects.get(pk=policy["id"]).status == Policy.Status.PAID

    pending = agent_client.get("/api/insurer/policies?status=paid").data
    assert [p["id"] for p in pending] == [policy["id"]]
    assert pending[0]["payment_provider"] == "simulated"

    with django_capture_on_commit_callbacks(execute=True):
        resp = agent_client.post(
            f"/api/insurer/policies/{policy['id']}/validate", {"insurer_reference": "B-0001"}, format="json"
        )
    assert resp.status_code == 200 and resp.data["status"] == "active"

    mine = customer_client.get(f"/api/policies/{policy['id']}").data
    att = mine["attestation"]
    assert att["number"].startswith("SN-") and att["status"] == "valid"
    assert any(m["channel"] == "sms" and att["number"] in m["body"] for m in outbox)  # attestation par SMS

    assert Commission.objects.get(policy_id=policy["id"]).amount == 3375  # 15 % de 22 500

    token = att["verify_url"].rsplit("/", 1)[-1]
    check = APIClient().get(f"/api/verify/{token}").data
    assert check["status"] == "valid"
    assert check["plate"] == "56 78 AB 00"  # affichée par groupes
    assert check["holder"] == "S*** M***"  # nom masqué pour l'agent de contrôle

    page = APIClient().get(f"/v/{token}")
    html = page.content.decode()
    assert page.status_code == 200 and html.count("Attestation valide") == 1  # pas de mention répétée
    assert "/" not in check["valid_from"]  # API : format ISO conservé
    day, month, year = check["valid_from"][8:10], check["valid_from"][5:7], check["valid_from"][:4]
    assert f"{day}/{month}/{year}" in html  # page : « 21/11/2026 »

    qr = customer_client.get(f"/api/attestations/{att['id']}/qr.png")
    assert qr.status_code == 200 and qr.content[:8] == b"\x89PNG\r\n\x1a\n"

    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"policy.created", "payment.succeeded", "policy.activated", "attestation.issued"} <= actions


def test_auto_validating_insurer_activates_on_payment(customer_client, auto_insurer):
    policy, pay = buy(customer_client, insurer="iman")
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    assert Policy.objects.get(pk=policy["id"]).status == Policy.Status.ACTIVE
    assert Attestation.objects.filter(policy_id=policy["id"]).exists()


# --- Paiements ----------------------------------------------------------------


def test_callback_is_idempotent(customer_client):
    policy, pay = buy(customer_client)
    assert simulate_callback(APIClient(), pay["reference"], pay["amount"]).data["outcome"] == "succeeded"
    assert simulate_callback(APIClient(), pay["reference"], pay["amount"]).data["outcome"] == "already_processed"
    assert Payment.objects.filter(policy_id=policy["id"], status="succeeded").count() == 1


def test_callback_with_bad_signature_is_rejected(customer_client):
    policy, pay = buy(customer_client)
    assert simulate_callback(APIClient(), pay["reference"], pay["amount"], tamper=True).status_code == 400
    assert Policy.objects.get(pk=policy["id"]).status == Policy.Status.DRAFT


def test_callback_amount_mismatch_does_not_pay(customer_client):
    policy, pay = buy(customer_client)
    assert simulate_callback(APIClient(), pay["reference"], 1).data["outcome"] == "amount_mismatch"
    assert Policy.objects.get(pk=policy["id"]).status == Policy.Status.DRAFT


def test_second_confirmed_payment_is_refunded(customer_client):
    policy, first = buy(customer_client)
    stale = Payment.objects.get(external_ref=first["reference"])
    second = customer_client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json").data
    simulate_callback(APIClient(), second["reference"], second["amount"])
    # L'opérateur confirme aussi l'ancienne tentative : elle ne doit pas être encaissée deux fois.
    stale.status = Payment.Status.PENDING
    stale.save()
    assert simulate_callback(APIClient(), first["reference"], first["amount"]).data["outcome"] == "duplicate_refunded"
    assert Refund.objects.get(payment=stale).status == Refund.Status.DONE


# --- Décisions de l'assureur ----------------------------------------------------


def test_refusal_refunds_and_notifies(customer_client, agent_client, outbox, django_capture_on_commit_callbacks):
    policy, pay = buy(customer_client)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    assert agent_client.post(f"/api/insurer/policies/{policy['id']}/refuse", {"reason": ""}, format="json").status_code == 400
    with django_capture_on_commit_callbacks(execute=True):
        resp = agent_client.post(
            f"/api/insurer/policies/{policy['id']}/refuse", {"reason": "Véhicule hors catégorie"}, format="json"
        )
    assert resp.data["status"] == "refused"
    assert Payment.objects.get(external_ref=pay["reference"]).status == Payment.Status.REFUNDED
    assert any("remboursé" in m["body"] for m in outbox)


def test_agent_cannot_decide_for_another_insurer(customer_client, demo):
    policy, pay = buy(customer_client, product_code="rc", insurer="nasr")  # produit de NASR, agent de MAR
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    agent_b = APIClient()
    agent_b.force_authenticate(User.objects.get(phone="+22220000002"))
    assert agent_b.post(f"/api/insurer/policies/{policy['id']}/validate").status_code == 404
    assert agent_b.get("/api/insurer/policies").data == []


def test_customer_cannot_use_insurer_portal(customer_client):
    assert customer_client.get("/api/insurer/policies").status_code == 403


# --- Attestations ---------------------------------------------------------------


def test_cancellation_revokes_attestation(customer_client, agent_client):
    from apps.policies.services import cancel_policy

    policy, pay = buy(customer_client)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    agent_client.post(f"/api/insurer/policies/{policy['id']}/validate")
    att = Attestation.objects.get(policy_id=policy["id"])
    cancel_policy(Policy.objects.get(pk=policy["id"]), User.objects.get(phone="+22220000002"), "Fraude constatée")
    assert APIClient().get(f"/api/verify/{att.token}").data["status"] == "revoked"
    html = APIClient().get(f"/v/{att.token}").content.decode()
    assert html.count("Attestation révoquée") == 1 and "Attestation valide" not in html


def test_tampered_token_is_not_authentic(customer_client, agent_client):
    policy, pay = buy(customer_client)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    agent_client.post(f"/api/insurer/policies/{policy['id']}/validate")
    token = Attestation.objects.get(policy_id=policy["id"]).token
    body, sig = token.split(".")
    forged = body[:-2] + ("AA" if body[-2:] != "AA" else "BB") + "." + sig
    assert APIClient().get(f"/api/verify/{forged}").data["status"] == "invalid"
    assert APIClient().get(f"/v/{forged}").content.decode().count("Attestation non authentique") == 1


def test_offline_verification_with_public_key_only(customer_client, agent_client):
    import base64

    from nacl.signing import VerifyKey

    from apps.attestations import signing

    policy, pay = buy(customer_client)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    agent_client.post(f"/api/insurer/policies/{policy['id']}/validate")
    key = APIClient().get("/api/verify/public-key").data
    vk = VerifyKey(base64.b64decode(key["public_key"]))
    payload = signing.verify(Attestation.objects.get(policy_id=policy["id"]).token, vk)
    assert payload["p"] == "1234AB00" and payload["k"] == key["key_id"]


# --- Règles métier --------------------------------------------------------------


def test_same_vehicle_cannot_be_covered_twice(customer_client):
    policy, pay = buy(customer_client, plate="9999AB00")
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    asset = customer_client.post(
        "/api/assets", {"reference": "9999ab00", "attributes": {"fiscal_power": 5, "usage": "personal"}}, format="json"
    ).data
    quote = customer_client.post(f"/api/assets/{asset['id']}/quotes").data[0]
    resp = customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json")
    assert resp.status_code == 400 and "déjà couvert" in resp.data["detail"]


def test_quotes_require_vehicle_attributes(customer_client):
    asset = customer_client.post("/api/assets", {"reference": "1111AA00", "attributes": {}}, format="json").data
    resp = customer_client.post(f"/api/assets/{asset['id']}/quotes")
    assert resp.status_code == 400 and "fiscal_power" in resp.data["detail"]


def test_customer_cannot_see_others_policies(customer_client):
    policy, _ = buy(customer_client)
    other = APIClient()
    login(other, "+22236000077")
    assert other.get(f"/api/policies/{policy['id']}").status_code == 404
    assert other.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json").status_code == 404


def test_audit_events_are_immutable(customer_client):
    buy(customer_client)
    event = AuditEvent.objects.first()
    event.action = "edited"
    with pytest.raises(ValueError):
        event.save()
    with pytest.raises(ValueError):
        event.delete()


def test_payment_simulator_only_when_enabled(customer_client, settings):
    policy, pay = buy(customer_client)
    url = f"/api/payments/{pay['payment_id']}/simulate-confirm"
    settings.ENABLE_PAYMENT_SIMULATOR = False
    assert customer_client.post(url).status_code == 404
    settings.ENABLE_PAYMENT_SIMULATOR = True
    other = APIClient()
    login(other, "+22236000088")
    assert other.post(url).status_code == 404  # pas le paiement d'un autre client
    assert customer_client.post(url).data["outcome"] == "succeeded"
    assert Policy.objects.get(pk=policy["id"]).status == Policy.Status.PAID


def test_renewal_starts_after_current_cover(customer_client, auto_insurer):
    from datetime import timedelta

    policy, pay = buy(customer_client, insurer="iman")  # IMAN : activation automatique
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    current = Policy.objects.get(pk=policy["id"])
    current.ends_on = current.starts_on + timedelta(days=10)
    current.save()
    quote = customer_client.post(f"/api/assets/{current.asset_id}/quotes").data[0]
    resp = customer_client.post(
        "/api/policies",
        {"quote_id": quote["id"], "starts_on": str(current.ends_on + timedelta(days=1)), "renewal_of": current.pk},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert customer_client.get(f"/api/policies/{current.pk}").data["renewed"] is True


def test_seed_retires_old_demo_insurers(db):
    from django.core.management import call_command

    from apps.catalog.models import Insurer

    Insurer.objects.create(name="Assureur A (démo)", slug="assureur-a", commission_rate="0.1500")
    Insurer.objects.create(name="DAMANE Assurances", slug="damane", commission_rate="0.1500")
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)  # relançable sans doublon
    assert sorted(Insurer.objects.filter(is_active=True).values_list("slug", flat=True)) == [
        "iman", "mar", "medina", "nasr"
    ]
    assert not Insurer.objects.filter(slug__in=["assureur-a", "damane"]).exists()


def test_import_logos_and_expose_in_api(customer_client, tmp_path):
    from django.core.management import call_command
    from PIL import Image

    folder = tmp_path / "logos"
    folder.mkdir()
    Image.new("RGB", (64, 32), "white").save(folder / "nasr.png")
    (folder / "inconnu.png").write_bytes((folder / "nasr.png").read_bytes())
    (folder / "mar.png").write_bytes(b"pas une image")
    (folder / "iman.svg").write_text("<svg/>")  # SVG ignoré
    call_command("import_logos", str(folder), verbosity=0)

    asset = customer_client.post(
        "/api/assets", {"reference": "4321AB00", "attributes": {"fiscal_power": 5, "usage": "personal"}}, format="json"
    ).data
    quotes = customer_client.post(f"/api/assets/{asset['id']}/quotes").data
    logos = {q["insurer_slug"]: q["insurer_logo"] for q in quotes}
    assert logos["nasr"] == "/media/insurers/nasr.png"
    assert logos["mar"] is None and logos["iman"] is None
