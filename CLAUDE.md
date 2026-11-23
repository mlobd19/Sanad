# Sanad — instructions pour Claude Code

Sanad (سند, « appui, soutien ») est une plateforme d'assurance digitale pour la
**Mauritanie** : un portail unique pour souscrire des assurances auprès de
plusieurs compagnies (modèle courtier digital). Le MVP couvre **l'assurance auto**
de bout en bout. Le porteur du projet est Mohamed Lemine OUBEID.

Langue de travail : **français** (code commenté en français, messages de commit
en français). Les utilisateurs finaux lisent **français et arabe**.

## Démarrer

```bash
# Backend (Python 3.13)
cd backend && source .venv/bin/activate
python manage.py migrate && python manage.py seed_demo
python manage.py runserver            # API sur :8000 (ne pas ouvrir directement)
python manage.py reset_demo           # remise à zéro de la démo (DEMO_MODE seulement)

# Application client
cd frontend && npm run dev            # http://localhost:3000 : app, /assureur, /entreprise, /admin
```

Dans VS Code : tâche **« Lancer Sanad »** (les deux serveurs).
Adresses : `/` (accueil visiteur ou espace client), `/connexion` (connexion
unique ; `?espace=pro` pour assureurs et entreprises), `/entreprise`,
`/assureur`, `/admin/` (équipe). Les codes SMS
s'affichent dans la console du backend (backend de notification `Console`).

## Vérifier avant de dire « fini »

```bash
cd backend && pytest                  # doit rester 100 % vert
cd frontend && npx next build         # doit compiler sans erreur TypeScript
```

Ajouter un test pour chaque règle métier nouvelle ou bug corrigé.

Back-office : tout nouveau texte en `_("…")` (français), sa traduction arabe dans
`backend/locale/ar/LC_MESSAGES/django.po`, puis `python manage.py
compile_translations` ; sinon le test des traductions échoue.

## Architecture

