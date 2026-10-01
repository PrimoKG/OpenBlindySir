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
