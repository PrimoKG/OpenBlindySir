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

## 2026-10-02 — Passe UX/UI du jeu

**Objectif** — Après lecture de la spec, du HANDOFF et du journal, améliorer le
frontend existant pour une soirée entre amis : priorité au joueur, actions hôte
contextuelles, identité cohérente et lecture confortable sur téléphone.

**Décisions**
- Réutilisation des composants React locaux et des éléments HTML natifs ; aucune
  bibliothèque de design, d'icônes ni police distante ajoutée.
- Fond papier, encre sombre, un accent terre cuite, corps à 17 px, titres Georgia
  et signature de disque en CSS. Contrastes des principaux textes vérifiés
  numériquement, cibles de boutons d'au moins 44 × 44 px et mouvement réduit.
- Une scène de jeu commune aux trois rôles. Les commandes hôte suivent la partie
  sur téléphone et restent à côté sur ordinateur ; la notation et la vérification
  finale prennent toute la largeur. Réglages avancés et diagnostic accessibles
  dans des disclosures natifs. Inspection, grammaire et parcours dans [UX.md](UX.md).
- Aucune modification du protocole, du cœur, des scores, des délais, des
  permissions ou du moteur de synchronisation audio.

**Implémentation et scénarios**
- Entrée avec pseudo puis mot de passe partagé, élévation hôte distincte,
  connexion en cours, erreur compréhensible et relance.
- Lobby avec test audio, confirmation entendue, volume et participants. La reprise
  audio reste dans le flux et ne recouvre plus les réponses ni les commandes hôte.
- Préparation, chargement, compte à rebours, lecture et fin d'extrait explicités.
  Brouillon restauré, validation vide désactivée, attente d'accusé et réponse
  définitive affichée ; aucun temps personnel anticipé ajouté.
- Revue lisible avec notation manuelle, temps, quasi-ex æquo, retard audio et
  brouillon capturé. Publication après les réponses. Révélation, classement,
  corrections finales, confirmation, podium, nouvelle partie et fin de session.
- Hôte joueur et MC vérifiés. Le MC voit la progression autorisée sans saisie de
  réponse ; les prochains morceaux restent accessibles dans « À venir ».
- Chargement/erreur de bibliothèque et diagnostic, échec audio et relance,
  reconnexion avec mutations hôte désactivées, reprise d'une session supplantée
  et exclusion explicites. Textes ajoutés dans les dictionnaires français et anglais.
- Trois parcours Playwright avec le vrai serveur et Bridge démo : deux parties de
  deux manches à 1280 et 320 px, puis une partie MC à 390 px avec réponse capturée,
  publication, résultats, nouvelle partie et retour au mode joueur. Les tests
  contrôlent aussi les trames anti-spoiler, READY/PLAYBACK_REPORT, la restauration
  du brouillon, les scores figés pendant la correction finale, les rangs partagés
  et l'absence de compteur pour les deux compétiteurs du MC.
- Seize scénarios d'interface complémentaires avec vues synthétiques : toutes les
  phases à 320/390/1280 px, textes longs, cibles et tableaux, démarrage forcé permis,
  Enter pour valider, focus/Échap du dialogue, erreurs et reconnexions, langue
  anglaise, contrastes et réduction de mouvement. Captures relues visuellement.

**Bugs réellement découverts**
- L'ancienne élévation restait mémorisée côté interface après une fin de session,
  puis une nouvelle entrée sur `/host`. Le formulaire d'élévation est de nouveau
  présenté. Les permissions du serveur n'étaient pas contournées.
- En OPEN, le serveur retire le PLAY actif à la fin ou à l'arrêt de l'extrait.
  L'affichage pouvait alors rester sur un état audio « prêt ». Il montre désormais
  « Extrait terminé », sans fermer le champ pendant le délai de réponse.
- Une régression de la refonte a été interceptée avant livraison : à 320 px, le
  réglage son dépassait le bord droit avec un pseudo court. Il est ancré à l'en-tête
  sur téléphone ; un test couvre les pseudos courts et longs.
- L'E2E précédent laissait une session non terminée après un échec, ce qui pouvait
  bloquer les relances avec des pseudos déjà pris. Nettoyage du salon de test avant
  et après chaque parcours réel par les commandes existantes. Cela ne constitue
  pas une résolution de l'échec du compteur WebKit Linux.

**Zones touchées** — `web/src/app`, `web/src/player`, `web/src/host`,
`web/src/ui/components.tsx`, `web/src/styles.css`, les deux dictionnaires i18n,
`web/tests/presentation.test.ts`, `web/e2e`, `CHANGELOG.md`, `docs/UX.md` et ce journal.
Le `docs/HANDOFF.md` préexistant est laissé intact et hors des commits.

**Tests exécutés** — Poste Windows, Chromium headless installé dans le cache
ignoré de `web/node_modules`, pile serveur et Bridge démo dédiée aux tests (8766).
- Python ciblé : `.venv/Scripts/python.exe -m pytest
  server/tests/game/test_views_leak_matrix.py server/tests/game/test_permissions.py
  server/tests/game/test_final_review.py -p no:cacheprovider --basetemp
  web/test-results/python-ui-checks` : **123/123**.
- Intégration Python : **non relancée** pendant cette passe frontend.
- Bridge unitaire : **non relancé** ; le Bridge démo réel est exercé par les trois
  parcours navigateur. Les sons restent synthétiques, aucune musique personnelle.
- Web : `npm run lint` **OK**, `npm run typecheck` (dans le build) **OK**, Vitest
  `npm run test` **28/28**, dont sept cas de présentation de l'extrait.
- Playwright Chromium : `E2E_PORT=8766`, cache navigateur local puis `npm run e2e`
  **19/19**, dernière exécution **53,4 s**. Le contrôle ajouté sur le réglage son
  avait d'abord échoué à 320 px (bord droit à 444,6 px), puis la suite complète est
  passée après correction. Des échecs intermédiaires de fixture/type, d'état de
  disclosure et d'isolation ont été corrigés avant ce résultat final.
- Playwright WebKit : **non exécuté**, toujours non validé ; aucun appareil iOS ou
  Android réel testé. Les extraits E2E sont Opus et le navigateur est muet : pas de
  mesure acoustique ni de validation AAC de production.
- Build : `npm run build` **OK** ; types et compilation Vite passent.
- `git diff --check` **OK**. Hygiène exécutée après chaque `git add` avant les
  commits ; aucun secret, son, build, cache, capture ou dépendance indexé.
- Environnement : le premier pytest avait réussi les assertions mais terminé en
  erreur en écrivant le cache préexistant interdit ; relance sans cache réussie.
  Le navigateur Chromium était absent et a été installé dans le dossier ignoré.
  Ces ajustements ne changent ni les dépendances du projet ni les règles du jeu.

**Git / GitHub** — Branche locale `codex/ux-game-experience`, issue de `main`
`8d240d0`. Commits granulaires : `04275c8`
(`feat(web): refresh game screens and shared visual language`), `871754c`
(`test(web): cover responsive game and host journeys`), puis documentation séparée.
Aucun push ni PR pendant cette intervention : résultat livré localement pour
revue visuelle. Aucune nouvelle CI GitHub déclenchée ; les résultats ci-dessus
sont locaux. Aucun squash, merge ni release.

**Gates**
- G1: PENDING USER MEASUREMENT
- G2: PENDING USER MEASUREMENT

**État** — DONE pour la passe UX/UI et les vérifications locales demandées.

**Restant / problèmes connus** — WebKit Linux (compteur) reste ouvert ; Safari,
iOS et Android demandent de vrais appareils. Le contrôle de contraste ne remplace
pas un audit d'accessibilité complet. La vraie bibliothèque du mainteneur, G1/G2,
le VPS et toute release restent hors de cette intervention.

**Prochaine étape recommandée** — Revue sur appareils réels des vues joueur et
hôte, en gardant G1/G2 en attente jusqu'aux mesures du mainteneur.

## 2026-10-02 — Guides utilisateur et hébergement natif sur PC

**Objectif** — À la demande du mainteneur, documenter concrètement l'usage du jeu,
permettre le serveur sur son propre PC pour un LAN ou une partie distante, puis
commiter, fusionner et pousser les changements après validation.

**Décisions**
- Le VPS reste facultatif : même serveur, même processus, même protocole. Pas
  d'ajout de room, de compte, de persistance ni de changement des règles du jeu.
- `tools/host_pc.py` supervise le serveur existant et le binaire Caddy standard.
  `init` génère une configuration privée et trois secrets sans écraser un fichier
  existant ; `run` valide le build/config puis lance les deux services. Une panne
  d'un service et Ctrl+C entraînent l'arrêt de l'autre.
- Profil privé : IP LAN ou VPN choisie, HTTPS avec autorité locale à approuver par
  les appareils ; profil public : domaine, HTTPS et TCP 80/443 redirigés vers le
  PC. Les procédures box, pare-feu, VPN et certificats sont documentées ; aucune
  de ces configurations système/réseau n'est appliquée sur le poste par l'agent.
- Backend uniquement sur 127.0.0.1, proxy approuvé uniquement en boucle locale,
  cookies Secure et origine exacte conservés ; DEV_MODE refusé pour ce lanceur.
  Caddy n'installe pas automatiquement une autorité privée dans la confiance
  système. Son administration est désactivée dans les deux profils.
- Données Caddy dans `.local/`, ignorées et interdites par le contrôle d'hygiène
  même en cas d'indexation forcée. Le binaire utilisé pour les vérifications reste
  dans un cache ignoré, sans installation globale ou dépendance Python/JS ajoutée.
- Guides en français, correspondant aux textes de l'interface actuelle ; README
  public anglais corrigé pour supprimer « rien n'est jouable » et l'obligation VPS.

**Implémentation / zones touchées**
- `tools/host_pc.py`, `deploy/Caddyfile.pc.private`, `deploy/Caddyfile.pc.public`,
  `.gitignore`, `.env.example`, `tools/check_repo_hygiene.py`.
- `docs/guide-utilisateur.md` : rejoindre, audio, brouillon/validation, attente,
  révélation, hôte joueur/MC, notation, corrections, résultats et dépannage.
- `docs/deployment.md` : prérequis, installation, adresses LAN/VPN/Internet,
  lancement, arrêt, confiance TLS, Bridge sur le même PC ou ailleurs, DNS/NAT,
  pare-feu, maintien du PC allumé et perte de la partie à l'arrêt.
- `README.md`, `CHANGELOG.md`, ajout du parcours PC à `docs/architecture.md`.
- `server/tests/shell/test_host_pc.py` : 32 nouveaux cas, dont adresses canoniques
  (IPv4/IPv6 et port standard), entrées ambiguës refusées, secrets conservés,
  génération sans BOM, origine exacte, loopback et arrêt après échec d'un service.
- `server/tests/integration/conftest.py` : isolation du format/niveau de logs.

**Bugs réellement découverts**
- Quatre scénarios d'intégration jouaient correctement mais échouaient sur leurs
  assertions `event=...` : le terminal hérite de `LOG_FORMAT=json`. Le fixture
  subprocess impose maintenant `LOG_FORMAT=text` et `LOG_LEVEL=INFO`. Après
  correction, les huit scénarios passent en gardant JSON dans le terminal parent.
- Les validations du nouveau lanceur ont aussi intercepté le port zéro et une
  collision entre port HTTPS et port interne ; ces configurations sont refusées.
  Aucun nouveau défaut des règles métier découvert.

