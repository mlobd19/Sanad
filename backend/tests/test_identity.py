"""Vérification d'identité au registre national (ANRPTS), en mode simulé."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.identity import SimulatedRegistry, normalize_name
from apps.accounts.models import IdentityCheck, User
from apps.audit.models import AuditEvent



@pytest.fixture
def customer_client(customer_client):
    """Client démo (Sidi Mohamed, 1234567890) dont l'identité n'est pas encore vérifiée."""
    User.objects.filter(phone="+22236000001", role=User.Role.CUSTOMER).update(kyc_status=User.KycStatus.NONE)
    return customer_client


def set_identity(client, full_name, nni):
    resp = client.patch("/api/me", {"full_name": full_name, "nni": nni}, format="json")
    assert resp.status_code == 200, resp.data
    return resp


def verify(client):
    return client.post("/api/me/identity")


def me(client):
    return User.objects.get(pk=client.get("/api/me").data["id"])


def test_matching_identity_is_verified(customer_client):
    """Le client démo (Sidi Mohamed, 1234567890) figure au registre simulé."""
    assert customer_client.get("/api/me/identity").data == {"available": True}
    resp = verify(customer_client)
    assert resp.status_code == 200, resp.data
    assert resp.data["outcome"] == "match" and resp.data["user"]["kyc_status"] == "verified"
    check = IdentityCheck.objects.get()
    assert (check.provider, check.nni, check.outcome) == ("simulated", "1234567890", "match")
    assert check.reference.startswith("SIM-ID-")
    event = AuditEvent.objects.get(action="kyc.verified")
    assert event.data == {"method": "simulated", "reference": check.reference}


def test_name_comparison_ignores_accents_case_and_punctuation():
    assert normalize_name("  SIDI-Mohamed ") == normalize_name("sidi mohamed")
    assert normalize_name("Fatimétou Mint Sidi") == normalize_name("fatimetou mint sidi")
    registry = SimulatedRegistry()
    assert registry.verify("2345678901", "FATIMÉTOU mint-Sidi").outcome == "match"


def test_mismatch_does_not_reject_the_customer(customer_client):
    set_identity(customer_client, "Ahmed Salem", "1234567890")
    resp = verify(customer_client)
    assert resp.status_code == 200 and resp.data["outcome"] == "mismatch"
    assert me(customer_client).kyc_status == User.KycStatus.NONE  # il peut corriger ou déposer une pièce
    assert AuditEvent.objects.filter(action="kyc.registry_no_match").exists()

    set_identity(customer_client, "Sidi Mohamed", "1234567890")
    assert verify(customer_client).data["outcome"] == "match"


def test_unknown_nni(customer_client):
    set_identity(customer_client, "Sidi Mohamed", "0001234567")
    resp = verify(customer_client)
    assert resp.data["outcome"] == "not_found"
    assert me(customer_client).kyc_status == User.KycStatus.NONE


def test_registry_down_is_logged_and_reported(customer_client):
    set_identity(customer_client, "Sidi Mohamed", "9991234567")
    resp = verify(customer_client)
    assert resp.status_code == 503 and resp.data["code"] == "unavailable"
    assert IdentityCheck.objects.get().outcome == "unavailable"
    assert me(customer_client).kyc_status == User.KycStatus.NONE


@pytest.mark.parametrize("full_name, nni, code", [
    ("", "1234567890", "missing_fields"),
    ("Sidi Mohamed", "", "missing_fields"),
    ("Sidi Mohamed", "12345", "invalid_nni"),
    ("Sidi Mohamed", "12345ABCDE", "invalid_nni"),
])
def test_profile_must_be_complete_before_checking(customer_client, full_name, nni, code):
    set_identity(customer_client, full_name, nni)
    resp = verify(customer_client)
    assert resp.status_code == 400 and resp.data["code"] == code
    assert not IdentityCheck.objects.exists()


def test_verified_identity_is_not_checked_again(customer_client):
    verify(customer_client)
    resp = verify(customer_client)
    assert resp.status_code == 400 and resp.data["code"] == "already_verified"
    assert IdentityCheck.objects.count() == 1


def test_changing_name_or_nni_after_verification_resets_it(customer_client):
    verify(customer_client)
    customer_client.patch("/api/me", {"language": "ar"}, format="json")
    assert me(customer_client).kyc_status == User.KycStatus.VERIFIED  # la langue ne change rien

    resp = set_identity(customer_client, "Sidi Mohamed", "1234567899")
    assert resp.data["kyc_status"] == "none"
    assert AuditEvent.objects.filter(action="kyc.reset").exists()


def test_rejected_customer_cannot_self_verify(customer_client):
    user = me(customer_client)
    user.kyc_status = User.KycStatus.REJECTED
    user.save()
    resp = verify(customer_client)
    assert resp.status_code == 400 and resp.data["code"] == "rejected"


def test_disabled_registry(customer_client, settings):
    settings.IDENTITY_PROVIDER = ""
    assert customer_client.get("/api/me/identity").data == {"available": False}
    resp = verify(customer_client)
    assert resp.status_code == 503 and resp.data["code"] == "unavailable"
    assert not IdentityCheck.objects.exists()


def test_pro_accounts_cannot_use_it(agent_client):
    assert agent_client.get("/api/me/identity").status_code == 403
    assert agent_client.post("/api/me/identity").status_code == 403


def test_requires_login(db):
    assert APIClient().post("/api/me/identity").status_code == 401


def test_registry_checks_are_throttled():
    from rest_framework.test import APIRequestFactory
    from rest_framework.throttling import ScopedRateThrottle

    from apps.accounts.api import IdentityCheckView

    factory = APIRequestFactory()
    for method, throttled in (("get", False), ("post", True)):
        view = IdentityCheckView()
        view.throttle_classes = [ScopedRateThrottle]  # les tests désactivent les limites par défaut
        view.request = getattr(factory, method)("/api/me/identity")
        assert any(isinstance(t, ScopedRateThrottle) for t in view.get_throttles()) is throttled


def test_simulated_registry_is_forbidden_in_production():
    import subprocess
    import sys
    code = "import config.settings"
    env = {"DJANGO_DEBUG": "false", "IDENTITY_PROVIDER": "simulated", "PAYMENT_PROVIDERS": "bankily",
           "ATTESTATION_SIGNING_KEY": "x", "PATH": ""}
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert proc.returncode != 0 and "registre d'identité simulé est interdit" in proc.stderr


# --- Identité vérifiée avant paiement ------------------------------------------


def draft_policy(client):
    asset = client.post("/api/assets", {"reference": "4321AB00", "attributes": {"fiscal_power": 8, "usage": "personal"}},
                        format="json").data
    quote = client.post(f"/api/assets/{asset['id']}/quotes").data[0]
    return client.post("/api/policies", {"quote_id": quote["id"]}, format="json").data


def pay(client, policy):
    return client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json")


@pytest.mark.parametrize("status", ["none", "pending"])
def test_payment_requires_verified_identity(customer_client, status):
    User.objects.filter(phone="+22236000001").update(kyc_status=status)
    policy = draft_policy(customer_client)  # le devis et la police brouillon restent possibles
    resp = pay(customer_client, policy)
    assert resp.status_code == 400 and resp.data["code"] == "kyc_required"
    assert customer_client.get(f"/api/policies/{policy['id']}").data["status"] == "draft"

    assert verify(customer_client).data["outcome"] == "match"
    assert pay(customer_client, policy).status_code == 201


def test_identity_reset_blocks_payment_again(customer_client):
    verify(customer_client)
    policy = draft_policy(customer_client)
    set_identity(customer_client, "Sidi Mohamed", "1234567899")
    assert pay(customer_client, policy).data["code"] == "kyc_required"
