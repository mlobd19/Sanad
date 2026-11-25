"""Vérification de l'identité numérique (eID Houwiyeti) auprès de l'ANRPTS, avec le seul NNI."""
import subprocess
import sys

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts import identity
from apps.accounts.api import IdentityCheckView
from apps.accounts.identity import EidProvider, EidResult, EidStatus, SimulatedEid, verify_eid
from apps.accounts.models import IdentityCheck, User
from apps.audit.models import AuditEvent

from .conftest import login


@pytest.fixture
def customer_client(customer_client):
    """Client démo (+22236000001) qui n'a encore ni NNI, ni nom, ni identité vérifiée."""
    User.objects.filter(phone="+22236000001", role=User.Role.CUSTOMER).update(
        nni="", full_name="", full_name_ar="", kyc_status=User.KycStatus.NONE)
    return customer_client


def set_nni(client, nni):
    resp = client.patch("/api/me", {"nni": nni}, format="json")
    assert resp.status_code == 200, resp.data
    return resp


def verify(client):
    return client.post("/api/me/identity")


def me(client):
    return User.objects.get(pk=client.get("/api/me").data["id"])


class PhoneLinkedEid(EidProvider):
    """Source de test qui renvoie le téléphone lié à l'eID (le simulateur n'en renvoie pas)."""

    name = "test-phone"
    phone = "+22299999999"

    def verify_eid(self, nni):
        return EidResult(EidStatus.VALID, full_name="Mariem Mint Ahmed", phone=self.phone, reference="T-1")


@pytest.fixture
def phone_linked(settings, monkeypatch):
    monkeypatch.setitem(identity.REGISTRY, PhoneLinkedEid.name, PhoneLinkedEid)
    settings.IDENTITY_PROVIDER = PhoneLinkedEid.name
    return PhoneLinkedEid


# --- Simulateur (DEBUG ou DEMO_MODE) -----------------------------------------------------------------

def test_valid_eid_verifies_and_takes_both_names_from_anrpts(customer_client):
    set_nni(customer_client, "1234567890")
    resp = verify(customer_client)
    assert resp.status_code == 200, resp.data
    assert resp.data["outcome"] == "verified"
    user = resp.data["user"]
    assert (user["kyc_status"], user["full_name"], user["full_name_ar"]) == ("verified", "Sidi Mohamed", "سيدي محمد")
    check = IdentityCheck.objects.get()
    assert (check.provider, check.nni, check.outcome) == ("simulated", "1234567890", "valid")
    assert check.reference.startswith("SIM-EID-")
    event = AuditEvent.objects.get(action="kyc.verified")
    assert event.data == {"method": "simulated", "reference": check.reference}


def test_no_valid_eid(customer_client):
    set_nni(customer_client, "0001234567")
    resp = verify(customer_client)
    assert resp.status_code == 200 and resp.data["outcome"] == "no_eid"  # « Créez votre identité… Houwiyeti »
    user = me(customer_client)
    assert user.kyc_status == User.KycStatus.NONE and user.full_name == ""
    assert IdentityCheck.objects.get().outcome == "no_eid"
    assert AuditEvent.objects.filter(action="kyc.eid_not_verified", data__outcome="no_eid").exists()


def test_anrpts_unreachable(customer_client):
    set_nni(customer_client, "9991234567")
    resp = verify(customer_client)
    assert resp.status_code == 503 and resp.data["code"] == "unavailable"
    assert resp.data["detail"] == "Service indisponible, réessayez dans quelques minutes."
    assert IdentityCheck.objects.get().outcome == "unavailable"
    assert me(customer_client).kyc_status == User.KycStatus.NONE


def test_any_other_nni_is_valid_with_a_fictional_name(customer_client):
    set_nni(customer_client, "4567890123")
    resp = verify(customer_client)
    assert resp.data["outcome"] == "verified"
    name, name_ar = resp.data["user"]["full_name"], resp.data["user"]["full_name_ar"]
    assert (name, name_ar) in SimulatedEid.FICTIONAL
    again = SimulatedEid().verify_eid("4567890123")
    assert (again.full_name, again.full_name_ar) == (name, name_ar)  # toujours le même nom pour un NNI


def test_simulator_sends_no_phone():
    assert SimulatedEid().verify_eid("1234567890").phone == ""


# --- Téléphone lié à l'eID ------------------------------------------------------------------------------