**Tests exécutés** — Windows, FFmpeg 9.0.2 local, Caddy officiel **2.11.6** en cache.
- Python : `.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp
  web/test-results/python-pc-full`, avec FFmpeg dans PATH et profil Hypothesis `ci`
  : **530 réussis, 1 ignoré, 8 désélectionnés**, 15,84 s. Détail : protocole 143,
  cœur 257, shell serveur 97, Bridge 33 ; le lien symbolique reste ignoré Windows.
- Intégration : `pytest server/tests/integration -m integration
  -p no:cacheprovider --basetemp web/test-results/python-pc-integration-fixed` :
  **8/8**, 264,02 s. Premier passage : 4/8 réussis, quatre assertions de format
  héritées échouées, comme expliqué ci-dessus.
- Bridge : **33 réussis + 1 ignoré**, inclus dans la suite Python ; les huit
  scénarios d'intégration utilisent aussi le Bridge démo réel avec sons synthétiques.
- Lanceur/configuration : tests ciblés `test_host_pc.py` + `test_config.py`
  **46/46** ; inclus ensuite dans la suite complète.
- Caddy : adaptation et validation réelles des **deux profils** ; écoute privée
  sur l'interface choisie, publique sur 443, upstream loopback, administration
  désactivée. Aucun démarrage public ni émission ACME Internet effectué.
- Smoke HTTPS réel : serveur + Caddy, certificat vérifié avec la racine de test,
  build Web servi, mauvaise origine refusée, entrée/élévation, cookie `__Host-`
  Secure/HttpOnly et WSS jusqu'à STATE LOBBY ; arrêt des enfants contrôlé. PASS
  pour localhost et 127.0.0.1, puis **trois répétitions consécutives** sur l'IP.
  Le premier probe avait échoué sur une entrée ; sa boucle de readiness pouvait
  rejouer une entrée après avoir perdu les cookies. Le retry après readiness a
  été supprimé avant les répétitions. Ce probe ponctuel reste dans le cache ignoré.
- Hygiène : contrôle positif de l'index après chaque `git add` ; contrôle négatif
  dans un dépôt jetable, `.local/example-state.json` indexé → refus attendu.
- Ruff et format : **OK**. Pyright : **0 erreur** avec
  `--pythonpath .venv/Scripts/python.exe` (le premier appel sans ce chemin cherchait
  les imports dans le Python système). Génération protocole `--check` : **OK**,
  aucune dérive. `git diff --check` : **OK**.
- Web/Vitest : **28/28**, Biome et typecheck **OK**, build **OK** ; Playwright
  Chromium **19/19**, vérifications de la passe UX précédente, code UI inchangé
  pendant cette extension d'hébergement. La CI de PR devra les réexécuter.
- Playwright WebKit : **non exécuté** ; aucun iOS/Android réel ni mesure acoustique.

**Git / GitHub** — Branche `codex/ux-game-experience`. Commits de cette extension :
`d8f598c` (`feat(tools): support native PC hosting over HTTPS`) et `ad0cffe`
(`test(server): isolate integration logging from caller`), puis guides et journal
dans un commit distinct. Les trois commits UX antérieurs sont conservés. Le
mainteneur a explicitement demandé le commit, la fusion et le push ; la branche
sera soumise en PR, fusionnée par rebase après CI verte, puis `main` synchronisée.
L'état distant final et l'URL de PR sont rapportés dans le compte rendu de fin.

**Gates**
- G1: PENDING USER MEASUREMENT
- G2: PENDING USER MEASUREMENT

**État** — DONE pour le code, les guides et les vérifications locales.

**Restant** — Essai sur de vrais appareils LAN/VPN et configuration de la box pour
un accès public ; aucun port ni confiance système modifié ici. WebKit Linux,
mesures G1/G2, vraie bibliothèque, déploiement VPS/Docker et release restent ouverts.

**Prochaine étape recommandée** — Suivre `docs/deployment.md` avec l'adresse LAN
ou VPN réelle du PC, puis faire une partie d'essai avec les appareils des participants.

## 2026-10-02 — Environnement complet Docker (implémentation)

**Objectif** — GO du mainteneur pour isoler serveur, interface construite, Caddy
et Bridge/FFmpeg dans Docker ; conserver le parcours manuel et ouvrir `/host`
dans le navigateur avec un lanceur local.

**Décisions / modifications** — Dockerfile multi-stage avec cibles app et bridge,
bases multi-architecture fixées par digest, dépendances Python/npm verrouillées.
FFmpeg est uniquement dans le Bridge ; ses paquets Debian sont installés au build.
L'app est non root, le dossier musical est monté en lecture seule, les secrets
et données privées restent hors du contexte de build grâce à une allowlist.
Les services partagent un espace réseau pour conserver le backend en boucle
locale, le Bridge HTTP localhost autorisé et les proxies approuvés loopback.
Seuls HTTPS et, en public, HTTP pour certificats/redirection sont publiés.
Configuration privée générée dans un conteneur sans Python hôte ; lanceurs
PowerShell et POSIX init/start/stop/status/open/certificate. Les données Caddy
et l'identité du Bridge persistent en volumes, pas la partie en RAM.
Les variables du lancement natif ne remplacent pas les réglages du lanceur.

**Tests locaux exécutés** — `pytest test_docker_config.py test_host_pc.py` :
43/43, dont 11 nouveaux cas Docker. Ruff/format : OK ; Pyright avec le Python
du venv : 0 erreur. Parsing PowerShell : OK. `docker compose config --quiet`
avec configuration privée générée : OK. Moteur Docker Desktop arrêté au départ ;
`docker desktop start` lancé, mais son API ne répond toujours pas. Aucun test
conteneur local n'est encore déclaré réussi. Validation réelle prévue dans
le nouveau job Docker CI : init PowerShell, build, services, certificat vérifié,
UI, origine, cookie Secure, WSS, clips, deux manches et résultats, arrêt POSIX.
Les bots de test acceptent une autorité TLS explicite, sans désactiver TLS.

**Bugs réellement découverts** — Aucun nouveau bug métier. Pendant cette
implémentation, publication IPv6 passée en syntaxe longue et typage des options
WebSocket TLS corrigés avant commit. Le tag Caddy 2.11.6-alpine n'existe pas
dans le registre ; l'image officielle disponible 2.11.4 est fixée par digest.

**Git / GitHub** — Issue #5, branche `codex/full-docker-hosting` depuis main
`a2c717b`. Commits granulaires, PR et CI avant rebase-merge et push demandés.
Le HANDOFF préexistant reste intact et non suivi. Guides et résultat distant
seront consignés dans une entrée supplémentaire après validation.

**Gates** — G1: PENDING USER MEASUREMENT ; G2: PENDING USER MEASUREMENT.
**État** — PARTIAL : code et validations statiques prêts, conteneurs/CI et guides
en cours. Pas de VPS, soirée réelle, mesure acoustique ou release.
**Restant** — Validation des images/partie Docker, guides, publication Git.
**Prochaine étape recommandée** — Exécuter la partie Docker synthétique en CI.

## 2026-10-02 — Docker : partie réelle, distribution locale et guides

**Objectif / décisions** — Finaliser le GO full Docker avec parcours manuel
conservé, guides d'installation et utilisation du navigateur. Les deux images
applicatives peuvent être exportées/importées sur des PC de même architecture ;
chaque hôte conserve ses propres secrets et chemins. Pas de publication GHCR,
VPS ou release ajoutée. Bridge distant avec Compose et racine TLS en montage
read-only. Les lanceurs démarrent la pile en arrière-plan et ouvrent `/host` ;
absence de navigateur traité par affichage de l'URL. Pas d'installation de confiance
TLS ni modification automatique de pare-feu ou de réseau.

**Modifications** — `docs/docker.md` couvre installation Docker/WSL, ZIP sans Git,
init/start Windows et POSIX, certificats, LAN/VPN/public, arrêt et perte de l'état
RAM, partage exact des images, Bridge distant et dépannage. README, guide natif,
guide utilisateur, CONTRIBUTING, architecture, `.env.example`, CHANGELOG adaptés.
Les réglages proxy natifs et Docker sont loopback. Deux fichiers Compose pour
Bridge distant, validation des profils dans le smoke et contrôle public Caddy.

**Bugs réellement découverts / corrections**
- Sous PowerShell Unix, vider les variables avec l'API .NET les laissait vides
  dans l'environnement enfant, masquant le fichier Compose. Suppression/restauration
  via le provider Env ; le lanceur init/start réel est passé ensuite.
- HTTPS par IP sans SNI ne sélectionnait pas le certificat privé Caddy 2.11.4.
  `default_sni` utilise le nom/IP du certificat, avec variable séparée pour IPv6.
  TLS vérifié passe ensuite, sans contournement de certificat.
- Le smoke attendait un état Bridge dans `/healthz`, qui est volontairement masqué
  hors développement. L'attente utilise maintenant la vue hôte authentifiée des
  bots. Aucun changement du endpoint ni des permissions.
- `docker cp` vers le rootfs read-only refusait même un chemin tmpfs ; le contrôle
  public écrit par `exec` dans `/tmp`, sans assouplir le filesystem read-only.

**Tests exécutés**
- Python complet local : `.venv/Scripts/python.exe -m pytest -p no:cacheprovider
  --basetemp web/test-results/python-docker-full`, FFmpeg local dans PATH et
  Hypothesis ci : **541 réussis, 1 ignoré, 8 désélectionnés**, 12,19 s.
  Bridge inclus : **33 réussis + 1 ignoré** (symlink Windows non autorisé).
- Configuration ciblée : **43/43**, dont 11 Docker ; sélection SNI **11/11**.
- Ruff/check/format : **OK**, 151 fichiers ; Pyright venv : **0 erreur** ; parser
  PowerShell : **OK**. Compose privé/public/Bridge distant : **PASS** localement,
  sans impression de secrets. Protocole/core/audio inchangés.
- CI run **37047817661** : images app/web et Bridge construites réellement sous
  Linux amd64 ; Python 3.13 dans les images, FFmpeg Debian **5.1.9**, AAC/Opus/FLAC
  disponibles. Init PowerShell sans Python hôte, start et export racine **PASS**.
  `tools/docker_smoke.py` : profils, HTTPS vérifié, UI servie, CSP/HSTS, mauvaise
  origine 403, cookie Secure/HttpOnly, Bridge connecté, extraits synthétiques,
  WSS, réponses, deux manches, revue finale et résultats **PASS**.
  Utilisateur app 10001, FFmpeg absent du serveur, musique montée read-only **PASS**.
  Ce run a échoué ensuite uniquement sur le `docker cp` du contrôle public,
  corrigé comme ci-dessus ; validation finale CI à confirmer sur la nouvelle tête.
- Intégration native CI : **8/8** ; Web/Vitest : **28/28** ; Chromium : **19/19** ;
  build : **OK**. WebKit **non exécuté**, G1/G2 et vrais appareils non mesurés.
- Docker Desktop local : démarrage tenté, puis erreur de son Inference manager
  sur le socket `dockerInference`. Aucun reset, suppression de données Docker
  ou modification système effectué. Les tests conteneurs sont ceux de CI Linux,
  pas une affirmation de lancement réussi sur le PC Windows.
- Hygiène de l'index après git add et avant chaque commit : **OK** ; aucun secret,
  musique, image Docker, certificat ou cache commité. Une interpolation YAML avec
  espaces a été citée explicitement pour éviter un faux positif du scanner.

**Git / GitHub** — Issue #5, PR #6 attachée au chat, branche
`codex/full-docker-hosting`. Commits déjà poussés : `db7adab` feat Docker,
`e5e70ba` tests, `b7a6884` correction Env, `6af7887` correction SNI,
`b9c6bcd` Bridge distant/profils ; correctif des checks et guides dans des commits
séparés. Rebase-merge après CI verte puis sync/push main, autorisés par le mainteneur.
Résultat distant final rapporté dans la conversation ; HANDOFF laissé intact.

