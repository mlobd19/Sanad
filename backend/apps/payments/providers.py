"""Adaptateurs de paiement : une interface, un adaptateur par opérateur.

Les adaptateurs Bankily, Masrvi et Sedad restent à écrire dès que les
opérateurs ouvrent leur API marchande (documentation, clés, environnement
de test). Le simulateur reproduit le même contrat pour développer et tester.
"""
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass

from django.conf import settings


@dataclass
class InitiationResult:
    external_ref: str
    instructions: str


@dataclass
class CallbackData:
    external_ref: str
    succeeded: bool
    amount: int
    failure_reason: str = ""


class InvalidCallback(Exception):
    pass


class PaymentProvider:
    name = ""
    label = ""

    def initiate(self, payment) -> InitiationResult:
        raise NotImplementedError

    def parse_callback(self, body: bytes, headers) -> CallbackData:
        raise NotImplementedError

    def refund(self, payment, amount: int) -> str:
        raise NotImplementedError

    def _check_hmac(self, body: bytes, signature: str):
        secret = settings.PAYMENT_CALLBACK_SECRETS.get(self.name, "")
        if not secret:
            raise InvalidCallback("Secret de callback non configuré.")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise InvalidCallback("Signature invalide.")


class SimulatedProvider(PaymentProvider):
    """Simulateur local. Interdit en production (voir settings)."""

    name = "simulated"
    label = "Simulateur (développement)"

    def initiate(self, payment) -> InitiationResult:
        return InitiationResult(
            external_ref=f"SIM-{uuid.uuid4().hex[:12].upper()}",
            instructions="Paiement simulé : appelez le callback pour le confirmer.",
        )

    def parse_callback(self, body: bytes, headers) -> CallbackData:
        self._check_hmac(body, headers.get("X-Signature", ""))
        try:
            data = json.loads(body)
            return CallbackData(
                external_ref=str(data["reference"]),
                succeeded=data["status"] == "success",
                amount=int(data["amount"]),
                failure_reason=data.get("reason", ""),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidCallback(f"Corps de callback illisible : {exc}") from exc

    def refund(self, payment, amount: int) -> str:
        return f"SIMREF-{uuid.uuid4().hex[:10].upper()}"

    @staticmethod
    def sign(body: bytes) -> str:
        secret = settings.PAYMENT_CALLBACK_SECRETS["simulated"]
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class _PendingOperatorAPI(PaymentProvider):
    def initiate(self, payment):
        raise NotImplementedError(f"API marchande {self.label} non encore intégrée.")

    def parse_callback(self, body, headers):
        raise InvalidCallback(f"API marchande {self.label} non encore intégrée.")

    def refund(self, payment, amount):
        raise NotImplementedError(f"Remboursement {self.label} non encore intégré.")


class BankilyProvider(_PendingOperatorAPI):
    name, label = "bankily", "Bankily"


class MasrviProvider(_PendingOperatorAPI):
    name, label = "masrvi", "Masrvi"


class SedadProvider(_PendingOperatorAPI):
    name, label = "sedad", "Sedad"


REGISTRY = {p.name: p for p in (SimulatedProvider, BankilyProvider, MasrviProvider, SedadProvider)}


def get_provider(name: str) -> PaymentProvider:
    if name not in settings.PAYMENT_PROVIDERS or name not in REGISTRY:
        raise KeyError(f"Moyen de paiement indisponible : {name}")
    return REGISTRY[name]()


def available_providers():
    return [{"code": n, "label": REGISTRY[n].label} for n in settings.PAYMENT_PROVIDERS if n in REGISTRY]