def test_phone_mismatch_verifies_nothing_and_answers_neutrally(customer_client, phone_linked):
    set_nni(customer_client, "4567890123")
    resp = verify(customer_client)
    assert resp.status_code == 200 and resp.data["outcome"] == "not_verified"
    assert set(resp.data) == {"outcome", "user"}  # rien ne dit pourquoi
    assert PhoneLinkedEid.phone not in str(resp.data) and "Mariem" not in str(resp.data)
    user = me(customer_client)
    assert user.kyc_status == User.KycStatus.NONE and user.full_name == ""  # aucun nom repris
    assert IdentityCheck.objects.get().outcome == "phone_mismatch"  # le détail reste au journal


def test_matching_phone_in_another_format_verifies(customer_client, phone_linked, monkeypatch):
    monkeypatch.setattr(PhoneLinkedEid, "phone", "36 00 00 01")  # téléphone du compte, autre écriture
    set_nni(customer_client, "4567890123")
    resp = verify(customer_client)
    assert resp.data["outcome"] == "verified"
    assert resp.data["user"]["full_name"] == "Mariem Mint Ahmed" and resp.data["user"]["full_name_ar"] == ""


# --- Réponses inexploitables : toujours « injoignable » ---------------------------------------------

def test_disabled_provider_is_unavailable(customer_client, settings):
    settings.IDENTITY_PROVIDER = ""
    set_nni(customer_client, "1234567890")
    resp = verify(customer_client)
    assert resp.status_code == 503 and resp.data["code"] == "unavailable"


@pytest.mark.parametrize("answer", [
    RuntimeError("réponse illisible"),
    EidResult(EidStatus.VALID, full_name="  "),  # « valide » sans nom
    EidResult("inattendu", full_name="X"),
])
def test_unusable_answers_count_as_unavailable(settings, monkeypatch, answer):
    class Broken(EidProvider):
        name = "broken"

        def verify_eid(self, nni):
            if isinstance(answer, Exception):
                raise answer
            return answer

    monkeypatch.setitem(identity.REGISTRY, "broken", Broken)
    settings.IDENTITY_PROVIDER = "broken"
    assert verify_eid("1234567890").status == EidStatus.UNAVAILABLE


# --- Profil : un seul champ, le NNI ---------------------------------------------------------------------

def test_name_cannot_be_typed_by_the_customer(customer_client):
    resp = customer_client.patch("/api/me", {"full_name": "Faux Nom", "full_name_ar": "اسم", "nni": "1234567890"},
                                 format="json")
    assert resp.status_code == 200
    assert resp.data["full_name"] == "" and resp.data["full_name_ar"] == "" and resp.data["nni"] == "1234567890"


@pytest.mark.parametrize("nni, code", [("", "missing_nni"), ("12345", "invalid_nni"), ("12345ABCDE", "invalid_nni")])
def test_nni_must_have_10_digits(customer_client, nni, code):
    set_nni(customer_client, nni)
    resp = verify(customer_client)
    assert resp.status_code == 400 and resp.data["code"] == code
    assert not IdentityCheck.objects.exists()


def test_verified_identity_is_not_checked_again(customer_client):
    set_nni(customer_client, "1234567890")
    verify(customer_client)
    resp = verify(customer_client)
    assert resp.status_code == 400 and resp.data["code"] == "already_verified"
    assert IdentityCheck.objects.count() == 1


def test_changing_nni_resets_verification(customer_client):
    set_nni(customer_client, "1234567890")
    verify(customer_client)
    customer_client.patch("/api/me", {"language": "ar"}, format="json")
    set_nni(customer_client, "1234567890")  # même NNI : rien ne change
    assert me(customer_client).kyc_status == User.KycStatus.VERIFIED

    resp = set_nni(customer_client, "4567890123")
    assert resp.data["kyc_status"] == "none"
    assert AuditEvent.objects.filter(action="kyc.reset").exists()
    assert verify(customer_client).data["outcome"] == "verified"  # nouveau nom, celui du nouveau NNI
    assert me(customer_client).full_name != "Sidi Mohamed"


def test_identity_documents_endpoint_is_gone(customer_client):
    assert customer_client.get("/api/me/documents").status_code == 404


# --- Accès et limite d'interrogations ------------------------------------------------------------------

def test_pro_accounts_cannot_use_it(agent_client):
    assert agent_client.post("/api/me/identity").status_code == 403


def test_requires_login(db):
    assert APIClient().post("/api/me/identity").status_code == 401