**Gates** — G1: PENDING USER MEASUREMENT ; G2: PENDING USER MEASUREMENT.
**État** — DONE pour code, guides et partie Docker réelle ; CI finale et fusion
en cours à l'écriture de cette entrée.
**Restant** — Docker Desktop de ce PC à rendre opérationnel ; appareils LAN/VPN,
Internet réel, arm64, Bridge réellement distant et vraie bibliothèque à tester.
GHCR/VPS, soirée, WebKit, G1/G2 et release restent hors de cette intervention.
**Prochaine étape recommandée** — Une fois Docker opérationnel, lancer une démo
locale avec `tools/docker-host.ps1 init -Address localhost:8443 -Demo`, puis `start`.

## 2026-10-03 — Retour vidéo : parcours de soirée, notation et reprise

**Objectif / autorisation** — Après l'analyse des deux enregistrements fournis,
le mainteneur a donné le GO « implémenter tout ça ». Appliquer les améliorations
du parcours sans attribuer automatiquement des points : préparation explicite,
revue exploitable, pause, récupération, résultats détaillés et confort mobile.
Travail séquentiel local sur `codex/ux-game-night`, depuis `main` `e6b9567`.

**Décisions / principales modifications**
- Protocole **2** pour serveur, Bridge et web ; modèles Python stricts, types TS
  et schema lock régénérés. Les trois composants se mettent à jour ensemble.
- Réserve : morceaux disponibles/neufs, sélection parent/enfant sans doublon,
  réduction des manches, lancement atomique avec les nouveaux réglages et
  récupération d'une réserve épuisée. Les scores repartent de zéro à la nouvelle
  partie ; les morceaux entendus restent exclus pendant la soirée.
- Revue : morceau courant privé pour l'hôte après fermeture des réponses,
  nettoyage conservateur et correction titre/artiste, zéro explicitement vérifié,
  compteur des lignes vérifiées, brouillons numériques locaux et attente de
  l'accusé serveur. Confirmation nécessaire pour publier des lignes non vérifiées.
- Consigne, réponse attendue, barème titre/artiste et politique des brouillons
  partagés ; notation manuelle, sans bonus de vitesse. Permissions de rôle
  alignées entre commandes affichées et handlers.
- Pause/reprise du son et du délai sur des instants serveur, avec position
  conservée et suspension exclue du temps de réponse. Arrêt et départ utilisent
  la même conversion d'horloge et de latence de sortie.
- Snapshots JSON atomiques privés avec repli sur la version précédente : cookies
  hachés, réponses, réglages, scores et historique, sans audio ni secrets en clair.
  Une manche OPEN interrompue devient REVIEW avec brouillons capturés et alerte.
  Le conteneur utilise `app_data:/data` ; une erreur de sauvegarde avertit l'hôte.
- Récapitulatif par manche/joueur, corrections et exports JSON/CSV avec protection
  des formules CSV ; historique hôte des 50 dernières parties. QR sans mot de
  passe, sélections favorites locales, équipes par somme des points individuels
  et spectateurs exclus des réponses, scores et joueurs attendus au départ.
- Bandeau compact, délai de réponse distinct de la fin audio, focus ordinateur
  sans ouverture automatique du clavier mobile, défilement de page pour l'hôte,
  états d'erreur récupérables, cibles tactiles et dictionnaires FR/EN.
- Bridge : `loudnorm` fixe, évitement du silence sur trois fenêtres bornées,
  traitement des enregistrements faibles et diagnostic privé des fichiers
  écartés lorsqu'ils sont rencontrés. Le scan initial reste sans ffprobe global.
- ADR 0009 remplace la non-persistance de 0005 ; ADR 0010 documente les décisions
  de produit. Spécification, protocole, synchronisation, sécurité Bridge,
  CHANGELOG, README et guides mis à jour. Checklist manuelle dans `docs/testing.md`.

**Bugs réellement découverts / corrections**
- Une petite réserve ou des morceaux déjà entendus pouvaient laisser une nouvelle
  partie en préparation ; diagnostic explicite et répétitions récupérables.
  La reconstruction de réserve avec un seul morceau accepte maintenant les répétitions.
- Le changement de rôle présenté par l'interface ne suivait pas exactement le
  handler. Un même prédicat gouverne désormais la permission et l'action.
- Le zéro initial de notation était indiscernable d'une décision explicite ;
  `reviewed` sépare ces états. Les échos serveur pouvaient perturber une saisie
  numérique ; la modification reste locale jusqu'à sa validation et son accusé.
- Un seuil de silence trop strict écartait les morceaux faibles pourtant
  normalisables. Les essais synthétiques contrôlent le gain obtenu et la
  conservation d'un signal faible, ainsi que le rejet d'un silence réel.
- Au démarrage, la purge Bridge supprimait les dossiers temporaires d'une autre
  instance active. Le problème a été reproduit en lançant plusieurs piles de
  test. Marqueur PID et détection sûre Windows/POSIX protègent maintenant les
  processus actifs ; les dossiers anciens sans propriétaire sont conservés.
- WebKit mobile débordait horizontalement avec l'option longue des brouillons.
  Sélecteur borné et options raccourcies ; vérification 320/390/1280 px réussie.
- La relecture visuelle a révélé une consigne demandant à l'animateur de noter sa
  propre réponse. Le texte dépend maintenant de sa participation effective.

**Tests réellement exécutés**
- **Python** : `.venv/Scripts/python.exe -m pytest -p no:cacheprovider
  --basetemp=.local/pytest-ux-complete-4`, FFmpeg/ffprobe dans PATH et Hypothesis
  profil ci : **585 réussis, 1 ignoré, 8 intégration désélectionnés**, 27,53 s.
  Le test ignoré nécessite la création de symlinks non autorisée sur ce Windows.
- **Intégration** : suite complète serveur + Bridge démo : **8/8**, 285,19 s.
  Après le correctif de purge et la notification des erreurs de snapshot,
  `pytest server/tests/integration/test_full_game.py -m integration` a reconfirmé
  la partie complète avec dix bots : **1/1**, 47,90 s.
- **Bridge** : `pytest bridge/tests -p no:cacheprovider` : **39 réussis, 1 ignoré**,
  9,24 s. FFmpeg réel, confinement, codecs, normalisation/silence et protection
  des instances actives. Ces tests sont inclus dans la suite Python complète.
- **Statique Python/protocole** : Ruff check/format **OK** (162 fichiers), Pyright
  avec `.venv/Scripts/python.exe` : **0 erreur** ; `tools/gen_ts_types.py --check` :
  types et schema lock **à jour**. Les bots n'utilisent plus un protocole 1 codé en dur.
- **Web/Vitest** : `npm run lint` **OK** (46 fichiers), `npm test` : **31/31**, quatre
  fichiers, sur la version finale. Capacités, clés de réglages, export CSV et
  comportement de l'application couverts.
- **Playwright Chromium** : `playwright test --project=chromium` : **22/22**,
  1,2 min. Trois parties réelles (bureau/mobile/animateur), pause, réponses,
  reconnexion, confidentialité et résultats, plus 19 scénarios d'interface.
  Après la dernière correction de texte, parcours animateur reconfirmé : **1/1**,
  23,4 s. Captures relues visuellement, dont revue MC et corrections finales mobile.
- **Playwright WebKit** : suite complète **18 réussis, 4 ignorés**, 43,5 s.
  Probe direct : `AudioContext` et `webkitAudioContext` absents dans ce build
  Windows. Les trois parties audio et le test de téléchargement audio sont
  explicitement ignorés par capacité ; les tests d'affichage restent exécutés.
  Cela ne valide ni Safari réel ni l'audio iOS.
- **Build** : TypeScript/Vite **OK**, 75 modules, bundle final 349,50 kB brut /
  107,81 kB gzip. Docker app réellement construit sous Python 3.13.16 depuis un
  contexte filtré d'environ 844 kB, sans parcourir les caches personnels.
- **Docker** : image/UI, utilisateur **10001**, snapshot propriétaire 10001 et
  mode **0600** : **PASS**. Deux conteneurs jetables ont partagé un volume de test ;
  après SIGKILL et remplacement du premier conteneur, le second a restauré le
  cookie hôte, l'identité, l'epoch et les réglages. Conteneurs et volume de test
  supprimés. Ce contrôle cible le backend ; pas de nouveau test Caddy/TLS/VPS.
- **Hygiène** : `tools/check_repo_hygiene.py` exécuté après staging et avant les
  commits ; index et `git diff --cached --check` **OK**. Aucun enregistrement vidéo,
  morceau réel, secret, configuration personnelle ou cache ajouté à Git.

**Échecs / limites observées** — Les premières relances ont identifié des
locators E2E devenus ambigus et les bots restés en protocole 1 ; corrigés.
L'environnement a nécessité un interpréteur explicite pour Playwright et des
répertoires de sortie neufs. Les tests désactivent le cache pytest pour éviter
les différences d'ACL entre exécutions sandboxées et escaladées. Une fermeture
volontaire de socket peut produire un callback `ConnectionResetError` Windows
dans les logs ; les scénarios concernés passent. Aucun masquage du défaut ajouté.

**Git / GitHub** — Branche locale `codex/ux-game-night` ;
`72532ff fix(bridge): preserve temporary audio owned by live processes`,
`ecfba4e feat: add resilient game-night controls and scoring UX`.
Un commit documentaire distinct finalise les guides et ce compte rendu.
Pas de push, PR, fusion, déploiement ou release dans cette intervention.
Le HANDOFF historique préexistant est resté intact et ignoré par Git.

**Gates** — G1: PENDING USER MEASUREMENT ; G2: PENDING USER MEASUREMENT.
**État** — DONE pour l'implémentation et les validations locales disponibles.
**Restant** — Safari/iPhone/Android réels, AAC de production, vraie bibliothèque,
réseau/Bridge distant et mesures acoustiques/performances G1/G2. Les snapshots
contiennent des réponses et des chemins privés et nécessitent des sauvegardes
protégées ; aucune migration future du format local n'est promise.
**Prochaine étape recommandée** — Mettre à jour les trois composants et rejouer
une soirée de test sur les appareils et la bibliothèque du mainteneur selon
`docs/testing.md`, puis consigner les mesures.


## 2026-10-03 — Périmètre V0.2 : revue globale, sources et audio des vidéos

**Objectif** — Implémenter la demande de revue de fin de partie, réécoute privée,
vidéos utilisées comme sources audio, bibliothèque dynamique/recherche/métadonnées,
arrêt dans toutes les phases et éléments V0.2 annoncés. Dépôt initialement propre ;
README, guides, spec/roadmap, ADR et code relus. Pause/reprise, loudnorm/silence,
snapshots, exports, équipes/spectateurs, presets/QR et styles existants réutilisés.
La sélection manuelle de piste reste V0.3 ; équilibre par dossier, réponses MC,
latence locale, récupération par code et verrou d'inscription sont bien V0.2.

**Décisions** — [ADR 0011](adr/0011-global-review-and-private-replay.md),
[ADR 0012](adr/0012-dynamic-sources-and-metadata.md).

- Fermeture des manches sans points/reveal intermédiaires. Toutes les manches
  entendues gardent réponses, participants, entrée de catalogue et timing.
  Revue globale privée, notes signées ±1000 et zéro explicitement vérifié,
  brouillons persistés, totaux joueurs/équipes et confirmation finale atomique.
  Manches entendues annulées conservées avec zéro ; arrêt avant départ ne crée
  pas une manche entendue. Arrêt idempotent, STOP et nettoyage du pipeline.
