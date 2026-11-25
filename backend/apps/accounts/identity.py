"""Vérification de l'identité numérique (eID Houwiyeti) auprès de l'ANRPTS, avec le seul NNI.

Une interface, un adaptateur par source, comme pour les paiements. L'adaptateur
ANRPTS reste à écrire dès que l'agence fournit sa documentation (format de la
requête, authentification, champs renvoyés, cadre de la convention). Le
simulateur reproduit le même contrat pour développer et tester.

Contrat : on envoie le NNI ; la source répond
- « valide » : le NNI porte une identité numérique valide, avec le nom en
  caractères latins, le nom en arabe s'il est fourni et, s'il est fourni, le
  téléphone lié à l'eID ;
- « NNI introuvable » : le NNI n'existe pas dans la base de l'ANRPTS (erreur de
  saisie, le plus souvent) ;
- « pas d'eID valide » : le client doit créer son identité dans l'application
  Houwiyeti ;
- « injoignable » : source en panne, non configurée ou réponse inexploitable.
Aucune pièce d'identité n'est demandée au client.
"""
import logging
import re
import uuid
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

NNI_PATTERN = re.compile(r"^\d{10}$")


class EidStatus:
    VALID = "valid"            # identité numérique valide : nom(s) renvoyé(s)
    NOT_FOUND = "not_found"    # NNI introuvable dans la base de l'ANRPTS
    NO_EID = "no_eid"          # pas d'eID valide pour ce NNI
    UNAVAILABLE = "unavailable"  # source injoignable


@dataclass(frozen=True)
class EidResult:
    status: str
    full_name: str = ""     # nom en caractères latins
    full_name_ar: str = ""  # nom en arabe, s'il est fourni
    phone: str = ""         # téléphone lié à l'eID, s'il est fourni
    reference: str = ""     # référence de transaction côté ANRPTS, gardée pour l'audit
    provider: str = ""      # source interrogée (journal)


class EidProvider:
    name = ""
    label = ""

    def verify_eid(self, nni: str) -> EidResult:
        """Interroge la source. Peut lever n'importe quelle exception réseau : elle vaut « injoignable »."""
        raise NotImplementedError


class SimulatedEid(EidProvider):
    """Registre fictif pour le développement et la démo. Interdit en production hors DEMO_MODE.

    - 1234567890 : « Sidi Mohamed » / « سيدي محمد » ;
    - NNI commençant par 111 : introuvable à l'ANRPTS ;
    - NNI commençant par 000 : pas d'eID valide ;
    - NNI commençant par 999 : injoignable ;
    - tout autre NNI à 10 chiffres : valide, avec un nom fictif (toujours le même pour un NNI).
    Le simulateur ne renvoie pas de téléphone.
    """

    name = "simulated"
    label = "Registre simulé (développement)"

    KNOWN = {"1234567890": ("Sidi Mohamed", "سيدي محمد")}
    FICTIONAL = [
        ("Fatimetou Mint Ahmed", "فاطمة بنت أحمد"),
        ("Ahmed Salem Ould Sidi", "أحمد سالم ولد سيدي"),
        ("Aminetou Mint Cheikh", "أمينة بنت الشيخ"),
        ("Cheikh Ould Brahim", "الشيخ ولد ابراهيم"),
        ("Mariem Mint Mohamed", "مريم بنت محمد"),
        ("Brahim Ould Ely", "ابراهيم ولد اعلي"),
    ]

    def verify_eid(self, nni: str) -> EidResult:
        if nni.startswith("999"):
            raise ConnectionError("registre simulé injoignable")
        reference = f"SIM-EID-{uuid.uuid4().hex[:12].upper()}"
        if nni.startswith("111"):
            return EidResult(EidStatus.NOT_FOUND, reference=reference)
        if nni.startswith("000"):
            return EidResult(EidStatus.NO_EID, reference=reference)
        latin, arabic = self.KNOWN.get(nni) or self.FICTIONAL[int(nni) % len(self.FICTIONAL)]
        return EidResult(EidStatus.VALID, full_name=latin, full_name_ar=arabic, reference=reference)


REGISTRY: dict[str, type[EidProvider]] = {SimulatedEid.name: SimulatedEid}


def get_provider() -> EidProvider | None:
    """Source configurée (IDENTITY_PROVIDER), ou None si aucune (ou inconnue)."""
    cls = REGISTRY.get(settings.IDENTITY_PROVIDER or "")
    return cls() if cls else None


def verify_eid(nni: str) -> EidResult:
    """valide / NNI introuvable / pas d'eID valide / injoignable. Ne lève jamais : toute panne vaut « injoignable »."""
    provider = get_provider()
    if provider is None:
        return EidResult(EidStatus.UNAVAILABLE)
    try:
        result = provider.verify_eid(nni)
    except Exception as exc:  # réseau, délai, réponse illisible… (jamais le NNI dans le journal)
        logger.warning("Vérification eID injoignable (%s) : %s", provider.name, type(exc).__name__)
        return EidResult(EidStatus.UNAVAILABLE, provider=provider.name)
    if result.status == EidStatus.VALID and not result.full_name.strip():
        # Réponse « valide » sans nom : inexploitable, on ne vérifie rien.
        return EidResult(EidStatus.UNAVAILABLE, reference=result.reference, provider=provider.name)
    if result.status not in (EidStatus.VALID, EidStatus.NOT_FOUND, EidStatus.NO_EID):
        return EidResult(EidStatus.UNAVAILABLE, reference=result.reference, provider=provider.name)
    return EidResult(result.status, full_name=result.full_name.strip(), full_name_ar=result.full_name_ar.strip(),
                     phone=(result.phone or "").strip(), reference=result.reference, provider=provider.name)
