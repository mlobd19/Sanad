"""Téléphones : affichés « +222 36 00 00 01 » ; numéro payeur vérifié et enregistré sous une seule forme."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import format_phone
from apps.payments.models import Payment

from .conftest import buy

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("raw, shown", [
    ("+22236000001", "+222 36 00 00 01"),
    ("22236000001", "+222 36 00 00 01"),
    ("+33612345678", "+33612345678"),  # autre pays : inchangé
    ("", ""),
])
def test_format_phone(raw, shown):
    assert format_phone(raw) == shown


def test_payer_phone_is_normalized(customer_client):
    policy, _ = buy(customer_client)
    resp = customer_client.post(f"/api/policies/{policy['id']}/pay",
                                {"provider": "simulated", "payer_phone": "+222 46 00 00 07"}, format="json")
    assert resp.status_code == 201, resp.data
    assert Payment.objects.get(pk=resp.data["payment_id"]).payer_phone == "+22246000007"


def test_invalid_payer_phone_is_refused(customer_client):
    policy, _ = buy(customer_client)
    resp = customer_client.post(f"/api/policies/{policy['id']}/pay",
                                {"provider": "simulated", "payer_phone": "+22222236000001"}, format="json")
    assert resp.status_code == 400  # « 222 » en double : refusé au lieu d'être enregistré tel quel


def test_payer_phone_is_optional(customer_client):
    policy, _ = buy(customer_client)
    resp = customer_client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json")
    assert resp.status_code == 201
