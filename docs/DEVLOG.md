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
