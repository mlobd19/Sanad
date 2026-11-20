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

# Application client
cd frontend && npm run dev            # http://localhost:3000 : app, /assureur, /entreprise, /admin
```

Dans VS Code : tâche **« Lancer Sanad »** (les deux serveurs). Les codes SMS
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
    passe + code SMS ; le SMS seul n'ouvre jamais qu'un compte particulier.
    Codes SMS liés à un usage (`OtpCode.purpose`). Invitation / mot de passe
    oublié par email (lien 72 h). Back-office : `backends.PhonePasswordBackend`
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
  - `notifications` : SMS / WhatsApp derrière une interface, modèles FR + AR
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
  - Composants partagés : `components/Shell.tsx` (TopBar, Stepper, BottomNav…),
    `Logo.tsx` (logo khaïma), `InsurerLogo.tsx`, `OtpLogin.tsx` (connexion SMS
    partagée par `/connexion` et `/assureur/connexion`).
  - Portail assureur : `/assureur` (web, bureau d'abord, styles `.portal*`),
    réservé au rôle `insurer_agent`.

## Règles métier à respecter

- Cycle de vie d'une police : `draft → paid → active → expired`,
  `paid → refused` (remboursement automatique), `active → cancelled`
  (attestation révoquée). Toute transition passe par `policies/services.py`.
- Un véhicule ne peut pas être couvert deux fois sur la même période.
- Espace entreprise : une entreprise ne voit jamais les données d'une autre ;
  pas de paiement tant qu'elle n'est pas vérifiée (NIF + RC) ; mobile money
  uniquement, plafond `PAYMENT_MAX_AMOUNT`.
- **RC automobile : tarif homologué par l'État**, donc identique chez tous les
  assureurs. La comparaison joue sur les formules étendues et le service.
- Paiements : ne jamais activer une police sans callback valide (signature,
  montant exact). Le fournisseur `simulated` est interdit en production.
- Aucune donnée de compte mobile money stockée ; seules les références.
- Vérification publique : données personnelles **masquées**.
- Attestation PDF : jamais de prime dessus ; mention « SPÉCIMEN » obligatoire
  tant qu'aucun partenariat n'est signé avec la compagnie.

## Données et marques

- Catalogue démo (`seed_demo`) : **NASR, MAR, MEDINA Assurances, IMAN Assurance**.
  Agents démo `agent@<code>.test` (`+22220000001` à `+22220000004`), mot de
  passe `demo-sanad-2026` posé **uniquement en DEBUG**. **Les primes sont fictives** et
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

## Git

- Branche `main`, dépôt `mlobd19/Sanad`.
- Auteur des commits : `Mohamed Lemine OUBEID <ml.oubeid@gmail.com>`.
- Ne jamais committer : `.env`, `db.sqlite3`, `backend/logos/*` (sauf
  `LISEZMOI.md`), `node_modules`, `.venv`, `.next`.

## Pas encore fait (feuille de route)

1. Espace entreprise, suite : **voyage**, puis **santé de groupe** (l'auto de la
   flotte est faite ; un plan par produit)
2. Dépôt des pièces KYC et déclaration de sinistre dans l'app
3. Mise en ligne (Render : Django + PostgreSQL, Next.js) ; avant : code SMS
   pour la connexion au back-office `/admin/`
4. Vraies intégrations : Bankily / Masrvi / Sedad (API marchandes),
   fournisseur SMS et WhatsApp Business, envoi d'emails (SMTP)
5. Mode hors ligne (service worker)

### Espace entreprise : décisions du porteur (20/11/2026)

1. **Compte entreprise distinct** des comptes particuliers.
2. Pièces à l'ouverture : **NIF et Registre du Commerce**.
3. Paiement : **mobile money uniquement** (pas de virement sur facture).
4. Produits : **Auto, Santé et Voyage** (dans cet ordre : auto faite).
5. Un gérant peut utiliser le même numéro que son compte particulier.
6. Inscription libre en ligne ; pas de paiement avant vérification NIF + RC.
Connexion : email + mot de passe + code SMS (mécanisme des comptes pro).