- Protocole **3**, snapshot **2**, types TS/schema lock générés. Migration V1 des
  parties non terminées : anciennes publications reportées en brouillons avec
  révocations auditables ; archives finales préservées. Les anciennes commandes
  publish/undo/adjust restent reconnues mais ne sont plus autorisées.
- Sortie AAC/M4A **128 kb/s** inchangée ; Opus/WebM configurable. Liste blanche
  partagée scanner/probe/encode, démultiplexeur imposé par extension, file seul,
  références externes MOV désactivées, première piste audio, pas de vidéo/tags.
  Absence d'audio distincte, sous-processus/sorties/temps bornés.
- Réécoute SHA-256 exacte via cache Bridge d'extraits **64 MiB**, sans changer la
  lecture des joueurs. Écoute intégrale désactivée par défaut, opt-in local,
  segments réencodés ≤30 s, deux transferts privés serveur ≤2 MiB et un Blob
  navigateur. Révision de source vérifiée ; jamais d'upload du fichier original.
- Huit Bridges, tokens/jobs liés au propriétaire, rescans relatifs/NFC sous racine
  autorisée, aucun lien/junction, identités stables et diagnostics des collisions.
  Nouvelle racine/montage Docker : intervention locale et seul Bridge recréé.
  Recherche/filtres/pagination/arbre privés à l'hôte au moment autorisé.
- Métadonnées facultatives JSON version 1 : UUID + chemin relatif NFC, cinq champs,
  lignes valides acceptées indépendamment des diagnostics, priorité manuelle puis
  import puis tags/nom nettoyé. Valeurs importées préservées ; effacer une correction
  rétablit son repli. Accusé de révision, correction commune aux manches répétées,
  snapshot/export. Fin de session garde archives et métadonnées.
- Français/English, correction locale de latence ±500 ms, code de récupération
  privé/à usage unique sans rôle hôte, inscriptions verrouillables, MC en direct.
  Guides FR/EN, procédure Docker, UX, architecture, roadmap, ADR et changelog à jour.

**Vérifications réellement exécutées**

- Python : `.venv/Scripts/python.exe .local/run_v02_pytest.py -m 'not integration'
  -q -p no:cacheprovider` : **673 réussis, 1 ignoré, 8 désélectionnés**, 19,07 s.
  Le wrapper local configure FFmpeg/ffprobe réels dans l'environnement Python,
  sans dépendre de l'héritage PATH du terminal sandboxé. Le seul skip est la
  création de symlink non autorisée sur ce Windows ; le test de junction réel passe.
- Intégration : même wrapper avec `-m integration -q -p no:cacheprovider` :
  **8/8**, 244,10 s. Serveur + Bridge démo, dix bots, variantes et fins anticipées.
- Bridge/FFmpeg réel : inclus dans Python, MP4/MOV/MKV/AVI avec audio seul,
  piste absente, deux pistes dont la seconde par défaut, vidéo >96 MiB,
  playlist déguisée, replay identique après suppression source, full opt-in,
  segments bornés/source modifiée et copie partielle du cache en échec.
- Ruff `check .` et `format --check .` : **OK**, 178 fichiers. Pyright
  `--pythonpath .venv/Scripts/python.exe` : **0 erreur/avertissement**.
  `tools/gen_ts_types.py --check` : **types + lock à jour**. `git diff --check` : OK.
- Web : `npm run lint` **OK**, 50 fichiers ; `npm test` **32/32**, cinq fichiers ;
  `npm run build` (TypeScript/Vite) **OK**, 78 modules, JS 379,26 kB / 115,91 kB gzip.
- Chromium : `playwright test --project=chromium` via wrapper local :
  **26/26**, 1,3 min. Trois parties réelles, extrait/full privés décodés,
  aucune lecture collective de réécoute, mobile 320/390, bureau 1280, clavier,
  anti-spoiler, recherche/erreurs, notation/métadonnées confirmées et récupération.
  Captures relues, dont revue globale mobile/bureau, erreurs et résultats.
- WebKit : `playwright test --project=webkit` : **22 réussis, 4 ignorés**, 39,8 s.
  Ce build Windows n'a pas `AudioContext` ; trois parties audio et le test de
  téléchargement sont explicitement ignorés. Aucun résultat ne valide Safari/iOS réel.
- Docker : images `openblindysir-server:v02-check` et `openblindysir-bridge:v02-check`
  construites depuis un contexte filtré ~946 kB (Python 3.13.16, dépendances locked).
  Probe Bridge finale : conteneur jetable, réseau désactivé, racine read-only,
  cap_drop ALL/no-new-privileges, uid 10001, tmpfs 128 MiB ; MP4/MOV/MKV/AVI
  convertis en AAC audio seul, tags absents et NO_AUDIO vérifiés. App uid 10001,
  protocole 3 et absence de FFmpeg vérifiés. Compose principal/distant : montage
  musical read-only et opt-in false/true vérifiés avec valeurs synthétiques.
  Aucun déploiement Caddy/TLS/LAN/VPS de production effectué.
