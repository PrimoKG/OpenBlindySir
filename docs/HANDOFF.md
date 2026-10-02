# OpenBlindySir — Rapport de passation (2026-10-02)

Ce document s'adresse à l'IA ou à la personne qui reprend le projet. Il résume le contexte, ce qui est fait, ce qui reste à faire, les problèmes connus et les règles de travail.

**Sources de vérité, par ordre de priorité :**
1. `docs/architecture.md` : spécification canonique. Elle fusionne la v2, une mise à jour nom/licence et une mise à jour compteur/langues.
2. `docs/protocol.md`, `docs/sync.md`, `docs/bridge-security.md`, `docs/adr/0000` à `0008`.
3. `docs/DEVLOG.md` : historique détaillé de chaque étape, avec les nombres exacts de tests. Ne jamais réécrire une entrée passée ; on en ajoute une nouvelle.

---

## 1. Le projet en bref

OpenBlindySir est un **blind test musical multijoueur** auto-hébergé, sous licence MIT. Le titulaire est PrimoKG ; le dépôt public est https://github.com/PrimoKG/OpenBlindySir.

- **Serveur** (Python 3.12, FastAPI, uv) : un seul processus, tout en mémoire, sans base de données. Il sera hébergé sur un VPS derrière Caddy.
- **Bridge** (Python) : programme lancé sur le PC qui contient la bibliothèque musicale. Il se connecte au serveur en sortie (WSS), indexe les fichiers par `track_id` opaque et découpe des extraits avec FFmpeg, selon un gabarit fixe. Il envoie au serveur **seulement des extraits** de 5 à 60 s (20–30 s par défaut), sans métadonnées. Il considère le serveur comme non fiable.
- **Web** (React, TypeScript, Vite) :
  - `/` : écran joueur ;
  - `/host` : écran hôte, soit en « mode joueur » (vue joueur + tiroir de commandes), soit en mode animateur (MC) ;
  - audio synchronisé avec Web Audio (`getOutputTimestamp`, rattrapage si on arrive en retard).

**Déroulé d'une partie :** LOBBY → IN_GAME (rounds : QUEUED/PREPARING → LOADING → COUNTDOWN → OPEN → REVIEW → REVEALED) → FINAL_SCORE_REVIEW (obligatoire) → FINAL_RESULTS.

**Règles clés :**
- Le temps de réponse est mesuré **par le serveur**, à la réception.
- Avant le reveal, un joueur ne voit ni les réponses, ni les temps, ni les rangs des autres.
- Le compteur « n/m ont validé » est anonyme et n'apparaît pas si moins de 3 joueurs sont attendus.
- Les scores sont tenus dans un journal d'événements (`ScoreEvent`).

---

## 2. Préférences et règles de travail

