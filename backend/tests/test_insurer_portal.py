"""Portail assureur : isolation entre compagnies, polices émises, commissions."""
from decimal import ROUND_HALF_UP, Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.payments.models import Payment
from apps.policies.models import Commission, Policy

from .conftest import buy, simulate_callback

pytestmark = pytest.mark.django_db

ISSUED = "/api/insurer/policies?status=active,expired,cancelled"


def agent(phone: str) -> APIClient:
    client = APIClient()
    client.force_authenticate(User.objects.get(phone=phone))
    return client


@pytest.fixture
def mar_agent(demo):
    return agent("+22220000002")


@pytest.fixture
def nasr_agent(demo):
    return agent("+22220000001")


def paid_policy(customer_client, insurer: str, plate: str, product_code="tiers-etendu") -> dict:
    policy, pay = buy(customer_client, plate=plate, insurer=insurer, product_code=product_code)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    return policy


def expected_commission(premium: int, rate: str = "0.15") -> int:
    return int((Decimal(premium) * Decimal(rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- Isolation entre compagnies ---------------------------------------------------


def test_agent_only_sees_own_insurers_pending_policies(customer_client, mar_agent, nasr_agent):
    mar = paid_policy(customer_client, "mar", "1111AA00")
    nasr = paid_policy(customer_client, "nasr", "2222AA00", product_code="rc")

    mar_ids = [p["id"] for p in mar_agent.get("/api/insurer/policies?status=paid").data]
    nasr_ids = [p["id"] for p in nasr_agent.get("/api/insurer/policies?status=paid").data]
    assert mar_ids == [mar["id"]]
    assert nasr_ids == [nasr["id"]]
    # Sans filtre non plus, rien ne fuit.
    assert {p["insurer"] for p in mar_agent.get("/api/insurer/policies").data} == {"MAR"}


@pytest.mark.parametrize(
    "decision, body",
    [("validate", {"insurer_reference": "X-1"}), ("refuse", {"reason": "Tentative d'un autre assureur"})],
)
def test_agent_cannot_decide_on_another_insurers_policy(customer_client, mar_agent, decision, body):
    nasr = paid_policy(customer_client, "nasr", "3333AA00", product_code="rc")

    resp = mar_agent.post(f"/api/insurer/policies/{nasr['id']}/{decision}", body, format="json")

    assert resp.status_code == 404  # la police n'existe pas pour cet agent
    policy = Policy.objects.get(pk=nasr["id"])
    assert policy.status == Policy.Status.PAID
    assert policy.decided_by is None and policy.refusal_reason == ""
    assert Payment.objects.get(policy=policy, status=Payment.Status.SUCCEEDED)  # aucun remboursement
    assert not Commission.objects.filter(policy=policy).exists()


def test_agent_does_not_see_other_insurers_issued_or_refused_policies(customer_client, mar_agent, nasr_agent):
    nasr_ok = paid_policy(customer_client, "nasr", "4444AA00", product_code="rc")
    nasr_ko = paid_policy(customer_client, "nasr", "5555AA00", product_code="rc")
    nasr_agent.post(f"/api/insurer/policies/{nasr_ok['id']}/validate")
    nasr_agent.post(f"/api/insurer/policies/{nasr_ko['id']}/refuse", {"reason": "Pièces illisibles"}, format="json")

    assert mar_agent.get(ISSUED).data == []
    assert mar_agent.get("/api/insurer/policies?status=refused").data == []
    assert mar_agent.get("/api/insurer/commissions").data["items"] == []


def test_insurer_portal_is_reserved_to_agents(customer_client):
    for path in ("/api/insurer/me", "/api/insurer/policies", "/api/insurer/commissions"):
        assert customer_client.get(path).status_code == 403, path
    assert APIClient().get("/api/insurer/me").status_code in (401, 403)


# --- Polices émises et refusées ---------------------------------------------------


def test_issued_and_refused_tabs(customer_client, mar_agent):
    ok = paid_policy(customer_client, "mar", "6666AA00")
    ko = paid_policy(customer_client, "mar", "7777AA00")
    pending = paid_policy(customer_client, "mar", "8888AA00")

    validated = mar_agent.post(f"/api/insurer/policies/{ok['id']}/validate", {"insurer_reference": "MAR-42"}, format="json")
    assert validated.status_code == 200
    assert validated.data["attestation"]["number"].startswith("SN-")
    assert mar_agent.post(f"/api/insurer/policies/{ko['id']}/refuse", {"reason": "  "}, format="json").status_code == 400
    mar_agent.post(f"/api/insurer/policies/{ko['id']}/refuse", {"reason": "Véhicule hors catégorie"}, format="json")

    issued = mar_agent.get(ISSUED).data
    assert [p["id"] for p in issued] == [ok["id"]]
    assert issued[0]["insurer_reference"] == "MAR-42"
    assert issued[0]["decided_at"]
    assert issued[0]["indicative"] is True

    refused = mar_agent.get("/api/insurer/policies?status=refused").data
    assert [(p["id"], p["refusal_reason"]) for p in refused] == [(ko["id"], "Véhicule hors catégorie")]

    still_pending = mar_agent.get("/api/insurer/policies?status=paid").data
    assert [p["id"] for p in still_pending] == [pending["id"]]
    row = still_pending[0]
    assert row["customer"]["full_name"] == "Sidi Mohamed"
    assert row["vehicle"]["fiscal_power"] == 8
    assert row["payment_provider"] == "simulated"
    assert row["kyc_status"] == "none"


def test_unknown_status_filter_is_rejected(mar_agent):
    assert mar_agent.get("/api/insurer/policies?status=active,nimporte").status_code == 400


# --- Commissions -------------------------------------------------------------------


def test_commissions_by_month_are_indicative(customer_client, mar_agent):
    first = paid_policy(customer_client, "mar", "9191AA00")
    second = paid_policy(customer_client, "mar", "9292AA00", product_code="rc")
    for p in (first, second):
        mar_agent.post(f"/api/insurer/policies/{p['id']}/validate")
    older = Commission.objects.get(policy_id=second["id"])
    older.period, older.is_paid = "2026-01", True
    older.save()

    data = mar_agent.get("/api/insurer/commissions").data

    assert data["indicative"] is True
    current = Commission.objects.get(policy_id=first["id"])
    assert current.amount == expected_commission(first["premium"])
    assert data["months"] == [
        {"period": current.period, "policies": 1, "premiums": first["premium"],
         "amount": current.amount, "paid": 0, "due": current.amount},
        {"period": "2026-01", "policies": 1, "premiums": second["premium"],
         "amount": older.amount, "paid": older.amount, "due": 0},
    ]
    assert [i["policy_id"] for i in data["items"]] == [first["id"], second["id"]]
    assert data["items"][0]["plate"] == "9191AA00"


def test_insurer_me_returns_agents_company(mar_agent):
    data = mar_agent.get("/api/insurer/me").data
    assert data["insurer"]["slug"] == "mar"
    assert data["insurer"]["legal_name"] == "Mauritanienne d'Assurance et de Réassurance"
    assert data["agent"]["phone"] == "+22220000002"