- Hygiène : contenu actuel des **262 fichiers** suivis/non ignorés lu avec
  `check_worktree_file` (l'index inchangé ne contient pas encore les modifications) :
  **0 constat**. Aucun audio/vidéo réel, secret ou cache ajouté à Git ; médias de
  test synthétiques et outils temporaires uniquement dans les emplacements ignorés.

**Régressions corrigées pendant les contrôles** — Les options MOV spécifiques
ne doivent pas être appliquées aux autres démultiplexeurs : les vrais tests FFmpeg
ont détecté puis confirmé le correctif. Les bots/tests E2E attendaient encore
notation/reveal par manche : adaptés à la revue globale et aux accusés serveur.
L'écran d'attente joueur gardait un ancien classement vide : retiré et texte
actualisé. Corrections de métadonnées vides/repli importé, manches répétées,
busy à la sortie de revue et cache local plein sont couverts. Le lancement
Playwright sandboxé bloquait la fermeture de processus Windows ; le contrôle
local autorisé a permis de terminer les suites. Le callback Windows
`ConnectionResetError` peut apparaître lors des fermetures volontaires ; tests verts.

**Livraison / limites** — Modifications laissées dans le workspace, sans commit,
push, PR, release ou déploiement. Guides de recette dans [testing](testing.md).
G1/G2 : **PENDING USER MEASUREMENT**. Restent Safari/iPhone/Android réels, AAC
de production sur appareils, acoustique, vraie bibliothèque et Bridge distant.
Le code/browser headless ne remplace pas ces mesures. Après perte du cache Bridge,
une régénération Opus au hash différent est refusée ; l'écoute intégrale peut
attendre entre segments. Ces limites sont documentées, sans substitution silencieuse.

**Complément de clôture** — La réécoute privée plafonne explicitement l'upload à
**2 MiB**, même si la limite du cache de jeu est configurée plus haut. Le test
avec cache à 4 MiB vérifie HTTP 413, échec Bridge et libération du transfert.
Suite privée : **8/8** ; suite Python complète finale : **674 réussis, 1 ignoré,
8 désélectionnés**, 19,17 s. Ruff/Pyright/schéma restent verts. Images Docker de
test reconstruites après ce contrôle. Les comptes Chromium/WebKit/Vitest ci-dessus
restent ceux des dernières suites complètes exécutées.

## 2026-10-03 — Audit V0.2 et autofix

**Périmètre** — Audit des changements V0.2 présents dans le workspace : permissions
et phases, scores/journal/snapshots, transferts privés, sources et reconnexions,
concurrence de sauvegarde dans le navigateur. Les correctifs ci-dessous ont été
reproduits par des tests en échec avant modification, puis vérifiés après correction.

**Défauts confirmés et corrigés**

- Réécoute en attente après déconnexion ou remplacement du Bridge : le transfert
  propriétaire échoue immédiatement et libère jobs/tokens, sans attendre 75 s.
- Upload privé rejeté : l'attente est terminée par le serveur, sans dépendre
  d'un message `JOB_FAILED` ultérieur du Bridge.
- Corrections finales par boutons −/+ et remise à zéro : publication et contrôles
  attendent maintenant les valeurs confirmées côté serveur, comme la saisie numérique.
- Saisie numérique d'une manche pendant l'enregistrement d'un bouton de score :
  le champ reste désactivé jusqu'à réception de cette note, évitant deux éditions
  concurrentes sur la même ligne.
- Échec de recherche dans une réécoute complète : **Réessayer** et **Écouter**
  reprennent la position demandée. L'ancien Blob est libéré au début du chargement ;
  les erreurs de lecture restent accessibles et peuvent être retentées.
- Scan ou upload catalogue lent : le lecteur WebSocket reste disponible pour
  PONG/CANCEL. Un worker de scan sérialisé avec quatre commandes en attente, un
  upload catalogue actif et seulement le dernier jeton en attente ; annulation
  et purge lors d'une perte de connexion. Tests de saturation/erreur/reprise inclus.
- Deux changements rapides de dossier pouvaient perdre un ajout : les commandes
  restent bloquées jusqu'à réception du catalogue correspondant. Révision interne
  persistée, même à hash inchangé ; réponse HTTP 202 et en-tête privé
  `X-Catalog-Revisions` permettent une confirmation bornée à 75 s, avec backoff
  1/2/4 s. Une requête HTTP bloquée est annulée à cette échéance pour libérer les
  commandes ; quitter le composant annule aussi la requête en cours. Les schémas
  des messages restent ceux du protocole 3.
- Un upload catalogue déjà en cours pouvait être appliqué après remplacement de
  sa connexion : nouvelle vérification du propriétaire après réception, HTTP 409
  pour l'ancien transfert ; le jeton de la connexion actuelle continue de fonctionner.

**Documentation** — Guides FR/EN, protocole, architecture, sécurité Bridge,
changelog et recette mis à jour. Clarification du plafond privé fixe de 2 Mio,
des pages de recherche de 100 résultats, de la confirmation des sauvegardes et de
la conservation des métadonnées/archives en fin de session. Changelog corrigé en
protocole 3. Aucun changement de protocole ou de version de snapshot pendant cet audit.

**Vérifications réellement exécutées**

- Python : `.venv/Scripts/python.exe .local/run_v02_pytest.py -m 'not integration'
  -q -p no:cacheprovider` : **684 réussis, 1 ignoré, 8 désélectionnés**, 19,45 s.
  FFmpeg/ffprobe réels présents. Le skip est la création de symlink interdite sur
  ce Windows ; la couverture junction fonctionne. Log local ignoré :
  `.local/pytest-audit-v02.log`.
- Intégration : même wrapper, `-m integration` : **8/8**, 245,72 s, serveur/Bridge
  démo et bots réels. `.local/integration-audit-v02.log`.
- Ruff check + format : **OK**, 179 fichiers. Pyright avec le Python du venv :
  **0 erreur/avertissement**. `tools/gen_ts_types.py --check` : **types et lock à jour**.
- Web : `npm run lint` **OK**, 50 fichiers ; Vitest **32/32** ; `npm run build`
  **OK**, 78 modules, JS 381,70 kB / 116,58 kB gzip.
- Playwright Chromium complet : **31/31**, 1,3 min, dont cinq nouvelles
  régressions UI et trois parties réelles. WebKit complet après correction du
  scénario : **27 réussis, 4 ignorés**, 47,1 s ; les mêmes limites audio du build
  Windows restent explicitement ignorées.
  Le test de position utilise un WAV synthétique et contrôle le parcours de
  réessai ; les parties Chromium contrôlent aussi le décodage des vrais extraits.
  Un échec WebKit intermittent provenait du test qui modifiait le range sans
  événement de saisie : le scénario envoie maintenant input/pointerup dans le
  même geste, et vérifie aussi l'offset avant le réessai. Contrôle répété :
  **5/5 Chromium et 5/5 WebKit**, 13,5 s, sans retry automatique.
- Docker : deux images de test reconstruites (`server:v02-check`, `bridge:v02-check`).
  Conteneurs jetables, sans réseau, racine read-only, cap_drop ALL/no-new-privileges,
  uid 10001. Extraction MP4/MOV/MKV/AVI audio seul et NO_AUDIO **OK** ; workers
  de scan/upload, PONG, CANCEL et nettoyage **OK** sous Python 3.13.16 ; imports
  serveur/protocole 3 **OK**. Contexte temporaire de build supprimé après contrôle.
- Hygiène du contenu courant : **263 fichiers, 0 constat** ; `git diff --check` **OK**.

**Limites / livraison** — Correctifs laissés dans le workspace. Aucun commit,
push ou déploiement. Les essais Safari/iOS/Android et acoustiques réels, la vraie
bibliothèque et les mesures G1/G2 restent à effectuer ; aucun test headless ne
valide ces mesures. Aucun fichier musical personnel ni secret ajouté au dépôt.

---

## 2026-10-03 — V0.3 : distribution du Bridge, choix MC et autofix

**État de départ et écarts** — La V0.2 et son audit ci-dessus étaient déjà
implémentés dans le workspace : revue globale, écoute privée, audio des vidéos,
sources dynamiques, recherche/métadonnées, récupération et protections anti-fuite.
Aucun AGENTS.md supplémentaire trouvé. Le CLI/config/FFmpeg, le pipeline de
préparation et les composants de bibliothèque ont été réutilisés. Les principaux
écarts étaient les sdists dépendant de fichiers hors paquet, l'absence de
distribution native/release, de diagnostic guidé et de choix manuel numéroté.
Les noms PyPI/Trusted Publishers et validations des runners restent des dépendances
de publication ; aucun compte ou secret de publication n'est créé ici.

**Comportements livrés**

- Version unique **0.3.0.dev0**, CPython **3.12–3.14**. Modules de version et licences
  propres aux trois paquets ; dépendance exacte Bridge/serveur → protocole. Les
  wheels protocole/Bridge sont reconstruits depuis leurs sdists autonomes.
- Entrée stable `openblindysir-bridge`, aide/version, init/configure, check-config,
  check-ffmpeg, doctor/JSON et test de connexion explicite. Codes 0/2/3/4/130.
  Assistant français au clavier, secret masqué, texte adapté au terminal étroit,
  confirmation et sauvegarde privée. Configuration atomique, Unix 600/ACL Windows,
  UUID stable ; aide/version/check-config et doctor sans réseau restent sans écriture.
- FFmpeg/ffprobe ≥4.4, encodeur AAC/M4A, filtres et démultiplexeurs obligatoires
  contrôlés ; Opus facultatif. Scan des noms annoncé, contrôles réseau hors partie,
  catalogue et enregistrement puis fermeture du test. Aucun extrait/global decode.
  Diagnostics par liste blanche, sans URL/UUID/chemins/secret ou exception brute.
- Choix **MC uniquement**, par manche numérotée et révision, avant demande d'extrait.
  Recherche/source/dossier/fichier/tags/format/durée mesurée et disponibilités ;
  règles de sources/répétitions et réservations appliquées. Le choix contourne
  explicitement l'alternance aléatoire des dossiers. Confirmation serveur visible
  avant lancement ; attente bornée à dix secondes, même avec des STATE répétés.
  Préparation verrouille la cible ; une manche manuelle attend un lancement explicite.
- Fichier ou Bridge perdu : choix et diagnostic privés conservés, aucun remplacement
  silencieux ; remplacement, retour au hasard, passage ou arrêt possibles. Les
  réservations futures restent attachées à leur numéro, y compris après passage.
  Les joueurs et l'hôte joueur ne reçoivent pas ces champs en jeu.
- **Protocole 4**, lock/types TS régénérés ; **snapshot 3**, lecture des formats 1/2
  avec champs neutres. Réservations persistées, nettoyées si les sources/manches ou
  le rôle changent au lobby. Retour V0.2 avec backup d'avant migration requis.
- Outils PyInstaller **onedir**, builds natifs seulement, Windows/Linux x64 et
  macOS 15 Intel/arm64 prévus par la CI. FFmpeg exclu ; instructions FR/EN, licences
  Python/dépendances/bootloader, VERSION, manifest de fichiers et sommes SHA-256.
  Modules serveur/dev exclus. Ordre/timestamps ZIP normalisés ; aucune promesse
  d'identité binaire entre compilateurs, patches Python et runners.
- CI application/distribution réutilisables séparées de release. Tags/version/
  changelog/commit propres requis ; artefacts du même run, quatre cibles natives,
  métadonnées et hashes vérifiés avant OIDC PyPI puis GitHub. Permissions d'écriture
  limitées aux jobs de publication. Le nightly WebKit informatif existant est conservé.
- Guides installation, dépannage, opérations/backup/rollback et release, UX,
  architecture, feuille de route et changelog mis à jour. ADR **0013/0014** étendent
  les décisions acceptées ; historique V0.2 conservé. La documentation distingue
  montages accessibles, scan et sélection de partie, et limite honnêtement les
  preuves de validation. Le contexte Docker allowlist inclut les licences propres
  et README Bridge nécessaires au packaging autonome.

**Corrections trouvées pendant la validation** — WELCOME devait être validé depuis
son JSON pour respecter le mode strict Pydantic et les enums. Un refus permanent
HTTP 401/403 ou WS 1008 termine désormais run avec code 4/action concrète, plutôt
que de reconnecter sans fin ; les tâches possédées sont annulées et attendues avant
fermeture/nettoyage. Le diagnostic réseau persiste l'identité qui sera réutilisée
par run ; une identité existante invalide est refusée. Les premiers essais UI
utilisaient un build web protocole 3 et des labels anglais obsolètes : rebuild
protocole 4/scénarios corrigés puis suites complètes vertes. Le premier smoke Linux
avait son extraction sur un tmpfs noexec : le volume temporaire du **test natif**
autorise l'exécution, sans modifier les tmpfs de production. Les sélecteurs Python
des essais uvx hors checkout ont été relancés avec leurs chemins absolus.

**Vérifications réellement exécutées**

- Python Windows : `.venv/Scripts/python.exe .local/run_v02_pytest.py -q
  -p no:cacheprovider` : **758 réussis, 1 ignoré, 10 désélectionnés**, 19,63 s.
  Symlink Windows interdit dans cette session ; junctions testées. FFmpeg réel.
- Intégration complète : même wrapper, `-m integration server/tests/integration` :
  **10/10**, 289,99 s. Serveur/Bridge/bots réels, choix MC/extraction/publication,
  doctor enregistré et mauvais secret refusé sans fuite ni traceback.
- Bridge Linux : image de test Ubuntu 22.04, CPython 3.13.16/FFmpeg 4.4,
  uid 10001, sans réseau/racine read-only : **98 réussis, 4 ignorés**, 12,87 s.
  Symlinks réellement testés ; skips des cas junction Windows.
- Ruff check et format **OK**, 204 fichiers ; Pyright avec le Python du venv :
  **0 erreur/avertissement** ; `tools/gen_ts_types.py --check` **OK**.
  Actionlint **1.7.12** : les cinq workflows **OK**.
- Web : Biome **OK**, 50 fichiers ; Vitest **32/32** ; typecheck/build **OK**,
  78 modules, JS 387,53 kB / 118,26 kB gzip. Playwright complet :
  **33/33 Chromium** (1,4 min), **29 WebKit + 4 audio ignorés** (49,4 s).
  Confirmation/expiration MC, français/anglais, clavier et 320/390/1280 px inclus.
  Un callback asyncio Proactor Windows a affiché WinError 10054 au démarrage de la
  pile Chromium ; les 33 scénarios ont terminé sans échec. Les skips WebKit ne
  valident pas les parties audio ni Safari/iOS.
- `build --no-isolation` protocole/Bridge : **quatre wheel/sdist construits**,
  wheels depuis sdist ; `twine check` **4/4**, provenance/collecte **OK**.
  uvx isolé hors checkout **OK** sur Windows 3.12.4/3.13.16/3.14.8 et Linux
  Ubuntu 22.04 3.12.15/3.13.16/3.14.8 : aide/version, configuration sans écriture,
  FFmpeg réel, doctor JSON expurgé et configuration invalide.
- Archives **Windows 11 x64/Python 3.12.4** et **Ubuntu 22.04 x64/Python 3.13.16**
  construites avec PyInstaller 6.22.3/hooks 2026.8, extraites et smoke **OK** hors
  checkout. Windows gelé et uvx 3.14 ont aussi enregistré un vrai serveur et
  uploadé un catalogue d'un WAV synthétique ; mauvais secret → code 4, sorties privées
  absentes. Aucun test SmartScreen/antivirus/Gatekeeper revendiqué.
- Inspection des archives **OK** : hashes, notices Python/PyInstaller/dépendances,
  aucun serveur/dev/config/FFmpeg ni chemin personnel dans les documents ou noms
  de code. Windows : 719 modules/20 231 objets code avec filenames relatifs ;
  Linux : 759/21 095. **SHA256SUMS : 10 fichiers vérifiés**.
- Docker app/Bridge V0.3 reconstruits : **OK**. Probes jetables uid 10001,
  sans réseau, cap_drop ALL/no-new-privileges, racine read-only : extractions AAC
  MP4/MOV/MKV/AVI et NO_AUDIO **OK** ; scan/upload lents, PONG/CANCEL/nettoyage
  **OK** ; serveur/protocole 4/snapshot 3, sans FFmpeg **OK**. Contextes de build
  temporaires supprimés après contrôle.
- Hygiène du contenu courant : **295 fichiers, 0 constat** ; `git diff --check`
  **OK**. Les alertes de conversion LF/CRLF de Git n'indiquent pas d'erreur de diff.

**Livrables et limites** — `.local/distribution-v03-delivery/` contient les deux
archives natives, quatre paquets Python, provenance, manifest et SHA256SUMS.
Ce sont des builds **0.3.0.dev0, dirty=true**, liés au commit de base dans le
manifest et au contenu testé ; ils ne constituent pas une release publiée.
Tout reste dans le workspace, sans commit/push/tag/PyPI/GitHub Release/déploiement.
La CI native macOS Intel/arm64 est configurée mais **non exécutée dans cette session** ;
les essais utilisateur SmartScreen/antivirus/Gatekeeper, vraie saisie terminal,
Safari/iOS/Android, musique réelle, LAN/VPS et G1/G2 restent à effectuer avant
promesse de compatibilité/release. Les procédures et prérequis sont dans
[testing](testing.md), [installation Bridge](bridge-installation.md) et
[releasing](releasing.md). Aucun secret, fichier musical personnel ou endpoint
arbitraire de lecture ajouté.

## 2026-10-03 — Audit et autofix de sécurité après V0.3

**Demande** — Auditer le contenu courant et appliquer les corrections, notamment
sécuritaires. Le travail V0.2/V0.3 déjà présent est conservé. Version
**0.3.0.dev0**, protocole **4**, snapshot **3** inchangés par cet audit. Aucune
publication, migration supplémentaire, modification de secret ni action Git
d'écriture. Les résultats portent sur le workspace courant, pas seulement HEAD.

**Périmètre** — Sessions et élévation host, HTTP/WebSocket, transferts audio et
catalogues, tâches et reconnexion Bridge, sandbox/configuration/persistence,
logs, dépendances verrouillées et chaîne de distribution. Lecture des parcours,
tests de régression des conditions confirmées, puis validation Windows/Linux,
navigateurs et artefacts reconstruits. Ce contrôle ne constitue pas un pentest
externe ni une preuve d'absence de toute vulnérabilité.

**Constats corrigés**

| Condition et risque | Correction appliquée |
| --- | --- |
| Session ou droit host révoqué pendant l'attente d'un corps HTTP ou du HELLO WebSocket | Relecture de l'identité et des permissions après l'attente, avant toute mutation/enregistrement ; rejet propre des HELLO binaires. |
| Plusieurs requêtes d'authentification passent ensemble le contrôle initial, ou rotation répétée des codes de récupération | Recontrôle de quota après le corps ; plafond de rotation de 5 par minute, individuel et global. |
| Upload audio commencé avant annulation, expiration, déconnexion ou remplacement du Bridge | Grant lié à l'objet exact de connexion ; revalidation de cette connexion, du job et de l'état audio après le flux, avant cache/événement de validation. |
| Corps lent ou gzip incomplet, suivi de données ou composé de plusieurs membres | Délais totaux 15 s JSON / 60 s upload ; lecture bornée, EOF gzip obligatoire, suffixes et membres supplémentaires refusés, sans flush non borné. |
| Accumulation de buffers gzip via des uploads concurrents | Un catalogue en réception par UUID et huit globalement, même si le Bridge se déconnecte pendant le flux ; quota avant token/corps/décompression, libération en finally. Le 429 conserve le token ; le client réessaie au plus trois fois à 0,25/0,5/1 s. |
| Client lent ou Bridge bavard accumulant des messages | Files Bridge des deux côtés et file critique joueur limitées à 64 ; fermeture contrôlée en saturation. Messages entrants Bridge limités par un bucket de 40, recharge 20/s, avant validation. |
| Writer Bridge arrêté sans terminer la session, messages/jobs d'une ancienne connexion rejoués | Reader, writer et signal de saturation possédés par la session ; propagation des échecs, annulation et attente des tâches, purge du WELCOME et des messages obsolètes. |
| Très longue panne faisant déborder l'exponentielle de reconnexion | Exposant plafonné avant calcul ; attente maximale 30 s avant jitter, sans exception de débordement. |
| IP rejetées, compteurs vides ou clés expirées accumulés dans les tables | Aucun enregistrement vide sur refus ; retrait des entrées expirées et des compteurs à zéro. |
| Accumulation de secrets transitoires ou injection de lignes/ANSI/bidi dans un log via un champ rejeté | Redaction transitoire bornée à 4096 secrets, secrets de déploiement permanents ; échappement JSON des caractères de contrôle Cc/Cf avant émission du log. |
| Cache navigateur/proxy d'une réponse API privée ou d'erreur | Middleware imposant `Cache-Control: no-store, private` sur les réponses `/api/`. |
| Ancêtre config/root/snapshot lié alors que seule la feuille était contrôlée | Refus des symlinks/junctions sur tous les ancêtres avant canonicalisation ou accès ; scanner, sandbox, config et diagnostic utilisent ce contrôle. |
| Snapshot/backup exposé avant durcissement ou temporaire prévisible utilisé pour rediriger une écriture | Temporaires exclusifs aléatoires, permissions Unix 600/ACL Windows avant les octets, fsync/remplacement atomique et backup privé ; restauration bornée à 64 MiB et refus des liens. |
| Nom de paquet/version/cible ou métadonnées d'archive incohérents | Identités wheel/sdist exactes, métadonnées uniques au chemin attendu, racine native/cible/provenance/hash concordants. |
| Archive avec traversée, lien, collision portable, périphérique Windows, fichier privé ou volume excessif | Validation avant extraction/publication : chemins portables, absence de liens et doublons NFC/casefold, backups privés refusés, plafond 10 000 entrées/512 MiB total/128 MiB par fichier ; tar parcouru sans liste illimitée. |
| Staging release contenant un fichier étranger ou sidecar incohérent | Liste fermée de livrables, refus des liens/répertoires inattendus et sidecars orphelins ; vérification du contenu et SHA-256 avant collecte. |

La suite navigateur a également révélé une régression d'affichage : une réponse
du host participant, bien enregistrée, disparaissait du bandeau si son ACK était
coalescé avec le passage en REVIEW. Le bandeau conserve désormais **sa propre
réponse** sauvegardée, avec son statut ; il ne révèle aucune réponse tierce ou
future. L'attente E2E accepte aussi cette preuve durable de sauvegarde.

**Code et documentation** — Les corrections se trouvent principalement dans
`server/security.py`, `auth/routes.py`, `library/{routes,management}.py`,
`audio/routes.py`, `ws/{bridge_link,bridge_endpoint,player_endpoint,hub}.py`,
`ratelimit.py`, `logging.py`, `private_files.py`, `persistence.py` sous
`server/src/openblindysir_server/` ; et `client.py`, `config.py`, `scanner.py`,
`sandbox.py`, `diagnostics.py` sous `bridge/src/openblindysir_bridge/`.
La chaîne de livraison est durcie dans `tools/release.py` et
`tools/smoke_bridge_distribution.py`. L'affichage corrigé est dans
`web/src/player/PlayerApp.tsx`.

Tests ajoutés/étendus dans `server/tests/shell/test_security_audit.py`,
`server/tests/shell/test_uploads.py`, `server/tests/game/test_snapshot_security.py`,
`bridge/tests/runtime/test_client_security.py`,
`bridge/tests/runtime/test_client_sources.py`, `bridge/tests/fs/test_config_paths.py`
et `protocol/tests/test_release_artifacts.py` ; **64 cas Python supplémentaires**
par rapport au bilan V0.3 précédent. [SECURITY](../SECURITY.md),
[sécurité Bridge](bridge-security.md), [opérations](operations.md) et
[changelog](../CHANGELOG.md) reflètent les protections réellement présentes.

**Vérifications exécutées**

- Python final Windows 11 / CPython 3.12.4, FFmpeg réel : **821 réussis,
  2 ignorés, 10 désélectionnés**, 22,09 s. Skips : bits Unix et création de
  symlink Windows interdite ; les junctions Windows sont testées.
- Python final Linux Ubuntu 22.04 / CPython 3.13.16, uid 10001, racine read-only,
  sans réseau : **817 réussis, 6 ignorés, 10 désélectionnés**, 27,15 s.
  Permissions Unix et symlinks réellement testés ; skips PowerShell/junctions.
- Intégration complète serveur/Bridge/bots/FFmpeg : **10/10**, 319,21 s.
  Les derniers ajouts de quotas catalogue/logs ont ensuite été couverts par les
  suites Python finales et les essais d'enregistrement des livrables ci-dessous.
- Ruff check/format **OK**, 209 fichiers ; Pyright **0 erreur/avertissement** ;
  génération TS `--check` **OK** ; Actionlint 1.7.12 : cinq workflows **OK**.
- Web : lint/typecheck/build **OK**, Vitest **32/32** ; Playwright **33/33
  Chromium** (1,7 min), **29 WebKit + 4 cas audio ignorés** (48,5 s).
  Parties complètes, host participant et affichages mobile inclus.
- Dépendances : requête [OSV](https://google.github.io/osv.dev/api/) sur les
  **70 paquets PyPI verrouillés**, et `npm audit` sur le lock web (**132 dépendances
  déclarées par l'audit**) : **aucun avis connu signalé**, contrôle du 2026-10-03.
  Les quatre paquets locaux du workspace ne sont pas des entrées PyPI.
  Résultat brut conservé dans `.local/dependency-security-2026-10-03.json`.
  Pas de mise à jour de dépendance arbitraire en l'absence de constat.
- Protocole/Bridge reconstruits en **quatre wheel/sdist** ; `twine check` **4/4**.
  uvx final hors checkout : Windows Python **3.14.8** et Linux **3.13.16** **OK**,
  aide/version, FFmpeg, config sans écriture, doctor expurgé et config invalide.
  Les matrices Python 3.12/3.13/3.14 déjà contrôlées au bilan V0.3 ne remplacent
  pas ces essais des paquets reconstruits après audit.
- Natives finales Windows x64/Python **3.12.4** et Ubuntu 22.04 x64/Python
  **3.13.16**, PyInstaller **6.22.3** : construction, extraction et smoke **OK**.
  Windows natif et uvx 3.14 ont enregistré un vrai serveur et envoyé le catalogue
  d'un WAV synthétique ; mauvais secret : code 4, sans traceback ni sortie privée.
- Inspection finale : hashes/notices **OK**, aucun serveur/dev/config/FFmpeg ni
  chemin personnel embarqué. Windows : **719 modules/20 236 objets code** à noms
  relatifs ; Linux : **759/21 100**. **SHA256SUMS : 10 fichiers vérifiés**.
- Images Docker finales serveur/Bridge reconstruites et probes **OK**, uid 10001,
  sans réseau, cap_drop ALL/no-new-privileges, racine read-only : serveur protocole
  4/snapshot 3 sans FFmpeg ; extraction AAC MP4/MOV/MKV/AVI et NO_AUDIO ;
  scans/uploads lents, PONG/CANCEL et nettoyage des tâches.
- Hygiène du contenu courant : **300 fichiers, 0 constat** ; `git diff --check`
  **OK** après les corrections et leur documentation. Contexte temporaire du
  dernier build Docker supprimé par le helper qui vérifie son emplacement.

**Livrables** — `.local/distribution-security-v03-final/` remplace pour cet audit
les précédents dossiers de livraison : deux ZIP natifs, quatre paquets Python,
provenance, manifest, notes et SHA256SUMS. Builds **0.3.0.dev0, dirty=true**,
commit de base `a75290b719b2ae00b6dc05bcf44d87066cd184cb` ; le manifest distingue
les builds de développement d'une release propre. Aucun commit/push/tag,
déploiement, PyPI ou GitHub Release effectué.

**Limites restantes** — Les contrôles d'ancêtres réduisent les redirections mais
ne suppriment pas toute course TOCTOU face à un processus local capable de modifier
simultanément le filesystem. Les bornes par requête/connexion ne remplacent pas
une protection réseau contre un DDoS distribué. L'audit de dépendances ne couvre
pas formellement les CVE de FFmpeg, du système ou des bibliothèques natives.
CI macOS Intel/arm64 non exécutée ; SmartScreen/antivirus/Gatekeeper, Safari/iOS
réels, Android, LAN/VPS, musique réelle et mesures acoustiques G1/G2 restent
non validés dans cette session. Les quatre skips audio WebKit ne prouvent pas
la compatibilité Safari. Aucun secret ni fichier musical personnel utilisé.


## 2026-10-03 — V0.5 : Bridges privés, historique durable et revue sécurité/accessibilité

**Périmètre** — Implémentation V0.5 demandée, après vérification des sources V0.2
et V0.3 et de l'audit précédent. La V0.2 possédait déjà les références
`(bridge_id, track_id)`, les catalogues multiples et la revue globale ; la V0.3
ajoutait distribution et choix manuel MC. Ce travail complète ces fonctionnalités,
sans annoncer V1.0, release, publication ou gel du protocole. Les modifications
préexistantes sont conservées ; aucun commit/push/tag/déploiement n'est effectué.

**Décisions et comportement livré**

- Identité UUID stable, nom lisible et secret distinct par Bridge. Registre privé
  `STATE_DIR/bridge-credentials.json`, hashes et révocations durables, au plus
  64 identités et huit connexions. Bootstrap historique lié au premier UUID ;
  sa révocation/rotation ne peut être contournée par une ancienne variable.
  CLI serveur d'émission/rotation vers un nouveau fichier privé, révocation CLI
  ou hôte, chargement `--credentials` prioritaire pour l'identité côté Bridge.
  Aucun secret dans le panneau, les diagnostics ou les sorties de ces commandes.
- Catalogues/capacités/états/erreurs et propriétaires des travaux visibles à
  l'hôte autorisé. Reconnexion d'un UUID remplace son seul lien. Sélection hors
  ligne exclue ; un extrait aléatoire non préparé attend 45 s, puis tente une
  autre source. Un choix manuel garde son erreur et exige remplacement/retour
  hasard/saut/fin explicite. Audio déjà préparé utilisable, racines contrôlées
  localement, renouvellement de catalogue sans réécriture des manches jouées.
- Archives autonomes immuables au moment de la validation finale : dates,
  noms/équipes, réglages, sources copiées, révélations, réponses capturées ou
  verrouillées, rang/temps, scores et corrections. Aucun audio/URL/token/cookie.
  HTTP hôte à la demande, exports, suppression/purge confirmées ; 50 parties,
  90 jours, 16 Mio. Les deux snapshots gérés sont réécrits lors d'une suppression
  ou expiration ; un échec disque conserve l'archive en RAM et signale l'erreur.
  Exports/backups externes et résultats courants demandent un nettoyage distinct.
  Nouvelle partie libère journal et assets anciens ; le journal reste en ajout
  seul dans chaque partie et les archives gardent leur projection figée.
- Logiciel `0.5.0.dev0`, protocole 5, plage 5 à 5, snapshot 4, historique 2.
  Informations explicites dans WELCOME, erreurs, API et diagnostics. Refus propre
  des anciens protocoles, plage numérique sans recopier les messages distants,
  web sans boucle de rechargement. Snapshots 1/2/3 migrés ; archives ancien/1
  vers 2 ; format futur inconnu bloquant, corruption connue avec backup valide.
  Rotation Bridge indépendante des cookies en format 4. Migration/rollback et
  dépréciation future documentés sans promesse de support indéfini.
- Liens d'évitement, annonces de phase, focus sans interrompre la saisie,
  dialogues avec Annuler/Échap/retour au déclencheur, noms/états du lecteur,
  chargement/erreur/réessai des archives et diagnostics, petits écrans, texte
  agrandi et réduction des animations. Aucun état essentiel transmis seulement
  par couleur ou son. Les lecteurs d'écran physiques ne sont pas simulés.

**Audit et corrections** — Usurpation d'UUID refusée même avec le secret valide
d'un autre propriétaire ; identité/connexion/job/expiration revérifiés après
réception des corps et après HELLO. Révocation pendant catalogue/upload couverte,
contrôles d'origine/cookie/confirmation et permissions sur chaque API privée.
Les détails des Bridges, dossiers sélectionnés, bibliothèque HTTP et diagnostics
de sources sont maintenant masqués à l'hôte joueur pendant IN_GAME. Quota cumulé
de 200 000 pistes, même hors ligne, sans remplacement du catalogue après un 413.
Les limites réseau, gzip, files de messages, authentification, sandbox, whitelist
FFmpeg, timeouts, redaction, idempotence et anti-spoiler de l'audit précédent restent
couvertes. Cleanup de déconnexion synchrone avant toute attente pour qu'une
annulation de tâche ne laisse pas un Bridge ONLINE. Décodage fermé des snapshots,
valeurs finies et refus des formats inconnus ; fichiers privés et écritures atomiques.

Le build local a révélé un cache editable conservant les métadonnées protocole
0.3.0.dev0 après modification de son `_version.py`. Les trois paquets déclarent
désormais leurs fichiers de version dans les `cache-keys` uv, conformément à la
[documentation primaire uv](https://docs.astral.sh/uv/concepts/cache/#dynamic-metadata).
Le build natif refuse une version installée discordante avant construction ; trois
régressions couvrent ce contrôle. Synchronisation puis reconstruction vérifient
les trois métadonnées et les notices des deux archives en 0.5.0.dev0.

**Opérations et documentation** — Nouveau profil Compose d'identité privée,
montages musique/credentials/CA read-only, utilisateur 10001, système read-only,
drop ALL/no-new-privileges. Actions d'émission/révocation dans les deux lanceurs ;
variables ambiantes BRIDGE_SECRETS neutralisées. Guides FR/EN V0.5, installation,
opérations, utilisateurs, architecture, protocole, modèle de menace, UX, testing,
README/changelog/roadmap et ADR 0015 actualisés. ADR antérieurs complétés sans
effacer leurs décisions historiques. Sauvegarder tout STATE_DIR, registre compris ;
prévoir jusqu'à 256 Mio pour deux snapshots de 64 Mio et deux temporaires, hors
backups externes. La CI ajoute les scénarios nouveaux et exécute Chromium/WebKit.

**Vérifications réellement exécutées**

| Contrôle | Résultat |
|---|---|
| Python Windows 11 / CPython 3.12.4, FFmpeg réel | **873 réussis, 2 ignorés, 11 intégrations désélectionnées**, 25,00 s |
| Python Ubuntu 22.04 / CPython 3.13.16, uid 10001, root et dépôt read-only, sans réseau | **869 réussis, 6 ignorés, 11 intégrations désélectionnées**, 26,90 s |
| Intégration réelle serveur/Bridges/FFmpeg/bots | **11/11**, 360,33 s |
| Vitest | **32/32** |
| Playwright Chromium / WebKit | **38 Chromium + 34 WebKit**, quatre skips audio WebKit existants, 2,6 min |
| Ruff lint/format, Pyright, dérive schéma/TS, lock uv | **OK**, 225 fichiers Python, zéro erreur/avertissement Pyright |
| Biome, TypeScript, build web, Actionlint, hygiène, diff sans erreurs d'espacement | **OK** |
| Wheels/sdists protocole/Bridge V0.5 | Quatre livrables, **twine 4/4**, métadonnées exactes et collecte privée validées |
| Wheels hors checkout, uvx isolé Windows | **CPython 3.12/3.13/3.14 OK** : version, FFmpeg, credentials, doctor masqué, config invalide |
| Archives natives locales Windows x64 / Linux glibc 2.35 x64 | **Deux builds + deux smokes OK**, SHA-256/manifeste/versions ; FFmpeg exclu |
| Archive Windows contre vrai serveur V0.5 | Enregistrement/catalogue WAV synthétique **OK**, mauvais secret code 4, aucune sortie privée |
| Images Docker app/Bridge et profils Compose | **Deux builds OK** ; profils privé/public/bootstrap/credential + CA privée validés |
| Docker jetable V0.5 | API compatibilité, uid 10001, registre haché/fichiers 600, émission, arrêt brutal/reprise, cookie hôte/réglages, révocation/rotation et FFmpeg Bridge **OK** ; conteneurs/volume supprimés |

Les skips Windows sont bits Unix et symlink non autorisé ; les junctions y sont
testées. Les skips Linux concernent PowerShell et junctions Windows. L'intégration
nouvelle emploie deux UUID/secrets et les mêmes IDs locaux, prépare une manche de
chaque source, note/valide/archive, tue le serveur, récupère la même archive/notes
et reconnecte les Bridges, puis supprime l'archive des copies persistées.
Le test Hypothesis confirme ajout seul/projection dans la partie active et
immuabilité des archives retenues, y compris après Nouvelle partie.

Commandes principales : `python .local/run_v02_pytest.py -q` avec basetemp distinct,
la même suite sous Docker Linux isolé, `pytest -m integration server/tests/integration`,
`npm --prefix web run lint/typecheck/test/build` (commandes séparées),
`node .local/run_v02_playwright.cjs test --project=chromium --project=webkit`,
`ruff check .`, `ruff format --check .`, `python -m pyright --pythonpath .venv/Scripts/python.exe`,
`python tools/gen_ts_types.py --check`, `uv lock --check --offline`, Actionlint,
`python tools/check_repo_hygiene.py`, `python tools/release.py verify --version 0.5.0.dev0`,
build Python `--no-isolation`, `tools/build_bridge.py`, `tools/smoke_bridge_distribution.py`
et collecte **sans** `--require-clean`. Livrables privés de test dans
`.local/distribution-v05-final`, marqués checkout dirty ; aucune publication.
Les 70 dépendances Python et le lock npm n'ont pas changé depuis l'audit OSV/npm
du même jour (aucun avis connu alors signalé) ; ce contrôle n'est pas une preuve
d'absence de vulnérabilité et n'est pas annoncé comme une nouvelle requête réseau.

**Limites restantes** — Aucune CI distante ou release déclenchée. Binaires macOS,
les quatre runners officiels, signature/notarisation, SmartScreen/antivirus,
NVDA/JAWS/VoiceOver, Safari/iOS/Android physiques, zoom navigateur réel, grande
bibliothèque privée et synchronisation acoustique restent à vérifier. Les tests
320/390/1280 px, texte 200 %, contrastes et mouvement réduit ne constituent pas
une certification WCAG. Les dépendances, stockage et fenêtres TOCTOU locales
conservent les limites documentées du modèle de menace. **V0.5 reste en développement.**

### 2026-10-03 — Audit et autofix sécurité complémentaire de la V0.5

Demande : réexaminer la V0.5 implémentée, en priorité les frontières de sécurité,
corriger les problèmes reproduits et vérifier la reprise. Les changements V0.2,
V0.3 et V0.5 déjà présents restent conservés. Aucun commit, tag, publication,
déploiement utilisateur ou gel du protocole n'est effectué.

**Constats et corrections**

| Problème reproduit | Impact | Correction |
|---|---|---|
| Écriture CLI entre lecture et sauvegarde d'une révocation hôte | Une rotation d'un autre UUID réactivait le secret révoqué | Verrou OS non bloquant, relecture sous verrou et transaction ; l'opération concurrente échoue pour réessai |
| Rotation/révocation/bootstrap dont la sauvegarde échoue | Autorisation RAM différente de celle retrouvée après redémarrage | Copie de travail, rollback en cas d'échec, cache invalidé ; relire le disque même si l'erreur suit le remplacement |
| Émission interrompue par un échec du registre, sortie créée simultanément ou nom d'état choisi comme sortie | Secret inutilisable laissé sur disque, écrasement d'une autre sortie, corruption des fichiers gérés | Création privée sans remplacement par lien physique, nettoyage si mutation refusée, refus des noms réservés aux snapshots/registre |
| Joindre/quitter successivement avec le bon mot de passe | 1 001 identités conservées malgré le plafond de joueurs actifs ; croissance sans borne | 60 inscriptions/IP/minute, 600/serveur/minute, 1 000 identités en état puis `game_full` ; Nouvelle partie retire les identités retirées après archivage |
| Snapshot primaire avec index de manche 999 et secours valide | `IndexError` au démarrage au lieu de reprendre le secours | Validation des champs/types/index et de la récupération avant application ; score, cookie et fermeture de manche préservés dans le secours |
| Identité bootstrap non textuelle, noms/Unicode invalides, clés JSON privées dupliquées | Exception non gérée ou interprétation ambiguë d'un état d'authentification | Registre fermé, normalisation cohérente des noms, UUID typés, UTF-8 valide, doublons refusés |
| En-tête Content-Length non décimal ou très long dans une requête ASGI | `int()` levait au lieu de retourner une erreur bornée | Vérification ASCII et comparaison décimale sans conversion ; conservation des limites de taille/délai effectives |

Le dernier cas renforce la couche applicative : les transports HTTP peuvent déjà
refuser ces en-têtes avant l'ASGI ; aucun exploit distant au travers d'Uvicorn n'est
revendiqué. Le registre et les snapshots sont des fichiers privés sous contrôle
opérateur ; les corrections de validation ne changent pas cette frontière de confiance.

Le verrou `bridge-credentials.lock` garde un inode stable et ne doit jamais être
supprimé pendant le fonctionnement. Fermeture du descripteur/arrêt brutal libèrent
le verrou. Les mécanismes natifs sont documentés par Python :
[fcntl](https://docs.python.org/3/library/fcntl.html) et
[msvcrt](https://docs.python.org/3/library/msvcrt.html).
Cette coordination des commandes opérateur ne rend pas l'application compatible
avec plusieurs processus serveur. L'émission requiert liens physiques et verrous
sur stockage local ; les essais ci-dessous couvrent NTFS et le stockage Linux.

La restauration lit au plus 64 Mio + un octet pour vérifier la limite ; mêmes
bornes pour la copie du précédent snapshot. Les types dataclass sont contrôlés
sans convertir chaînes/booléens en nombres. Les collections deque sont contrôlées
comme deque puis par leurs éléments, afin de conserver les sauvegardes légitimes.
Les migrations de métadonnées V1 précèdent cette validation ; formats 1/2/3/4,
historiques 1/2 et refus des formats futurs restent couverts.

**54 cas de régression ajoutés** : 25 credentials/processus/CLI, 20 snapshots,
8 HTTP et un scénario noyau de saturation/libération des identités. Un test
d'émission valide explicitement que l'écriture échouée a été appelée, afin de ne
pas confondre une configuration synthétique invalide avec un échec disque.
SECURITY.md, architecture/modèle de menace, ADR 0015, changelog, guides V0.5 et
guides utilisateur FR/EN sont actualisés. La mention restante « Protocol 4 » du
README est corrigée en 5. Logiciel 0.5.0.dev0, protocole 5 et snapshot 4 inchangés.

**Vérifications réellement exécutées après corrections**

| Contrôle | Résultat |
|---|---|
| Python Windows 11 / CPython 3.12.4, FFmpeg réel | **927 réussis, 2 ignorés, 11 intégrations désélectionnées**, 33,67 s |
| Python Linux / Ubuntu 22.04, CPython 3.13.16, uid 10001, root/dépôt read-only, sans réseau | **923 réussis, 6 ignorés, 11 intégrations désélectionnées**, 28,75 s |
| Intégration réelle serveur/Bridges/FFmpeg/bots | **11/11**, 363,44 s ; deux propriétaires, scores/historique, kill/reprise, reconnexion et suppression |
| Vitest | **32/32** |
| Playwright Chromium/WebKit | **72 réussis**, quatre skips audio WebKit existants, 2,7 min |
| Ruff lint/format, Pyright, schéma/types générés, lock uv, hygiène, diff | **OK** ; 227 fichiers Python formatés, zéro erreur/avertissement Pyright, hygiène 242 fichiers |
| Docker app et Bridge | **Deux images de test reconstruites**, déploiement utilisateur inchangé |
| Profils Compose et conteneurs jetables | **OK** : modes privé/public/bootstrap/credential + CA, uid 10001, fichiers privés, émission CLI, cookie/état après kill, révocation/rotation, FFmpeg ; conteneurs/volume nettoyés |
| Dépendances verrouillées, requêtes OSV/npm actualisées | **70 paquets Python et 132 dépendances npm**, aucun avis connu signalé, 2026-10-03 à 09:13 UTC |

Commandes : `python .local/run_v02_pytest.py -q --tb=short -p no:cacheprovider`
avec basetemp distinct ; la même suite dans Docker Linux isolé ;
`python .local/run_v02_pytest.py -m integration server/tests/integration` ;
`npm test` dans web ;
`node .local/run_v02_playwright.cjs test --project=chromium --project=webkit` ;
`ruff check .`, `ruff format --check .`,
`python -m pyright --pythonpath .venv/Scripts/python.exe`,
`python tools/gen_ts_types.py --check`, `uv lock --check --offline`,
`python tools/check_repo_hygiene.py` et `git diff --check`.
Les constructions utilisent exclusivement les tags privés `security-v05-check`.
Les données réseau d'audit, sans secrets, sont conservées localement dans
`.local/dependency-security-v05-audit-2026-10-03.json` (hors Git).

Limites : macOS n'est pas exécuté dans cette passe ; pas de lecteurs d'écran,
appareils/audio physiques, grande bibliothèque privée ou CI distante. Les
contrôles de dépendances décrivent les avis connus à cette date. Les limites
TOCTOU et l'administration locale de confiance restent celles du modèle de menace.
Les archives natives privées construites avant cet audit ne sont pas présentées
comme reconstruites ici ; aucune distribution n'est publiée. **V0.5 en développement.**

## 2026-10-03 — Préparation de l'intégration Git et mise à jour des guides

À la demande de l'utilisateur, les travaux V0.2/V0.3/V0.5 et l'audit de sécurité
sont préparés pour commit, fusion dans `main` et push. La branche distante `main`
est vérifiée avant intégration ; les données privées et artefacts de `.local`
restent hors Git. Aucun tag de release n'est créé.

Les guides d'installation Bridge FR/EN proposent désormais le fichier d'identité
distinct dès le premier parcours : `init`, `run`, diagnostics et archives natives.
Ils expliquent la conservation du secret et du nom par Entrée dans l'assistant,
la priorité de `--credentials`/`OPENBLINDYSIR_BRIDGE_CREDENTIALS_FILE`, la rotation
vers un nouveau fichier, les verrous et le bootstrap limité à un UUID. L'exemple
figé sur 0.3.0 est remplacé par la version publiée correspondant au serveur ;
V0.5 reste en développement. Les guides utilisateur FR/EN précisent que chaque
propriétaire garde son fichier d'identité privé et ne le partage pas aux joueurs.

Le contrôle de tous les nouveaux fichiers repère aussi deux mots de passe
synthétiques dans un test CLI dont le préfixe ne satisfait pas la politique
d'hygiène ; ils sont renommés en `example-…`, sans changement du code applicatif.
Le test CLI concerné est relancé. Les résultats complets de
l'audit ci-dessus restent applicables au code. Vérification des options CLI,
des liens locaux des quatre guides, de l'hygiène du contenu destiné au commit
et de l'absence d'erreurs de whitespace avant intégration.

## 2026-10-03 — Rythme continu, préparation en modales et correction sémantique

Mise en œuvre du plan validé après l'observation vidéo : transitions pilotées par
le serveur (2 s par défaut, réglables de 0 à 10 s, mode manuel), pause des
intermissions et notation/publication uniquement en revue finale. La barre hôte
reste compacte ; paramètres et son s'ouvrent à la demande sans pause implicite.
La préparation regroupe Musique, Règles, Rythme, Joueurs/équipes et Avancé, avec
résumé/actions persistants, navigation clavier et confirmation d'abandon.

Le catalogue possède sa propre modale, des filtres, un tri global avant pagination
de 25 pistes et la conservation de la recherche/page. Le reset de bibliothèque
ne supprime ni joueurs, ni équipes, ni paramètres, ni métadonnées, ni archives.
Une piste allouée puis annulée est consommée même avant écoute ; le préchargement
seul ne consomme rien. Les réservations sont comptées une seule fois et excluent
les pistes déjà consommées. La correction de métadonnées vaut pour toute la
session, sans modifier les fichiers ni les résultats déjà publiés.

La notation distingue vrai/faux titre/artiste (ou critère personnalisé), tout
bon/tout faux et saisie manuelle signée, selon le barème. Une décision incomplète
reste à vérifier. Les révisions protègent les changements concurrents et les
accusés distinguent deux décisions de même total. La revue filtre les éléments
à vérifier ; le lot zéro ignore les brouillons capturés et attend chaque accusé.
Les corrections finales gardent un motif facultatif privé jusqu'à publication,
stocké atomiquement avec le montant et exporté dans les résultats/historiques.
Les équipes deviennent prioritaires sur le podium et dans les totaux/historiques.

Les dialogues conservent le focus, interceptent Échap sans fermer leur parent,
et ne se referment plus après une ouverture dans une nouvelle phase. WebKit ne
focalisant pas forcément les boutons cliqués, les déclencheurs de modales le font
explicitement. Les contrôles audio affichent les capacités et les erreurs utiles ;
les diagnostics techniques restent dans un détail repliable. Libellés adaptés au
mode, absence de doubles rangs et réduction des informations répétées.

Protocole **6**, snapshot **5**, historique **2**, logiciel **0.5.0.dev0** inchangé.
Le schéma généré/verrouillé est actualisé. Migration des snapshots 1–4, y compris
l'authentification du format 4, et champs d'archives ajoutés par défaut. Guides
utilisateur FR/EN, Docker, installation, protocole, opérations et changelog mis à jour.
Le lanceur Docker conserve `.local/docker/sources.override.yaml` lors des recreations.

Validation locale :

- Python Windows : **941 réussites, 2 exclusions Unix/symlinks, 11 intégrations
  désélectionnées** ; après le dernier ajustement de pause, 13 régressions ciblées réussies.
- Linux Python 3.13 : **936 réussites, 6 exclusions propres à Windows** à la première
  passe, avec un échec d'environnement Hypothesis sur montage en lecture seule.
  Relance avec `HYPOTHESIS_STORAGE_DIRECTORY=/tmp/hypothesis` : **14 réussites**, dont
  le test de propriétés précédemment bloqué ; les 937 tests Linux concernés sont validés.
- Intégration réelle serveur/Bridge : **10 réussites**, puis relance réussie de la
  partie à dix bots après adaptation de son assertion au champ `note:null` ajouté.
- Web : **32 tests Vitest réussis**, lint, TypeScript et build réussis.
- Suite Chromium/WebKit : **81 réussites et 4 exclusions audio explicites** ; le
  dernier échec concernait le retour du focus WebKit au bouton de catalogue.
  Après correction, les quatre parcours catalogue/podium/reset passent dans les
  deux navigateurs. Les 82 parcours uniques concernés sont donc validés, dont
  les parties complètes Chromium à 1280/320 px, les modales à 320/390/1280 px,
  clavier, contraste, texte à 200 %, mouvement réduit et protection anti-fuite.
- Ruff, format, Pyright, génération/schéma et `uv lock --check --offline` réussis.
- Images Docker app/Bridge construites ; contrôles isolés UID 10001, registre hashé,
  permissions privées, reprise après crash, conservation de session, révocation/
  rotation ciblée et FFmpeg Bridge réussis. Contrôles Compose privé/public réussis.

Déploiement Docker Desktop autorisé : sauvegarde privée des trois volumes et
configurations, tags locaux de retour arrière avant reconstruction. HTTPS avec CA
existante, protocole 6/snapshot 5, app/Caddy sains et Bridge connecté vérifiés.
Comparaison avec la sauvegarde : authentification, identités/joueurs/équipes,
réglages, exclusions, métadonnées et valeurs archivées conservés (champs nouveaux
par défaut uniquement). Les deux montages musicaux restent en lecture seule ;
21 pistes disponibles, dont les 16 du montage supplémentaire. Les secrets,
sauvegardes, images, médias et traces restent hors Git.

Commandes de référence : `ruff check .`, `ruff format --check .`, `python -m
pyright`, `python tools/gen_ts_types.py --check`, `uv lock --check --offline`,
`pytest -p no:cacheprovider`, `pytest -m integration`, `npm run lint`, `npm test`,
`npm run build`, `playwright test --project=chromium --project=webkit`, puis
`.\tools\docker-host.ps1 start -NoBrowser` (build app/Bridge, Compose avec override,
attente de santé, conservation des volumes). Les variantes locales isolent les
ports/répertoires de test et fournissent les binaires FFmpeg/browsers installés.

Limites : WebKit headless ne valide pas Safari/iOS audio, aucune mesure acoustique,
lecteur d'écran ou appareils physiques dans cette passe. Aucune release, archive
native de distribution, publication de package ou tag de version n'est produit.