def test_checks_are_limited_per_account(demo):
    """5 interrogations par heure et par compte (IDENTITY_THROTTLE_RATE) ; un autre compte n'est pas bloqué."""
    cache.clear()
    view = IdentityCheckView.as_view(throttle_classes=[ScopedRateThrottle])  # les tests désactivent les limites
    first = User.objects.create_user("+22236000201", nni="0001234567")
    second = User.objects.create_user("+22236000202", nni="0001234567")

    def post(user):
        request = APIRequestFactory().post("/api/me/identity", REMOTE_ADDR="10.0.0.1")  # même adresse IP
        force_authenticate(request, user=user)
        return view(request).status_code

    assert [post(first) for _ in range(5)] == [200] * 5
    assert post(first) == 429
    assert post(second) == 200
    cache.clear()


def test_simulated_registry_is_forbidden_in_production():
    # Sans le .env local (DJANGO_ENV_FILE) ni DEMO_MODE : le registre simulé est refusé en production.
    env = {"DJANGO_DEBUG": "false", "IDENTITY_PROVIDER": "simulated", "PAYMENT_PROVIDERS": "bankily",
           "ATTESTATION_SIGNING_KEY": "x", "PATH": "", "DJANGO_ENV_FILE": "/nonexistent/.env"}
    proc = subprocess.run([sys.executable, "-c", "import config.settings"], env=env, capture_output=True, text=True)
    assert proc.returncode != 0 and "registre d'identité simulé est interdit" in proc.stderr


# --- Identité vérifiée avant paiement ------------------------------------------------------------------


def draft_policy(client):
    asset = client.post("/api/assets", {"reference": "4321AB00", "attributes": {"fiscal_power": 8, "usage": "personal"}},
                        format="json").data
    quote = client.post(f"/api/assets/{asset['id']}/quotes").data[0]
    return client.post("/api/policies", {"quote_id": quote["id"]}, format="json").data


def pay(client, policy):
    return client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json")


def test_payment_requires_verified_identity(customer_client):
    policy = draft_policy(customer_client)  # le devis et la police brouillon restent possibles
    assert policy["status"] == "draft"
    resp = pay(customer_client, policy)
    assert resp.status_code == 400 and resp.data["code"] == "kyc_required"

    set_nni(customer_client, "1234567890")
    assert verify(customer_client).data["outcome"] == "verified"
    assert pay(customer_client, policy).status_code == 201


def test_nni_change_blocks_payment_again(customer_client):
    set_nni(customer_client, "1234567890")
    verify(customer_client)
    policy = draft_policy(customer_client)
    set_nni(customer_client, "4567890123")
    assert pay(customer_client, policy).data["code"] == "kyc_required"


def test_new_customer_starts_unverified(demo):
    client = APIClient()
    data = login(client, "+22236000203")
    assert data["user"]["kyc_status"] == "none" and data["user"]["full_name_ar"] == ""


# --- Migration : plus aucune pièce d'identité ----------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_migration_deletes_identity_documents_and_converts_statuses(settings, tmp_path):
    from django.core.files.base import ContentFile
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    before, after = [("accounts", "0008_jetons_et_totp")], [("accounts", "0010_identite_numerique")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    OldUser, KycDocument, OldCheck = (old.get_model("accounts", m) for m in ("User", "KycDocument", "IdentityCheck"))
    pending = OldUser.objects.create(phone="+22236000301", kyc_status="pending")
    rejected = OldUser.objects.create(phone="+22236000302", kyc_status="rejected")
    verified = OldUser.objects.create(phone="+22236000303", kyc_status="verified")
    doc = KycDocument(user=pending, kind="id_card")
    doc.file.save("cni.jpg", ContentFile(b"piece"), save=True)
    stored = settings.PRIVATE_MEDIA_ROOT / doc.file.name
    assert stored.exists()
    OldCheck.objects.create(user=pending, provider="simulated", nni="1", full_name="X", outcome="match")
    OldCheck.objects.create(user=pending, provider="simulated", nni="1", full_name="X", outcome="not_found")

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(after)
    new = executor.loader.project_state(after).apps
    NewUser, NewCheck = new.get_model("accounts", "User"), new.get_model("accounts", "IdentityCheck")

    assert not stored.exists() and not stored.parent.exists()  # fichier et dossier kyc/<compte> effacés
    assert "accounts_kycdocument" not in connection.introspection.table_names()
    statuses = dict(NewUser.objects.values_list("pk", "kyc_status"))
    assert (statuses[pending.pk], statuses[rejected.pk], statuses[verified.pk]) == ("none", "none", "verified")
    assert sorted(NewCheck.objects.values_list("outcome", flat=True)) == ["no_eid", "valid"]

    MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
