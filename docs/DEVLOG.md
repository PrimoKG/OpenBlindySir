# Journal de développement (DEVLOG)

> Histoire réelle du développement d'OpenBlindySir. On ajoute des entrées, on ne réécrit jamais les précédentes, et on n'y mentionne que les tests réellement exécutés (§19.11 de [architecture.md](architecture.md)).

## 2026-10-01 — Bootstrap du dépôt

**Objectif** — Après le « GO IMPLEMENTATION », poser un dépôt Git propre (§19.2) avec la documentation canonique, les ADR, les fichiers publics et l'outil d'hygiène, avant toute ligne de code applicatif.

**Décisions**
- Nom public OpenBlindySir, slug technique `openblindysir`, licence MIT (§0.1).
- Propriétaire GitHub : `PrimoKG`, confirmé par le mainteneur (gh n'étant pas encore authentifié, il n'a pas pu être lu via `gh`). Dépôt `PrimoKG/OpenBlindySir`, image `ghcr.io/primokg/openblindysir` (GHCR impose les minuscules), `Copyright (c) 2026 PrimoKG`.
- La spec canonique n'existait que dans la conversation de conception : elle a été reconstituée en un seul document (`docs/architecture.md`, spec v2 + mise à jour « nom et licence » + mise à jour « compteur de progression et langues »). Les sections 8, 9 et 11 ont été extraites dans `docs/protocol.md`, `docs/sync.md` et `docs/bridge-security.md`, avec la même numérotation.
- Les portes G1 et G2 des spikes S0 et S1 exigent du matériel réel (iPhone, Android, micro, bibliothèque musicale réelle, VPS). Décision du mainteneur : construire les outils des spikes sur leurs branches pour qu'il puisse mesurer, puis poursuivre le socle, le cœur du jeu, les vertical slices et la robustesse sans attendre ces mesures. Le format reste AAC par défaut et l'ADR 0004 reste « Proposé » jusqu'à G1.
- Outillage installé sur le poste de développement à la demande du mainteneur : FFmpeg 9.0.2 (build gyan.dev, encodeurs `aac` et `libopus` présents) et GitHub CLI 2.102.0, via winget.

