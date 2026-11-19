"""Signature Ed25519 des attestations.

Format du jeton porté par le QR code :
    base64url(JSON canonique du contenu) "." base64url(signature)

La vérification hors ligne n'a besoin que de la clé publique : une app de
contrôle peut la garder en cache et vérifier sans réseau.
"""
import base64
import hashlib
import json
import logging

from django.conf import settings
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

logger = logging.getLogger("attestations")


class InvalidToken(Exception):
    pass


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def get_signing_key() -> SigningKey:
    seed_b64 = settings.ATTESTATION_SIGNING_KEY
    if seed_b64:
        seed = base64.b64decode(seed_b64)
        if len(seed) != 32:
            raise ValueError("ATTESTATION_SIGNING_KEY doit encoder exactement 32 octets.")
        return SigningKey(seed)
    if not settings.DEBUG:
        raise RuntimeError("ATTESTATION_SIGNING_KEY manquante.")
    logger.warning("Clé de signature de développement dérivée de SECRET_KEY : ne pas utiliser en production.")
    return SigningKey(hashlib.sha256(b"attestation-dev:" + settings.SECRET_KEY.encode()).digest())


def public_key() -> VerifyKey:
    return get_signing_key().verify_key


def key_id(vk: VerifyKey | None = None) -> str:
    vk = vk or public_key()
    return hashlib.sha256(bytes(vk)).hexdigest()[:8]


def sign(payload: dict) -> str:
    body = canonical(payload)
    signature = get_signing_key().sign(body).signature
    return f"{_b64e(body)}.{_b64e(signature)}"


def verify(token: str, vk: VerifyKey | None = None) -> dict:
    """Vérifie la signature et renvoie le contenu. N'interroge pas la base."""
    vk = vk or public_key()
    try:
        body_part, sig_part = token.split(".", 1)
        body, signature = _b64d(body_part), _b64d(sig_part)
        vk.verify(body, signature)
        return json.loads(body)
    except (ValueError, BadSignatureError, json.JSONDecodeError) as exc:
        raise InvalidToken("Attestation non authentique.") from exc


def generate_seed_b64() -> str:
    return base64.b64encode(bytes(SigningKey.generate())).decode()
