"""Type de carrosserie déduit de « marque et modèle » (illustration du véhicule, sans question de plus)."""
import pytest

from apps.policies.body_types import BODY_TYPES, body_type

from .test_company import add_vehicles, company_client

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("make, expected", [
    # Modèles courants en Mauritanie
    ("Toyota Hilux", "pickup"),
    ("Toyota Land Cruiser", "suv"),
    ("Toyota Prado", "suv"),
    ("Toyota Corolla", "sedan"),
    ("Toyota Yaris", "city"),
    ("Toyota Hiace", "minibus"),
    ("Peugeot Partner", "van"),
    # Casse et écriture
    ("hilux", "pickup"),
    ("HILUX", "pickup"),
    ("toyota hi-lux", "pickup"),
    ("Land cruiser", "suv"),
    ("LAND-CRUISER", "suv"),
    ("landcruiser v8", "suv"),
    ("  corolla  ", "sedan"),
    ("Hyundai Santa Fé", "suv"),
    ("Nissan X-Trail", "suv"),
    ("Isuzu D-Max", "pickup"),
    ("Toyota RAV 4", "suv"),
    ("Peugeot 206", "city"),
    ("Mercedes Classe C 200", "sedan"),
    # La carrosserie dite explicitement l'emporte sur le modèle
    ("Toyota Land Cruiser pick-up", "pickup"),
    ("Toyota Land Cruiser 79", "pickup"),
    ("Toyota Hilux Surf", "suv"),
    ("Renault fourgon", "van"),
    ("Mercedes Sprinter", "minibus"),
    # Inconnu, vide → générique ; pas de faux positif sur une partie de mot
    ("Voiture de mon oncle", "generic"),
    ("Mario", "generic"),        # contient « rio » sans être une Kia Rio
    ("", "generic"),
    ("   ", "generic"),
    (None, "generic"),
])
def test_make_to_body_type(make, expected):
    assert body_type(make) == expected


def test_every_type_is_known_to_the_illustration():
    assert set(BODY_TYPES) == {"sedan", "city", "suv", "pickup", "van", "minibus", "generic"}


def test_api_exposes_body_type(customer_client):
    resp = customer_client.post("/api/assets", {"reference": "6602BA00", "attributes": {
        "make": "toyota HILUX", "fiscal_power": 9, "usage": "commercial"}}, format="json")
    assert resp.status_code == 201 and resp.data["body_type"] == "pickup"
    assert customer_client.get("/api/assets").data[0]["body_type"] == "pickup"

    plain = customer_client.post("/api/assets", {"reference": "1234AB00", "attributes": {
        "fiscal_power": 6, "usage": "personal"}}, format="json")
    assert plain.data["body_type"] == "generic"  # aucune marque saisie


def test_fleet_exposes_body_type(demo):
    client = company_client()
    add_vehicles(client, "7007GG00")  # « Toyota Hilux » dans l'aide de test
    assert client.get("/api/company/fleet").data[0]["body_type"] == "pickup"


def test_policy_exposes_body_type_for_the_home_card(customer_client, demo):
    asset = customer_client.post("/api/assets", {"reference": "5005EE00", "attributes": {
        "make": "Toyota Corolla", "fiscal_power": 7, "usage": "personal"}}, format="json").data
    quote = customer_client.post(f"/api/assets/{asset['id']}/quotes").data[0]
    customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json")
    assert customer_client.get("/api/policies").data[0]["body_type"] == "sedan"
