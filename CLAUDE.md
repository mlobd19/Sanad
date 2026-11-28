# Sanad — instructions pour Claude Code

Sanad (سند, « appui, soutien ») est une plateforme d'assurance digitale pour la
**Mauritanie** : un portail unique pour souscrire des assurances auprès de
plusieurs compagnies (modèle courtier digital). Le MVP couvre **l'assurance auto**
et **l'assurance voyage** (formule unique « Monde entier ») de bout en bout, pour les
particuliers et les entreprises. Le porteur du projet est Mohamed Lemine OUBEID.

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
  - `accounts` : utilisateurs, OTP, identité numérique (eID), rôles `customer` / `insurer_agent` /
    `company_member` / `staff`. Particuliers : téléphone + code SMS ; le numéro
    n'est unique que parmi eux. Comptes pro (`User.PRO_ROLES`) : email + mot de
    passe + code SMS ; le SMS seul n'ouvre jamais qu'un compte particulier
    (ni compte pro, ni compte équipe).
    Codes SMS liés à un usage (`OtpCode.purpose`). Invitation / mot de passe
    oublié par email (lien 72 h). Back-office : téléphone + mot de passe
    (`backends.PhonePasswordBackend`, verrouillage après 5 échecs) puis
    application d'authentification (`accounts/totp.py`, `backoffice/site.py`,
    `BACKOFFICE_2FA`). Connexions à l'app : `accounts/tokens.py`.
    Identité : **identité numérique eID Houwiyeti vérifiée auprès de l'ANRPTS
    avec le seul NNI**, plus aucun dépôt de pièce d'identité. `identity.py` :
    `verify_eid(nni)` → valide (nom latin, nom arabe et téléphone lié s'ils sont
    fournis) / NNI introuvable / pas d'eID valide / injoignable (toute panne ou réponse
    inexploitable) ; `simulated` en DEBUG ou DEMO_MODE, interdit en production ;
    adaptateur réel à écrire avec la documentation de l'ANRPTS
    (`IDENTITY_PROVIDER` obligatoire en production). Le profil n'a qu'un champ, le
    NNI : le nom (`full_name`, `full_name_ar`) vient de l'ANRPTS, jamais de la
    saisie ; le nom arabe s'affiche en mode arabe et sur la partie arabe du PDF.
    Téléphone de l'eID ≠ téléphone du compte : rien n'est vérifié, message
    neutre (`not_verified`), détail au journal `IdentityCheck`. NNI figé une fois
    l'identité vérifiée (app : champ grisé ; API : `nni_locked` ; back-office : lecture seule). Limite : `IDENTITY_THROTTLE_RATE` par compte
  - `companies` : entreprises (NIF, RC, statut de vérification), pièces,
    membres (administrateur / gestionnaire), flotte, devis groupés, commandes ;
    tout part de `services.member_company(user)`
  - `catalog` : compagnies, produits (branche `auto` ou `travel`), facteurs tarifaires, logos ;
    voyage : plafonds en euros (`Product.limits`, frais médicaux ≥ 30 000 € validés par
    `Product.clean`), assistance 24 h/24 (`Insurer.assistance_phone`), facteurs `trip_days` et `age`
    (`Product.travel_premiums`) ; commandes `seed_demo` et `import_logos`
  - `policies` : véhicules, devis, polices (cycle de vie dans `services.py`),
    sinistres, commissions, portail assureur (API `/api/insurer/*`, toujours
    filtrée sur la compagnie de l'agent via `services.insurer_*`, filtre `?branch=auto|travel`).
    **Voyage** : un voyage est un bien assuré de type `trip` (`Trip` : destinations ISO,
    départ, retour ; `Traveler` : NNI, nom, passeport, naissance, `verified` / `declared`) ;
    préparation et devis dans `travel.py` (`/api/trips…`, `/api/company/trips…`), même cycle
    de vie que l'auto dans `services.py`. Pays : `countries.json` (FR, AR, EN), identique à
    `frontend/lib/countries.json` (test)
  - `payments` : un adaptateur par opérateur (`providers.py`), callbacks signés
    HMAC et idempotents, remboursements ; un paiement porte une police OU une
    commande (`policies.Order`), remboursable ligne par ligne
  - `attestations` : numéro `SN-AAAA-NNNNNN`, signature Ed25519, QR, vérification
    publique `/v/<jeton>` (logo et nom en tête), révocation ; voyage : une attestation par voyageur
    (`Attestation.traveler`), PDF français, arabe et anglais (`pdf_travel.py` : nom et n° de passeport,
    naissance, destinations, dates, garanties et plafonds, assistance 24 h/24, mention Schengen) ;
    PDF bilingue de l'auto (`pdf.py`, fpdf2 + HarfBuzz
    pour l'arabe ; symbole arche et élan en tête, vectoriel, `logo.py` : fpdf2 ne lit pas
    les masques, la coupure passe par un `clipPath` ; mention « SPÉCIMEN »
    tant que `ATTESTATION_SPECIMEN` est vrai ; le ZIP des attestations d'une flotte passe par le même rendu)
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
    `Logo.tsx` (logo arche et élan : `SanadMark`, `Wordmark`, `StackedLogo` ;
    l'élan coupe l'arche par un masque SVG, jamais par un trait couleur du fond), `InsurerLogo.tsx`, `OtpLogin.tsx`, `ProAuth.tsx`,
    `ClaimForm.tsx`.
  - **Navigation et transitions** (app client et espace entreprise ; portail assureur et
    back-office inchangés) : les écrans client sont dans le groupe `app/(client)/`, avec un
    layout partagé (`components/ClientChrome.tsx`) qui rend **une seule fois** la TopBar (titre,
    retour, étape) et la BottomNav, décrites par `lib/screens.ts` (une entrée par écran, avec sa
    profondeur : accueil 0 → véhicule 1 → devis 2 → paiement 3 → contrat 4 → sinistre /
    contrôle 5 ; onglets accueil, contrats, profil au niveau 0) ; le garde-fou du compte y est
    posé une fois (`SpaceProvider` de `lib/spaces.ts`). Transitions de vue React
    (`<ViewTransition>`, types `nav-forward` / `nav-back` / `nav-tab`, `lib/transitions.ts`) :
    avancer → glissement vers la gauche, revenir → vers la droite, entre onglets (et onglets de
    l'espace entreprise, `addTransitionType("nav-tab")`) → fondu ; **sens inversés en arabe** ;
    220 ms, ease-out ; TopBar et BottomNav ne s'animent jamais (`sn-topbar`, `sn-bottomnav`) ;
    aucune animation avec « réduire les animations ». Toujours `Link` de
    `components/NavLink.tsx` (le sens est calculé) ; `useNav().push` seulement après une action
    (paiement, formulaire). Nouvel écran client : l'ajouter à `lib/screens.ts`. Un écran qui
    remplace la barre du haut (contrat assuré) : `useHideTopBar`.
  - **Accueil client** (`app/(client)/page.tsx`) : contrats en cours (actifs, payés, brouillons)
    en **carrousel horizontal** pour que « Souscrire une assurance » reste visible sans défiler
    (vérifié à 390 × 844 et 360 × 740). Défilement natif en CSS (`.carousel` : `scroll-snap`,
    barre masquée), aucune bibliothèque ni défilement automatique ; carte ≈ 78 % de l'écran, la
    suivante dépasse au bord (sens inversé en arabe) ; un seul contrat → pleine largeur, sans
    points ni « Tout voir (n) ». Ordre : ce qui demande une action (en validation, brouillon à
    payer, expire dans 30 jours ou moins) puis par date de fin. Liste accessible (`role="list"`,
    « Mes contrats »). Espaces : `--section-gap` (37 px) entre deux sections, réutilisable ;
    24 px au moins entre le texte du bandeau vert et les cartes (la carte chevauche le bandeau,
    jamais son texte). Si un petit écran ne tient pas, on réduit les tuiles (`--tile-height`),
    jamais les espaces entre sections.
  - **Assurance voyage** : `/voyage` (destinations et dates) → `/voyage/[id]/voyageurs` (« M'ajouter »
    pré-rempli avec le NNI du profil, nom affiché dès le NNI vérifié, sinon « nom du passeport ») →
    `/voyage/[id]/offres` → `/paiement/[id]` (écran commun, étapes du voyage via `useFlow`) →
    contrat (attestation PDF de chaque voyageur, assistance 24 h/24). Composants partagés avec
    l'onglet « Missions » de l'espace entreprise : `components/Travel.tsx` (`base` "" ou
    "company/"). Pays : `lib/countries.ts`. Onglet Contrats : filtre Tous / Auto / Voyage.
  - **Chargement** : jamais d'indicateur plein écran ; squelettes (`components/Skeletons.tsx`,
    blocs `--line`) aux dimensions du contenu, et tout ce qui dépend des données bascule d'un
    coup (rien ne doit être poussé ensuite). Dernières données de chaque écran en mémoire
    (`lib/cache.ts`, `useLoad`, `cachedPolicy`, `prefetch` de l'écran suivant probable),
    vidées à chaque `setToken` (connexion, déconnexion). Erreur de formulaire : `ErrorLine`
    (place réservée). Langue et sens de lecture posés avant l'affichage (`LANG_BOOT_SCRIPT`) ;
    barre du haut et étapes de même hauteur en français et en arabe.
  - Téléphones : **jamais d'indicatif +222 affiché ni saisi** (Sanad n'existe qu'en Mauritanie) ;
    `PhoneInput` (8 chiffres groupés « 36 00 00 01 », un « +222 » tapé ou collé est retiré),
    `formatPhone` ; l'appelant envoie `+222${chiffres}`. Champs écrits de gauche à droite
    (numéros, NNI, e-mails) : `dir="ltr"` sur l'`.input`, alignés à droite en arabe (`globals.css`).
  - Validation des champs : `components/FormValidation.tsx` (monté dans le layout)
    remplace la bulle du navigateur (langue et style du système) par un message
    sous le champ, traduit (`field*` dans `lib/i18n.tsx`). Garder les attributs
    HTML (`required`, `type="email"`, `minLength`, `min`/`max`) dans un `.field`.
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
  marchandises, VTC…) — `policies.models.VehicleUsage`. Dans l'app, les boutons
  disent seulement « Personnel » / « Commercial » ; la précision reste au back-office. Plus de « taxi » (refusé
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
- **Voyage « Monde entier »** (valable partout, Schengen compris) : 1 à 92 jours, départ et
  retour compris (aller-retour dans la journée = 1 jour), départ au plus tôt aujourd'hui ;
  contrat du départ au retour ; plusieurs voyageurs (9 au plus pour un particulier, 50 pour
  une entreprise), un paiement, **une attestation par voyageur**. Chaque voyageur :
  `verify_eid(NNI)` → eID valide : nom officiel de l'ANRPTS, jamais modifiable ; pas d'eID
  (souvent un enfant) : nom saisi tel que sur le passeport, marqué « déclaré », visible par
  l'assureur ; NNI introuvable ou injoignable : refusé, mêmes messages que le profil. Résultat
  gardé 30 min par compte ; limite propre `TRAVELER_CHECK_RATE` (30/h). **Un NNI, un seul
  contrat voyage à la fois** : vérifié au devis et à la confirmation du paiement (sinon
  `paid → refused`, remboursement). Voyageurs figés une fois payé. Tarif par voyageur : tranches
  de durée (1-8, 9-15, 16-31, 32-62, 63-92 j) × âge au départ (moins de 16, 16-65, plus de 65
  majoré). Aucune offre sous 30 000 € de frais médicaux. Pas de rappel de renouvellement.
  Sinistre voyage : types frais médicaux, rapatriement, bagages, retard, vol, autre ;
  voyageur concerné ; rappel d'appeler d'abord l'assistance 24 h/24.
- Particulier : **identité vérifiée avant tout paiement** (eID Houwiyeti auprès
  de l'ANRPTS, jamais à la main au back-office) ; devis et police brouillon
  restent possibles. NNI introuvable → « Ce NNI est introuvable. Vérifiez les
  chiffres saisis et réessayez » ; pas d'eID → « Créez votre identité numérique dans
  l'application Houwiyeti, puis réessayez » ; injoignable → « Service
  indisponible, réessayez dans quelques minutes » (FR + AR).
- Espace entreprise : une entreprise ne voit jamais les données d'une autre ;
  pas de paiement tant qu'elle n'est pas vérifiée (NIF + RC) ; mobile money
  uniquement, plafond `PAYMENT_MAX_AMOUNT`.
- **RC automobile : tarif homologué par l'État**, donc identique chez tous les
  assureurs. La comparaison joue sur les formules étendues et le service.
- Paiements : ne jamais activer une police sans callback valide (signature,
  montant exact). Le fournisseur `simulated` est interdit en production.
- Aucune donnée de compte mobile money stockée ; seules les références.
- Pièces justificatives (NIF / RC des entreprises) : stockage privé (`PRIVATE_MEDIA_ROOT`,
  `accounts/storage.py`), type vérifié sur le contenu, jamais d'URL publique ;
  ouvertes seulement au back-office, chaque consultation journalisée.
- Vérification publique : données personnelles **masquées**.
- Attestation PDF : jamais de prime dessus ; mention « SPÉCIMEN » obligatoire
  tant qu'aucun partenariat n'est signé avec la compagnie.

## Données et marques

- Catalogue démo (`seed_demo`) : **NASR, MAR, MEDINA Assurances, IMAN Assurance** ;
  voyage « Monde entier » chez NASR, MAR et IMAN (MEDINA : auto seulement), plafonds et
  numéros d'assistance fictifs.
  Agents démo `agent@<code>.test` (`+22220000001` à `+22220000004`), mot de
  passe = `DEMO_PASSWORD`, posé **uniquement en DEMO_MODE** (jamais en dur dans
  le code). Compte équipe démo : groupe « Équipe Sanad », jamais superutilisateur. Registre eID
  simulé : NNI `1234567890` = « Sidi Mohamed » / « سيدي محمد », `111…` NNI
  introuvable, `000…` pas d'eID valide (voyage : voyageur sans eID, nom déclaré), `999…` injoignable,
  tout autre NNI à 10 chiffres valide avec un nom
  fictif (toujours le même pour un NNI) ; jamais de téléphone renvoyé. **Les primes sont fictives** et
  marquées `is_indicative` (« Indicatif » dans l'app) : ne jamais les présenter
  comme de vrais tarifs.
- **Logos des compagnies** : uniquement les fichiers officiels fournis par les
  compagnies, déposés dans `backend/logos/` (hors dépôt git). Ne jamais
  télécharger, recréer ni dessiner un logo de compagnie.
- Aucun partenariat signé à ce stade : ne pas publier ces noms hors démo.

## Design

Maquettes de référence (V2, contraste renforcé) : toile « Sanad – Maquettes »
dans Claude. Logo : piste A « L'arche et l'élan » (page « Logo · nouvelles pistes ») ;
icône de l'app `public/icon.svg` (+ PNG 192 / 512, `icon-maskable-512.png`, `apple-touch-icon.png`, `favicon-32.png`). Palette dans `globals.css` (`--green #08603F`,
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

1. Espace entreprise, suite : **santé de groupe** (l'auto de la flotte et le voyage
   des salariés sont faits ; un plan par produit)
2. Adaptateur ANRPTS réel pour l'eID Houwiyeti (`verify_eid`, dès réception de
   la documentation ; déclaration de sinistre et sinistres de flotte faits)
3. Mise en ligne (Render : Django + PostgreSQL, Next.js ; code SMS du
   back-office fait)
4. Vraies intégrations : Bankily / Masrvi / Sedad (API marchandes),
   fournisseur SMS, envoi d'emails (SMTP)
5. Mode hors ligne (service worker)

### Espace entreprise : décisions du porteur (20/11/2026)

1. **Compte entreprise distinct** des comptes particuliers.
2. Pièces à l'ouverture : **NIF et Registre du Commerce**.
3. Paiement : **mobile money uniquement** (pas de virement sur facture).
4. Produits : **Auto, Santé et Voyage** (dans cet ordre : auto et voyage faits).
5. Un gérant peut utiliser le même numéro que son compte particulier.
6. Inscription libre en ligne ; pas de paiement avant vérification NIF + RC.
Connexion : email + mot de passe + code SMS (mécanisme des comptes pro).
