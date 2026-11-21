"""Sinistres des véhicules de flotte : déclarés par un membre de l'entreprise, traités par l'assureur."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies import services as company_services
from apps.notifications.backends import MemoryBackend
from apps.policies.models import Claim, Policy

from .conftest import simulate_callback
from .test_claims import jpeg
from .test_company import add_vehicles, agent, company_client, order_offer

pytestmark = pytest.mark.django_db


def claim_data(**overrides):
    return {"kind": "accident", "occurred_on": str(Policy.objects.first().starts_on), "place": "PK 7, route de Rosso",
            "description": "Pick-up percuté par un camion.", "injuries": "false", **overrides}


def active_fleet(client, *plates) -> list[Policy]:
    """Commande payée puis validée par l'agent MAR : contrats de flotte actifs."""
    _, order = order_offer(client, add_vehicles(client, *plates))
    pay = client.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json").data
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    for policy in Policy.objects.filter(order_id=order["id"]):
        assert agent().post(f"/api/insurer/policies/{policy.pk}/validate").status_code == 200
    return list(Policy.objects.filter(order_id=order["id"], status=Policy.Status.ACTIVE).order_by("pk"))


def manager_client(admin_email="admin@transmaur.test") -> tuple[APIClient, User]:
    admin = User.objects.get(email=admin_email)
    manager = company_services.invite_member(admin, full_name="Ahmed Ould Brahim", email="flotte@transmaur.test",
                                             phone="+22246000009")
    client = APIClient()
    client.force_authenticate(manager)
    return client, manager


def test_manager_declares_fleet_claim_and_insurer_handles_it(demo, django_capture_on_commit_callbacks):
    admin = company_client()
    policy = active_fleet(admin, "4004DD00")[0]
    manager, person = manager_client()

    MemoryBackend.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        resp = manager.post(f"/api/company/policies/{policy.pk}/claims", {**claim_data(), "photos": [jpeg()]},
                            format="multipart")
    assert resp.status_code == 201, resp.data
    assert resp.data["plate"] == "4004DD00" and resp.data["declared_by"] == "Ahmed Ould Brahim"
    assert resp.data["photos"] == 1
    claim = Claim.objects.get(pk=resp.data["id"])
    assert claim.declared_by == person
    # Le déclarant est prévenu, pas l'administrateur qui a souscrit.
    assert [m["to"] for m in MemoryBackend.outbox] == ["+22246000009"]

    # Toute l'entreprise voit le sinistre, y compris l'administrateur.
    listed = admin.get("/api/company/claims").data
    assert [c["number"] for c in listed] == [claim.number] and listed[0]["insurer"] == "MAR"

    # L'assureur voit le déclarant et l'entreprise titulaire, puis clôt.
    seen = agent().get("/api/insurer/claims").data[0]
    assert seen["customer"] == {"full_name": "Ahmed Ould Brahim", "phone": "+22246000009", "company": "TransMaur SARL"}
    MemoryBackend.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        agent().post(f"/api/insurer/claims/{claim.pk}/close", {"note": "Expertise le 12, garage agréé."}, format="json")
    assert [m["to"] for m in MemoryBackend.outbox] == ["+22246000009"]
    assert admin.get("/api/company/claims").data[0]["closing_note"] == "Expertise le 12, garage agréé."


def test_fleet_claim_follows_the_same_rules(demo):
    client = company_client()
    policy = active_fleet(client, "5005EE00")[0]
    resp = client.post(f"/api/company/policies/{policy.pk}/claims", claim_data(occurred_on="2001-01-01"),
                       format="multipart")
    assert resp.status_code == 400 and resp.data["code"] == "outside_cover"

    _, order = order_offer(client, add_vehicles(client, "6006FF00"))  # brouillon, non payé
    draft = Policy.objects.get(order_id=order["id"])
    resp = client.post(f"/api/company/policies/{draft.pk}/claims", claim_data(), format="multipart")
    assert resp.status_code == 400 and resp.data["code"] == "policy_inactive"


def test_fleet_claims_stay_inside_the_company(demo, customer_client):
    a = company_client()
    policy = active_fleet(a, "7117GG00")[0]
    assert a.post(f"/api/company/policies/{policy.pk}/claims", claim_data(), format="multipart").status_code == 201

    b = company_client(nif="00999999", email="admin@sahel.test", phone="+22246000050", legal_name="Sahel Logistique")
    assert b.get("/api/company/claims").data == []
    assert b.post(f"/api/company/policies/{policy.pk}/claims", claim_data(), format="multipart").status_code == 404
    # Ni le parcours particulier, ni un particulier ne passent par l'espace entreprise.
    assert a.post(f"/api/policies/{policy.pk}/claims", claim_data(), format="multipart").status_code == 403
    assert customer_client.post(f"/api/policies/{policy.pk}/claims", claim_data(), format="multipart").status_code == 404
    assert customer_client.get("/api/company/claims").status_code == 403
    assert Claim.objects.count() == 1


def test_member_of_another_company_is_refused_by_the_service(demo):
    from django.core.exceptions import PermissionDenied

    from apps.policies import services

    policy = active_fleet(company_client(), "8118HH00")[0]
    company_client(nif="00999999", email="admin@sahel.test", phone="+22246000050", legal_name="Sahel Logistique")
    other = User.objects.get(email="admin@sahel.test")
    with pytest.raises(PermissionDenied):
        services.declare_claim(other, policy, claim_data(), [])
    with pytest.raises(PermissionDenied):  # le souscripteur particulier n'existe pas pour une flotte
        services.declare_claim(User.objects.get(phone="+22220000002"), policy, claim_data(), [])
