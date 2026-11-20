"""Vérification d'identité auprès du registre national (ANRPTS).

Une interface, un adaptateur par source, comme pour les paiements. L'adaptateur
ANRPTS reste à écrire dès que l'agence fournit sa documentation (format de la
requête, authentification, ce qui est renvoyé, cadre de la convention). Le
simulateur reproduit le même contrat pour développer et tester.

Contrat : on envoie le NNI et le nom déclarés par le client ; la source répond
par un verdict (correspond / ne correspond pas / NNI inconnu) et une référence
de transaction. Sanad ne reçoit ni ne stocke aucune donnée du registre.
"""
import re
import unicodedata
import uuid
from dataclasses import dataclass

from django.conf import settings

NNI_PATTERN = re.compile(r"^\d{10}$")


class Outcome:
    MATCH = "match"            # le NNI existe et le nom correspond
    MISMATCH = "mismatch"      # le NNI existe mais le nom ne correspond pas
    NOT_FOUND = "not_found"    # NNI inconnu du registre


@dataclass
class IdentityResult:
    outcome: str
    reference: str  # référence de transaction côté registre, gardée pour l'audit


class IdentityUnavailable(Exception):
    """Source injoignable ou non configurée : le client réessaie plus tard ou dépose une pièce."""


class IdentityProvider:
    name = ""
    label = ""

    def verify(self, nni: str, full_name: str) -> IdentityResult:
        raise NotImplementedError


def normalize_name(name: str) -> str:
    """Nom comparable : sans accents, casse, ponctuation ni espaces multiples."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


class SimulatedRegistry(IdentityProvider):
    """Registre fictif pour le développement. Interdit en production (voir settings).

    - NNI commençant par 000 : inconnu du registre ;
    - NNI commençant par 999 : registre injoignable ;
    - NNI de DEMO_REGISTRY : le nom déclaré doit correspondre ;
    - tout autre NNI à 10 chiffres : correspond, quel que soit le nom.
    """

    name = "simulated"
    label = "Registre simulé (développement)"

    DEMO_REGISTRY = {
        "1234567890": "Sidi Mohamed",
        "2345678901": "Fatimetou Mint Sidi",
        "3456789012": "Mohamed Lemine Ould Ahmed",
    }

    def verify(self, nni: str, full_name: str) -> IdentityResult:
        if nni.startswith("999"):
            raise IdentityUnavailable("registre simulé injoignable")
        reference = f"SIM-ID-{uuid.uuid4().hex[:12].upper()}"
        if nni.startswith("000"):
            return IdentityResult(Outcome.NOT_FOUND, reference)
        known = self.DEMO_REGISTRY.get(nni)
        if known is not None and normalize_name(known) != normalize_name(full_name):
            return IdentityResult(Outcome.MISMATCH, reference)
        return IdentityResult(Outcome.MATCH, reference)


REGISTRY: dict[str, type[IdentityProvider]] = {SimulatedRegistry.name: SimulatedRegistry}


def get_identity_provider() -> IdentityProvider | None:
    """Source configurée (IDENTITY_PROVIDER), ou None si la vérification automatique est désactivée."""
    name = settings.IDENTITY_PROVIDER
    if not name:
        return None
    if name not in REGISTRY:
        raise IdentityUnavailable(f"Source d'identité inconnue : {name}")
    return REGISTRY[name]()
