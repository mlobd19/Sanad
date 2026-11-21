"""Plaques : une seule forme enregistrée (6602BA00), affichée « 66 02 BA 00 »."""
import pytest
from rest_framework.test import APIClient

from apps.policies.models import InsuredAsset, format_plate, normalize_plate

from .conftest import simulate_callback
from .test_company import add_vehicles, company_client, order_offer

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("raw, stored, shown", [
    ("6602BA00", "6602BA00", "66 02 BA 00"),
    ("6602 ba 00", "6602BA00", "66 02 BA 00"),
    (" 66-02-BA-00 ", "6602BA00", "66 02 BA 00"),
    ("CD 1234", "CD1234", "CD 1234"),  # autre format : affiché tel quel
])
def test_normalize_and_format(raw, stored, shown):
    assert normalize_plate(raw) == stored
    assert format_plate(stored if shown != "CD 1234" else raw) == shown


def test_customer_plate_is_stored_without_spaces(customer_client):
    resp = customer_client.post("/api/assets", {"kind": "vehicle", "reference": "6602 ba 00",
                                                "attributes": {"fiscal_power": 8, "usage": "personal"}}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["reference"] == "6602BA00"


def test_same_vehicle_typed_differently_cannot_be_covered_twice(customer_client, demo):
    """La flotte saisit « 7007GG00 », un particulier « 7007 gg 00 » : c'est le même véhicule."""
    company = company_client()
    _, order = order_offer(company, add_vehicles(company, "7007GG00"))
    pay = company.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json").data
    simulate_callback(APIClient(), pay["reference"], pay["amount"])

    asset = customer_client.post("/api/assets", {"reference": "7007 gg 00",
                                                 "attributes": {"fiscal_power": 8, "usage": "personal"}},
                                 format="json").data
    quote = customer_client.post(f"/api/assets/{asset['id']}/quotes").data[0]
    resp = customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json")
    assert resp.status_code == 400 and "déjà couvert" in str(resp.data)
