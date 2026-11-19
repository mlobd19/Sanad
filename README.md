# Sanad — plateforme d'assurance digitale (Mauritanie)

**Sanad** (سند, « appui, soutien »). Ce dépôt contient le MVP : le parcours
**assurance auto** de bout en bout, de la connexion par SMS à l'attestation
signée vérifiable par QR code.

- `backend/` : API Django, back-office, paiements, attestations.
- `frontend/` : application client Next.js (mobile d'abord, français et arabe).

## Démarrer en local (sans Docker)

```bash
cd backend
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo          # 4 compagnies auto (tarifs fictifs) + un agent démo chacune
python manage.py createsuperuser    # numéro +222XXXXXXXX
python manage.py runserver
```

- Back-office : http://localhost:8000/admin/
- Les codes SMS s'affichent dans la console (backend de notification `Console`).
- Tests : `cd backend && pytest`

## Lancer l'application client

Le backend doit tourner sur le port 8000 (voir ci-dessus).

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

L'app appelle `/api/...` sur son propre domaine ; Next.js relaie vers le
backend (`BACKEND_URL`, par défaut `http://localhost:8000`). Pour que les QR
codes pointent vers l'app, lancez le backend avec
`ATTESTATION_VERIFY_BASE_URL=http://localhost:3000/v/`.

En développement, l'écran de paiement propose « Simuler la confirmation » :
le backend joue le rôle de l'opérateur. Ce bouton n'existe pas en production.

Pour valider une police comme le ferait l'assureur : back-office Django,
action « Valider les polices payées », ou API du portail assureur avec le
compte de démo de la compagnie.

## Catalogue auto de démonstration

`seed_demo` crée le catalogue auto de démonstration : quatre compagnies agréées
(liste du rapport du ministère des Finances sur l'exercice 2022) et un agent
démo par compagnie :

| Compagnie | Raison sociale | Formules | Agent démo |
| --- | --- | --- | --- |
| NASR | Nationale d'Assurance et de Réassurance | RC, Tiers étendu, Tous risques | `+22220000001` |
| MAR | Mauritanienne d'Assurance et de Réassurance | RC, Tiers étendu, Tous risques | `+22220000002` |
| MEDINA Assurances | MEDINA Assurances | RC, Tiers étendu | `+22220000003` |
| IMAN Assurance | IMAN Assurance | RC, Tiers étendu | `+22220000004` |

**Les primes sont fictives.** Chaque produit est marqué « indicatif » et l'app
l'affiche. La RC automobile, seule branche à tarif homologué, a le même prix
partout. Aucun partenariat n'est signé à ce stade : ne pas publier ces noms
hors d'un cadre de démonstration. Relancer `seed_demo` retire les compagnies
des catalogues précédents (ou les désactive si elles ont déjà des contrats).

### Logos des compagnies

Les logos sont des marques : n'utiliser que les fichiers **officiels fournis par
chaque compagnie**, avec son accord. Ils ne sont pas versionnés dans ce dépôt.

1. Déposer les fichiers dans `backend/logos/`, nommés d'après le code de la
   compagnie : `nasr.png`, `mar.png`, `medina.png`, `iman.png`
   (PNG, JPG ou WebP ; fond transparent ou blanc ; 256 px de large ou plus).
2. `python manage.py import_logos logos/`

Ou un par un dans le back-office : Catalog › Insurers › la compagnie › Logo.
Sans logo, l'application affiche le sigle de la compagnie.

## Démarrer avec Docker

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py seed_demo
```

App client : http://localhost:3000 · back-office : http://localhost:8000/admin/

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
- **PDF de l'attestation**, dépôt des pièces KYC et déclaration de sinistre dans l'app client.
- **Portail assureur** (écran web ; l'API existe déjà).
- **Mode hors ligne** de l'app (service worker).
- **Grilles tarifaires réelles** et accords de partenariat avec les compagnies
  (les primes de `seed_demo` sont fictives).