- **Langue :** répondre en **français**. Les messages de commit sont en anglais (Conventional Commits) et se terminent par la ligne `Co-Authored-By: ...` de l'assistant.
- **« GO »** veut dire feu vert, pas le langage Go.
- **Méthode :** travail **séquentiel**, sans workflows multi-agents (pour économiser les tokens). Des sous-agents ponctuels sont acceptés.
- **Commits :** granulaires ; ne jamais squasher l'historique.
- **Hygiène :** toujours lancer `python tools/check_repo_hygiene.py` **après `git add`** (le script vérifie l'index) et avant de commiter.
- **Jamais dans le dépôt :** secrets, `.env`, musique.
  - Les valeurs de test commencent par `example`.
  - Un faux positif documenté se marque avec `# hygiene: allow`.
  - Pas de chemin de fichier ni de texte de réponse dans les logs.
- **Identifiants :** ne jamais demander ni tenter de récupérer ceux de l'utilisateur. Seules des valeurs de test sur localhost sont permises.
- **Portes G1/G2 :** ne **jamais** écrire `G1 PASS` ou `G2 PASS` sans mesure réelle faite par le mainteneur. État actuel : `G1: PENDING USER MEASUREMENT`, `G2: PENDING USER MEASUREMENT`.
- **Compte rendu de fin d'intervention** (§19.12), avec ces sections exactes : Réalisé / Principales modifications / Bugs réellement découverts (ou « Aucun nouveau bug découvert pendant cette étape. ») / Tests (séparés : Python, intégration, Bridge, Web/Vitest, Playwright Chromium, Playwright WebKit, build) / Git / Gates / État / Restant / Prochaine étape recommandée.
- **Entrée DEVLOG** à chaque étape : objectif, décisions, scénarios, bugs, tests avec nombres exacts, état GitHub, G1/G2, état, problèmes connus, prochaine étape.

---

## 3. Avancement par étape (§26 de la spec)

| # | Étape | État |
|---|---|---|
| 0 | Bootstrap (dépôt, licence, docs, ADR, hygiène) | DONE |
| 1 | Spike S0 : synchro et formats (branche `spike/audio-sync`) | Outillage DONE ; **G1 : PENDING USER MEASUREMENT** |
| 2 | Spike S1 : Bridge (branche `spike/bridge`) | Outillage DONE ; **G2 : PENDING USER MEASUREMENT** |
| 3 | Socle (workspace uv, paquet `protocol`, types TS générés, CI) | DONE |
| 4 | Cœur du jeu pur | DONE |
| 5 | Vertical slice n°1 (serveur, Bridge démo, web, partie complète) | DONE |
| 6 | Vertical slice n°2 : Bridge réel | PARTIAL selon l'utilisateur. Le code est en place (scanner, sandbox, sélection de dossiers, préchargement, remplacement), mais il n'a pas été validé sur la vraie bibliothèque du mainteneur. |
| 7 | Robustesse | **DONE** (`8d240d0`) |
| 8 | Déploiement réel (Compose, Caddy, image GHCR `ghcr.io/primokg/openblindysir`, VPS, soirée alpha) | **Pas commencé.** Attendre le GO explicite de l'utilisateur. |
| 9 | Durcissement et release (`v0.1.0-rc.1`, puis `v0.1.0`) | Pas commencé. Bloqué par G1/G2. |

**GitHub :**
- `main`, `spike/audio-sync` et `spike/bridge` sont poussées ; 38 commits sur `main`.
- La CI du dernier push est verte (8 jobs) : `hygiene`, `python`, `protocol-drift`, `web`, `bridge-linux`, `bridge-windows`, `integration`, `e2e`.
- Le workflow `nightly.yml` a été lancé une fois à la main : `fuzz-core` vert, `e2e-webkit` rouge (non bloquant).

---

## 4. Architecture du code

```
protocol/src/openblindysir_protocol/   messages Pydantic stricts, enums, erreurs, vues, bridge, catalog_rules
  schema.lock.json                       verrou du schéma (dérive vérifiée en CI)
server/src/openblindysir_server/
  game/            CŒUR PUR et synchrone : GameEngine.dispatch(cmd, Instant) -> Outcome(effects, error, value, version, changed)
                   horloge et ids injectés (FakeClock, SequentialIds) ; timers dérivés de l'état ; règle ruff banned-api
                   modules : state, rounds, answers, scoring, standings, assets, selection, readiness, permissions, views…
  runtime.py       dispatch + exécution des effets + TimerDriver
  ws/              hub joueurs (STATE regroupés sur 50 ms, dédupliqués ; fermetures 4001/4003/4004), endpoint Bridge, jetons à usage unique
  auth/            sessions hachées, cookie `__Host-openblindysir` (dev : `openblindysir_dev`), rate limit sur les échecs uniquement
  audio/           cache RAM, magic bytes, upload PUT /api/bridge/assets/{id}, GET /api/audio/{id}
  main.py          create_app, sweep_once (heartbeat, OFFLINE après 20 s), SPA statique
bridge/src/openblindysir_bridge/  scanner (ne suit ni symlinks ni junctions), catalog, sandbox, ffmpeg (gabarit fixe),
                                  jobs (1 job, file de 4), client, demo (--demo, --demo-fault), console, cli
web/src/  net/ (api, socket, viewStore, backoff), audio/ (clock, schedule, prefetch, engine), app/, player/, host/, i18n/ (fr, en)
tools/    check_repo_hygiene.py, gen_ts_types.py, bots.py (bots de test), e2e_stack.py (pile pour Playwright)
```

**Points de sécurité du Bridge :**
- FFmpeg est appelé avec `-protocol_whitelist file`, `-format_whitelist mp3,flac,wav,mov,ogg,aiff,asf,aac` et une entrée de la forme `file:` + chemin résolu (ADR 0008). Il n'y a jamais de shell, et le serveur ne fournit jamais d'argument FFmpeg.
- La durée de l'extrait produit est vérifiée après encodage.

---

## 5. Commandes utiles (poste Windows du mainteneur)

FFmpeg n'est **pas dans le PATH** du shell. Il faut le préfixer :
```bash
FFDIR="/c/Users/primo/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin"
PATH="$FFDIR:$PATH" uv run pytest                                          # 498 réussis, 1 ignoré (symlink)
PATH="$FFDIR:$PATH" uv run pytest server/tests/integration -m integration   # 8/8, environ 4 min
HYPOTHESIS_PROFILE=nightly uv run pytest server/tests/game/test_game_properties.py   # fuzzer long, environ 5 min
uv run ruff check . && uv run ruff format --check . && uv run pyright
cd web && npm run lint && npm run typecheck && npm run test && npm run build   # Vitest 21/21
cd web && PATH="$FFDIR:$PATH" npx playwright test --project=chromium          # E2E 1/1 (build web/dist d'abord)
python tools/check_repo_hygiene.py
```

- **GitHub CLI :** `"/c/Program Files/GitHub CLI/gh.exe"`, authentifié en PrimoKG.
- **pytest sous Windows :** utiliser `--basetemp` vers un dossier temporaire inscriptible.
- **Serveur en local :** `DEV_MODE=1`, `BLIND_PASSWORD`, `HOST_PASSWORD`, `BRIDGE_SECRET`, `PORT`, `STATIC_DIR=web/dist`. Ensuite `uv run python -m openblindysir_server serve`.
- **Bridge démo :** `OPENBLINDYSIR_BRIDGE_SECRET=... uv run python -m openblindysir_bridge --demo --server http://localhost:PORT`.

---

## 6. Ce qui a été fait à l'étape 7 (dernière étape)

- **7 scénarios d'intégration** (`server/tests/integration/test_variants.py`) :
  - reconnexion pendant OPEN, y compris la supplantation 4001 ;
  - Bridge tué puis relancé, y compris pendant un encodage ;
  - upload corrompu ;
  - fichier supprimé après le scan ;
  - fin anticipée `score` et `abandon`.
- **Tests serveur des uploads** (14 cas), du **heartbeat** et du **rate limit**.
- **Tests Bridge :**
  - fichier supprimé, renommé ou remplacé après le scan ;
  - playlists ffconcat et HLS déguisées en `.mp3` ;
  - métacaractères de shell dans les noms de fichiers.
- **ADR 0008** (liste blanche de démultiplexeurs FFmpeg).
- **Fuzzer :** machine à états Hypothesis avec un profil `nightly`.
- **E2E Playwright Chromium** (`web/e2e/game.spec.ts`) : 1 hôte et 2 joueurs, 2 rounds, jusqu'aux résultats puis fin de session. Il vérifie aussi :
  - l'absence de spoiler dans les trames WebSocket ;
  - le pipeline audio (READY et PLAYBACK_REPORT) ;
  - la reconnexion, par rechargement de page et par un second onglet.
- **CI :** job `e2e`, plus `nightly.yml` (fuzzer + WebKit non bloquant).
- **Correctif** (`771da99`) : trois cas de refus d'upload n'écrivaient pas de log `upload_rejected`.

---

## 7. Problèmes connus et points ouverts

1. **WebKit non validé.**
   - Sous Windows, le WebKit de Playwright n'a pas d'`AudioContext` ; c'est impossible localement.
   - Sous Linux (nightly), l'audio se déverrouille et Alice valide, mais Bob n'affiche jamais « 1/3 ont validé » dans les 30 s. La cause n'est pas analysée. Il faut regarder l'artefact `playwright-webkit` du run 36998597618 (trace.zip).
   - La relance échoue pour une raison d'isolation : la tentative précédente n'a pas atteint la fin de session, donc les pseudos sont déjà pris. Piste : nettoyer la session en `afterEach`, ou utiliser des pseudos uniques.
2. **G1 et G2 non mesurées.** Elles demandent de vrais appareils (iPhone, Android, Safari…), une mesure acoustique de synchronisation (p90 ≤ 60 ms) et la vraie bibliothèque, avec un vrai VPS (préparation + upload < 5 s au p95). L'ADR 0004 (format audio) reste « Proposé ». Elles bloquent toute release.
3. **Le Chromium de Playwright n'a pas de décodeur AAC.** L'E2E utilise donc `CLIP_FORMAT=opus`. Le format par défaut de production (AAC) dépend de G1.
4. **Étape 6 PARTIAL :** pas encore de validation sur la vraie bibliothèque du mainteneur.
5. **Pas de Dockerfile ni de Compose** (étape 8). Le job Dependabot « docker » échoue tant qu'il n'y a pas de Dockerfile ; c'est attendu. Des PR Dependabot (uvicorn, etc.) sont ouvertes et n'ont pas été traitées.
6. **Divers :**
   - les sdist ne se construisent pas (`../VERSION` et `../LICENSE` sont hors du paquet), sans impact avant une distribution PyPI ;
   - `docs/testing.md` et `docs/deployment.md`, prévus au §16, n'existent pas encore ;
   - le script d'hygiène ne reconnaît pas le MPEG Layer I (`.mp1`).
7. **Limite de test :** l'absence du compteur quand moins de 3 joueurs sont attendus est testée dans le cœur, pas en E2E.
8. **Pièges d'environnement rencontrés :**
   - l'outil Write convertit les `\uXXXX` en caractères littéraux ;
   - les heredocs bash avec apostrophes cassent parfois : passer par des scripts Python dans un dossier temporaire ;
   - sous Windows, `write_text` produit du CRLF : écrire en octets, ou laisser git normaliser.

---

## 8. Prochaines étapes recommandées

1. **Attendre le GO de l'utilisateur** avant l'étape 8. Tant qu'il n'est pas donné : pas de VPS, de soirée alpha, de RC, de v0.1 ni de nouvelles fonctionnalités.
2. **Optionnel, avant l'étape 8 :** analyser l'échec WebKit Linux et rendre l'E2E robuste aux relances.
3. **Étape 8 :**
   - Dockerfile (le serveur sert `web/dist`), Compose avec Caddy (HTTPS, HSTS) ;
   - image GHCR `ghcr.io/primokg/openblindysir:edge` ;
   - `docs/deployment.md` ;
   - déploiement sur le VPS du mainteneur ;
   - soirée alpha de 5 à 10 joueurs, avec les retours consignés tels quels dans le DEVLOG.
4. **En parallèle, côté mainteneur :** mesures G1 et G2 avec les outils des branches de spike.
5. **Étape 9** (durcissement et release), seulement après G1/G2 PASS mesurés.
