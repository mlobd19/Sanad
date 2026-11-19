# Taamine — plateforme d'assurance digitale (Mauritanie)

« Taamine » est un nom de travail. Ce dépôt contient le backend du MVP :
le parcours **assurance auto** de bout en bout, de la connexion par SMS à
l'attestation signée vérifiable par QR code.

## Démarrer en local (sans Docker)

```bash
cd backend
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo          # 3 assureurs FICTIFS + un agent assureur
python manage.py createsuperuser    # numéro +222XXXXXXXX
python manage.py runserver
```

- Back-office : http://localhost:8000/admin/
- Les codes SMS s'affichent dans la console (backend de notification `Console`).
- Tests : `cd backend && pytest`

## Démarrer avec Docker

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py seed_demo
```

## Organisation

Un monolithe Django modulaire. Chaque module garde ses tables et expose ses
services ; les vues API ne contiennent pas de logique métier.

| Module | Rôle |
| --- | --- |
| `accounts` | Compte par téléphone, OTP, pièces KYC, rôles (client, agent assureur, équipe) |
| `catalog` | Assureurs, produits, grilles tarifaires (facteurs multiplicatifs) |
| `policies` | Biens assurés, devis, polices et leur cycle de vie, sinistres, commissions |
| `payments` | Adaptateurs de paiement, callbacks signés et idempotents, remboursements |
| `attestations` | Numérotation, signature Ed25519, QR code, vérification publique, révocation |
| `notifications` | SMS / WhatsApp derrière une interface unique, modèles FR et AR |
| `audit` | Journal non modifiable de chaque action sensible |

## Cycle de vie d'une police

```
brouillon ──paiement confirmé──▶ payée ──validation assureur──▶ active ──▶ expirée
                                   │   (automatique si l'assureur est en API)
                                   └──refus──▶ refusée + remboursement
active ──résiliation──▶ résiliée (attestation révoquée)
```

## API

Authentification : `Authorization: Token <jeton>` obtenu après l'OTP.

| Méthode | Chemin | Usage |
| --- | --- | --- |
| POST | `/api/auth/otp/request` | `{phone}` → envoie un code par SMS |
| POST | `/api/auth/otp/verify` | `{phone, code}` → `{token, user}` |
| GET/PATCH | `/api/me` | Profil (nom, NNI, langue) |
| GET/POST | `/api/me/documents` | Pièces KYC (JPEG, PNG, PDF, 8 Mo max) |
| GET/POST | `/api/assets` | Véhicules : `{reference, attributes: {fiscal_power, usage, …}}` |
| POST | `/api/assets/{id}/quotes` | Devis de tous les assureurs actifs, triés par prix |
| GET/POST | `/api/policies` | Polices du client ; créer : `{quote_id, starts_on?}` |
| GET | `/api/payments/providers` | Moyens de paiement disponibles |
| POST | `/api/policies/{id}/pay` | `{provider, payer_phone}` → référence de paiement |
| POST | `/api/payments/callback/{provider}` | Callback opérateur (signature HMAC `X-Signature`) |
| POST | `/api/policies/{id}/claims` | Déclarer un sinistre |
| GET | `/api/attestations/{id}/qr.png` | QR code de l'attestation |
| GET | `/api/verify/{jeton}` | Vérification publique (données masquées) |
| GET | `/api/verify/public-key` | Clé publique pour la vérification hors ligne |
| GET | `/v/{jeton}` | Page web ouverte en scannant le QR |
| GET | `/api/insurer/policies?status=paid` | Portail assureur : demandes à valider |
| POST | `/api/insurer/policies/{id}/validate` ou `/refuse` | Décision de l'assureur |

## Ce qui reste à brancher

- **Paiements réels** : `BankilyProvider`, `MasrviProvider`, `SedadProvider` dans
  `apps/payments/providers.py` attendent l'API marchande de chaque opérateur.
  Le simulateur suit le même contrat ; il est refusé en production.
- **SMS et WhatsApp** : écrire un backend dans `apps/notifications/backends.py`
  (agrégateur SMS local, fournisseur WhatsApp Business).
- **Stockage des pièces** : stockage objet chiffré en production.
- **PDF de l'attestation** et **frontend** (PWA Next.js FR/AR).
- **Grilles tarifaires réelles** des assureurs partenaires (les données de
  `seed_demo` sont fictives).
