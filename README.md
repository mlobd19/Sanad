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

## Portail assureur

http://localhost:3000/assureur : l'espace web des agents des compagnies
(bureau d'abord, utilisable sur tablette, français et arabe).

**Connexion en deux facteurs** : email professionnel + mot de passe, puis code
reçu par SMS sur le téléphone du compte. Un agent ne peut **pas** se connecter
par SMS seul (l'app client refuse son numéro). En démo : `agent@mar.test`, mot de
passe `demo-sanad-2026` (posé par `seed_demo` **uniquement si DEBUG**), code SMS
dans la console du backend.

- 5 mots de passe faux bloquent le compte 15 minutes ; même message d'erreur
  que l'email existe ou non.
- Nouvel agent : l'équipe le crée dans le back-office (téléphone, email, rôle,
  compagnie), puis action « Envoyer l'invitation par email ». Le lien, valable
  72 h et à usage unique, sert à choisir le mot de passe. « Mot de passe
  oublié ? » envoie le même type de lien.
- En développement, les emails s'affichent dans la console du backend.

- **Demandes à valider** : polices payées de la compagnie de l'agent (client,
  véhicule, formule, prime, moyen de paiement, statut KYC). « Valider » active la
  police et émet l'attestation ; « Refuser » exige un motif et rembourse le client.
- **Polices émises** : actives, expirées et résiliées ; filtre « Refusées » pour
  retrouver les refus et leur motif.
- **Commissions** : relevé par mois et détail par police. Le taux (15 %) est
  provisoire : les montants sont marqués « Indicatif ».

Un agent ne voit et ne décide que sur les polices de **sa** compagnie.

> Démo : le jeton de session est commun à l'app client et au portail. Se connecter
> en agent remplace donc la session client dans le même navigateur (et
> inversement). Pour tester les deux à la fois, utilisez une fenêtre de
> navigation privée ou un autre navigateur.

On peut aussi valider une police depuis le back-office Django (action « Valider
les polices payées »).

## Catalogue auto de démonstration

`seed_demo` crée le catalogue auto de démonstration : quatre compagnies agréées
(liste du rapport du ministère des Finances sur l'exercice 2022) et un agent
démo par compagnie :

| Compagnie | Raison sociale | Formules | Agent démo |
| --- | --- | --- | --- |
| NASR | Nationale d'Assurance et de Réassurance | RC, Tiers étendu, Tous risques | `agent@nasr.test` · `+22220000001` |
| MAR | Mauritanienne d'Assurance et de Réassurance | RC, Tiers étendu, Tous risques | `agent@mar.test` · `+22220000002` |
| MEDINA Assurances | MEDINA Assurances | RC, Tiers étendu | `agent@medina.test` · `+22220000003` |
| IMAN Assurance | IMAN Assurance | RC, Tiers étendu | `agent@iman.test` · `+22220000004` |

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

## Attestation PDF

Le client la télécharge depuis l'écran de son contrat, l'agent depuis l'onglet
« Polices émises » du portail. Une page A4, français et arabe côte à côte, avec
le logo officiel de la compagnie (sigle sinon) et le QR code de vérification :
**seul le QR code fait foi**, le PDF n'est qu'une présentation.

Tant qu'aucun partenariat n'est signé, le PDF porte la mention et le filigrane
**« SPÉCIMEN · sans valeur d'assurance »** (`ATTESTATION_SPECIMEN=true` par
défaut ; ne le désactiver qu'avec un accord signé avec la compagnie).
Polices : Noto Sans et Noto Kufi Arabic (licence OFL), dans
`backend/apps/attestations/fonts/`.

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
| POST | `/api/auth/otp/verify` | `{phone, code}` → `{token, user}` (refusé aux comptes professionnels) |
| POST | `/api/auth/pro/login` | Comptes pro : `{email, password}` → `{challenge, phone}` + code SMS |
| POST | `/api/auth/pro/verify` | `{challenge, code}` → `{token, user}` |
| POST | `/api/auth/pro/password/forgot` | `{email}` → lien par email (réponse identique si l'email est inconnu) |
| POST | `/api/auth/pro/password/reset` | `{uid, token, password}` : choisir le mot de passe (invitation ou oubli) |
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
| GET | `/api/attestations/{id}/pdf` | Attestation PDF (A4, français et arabe) : client propriétaire ou agent de la compagnie ; 410 si révoquée |
| GET | `/api/verify/{jeton}` | Vérification publique (données masquées) |
| GET | `/api/verify/public-key` | Clé publique pour la vérification hors ligne |
| GET | `/v/{jeton}` | Page web ouverte en scannant le QR |
| GET | `/api/insurer/me` | Portail assureur : agent et compagnie (nom, logo) |
| GET | `/api/insurer/policies?status=paid` | Polices de la compagnie de l'agent ; plusieurs statuts possibles (`status=active,expired,cancelled`) |
| POST | `/api/insurer/policies/{id}/validate` ou `/refuse` | Décision de l'assureur (`{insurer_reference?}` ou `{reason}` obligatoire) |
| GET | `/api/insurer/commissions` | Commissions par mois et détail par police (`indicative` tant que le taux est provisoire) |

## Ce qui reste à brancher

- **Paiements réels** : `BankilyProvider`, `MasrviProvider`, `SedadProvider` dans
  `apps/payments/providers.py` attendent l'API marchande de chaque opérateur.
  Le simulateur suit le même contrat ; il est refusé en production.
- **SMS et WhatsApp** : écrire un backend dans `apps/notifications/backends.py`
  (agrégateur SMS local, fournisseur WhatsApp Business).
- **Stockage des pièces** : stockage objet chiffré en production.
- **Dépôt des pièces KYC** et **déclaration de sinistre** dans l'app client.
- **Mode hors ligne** de l'app (service worker).
- **Grilles tarifaires réelles** et accords de partenariat avec les compagnies
  (les primes de `seed_demo` sont fictives).