**Implémentation**
- README, LICENSE, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT (Contributor Covenant 2.1 par référence), CHANGELOG (section `Unreleased`), VERSION (`0.0.0`).
- `.gitignore`, `.gitattributes`, `.env.example` (valeurs fictives uniquement).
- `docs/architecture.md`, `docs/protocol.md`, `docs/sync.md`, `docs/bridge-security.md`.
- ADR 0000 (modèle), 0001 à 0003 et 0005 à 0007 « Accepté », 0004 « Proposé ».
- `tools/check_repo_hygiene.py` : en dépôt Git, analyse le contenu **indexé** (blobs de l'index) ; sinon, parcours du dossier. Détecte fichiers audio (extension et signature), `.env`, clés et certificats, dossiers de build, fichiers de plus de 5 Mo, secrets évidents et affectations de `BLIND_PASSWORD`/`HOST_PASSWORD`/`BRIDGE_SECRET` à une valeur qui n'est pas un placeholder.
- Une relecture adverse (complétude de la spec fusionnée, cohérence entre documents, robustesse du script d'hygiène) a relevé 21 points, dont aucun bloquant, tous corrigés avant le commit : alignement du diagramme du §4, affirmations non vérifiées retirées d'une ADR et de SECURITY.md, consigne `TRUSTED_PROXIES` erronée dans `.env.example`, lacunes du `.gitignore` et du script (fichiers UTF-16, lecture de l'index, placeholders reconnus trop largement, formats audio/vidéo supplémentaires).
- `git init` (branche `main`), puis commit `chore: bootstrap repository`.

**Zones touchées** — docs, tools, configuration du dépôt. Aucun code dans protocol, server, web ou bridge.

**Tests**
- Aucun test de code : il n'existe encore ni code applicatif, ni pytest, ni Vitest, ni Playwright, ni image Docker.
- `python tools/check_repo_hygiene.py` sur le dépôt après `git add` (mode index) : voir le résultat consigné dans le compte rendu de cette intervention.
- `ruff check` et `ruff format --check` sur `tools/check_repo_hygiene.py` : aucun problème.
- Essais manuels du script d'hygiène sur des fichiers fabriqués hors du dépôt (dossier temporaire et dépôt Git jetable) : secrets en UTF-8/UTF-16/UTF-32, secret indexé puis retiré de l'arbre de travail, formes `os.environ[...]`, `NAME: str = "..."`, `ENV` de Dockerfile, clé `secret` de `config.toml`, signatures MP4 et MPEG Layer II, placeholders légitimes. Résultats conformes. Ces essais ne sont pas des tests automatisés versionnés.

**État** — DONE localement. Création du dépôt GitHub et push **bloqués** : GitHub CLI est installé mais pas authentifié (`gh auth status` : « You are not logged into any GitHub hosts »). Aucun identifiant n'est saisi par l'assistant.

**Problèmes connus**
- Pas de remote, donc ni CI, ni push protection, ni secret scanning GitHub actifs pour l'instant.
- `docs/testing.md` et `docs/deployment.md`, prévus au §16, n'existent pas encore.
- Le script d'hygiène ne reconnaît pas le MPEG Layer I à son contenu (un en-tête Layer I avec CRC commence comme le BOM UTF-16 LE) ; l'extension `.mp1` n'est pas listée.

**Prochaine étape** — Outils des spikes S0 (synchro et formats) et S1 (Bridge) sur les branches `spike/audio-sync` et `spike/bridge`.

## 2026-10-02 — Outils des spikes S0 (synchro et formats) et S1 (Bridge)

**Objectif** — Fournir au mainteneur l'outillage complet pour mesurer les portes G1 et G2 (§26, étapes 1 et 2) sur du matériel réel, et tester localement tout ce qui peut l'être.

**Décisions**
- Code jetable sur les branches `spike/audio-sync` et `spike/bridge`, non fusionné dans `main` (§19.5). Les outils réutilisables (`tools/calibration_clip.py`, `tools/sync_analyze.py` et son test) seront réintégrés proprement plus tard.
- Fréquences de calibration 1400 à 3400 Hz par pas de 400 Hz (au lieu de 1000 à 3000 Hz) : aucun harmonique 2 ou 3 d'une voix ne tombe près d'une autre voix.
- **Constat de sécurité à reporter dans la spec** : le gabarit FFmpeg exact du §10 laisse FFmpeg lire un fichier hors de la racine quand un fichier à extension audio contient en fait une playlist ffconcat qui passe par une junction située dans la bibliothèque (le démultiplexeur concat est choisi d'après le contenu, et `-protocol_whitelist file` ne le bloque pas). `-format_whitelist` (liste fermée de démultiplexeurs audio) bloque ce cas. Le §10 et `docs/bridge-security.md` devront l'intégrer avant l'implémentation du vrai Bridge (étape 6).
- Autre constat S1 : un FLAC tronqué dont l'en-tête annonce une durée plus longue que les données peut produire un `.m4a` valide mais vide (257 o) ; le client du spike vérifie la durée réellement produite et refuse en `DECODE_ERROR` sous la moitié de l'extrait demandé. À reporter dans la spec avec le gabarit.
- Incohérence relevée : la spec borne les extraits à 20–30 s (§1) mais autorise `CLIP_MAX_S=60` (§15) ; le spike plafonne à 30 s côté Bridge. À trancher dans la spec.

**Implémentation**
- S0 : serveur FastAPI de test (synchro d'horloge PING/PONG, diffusion PLAY, rapports de décodage par format, page d'admin), page de test vanilla JS (recettes de déverrouillage §9.7, matrice de formats AAC/M4A, Opus/WebM, Opus/Ogg, MP3, planification §9.5), README de protocole de mesure (§20.5) et tableaux de résultats à remplir.
- S1 : bibliothèque synthétique (FLAC, MP3 CBR, MP3 VBR avec et sans en-tête Xing, M4A avec `moov` en fin, WAV, Ogg, Opus, AIFF, noms NFD, fichiers piégés), banc de scan, sonde de sandbox, banc du gabarit FFmpeg, serveur relais et client sortant mesurant PREPARE → upload, README de protocole G2.
- Une relecture adverse a relevé 13 problèmes réels (7 sur S0, 6 sur S1), tous corrigés, dont : repliement silencieux des décalages proches de 500 ms dans `sync_analyze.py`, recettes iOS qui se contaminaient sur la même page, worker du client Bridge qui mourait sur une exception inattendue, verdict G2 calculé sur les seuls jobs réussis.

**Zones touchées** — branches de spike uniquement (`spikes/`, `tools/` de ces branches). Rien sur `main` hors ce DEVLOG.

**Tests** (réellement exécutés sur le poste Windows du mainteneur, fichiers synthétiques uniquement)
- S0 : `node --test` (maths d'horloge) 14/14 ; `pytest tools/test_sync_analyze.py` 25/25 après corrections ; test de fumée HTTP + WebSocket du serveur : PASS ; ffprobe des clips générés : AAC-LC / Opus, 48 kHz stéréo, aucun tag title/artist ; répétitions à blanc de mesure acoustique sur enregistrements synthétiques (décalages retrouvés à 0,1 ms près, PASS/FAIL attendus).
- S1 : banc FFmpeg sur 42 extraits synthétiques : préparation p50 532 ms, p95 619 ms ; relais local + client en 127.0.0.1 : PREPARE → upload p50 446 ms, p95 499 ms sur 20 jobs réussis (5 TOO_SHORT attendus) ; 6 `track_id` forgés tous refusés `NOT_FOUND` ; sonde sandbox : tous les cas passent sauf le cas ffconcat, qui échoue avec le gabarit exact du §10 (attendu, voir Décisions).
- **Non exécuté** : aucun navigateur, aucun appareil réel, aucune bibliothèque réelle, aucun VPS.

**État** — PARTIAL : outillage prêt et testé localement ; portes G1 et G2 **non mesurées** (en attente du mainteneur).

**Problèmes connus**
- G1 et G2 ne sont pas franchies ; ADR 0004 reste « Proposé ».
- Gabarit FFmpeg du §10 insuffisant (ffconcat), voir Décisions.
- Branches de spike non poussées : pas encore de remote (gh non authentifié).

**Prochaine étape** — Socle (§26 étape 3) : workspace uv, paquet `protocol`, génération des types TS, squelette web, CI.

## 2026-10-02 — Socle (§26 étape 3)

**Objectif** — Workspace uv, paquet `protocol`, génération des types TS, squelette web et CI (jobs `hygiene`, `python`, `protocol-drift`, `web`).

**Décisions**
- Méthode : à partir de ce jalon, implémentation séquentielle (sans orchestration multi-agents), à la demande du mainteneur, pour limiter la consommation. Le découpage suit un plan technique détaillé (« blueprint », document de travail non versionné) dérivé de la spec.
- Le gabarit FFmpeg du §10 est durci (`-format_whitelist`, contrôle de la durée produite) et les extraits sont plafonnés à 60 s (`CLIP_MAX_S`), 20 à 30 s par défaut (commit `b074fee`, choix du mainteneur).
- Vues : trois modèles racine distincts (`PlayerView`, `HostPlayerModeView`, `HostMcView`) ; une donnée interdite à une audience n'a aucun champ où exister. Vérifié statiquement sur le JSON Schema.
- Types TS : convertisseur maison JSON Schema → TypeScript (déterministe, sans dépendance npm) ; tout mot-clé non géré fait échouer la génération.
- Verrou de schéma `protocol/schema.lock.json` : tout changement de schéma impose d'incrémenter `PROTOCOL_VERSION`.
- Choix laissés ouverts par la spec consignés dans `docs/protocol.md` §8.4 (clés d'idempotence des commandes HOST, raisons de rejet, codes de fermeture, ajouts aux vues).
- Versions d'outillage retenues (les plus récentes disponibles) : Python 3.12, Pydantic 2.13, FastAPI 0.142, React 19.3, Vite 8, Vitest 5, TypeScript 7, Biome 2.5.
- Actions GitHub épinglées par SHA complet ; le script d'hygiène le vérifie.

**Implémentation**
- `pyproject.toml` racine (workspace uv, ruff, pyright, pytest), paquets `openblindysir-protocol`, `-server`, `-bridge` (hatchling, version lue dans `VERSION` = `0.1.0.dev0`, LICENSE incluse dans chaque wheel), `ruff.toml` interdisant toute E/S et tout asyncio dans `server/.../game/`.
- `openblindysir_protocol` : enums, codes d'erreur, normalisation des pseudos et réponses, réglages, messages joueur (dont les 23 commandes HOST), messages serveur, vues, messages Bridge, corps HTTP, diagnostic, règles de catalogue, export JSON Schema.
- `tools/gen_ts_types.py` → `web/src/protocol/generated.ts` ; `web/src/protocol/index.ts` (gardes de type).
- Squelette web (page « En construction »), Biome, Vitest, Vite (proxy `/api` vers le serveur de dev).
- `.github/workflows/ci.yml`, `.github/dependabot.yml`.

**Zones touchées** — protocol, tools, web (outillage), CI.

**Tests** (exécutés sur le poste du mainteneur, puis rejoués sur un clone propre du dépôt)
- `uv run pytest` : 143/143 (protocole : schémas stricts, timestamp client refusé, 23 commandes HOST et clés d'idempotence, normalisation, catalogue, atteignabilité anti-fuite des vues, verrou de schéma, golden du générateur TS).
- `ruff check`, `ruff format --check`, `pyright` : 0 erreur.
- `tools/gen_ts_types.py --check` : OK. `check_repo_hygiene.py` : OK (et échoue bien sur une action non épinglée).
- Web : `biome check`, `tsc --noEmit`, `vitest run` (aucun test encore), `vite build` : OK.
- `uv build --wheel --all-packages` : OK.

**État** — DONE localement. CI GitHub non exécutée : pas encore de remote (gh non authentifié).

**Problèmes connus**
- Les sdist ne se construisent pas (`../VERSION` et `../LICENSE` hors du paquet) ; sans impact avant la distribution PyPI prévue en V0.3.
- La rejouée sur clone propre a révélé que `pytest protocol/tests server/tests` échoue tant que `server/tests` n'existe pas : corrigé en passant par les `testpaths` (`185d406`).

**Prochaine étape** — Cœur du jeu pur (§26 étape 4) : machines à états, réponses et timing, journal `ScoreEvent`, `view_for`, sélection, tests de priorité 1.

## 2026-10-02 — Cœur du jeu pur (§26 étape 4)

**Objectif** — Machines à états, réponses et timing, journal `ScoreEvent`, `view_for` par rôle, sélection, avec les tests de priorité 1 sans réseau (§20.1 points 1 à 7).

**Décisions**
- Cœur synchrone piloté par `dispatch(commande, instant)` : l'instant est lu par le shell à la réception ; le cœur ne lit jamais d'horloge et ne fait aucune E/S (vérifié par l'AST et par une règle ruff qui interdit `asyncio`, `os`, `time`… dans `game/`). Il renvoie des effets (PLAY, ACK, PREPARE…) que le shell exécute après la mutation.
- Les transitions temporisées (fin du compte à rebours, timeout du ready check, deadline, fin de lecture, timeout de job) sont dérivées de l'état et appliquées à leur instant exact avant chaque commande : une validation arrivée après la deadline est refusée même si la minuterie n'a pas encore tourné.
- Un round FAILED ou passé ne consomme pas de numéro ; un morceau n'entre dans `played` qu'à sa première lecture ; le passage en MC Mode est refusé pendant COUNTDOWN/OPEN et le retour en Player Mode refusé en partie (anti-triche).
- `READY_TIMEOUT` lance le round même avec `auto_start` désactivé (lecture littérale du §9.4) ; après `end_game{score}`, l'hôte publie (reveal) puis passe explicitement à la vérification finale.

**Implémentation** — `server/src/openblindysir_server/game/` : état (§13), commandes et effets, moteur, minuteries, joueurs, rounds, réponses et timing, assets (préchargement, remplacement, rétention), sélection, journal des scores, vérification finale, classement, table de permissions HOST, `view_for`.

**Zones touchées** — server/game, tests du cœur.

**Tests**
- `uv run pytest` : cœur 251 tests au premier commit, dont une machine à états Hypothesis (profil CI, 250 exemples) vérifiant les invariants globaux (journal, round unique, ordres stricts, `official_start_at` écrit une fois, aucune transition IN_GAME → FINAL_RESULTS, anti-fuite par canaris, compteur de progression).
- Matrice anti-fuite §20.1-7 : chaque audience (joueur, hôte Player Mode, hôte MC) × chaque phase, sur l'objet sérialisé entier.
- Relecture adverse du cœur par un agent indépendant : fuzzer de 5 550 graines × 250 pas, sans fuite ni rupture d'invariant ; 5 problèmes réels trouvés et corrigés (`a948155`) avec tests de non-régression : éviction de l'asset courant pendant LOADING (blocage du moteur), N+2 jeté à chaque round avec `prefetch_depth=2`, slot en attente après `QUEUE_FULL` jamais réveillé, désactivation d'`allow_repeats` sans effet sur la file, croissance de `asset_ready` par de faux READY.
- `ruff`, `pyright` : 0 erreur.

**État** — DONE.

**Problèmes connus** — Aucun bloquant connu.

**Prochaine étape** — Vertical slice n°1 : shell HTTP/WebSocket, Bridge démo, interfaces minimales.

## 2026-10-02 — Vertical slice n°1, partie serveur et Bridge (§26 étape 5)

**Objectif** — Partie complète jusqu'à `FINAL_RESULTS` avec des sons synthétiques : auth, WebSocket, Bridge démo, bots.

**Décisions**
- **Limitation de débit des connexions** : seules les tentatives **échouées** sont comptées (join 5/min, host 3/min par IP). Compter toutes les connexions bloquait des amis derrière une même box (constaté avec les bots : le 6e joueur était refusé). §12 mis à jour (`3534e89`).
- Cookie `__Host-openblindysir` en production ; en `DEV_MODE`, cookie distinct `openblindysir_dev` non Secure (le préfixe `__Host-` exige Secure, impossible sur `http://localhost`).
- `DEV_MODE` refusé si `DOMAIN` n'est pas local ; `HOST_PASSWORD == BLIND_PASSWORD` toujours refusé.
- Catalogue accepté seulement avec le secret **et** un jeton à usage unique demandé par le Bridge actif ; décompression bornée (protection contre les bombes gzip).
- Bridge : liste fermée de démultiplexeurs (`-format_whitelist`) et contrôle de durée de l'extrait produit, conformément à l'amendement du §10.

**Implémentation**
- Shell serveur : configuration et refus de démarrage, CLI (`serve`, `gen-secrets`), sessions hachées, routes de session, en-têtes de sécurité, hub WebSocket joueur (supplantation 4001, kick 4003, STATE regroupés et dédupliqués par destinataire), WebSocket et routes du Bridge, cache audio RAM, diagnostic, journalisation avec masquage.
- Bridge : scanner, catalogue, sandbox, gabarits FFmpeg, jobs, client sortant, mode `--demo`, console.
- `tools/bots.py` et test d'intégration (serveur + Bridge démo en sous-processus + 10 bots).
- CI : jobs `bridge-linux`, `bridge-windows`, `integration`.

**Zones touchées** — server (shell), bridge, tools, CI, docs (§12).

**Tests** (exécutés sur le poste Windows du mainteneur)
- `uv run pytest` : 472 réussis, 1 ignoré (création de lien symbolique non autorisée sans le mode développeur Windows) ; dont tests du shell (configuration, auth, en-têtes, WebSocket : HELLO, PONG, timestamp client refusé, 4001, 4003, permissions ; Bridge : catalogue gzip, jeton unique, bombe gzip, upload, audio servable), Bridge (junctions Windows, sandbox, gabarit FFmpeg exact, jobs FFmpeg réels sur fixtures lavfi, extrait sans tags en AAC 48 kHz stéréo, **régression de l'évasion ffconcat**).
- `uv run pytest server/tests/integration -m integration` : 1/1 (partie complète, 10 bots, 2 rounds, 22 validations acceptées, vérification finale, FINAL_RESULTS ; 50 s).
- Essais manuels : serveur `DEV_MODE` lancé, `/healthz` et en-têtes vérifiés ; refus de démarrage avec mot de passe trop court (code 2, valeur non affichée) ; Bridge démo connecté (catalogue de 12 pistes).

**État** — PARTIAL : serveur, Bridge et partie complète par bots validés ; **interface web (joueur, hôte, moteur audio) pas encore écrite**.

**Problèmes connus**
- Pas d'interface web : la porte 5 (« interfaces joueur et hôte minimales ») n'est pas franchie.
- CI GitHub jamais exécutée (pas de remote).

**Prochaine étape** — Interface web : socket, horloge, moteur audio, écrans joueur et hôte.

## 2026-10-02 — Vertical slice n°1 : interface web et partie dans le navigateur (§26 étape 5, fin)

**Objectif** — Interfaces joueur et hôte minimales et moteur audio, pour une partie complète jouée dans un vrai navigateur.

**Décisions**
- Le client n'applique aucune règle de jeu : les boutons de l'hôte sont exactement `view.host.commands` ; chaque commande hôte lit ses clés d'idempotence dans la vue affichée (`undo_publish` utilise `host.undo_round_id`, jamais le round affiché).
- Moteur audio : un seul `AudioContext`, créé au premier geste ; planification avec `getOutputTimestamp` (repli `outputLatency`/`baseLatency`) ; rattrapage si le départ est passé ; l'extrait N+1 n'est jamais téléchargé pendant la lecture du client.
- Interface en français ; dictionnaire anglais complet pour garder la parité des clés (la langue reste fixée à `fr` en V0.1).
- Une réponse validée pendant une coupure réseau est gardée (une seule) et envoyée à la reconnexion si le round est toujours le même ; le serveur l'horodate à la réception.

**Implémentation** — `web/src` : réseau (API, socket, store de vue, backoff, codes de fermeture), audio (horloge, planification, préchargement, rapports, déverrouillage, moteur), i18n, écrans joueur, tiroir hôte / tableau de bord MC (réglages et arborescence de la bibliothèque, ready check, commandes du round, notation, publication, annulation, ajustements, vérification finale avec confirmation, résultats, kick, diagnostic).

**Zones touchées** — web, server (heartbeat), tools (bots).

**Tests**
- Web : Biome, `tsc --noEmit`, Vitest 21/21 (horloge avec gigue, asymétrie et valeurs aberrantes ; planification ; préchargement ; formats ; parité i18n et couverture des codes ; commandes hôte ; backoff ; codes de fermeture ; store de vue), `vite build` OK.
- Python : 473 réussis, 1 ignoré ; intégration 1/1 (49 s).
- **Test manuel** dans le navigateur intégré de l'application Claude (Chromium/Electron), serveur `DEV_MODE` servant le build, Bridge démo, hôte dans le navigateur et bots joueurs : entrée, élévation hôte, déverrouillage audio, réglages et sélection de dossier, lancement, remplacement automatique d'une piste démo trop courte (« Morceau remplacé »), round OPEN avec compteur anonyme « 0/4 ont validé », validation « ✓ Réponse enregistrée » sans temps, notation (« 1. Yo — Sinus 440 — 16,6 s »), publication et reveal (« OpenBlindySir Demo — Mélodie 3 »), round 2, vérification finale (« 3 → 0 → 3 »), confirmation, résultats (« 2 rounds joués »), nouvelle partie. Le son lui-même n'a pas été écouté (pas de sortie audio vérifiable dans cet environnement).
- **Bug trouvé pendant ce test et corrigé** (`bdf8a62`) : le balayeur de heartbeat fermait les connexions silencieuses sans signaler la déconnexion au cœur ; les joueurs concernés restaient « en ligne » et attendus à chaque ready check. Les bots, qui n'envoyaient pas de PING, en étaient victimes (heartbeat ajouté aux bots, `ebd0ad1`). Test de non-régression ajouté.

**État** — DONE pour la porte 5 (partie complète par bots en intégration, et dans le navigateur avec l'interface).

**Problèmes connus**
- Pas encore d'E2E Playwright ni des variantes d'intégration du §20.2 (reconnexion d'un bot pendant OPEN, Bridge tué puis relancé, upload corrompu, fichier supprimé après le scan, fin anticipée pendant OPEN) : étape 7.
- Aucun test sur appareils réels (iOS, Android, Safari) ni mesure de synchronisation : dépend des portes G1/G2 (mainteneur).
- CI GitHub jamais exécutée (pas de remote).

**Prochaine étape** — Étape 6 (Bridge réel) : déjà en grande partie couverte (scanner, sandbox, sélection de dossiers, préchargement, remplacement ; tests Windows verts en local). Puis étape 7 : variantes d'intégration et E2E Playwright.

## 2026-10-02 — Robustesse (§26 étape 7)

**Objectif** — Couvrir les scénarios de panne du §20.2 sur la vraie pile (serveur, Bridge démo, bots, navigateurs) : reconnexion, perte du Bridge, assets invalides, fichiers disparus, fin anticipée. Ajouter un E2E Playwright passant réellement par l'interface et vérifier l'absence de fuite et de régression. Aucune nouvelle fonctionnalité.

**Scénarios couverts**
- **Reconnexion pendant OPEN** (intégration, 3 bots + hôte) :
  - brouillon puis coupure brutale du transport : le joueur passe OFFLINE et le compteur des autres n'attend plus que 3 joueurs ;
  - reconnexion avec le même cookie : même identité, round OPEN, brouillon restauré, `play` présent (départ en rattrapage) ;
  - un second onglet supplante la connexion (4001), qui ne peut plus rien envoyer ;
  - reprise, validation acceptée, `late_start_ms > 0` dans la revue de l'hôte, points conservés jusqu'à `FINAL_RESULTS`.
- **Bridge tué puis relancé** (intégration) :
  - les extraits déjà `STORED` restent servis (HTTP 200) ;
  - l'hôte voit `bridge_offline`, le round 2 se joue avec l'extrait préchargé et le round 3 attend en QUEUED/PREPARING sans job zombie ;
  - relance : nouvelle connexion, catalogue resynchronisé, round 3 joué, `FINAL_RESULTS` ;
  - cas limite : Bridge tué **pendant l'encodage d'un PREPARE** (`--demo-fault slow-encode=4000`). Le job passe en `job_failed`, la liste des jobs en vol est vide, puis la partie reprend après relance.
- **Uploads corrompus** :
  - en intégration, `--demo-fault corrupt-upload=1` : refus sur le SHA-256, nouvel essai, puis `asset_stored` ;
  - en tests serveur (14 cas) : mauvais magic bytes, Ogg envoyé à un serveur AAC (MIME incohérent), contenu tronqué, SHA-256 faux ou mal formé, corps trop gros (annoncé ou en flux), jeton faux, expiré, rejoué, jeton d'un autre asset, asset sans job, identifiant d'asset malformé ;
  - un asset refusé n'est jamais `STORED` ni servi ; un seul nouvel essai sur le même morceau, puis le morceau est remplacé ; aucun jeton dans les logs.
- **Fichier supprimé après le scan** :
  - en intégration, `--demo-fault delete-track=1` : `track_unavailable code=NOT_FOUND`, remplacement automatique, aucun chemin dans la console du Bridge ;
  - côté Bridge : fichier supprimé, renommé ou remplacé après le scan → `NOT_FOUND`, et aucun message ne contient le nom, le dossier ou la racine.
  - Les cas lien symbolique et junction étaient déjà couverts par les tests du bac à sable ; ils n'ont pas été dupliqués.
- **Fin anticipée pendant OPEN** (intégration, paramétrée) :
  - `score` : OPEN → REVIEW (`ending`), aucun N+1 proposé, notation puis publication, `FINAL_SCORE_REVIEW` puis `FINAL_RESULTS` avec exactement les points attribués ;
  - `abandon` : directement `FINAL_SCORE_REVIEW` puis `FINAL_RESULTS`, 0 round joué, tous les scores à 0 alors que des réponses étaient validées ;
  - dans les deux cas : aucun job en vol et cache audio vide à la fin.
- **Heartbeat** (horloge contrôlable, balayeur exécuté dans la boucle de l'application) :
  - des PING réguliers maintiennent le joueur en ligne ;
  - un joueur silencieux passe OFFLINE seul (fermeture 1001), les autres le voient, puis il revient ONLINE avec la même session ;
  - le fait que le ready check ignore les joueurs OFFLINE reste couvert par le test du cœur.
- **Limitation de débit** :
  - des mots de passe faux répétés déclenchent 429 ; un mot de passe correct passe une fois la fenêtre écoulée ;
  - les succès ne comptent pas, même entrelacés avec des échecs ;
  - la limite du mot de passe hôte est distincte et ne bloque pas l'entrée des joueurs.
  - La spec §12 reste canonique et inchangée.
- **FFmpeg** :
  - des playlists ffconcat et HLS déguisées en `.mp3` sont refusées (`DECODE_ERROR`), même quand elles pointent dans la racine. C'est le complément multiplateforme de la régression junction, qui reste propre à Windows ;
  - des métacaractères de shell dans un nom de fichier restent de simples données ;
  - test de mutation manuel : en retirant `-format_whitelist`, les deux tests ffconcat échouent ;
  - [ADR 0008](adr/0008-ffmpeg-demuxer-whitelist.md) et `bridge-security.md` documentent la décision.
- **Fuzzer** : la machine à états Hypothesis du cœur reste le fuzzer permanent. Un profil `nightly` (3 000 séquences d'au plus 120 pas, environ 5 min) a été exécuté une fois en local sans rupture d'invariant ; il tourne chaque nuit en CI. Toute découverte devra devenir un test déterministe.

**E2E Playwright (Chromium)** — `web/e2e/game.spec.ts`, lancé par `tools/e2e_stack.py` (serveur servant `web/dist`, `DEV_MODE`, `CLIP_FORMAT=opus`, Bridge démo). Un hôte en mode joueur et deux joueurs, chacun dans son propre contexte, jouent 2 rounds en passant par l'interface :
- lobby, supplantation par un second onglet puis « Reprendre ici » ;
- réglages et dossier dans le tiroir hôte, lancement, compte à rebours ;
- VALIDER et « ✓ Réponse enregistrée » sans aucun temps affiché ; compteur « 1/3 ont validé » sans nom ;
- rechargement de la page en plein round : le brouillon est restauré, puis validé ;
- en REVIEW, le joueur ne voit ni les réponses, ni les temps, ni les rangs des autres ; l'hôte voit tout et note ;
- au reveal, tout le monde voit tout ;
- vérification finale : +2 pour un joueur et −1 pour l'hôte lui-même, affichés « avant → delta → après ». Les joueurs ne voient pas ce brouillon de correction ;
- confirmation, résultats (podium, scores, ajustements finaux), puis fin de session : tout le monde revient à l'écran d'entrée.

Contrôles transverses de l'E2E :
- **anti-spoiler** : les trames WebSocket reçues par chaque joueur avant REVEALED ne contiennent ni `relpath`, ni `track_id`, ni `elapsed_ms`, ni dossier, ni nom de fichier, ni titre ou artiste démo, ni la réponse d'un autre ;
- **audio** : chaque navigateur a envoyé `AUDIO_STATUS READY` (téléchargement et décodage) et un `PLAYBACK_REPORT` par round.

**Configuration headless** — Le Chromium de Playwright n'a pas de décodeur AAC, d'où les extraits Opus pour l'E2E. Le Chromium headless est lancé avec `--autoplay-policy=no-user-gesture-required` ; le test clique quand même sur « Tester mon audio ». Aucune vérification acoustique : seuls l'état, le décodage, la planification et les rapports sont vérifiés.

**WebKit** — Non validé. Sous Windows, le WebKit de Playwright n'expose pas `AudioContext`, et l'écran de déverrouillage audio ne peut pas se fermer. Le job nightly `e2e-webkit` tourne sous Linux sans être bloquant (`continue-on-error`) ; son premier passage échoue plus loin. L'audio se déverrouille et Alice valide, mais Bob n'affiche jamais « 1/3 ont validé » dans les 30 s. La relance échoue ensuite pour une raison d'isolation : la première tentative n'a pas atteint la fin de session, et les pseudos sont déjà pris. Cause non analysée (pas d'instantané de page dans le rapport) : **point ouvert**. Ce n'est **pas** une validation iOS.

**Reconnexion en E2E** — Couverte par le rechargement de page en plein round et par la supplantation via un second onglet. Une coupure réseau simulée (`setOffline`) n'est pas utilisée, car elle ne ferme pas de façon fiable un WebSocket déjà ouvert. La coupure brutale du transport est couverte en intégration.

**Bugs** — Aucun bug fonctionnel découvert.
- Défaut d'observabilité corrigé (`771da99`) : trois branches de refus d'upload (en-tête SHA-256 mal formé, corps annoncé trop gros, asset plus en vol) refusaient sans écrire `upload_rejected`.
- Défaut de test corrigé dans `47b2c20` : le test Windows de régression ffconcat passait aussi pour une mauvaise raison, car le dossier de travail du job n'existait pas. Le helper le crée désormais, et le test de mutation confirme que la protection est bien ce qui le fait passer.

**Zones touchées** — server/tests (integration, shell, conftest), server/src (`audio/routes.py`, logs uniquement), bridge/tests, tools (`bots.py`, `e2e_stack.py`), web (e2e, `playwright.config.ts`), CI (`e2e`, `nightly.yml`), docs (ADR 0008, `bridge-security.md`).

**Tests exécutés** (poste Windows du mainteneur)
- Ruff, ruff format, Pyright : OK.
- Python, `uv run pytest` (profil `ci`) : **498 réussis, 1 ignoré** (lien symbolique non autorisé sans le mode développeur Windows) :
  - protocole 143 ;
  - cœur 257 ;
  - shell serveur 65 ;
  - Bridge 33 + 1 ignoré.
- Intégration, `pytest server/tests/integration -m integration` : **8/8** (partie complète + 7 variantes, 4 min 17 s).
- Fuzzer `nightly` du cœur : 1/1 (4 min 55 s).
- Web : Biome OK, `tsc` OK, Vitest **21/21**, build OK.
- Playwright Chromium : **1/1** ; stabilité vérifiée sur 3 puis 5 répétitions consécutives, toutes réussies.
- Playwright WebKit (Windows) : 0/1, limitation de l'environnement décrite plus haut.

**GitHub** — Dépôt public `PrimoKG/OpenBlindySir` ; `main` poussé (`fd64827`). CI du push (run 36998584922) : 8/8 jobs verts (hygiene, python, protocol-drift, web, bridge-linux, bridge-windows, integration, **e2e** Chromium sous Linux). Nightly déclenché manuellement (run 36998597618) : `fuzz-core` vert ; `e2e-webkit` rouge (non bloquant), voir WebKit.

**Portes**
- G1: PENDING USER MEASUREMENT
- G2: PENDING USER MEASUREMENT

Elles ne bloquent pas l'étape 7, mais bloquent toute validation de release.

**État** — DONE pour l'étape 7 (robustesse).

**Problèmes connus**
- WebKit n'est pas validé : compteur non affiché chez un joueur sous WebKit Linux, à analyser avec la trace du nightly ; iOS et Android n'ont pas été testés sur appareils réels.
- L'absence du compteur quand moins de 3 joueurs sont attendus est couverte par les tests du cœur, pas en E2E.

**Prochaine étape** — Étape 8 (déploiement VPS et soirée alpha). Non commencée, en attente du feu vert.