- `backend/` : Django 5.2 + DRF, **monolithe modulaire** (pas de microservices).
  Chaque app garde ses tables ; la logique métier vit dans `services.py`, jamais
  dans les vues (`api.py`).
  - `accounts` : utilisateurs, OTP, KYC, rôles `customer` / `insurer_agent` /
    `company_member` / `staff`. Particuliers : téléphone + code SMS ; le numéro
    n'est unique que parmi eux. Comptes pro (`User.PRO_ROLES`) : email + mot de
    passe + code SMS ; le SMS seul n'ouvre jamais qu'un compte particulier
    (ni compte pro, ni compte équipe).
    Codes SMS liés à un usage (`OtpCode.purpose`). Invitation / mot de passe
    oublié par email (lien 72 h). Back-office : téléphone + mot de passe
    (`backends.PhonePasswordBackend`, verrouillage après 5 échecs) puis
    application d'authentification (`accounts/totp.py`, `backoffice/site.py`,
    `BACKOFFICE_2FA`). Connexions à l'app : `accounts/tokens.py`.
    Identité : `identity.py` (registre national ANRPTS derrière une interface ;
    `simulated` en développement, interdit en production ; adaptateur réel à
    écrire avec la documentation de l'ANRPTS). Un désaccord ne refuse jamais
    automatiquement ; changer nom ou NNI d'une identité vérifiée la réinitialise
  - `companies` : entreprises (NIF, RC, statut de vérification), pièces,
    membres (administrateur / gestionnaire), flotte, devis groupés, commandes ;
    tout part de `services.member_company(user)`
  - `catalog` : compagnies, produits, facteurs tarifaires, logos ;
    commandes `seed_demo` et `import_logos`
  - `policies` : véhicules, devis, polices (cycle de vie dans `services.py`),
    sinistres, commissions, portail assureur (API `/api/insurer/*`, toujours
    filtrée sur la compagnie de l'agent via `services.insurer_*`)
  - `payments` : un adaptateur par opérateur (`providers.py`), callbacks signés
    HMAC et idempotents, remboursements ; un paiement porte une police OU une
    commande (`policies.Order`), remboursable ligne par ligne
  - `attestations` : numéro `SN-AAAA-NNNNNN`, signature Ed25519, QR, vérification
    publique `/v/<jeton>`, révocation, PDF bilingue (`pdf.py`, fpdf2 + HarfBuzz
    pour l'arabe ; mention « SPÉCIMEN » tant que `ATTESTATION_SPECIMEN` est vrai)
  - `notifications` : SMS (et e-mail) derrière une interface, modèles FR + AR.
    **Tous les messages aux clients partent par SMS**, jamais par WhatsApp
    (attestation, refus, sinistres, rappels de renouvellement).
  - `audit` : journal append-only (`record(...)` pour toute action sensible)
  - `backoffice` : site d'administration de Sanad (`site.py` : tableau de bord
    « À traiter », menu par métier), thème, gabarits, actions avec motif
    (`actions.reason_page`), pastilles (`ui.py`). Textes en `_()` (français) et
    traduction arabe dans `locale/ar/LC_MESSAGES/django.po`, compilée par
    `python manage.py compile_translations` (pas besoin de gettext)
- `frontend/` : Next.js 16 (App Router), TypeScript, CSS maison
  (`app/globals.css`, pas de Tailwind). Mobile d'abord, max 480 px.
  - Textes : **toujours** dans `lib/i18n.tsx`, en **français ET arabe**
    (l'arabe s'affiche en RTL). Jamais de texte en dur dans les écrans.
  - API : `lib/api.ts` ; `/api`, `/v` et `/media` sont relayés vers Django
    (`next.config.ts`).
  - **Porte d'entrée unique** : `lib/spaces.ts` (`homeFor(rôle)` : customer →
    `/`, company_member → `/entreprise`, insurer_agent → `/assureur`, staff →
    `/admin/` ; `useSpace(rôle)`, garde-fou de chaque espace ; `logout`). Ne
    jamais coder une redirection liée au rôle ailleurs. `/connexion` a deux
    onglets (Particulier : `OtpLogin` ; Professionnel : `ProAuth`) ; les
    anciennes `/assureur/connexion` et `/entreprise/connexion` redirigent.
  - Illustration du véhicule : `VehicleIllustration.tsx` (7 silhouettes originales,
    toujours gris métallisé, aucun logo de constructeur) ; type de carrosserie
    déduit de « marque et modèle » côté backend (`policies/body_types.py`,
    champ `body_type` de l'API), sans aucun champ de plus dans le formulaire.
  - Composants partagés : `components/Shell.tsx` (TopBar, Stepper, BottomNav…),
    `Logo.tsx` (logo khaïma), `InsurerLogo.tsx`, `OtpLogin.tsx`, `ProAuth.tsx`,
    `ClaimForm.tsx`.
  - Portail assureur : `/assureur` (web, bureau d'abord, styles `.portal*`),
    réservé au rôle `insurer_agent`.

## Configuration et production

- **DEBUG faux par défaut** : le `.env` local porte `DJANGO_DEBUG=1`. Hors DEBUG,
  `config/production.py` refuse de démarrer (clé secrète, PostgreSQL, SMS et
  e-mails réels, paiement opérationnel avec secret, clé de signature,
  application d'authentification du back-office…). Toute nouvelle variable indispensable y ajoute sa règle et
  son test (`tests/test_production_settings.py`).
- **DEMO_MODE** (distinct de DEBUG) : simulateurs, comptes démo, `reset_demo`.
  Ne lève aucune autre protection.
- Tests : `config/settings_test.py` (DEBUG, sans démo ni `.env` local).
- Codes SMS : 5 par numéro et par heure, tous parcours confondus
  (`OTP_MAX_SMS_PER_PHONE_PER_HOUR`, dans `accounts.services.send_code`) : la
  protection principale. Par adresse IP : 60 par heure (`OTP_THROTTLE_RATE`), car
  une adresse d'opérateur mobile est partagée. `NUM_PROXIES` = relais de
  confiance devant Django, **obligatoire et explicite en production** (Render : 1).
- **Surveillance** : Sentry si `SENTRY_DSN` (`config/monitoring.py`,
  `data_collection` : aucune donnée personnelle) ; alertes e-mail toutes les
  15 min au groupe « Équipe Sanad » (`backoffice/monitoring.py` : paiement en
  attente > 1 h, envois en échec) ; `GET /api/health` (base joignable) pour
  l'hébergeur. Un envoi qui échoue est enregistré (`NotificationFailure`, numéro
  masqué) et ne fait jamais échouer l'opération qui l'a demandé.
- Jamais de code SMS ni de lien de mot de passe dans les journaux hors DEBUG
  (`notifications/backends.redact`).
- **Connexions à l'app** (`accounts/tokens.py`, modèle `AuthToken`) : un jeton
  par appareil, seule son empreinte SHA-256 est enregistrée ; 30 jours pour un
  particulier, 8 h pour un compte pro (`AUTH_TOKEN_TTL_*`). Expiré ou révoqué →
  401 (l'app renvoie vers `/connexion`). `POST /api/auth/logout` (appelé par
  `logout()` de `lib/spaces.ts`), `POST /api/auth/logout-others` (Profil).
  Tout nouveau mot de passe (`User.set_password` puis `save`) ferme toutes les
  connexions du compte. Nettoyage : tâche Celery quotidienne et
  `manage.py purge_expired_tokens`. Ne jamais revenir au `Token` DRF.
- **Back-office** : second facteur par application d'authentification (TOTP,
  `accounts/totp.py`, un code ne sert qu'une fois, 5 essais) ; QR code au premier
  accès. `BACKOFFICE_2FA=totp` obligatoire en production ; `sms` ou `off`
  seulement en DEBUG. Téléphone perdu : `manage.py reset_totp <téléphone>`
  (audit « totp.reset »). Session : 8 h, fermée avec le navigateur.
- CI GitHub (`.github/workflows/ci.yml`) : pytest, build, pip-audit, npm audit.

## Règles métier à respecter

- Cycle de vie d'une police : `draft → paid → active → expired`,
  `paid → refused` (remboursement automatique), `active → cancelled`
  (attestation révoquée). Toute transition passe par `policies/services.py`.
- **Deux usages de véhicule seulement**, particuliers comme flottes : `personal`
  (Personnel : trajets privés, famille) et `commercial` (Commercial : livraisons,
  marchandises, VTC…) — `policies.models.VehicleUsage`. Plus de « taxi » (refusé
  par l'API ; anciens véhicules et devis passés en commercial, montants inchangés).
- Un véhicule ne peut pas être couvert deux fois sur la même période : vérifié au
  devis **et revérifié à la confirmation du paiement** (sinon paid → refused,
  remboursement automatique).
- Immatriculation : enregistrée sous une seule forme (`normalize_plate` : majuscules,
  sans espaces, ex. `6602BA00`), sinon la règle précédente ne reconnaît pas le
  véhicule ; affichée par groupes « 66 02 BA 00 » (`formatPlate` dans
  `lib/format.ts`, `format_plate` pour le PDF et la vérification publique).
- Sinistre : déclaré par le client (ou, pour un véhicule de flotte, par tout
  membre de l'entreprise, qui reçoit les messages) sur un contrat actif ou échu, date dans la
  période couverte ; `submitted → in_review → closed` (note de clôture
  obligatoire, envoyée au client). Traité par l'assureur dans son portail,
  ou par l'équipe au back-office en renfort. Photos en stockage privé.
- Particulier : **identité vérifiée avant tout paiement** (registre national ou
  pièce validée au back-office) ; devis et police brouillon restent possibles.
- Espace entreprise : une entreprise ne voit jamais les données d'une autre ;
  pas de paiement tant qu'elle n'est pas vérifiée (NIF + RC) ; mobile money
  uniquement, plafond `PAYMENT_MAX_AMOUNT`.
- **RC automobile : tarif homologué par l'État**, donc identique chez tous les
  assureurs. La comparaison joue sur les formules étendues et le service.
- Paiements : ne jamais activer une police sans callback valide (signature,
  montant exact). Le fournisseur `simulated` est interdit en production.
- Aucune donnée de compte mobile money stockée ; seules les références.
- Pièces justificatives (identité, NIF / RC) : stockage privé (`PRIVATE_MEDIA_ROOT`,
  `accounts/storage.py`), type vérifié sur le contenu, jamais d'URL publique ;
  ouvertes seulement au back-office, chaque consultation journalisée.
- Vérification publique : données personnelles **masquées**.
- Attestation PDF : jamais de prime dessus ; mention « SPÉCIMEN » obligatoire
  tant qu'aucun partenariat n'est signé avec la compagnie.

## Données et marques

- Catalogue démo (`seed_demo`) : **NASR, MAR, MEDINA Assurances, IMAN Assurance**.
  Agents démo `agent@<code>.test` (`+22220000001` à `+22220000004`), mot de
  passe = `DEMO_PASSWORD`, posé **uniquement en DEMO_MODE** (jamais en dur dans
  le code). Compte équipe démo : groupe « Équipe Sanad », jamais superutilisateur. Registre d'identité
  simulé : NNI `1234567890` = « Sidi Mohamed », `000…` inconnu, `999…`
  injoignable, tout autre NNI à 10 chiffres correspond. **Les primes sont fictives** et
  marquées `is_indicative` (« Indicatif » dans l'app) : ne jamais les présenter
  comme de vrais tarifs.
- **Logos des compagnies** : uniquement les fichiers officiels fournis par les
  compagnies, déposés dans `backend/logos/` (hors dépôt git). Ne jamais
  télécharger, recréer ni dessiner un logo de compagnie.
- Aucun partenariat signé à ce stade : ne pas publier ces noms hors démo.

## Design

Maquettes de référence (V2, contraste renforcé) : toile « Sanad – Maquettes »
dans Claude. Palette dans `globals.css` (`--green #08603F`,
`--green-deep #062F22`, `--sand #F0A43A`, `--ink #0B1A14`). Contraste élevé,
cibles tactiles ≥ 44 px, vrais `<button>` / `<a>`, libellés accessibles.

**Mode sombre** : suit le réglage de l'appareil ; bouton soleil / lune à côté du
bouton des langues sur chaque écran (bascule clair ↔ sombre), et choix « Automatique /
Clair / Sombre » dans le Profil (`components/ThemeChoice.tsx`, `lib/theme.ts`, posé sur
`<html data-theme>` avant l'affichage). Toutes les couleurs passent par les
variables de `globals.css`, jamais de couleur en dur dans un écran. Texte sur un
aplat : `--on-green`, `--on-ink`, `--on-red`, `--on-sand` (le vert devient clair
en sombre, son texte devient foncé). Exceptions voulues : blanc sur le vert
profond des en-têtes, fond blanc du QR code et des logos des compagnies.

## Git

- Branche `main`, dépôt `mlobd19/Sanad`.
- Auteur des commits : `Mohamed Lemine OUBEID <ml.oubeid@gmail.com>`.
- Ne jamais committer : `.env`, `db.sqlite3`, `backend/logos/*` (sauf
  `LISEZMOI.md`), `node_modules`, `.venv`, `.next`.

## Pas encore fait (feuille de route)

1. Espace entreprise, suite : **voyage**, puis **santé de groupe** (l'auto de la
   flotte est faite ; un plan par produit)
2. Adaptateur ANRPTS réel (dépôt de pièce en secours, déclaration de
   sinistre et sinistres de flotte faits)
3. Mise en ligne (Render : Django + PostgreSQL, Next.js ; code SMS du
   back-office fait)
4. Vraies intégrations : Bankily / Masrvi / Sedad (API marchandes),
   fournisseur SMS, envoi d'emails (SMTP)
5. Mode hors ligne (service worker)

### Espace entreprise : décisions du porteur (20/11/2026)

1. **Compte entreprise distinct** des comptes particuliers.
2. Pièces à l'ouverture : **NIF et Registre du Commerce**.
3. Paiement : **mobile money uniquement** (pas de virement sur facture).
4. Produits : **Auto, Santé et Voyage** (dans cet ordre : auto faite).
5. Un gérant peut utiliser le même numéro que son compte particulier.
6. Inscription libre en ligne ; pas de paiement avant vérification NIF + RC.
Connexion : email + mot de passe + code SMS (mécanisme des comptes pro).
