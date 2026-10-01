# 0001 — Serveur mono-processus, état en mémoire
Statut : Accepté   ·   Date : 2026-10-01

## Contexte
OpenBlindySir sert **une seule partie privée à la fois**, entre 2 et 15 amis qui jouent à distance. Il n'y a ni rooms ni comptes : le processus serveur *est* la room (`docs/architecture.md` §1).

Le serveur fait autorité sur l'identité, les permissions, l'état, l'heure officielle, les réponses acceptées, l'ordre de validation et les scores (§2). Il doit donc :
- sérialiser des événements concurrents : validations reçues dans la même milliseconde, commandes hôte envoyées depuis deux appareils, résultats de jobs du Bridge, reconnexions ;
- produire un **ordre de validation strict et déterministe** et des horodatages fiables ([0003](0003-server-side-answer-timing.md)) ;
- répondre aux `PING` de synchronisation d'horloge sans gigue parasite (§9.2).

Contraintes : projet maintenu par une seule personne, « la solution la plus simple qui fonctionne » pour 10 à 15 joueurs, peu de services à déployer et à sécuriser, VPS minimal de 1 vCPU / 512 Mo (§22). Le besoin exprimé dès le départ : un seul worker, l'état en mémoire, pas de Redis.

## Options considérées
**A. Python, FastAPI, Uvicorn avec un seul worker, une boucle asyncio, état en RAM.**
- Pour : la boucle unique sérialise les messages sans verrou ; Pydantic v2 valide chaque message ; HTTP et WebSocket dans le même processus ; même langage que le Bridge, qui partage le paquet `openblindysir_protocol` ; Python 3.12 apporte `os.path.isjunction`, utile au Bridge.
- Contre : aucune montée en charge horizontale ; un crash ou un redémarrage perd la partie.

**B. Plusieurs workers et état partagé dans Redis (ou dans une base).**
- Pour : montée en charge, redémarrage d'un worker sans perte d'état.
- Contre : sans objet pour 15 joueurs ; un service de plus à déployer, superviser et sécuriser ; l'ordre de validation exige des verrous ou des transactions distribués ; des WebSockets répartis sur plusieurs workers imposent des sessions collantes et un pub/sub pour diffuser l'état.

**C. Node.js / TypeScript de bout en bout.**
- Pour : types partagés nativement avec l'interface web.
- Contre : gain modeste, puisque les types TypeScript sont de toute façon générés depuis les modèles Pydantic (`tools/gen_ts_types.py`) ; piloter FFmpeg et le bac à sable de fichiers du Bridge est plus simple en Python, langage retenu par le porteur du projet pour le serveur et le Bridge.

**D. Go.**
- Pour : binaire unique, idéal pour distribuer le Bridge ; performances.
- Contre : deux paradigmes à maintenir pour un développeur seul ; aucun besoin de performance ne le justifie côté serveur.

## Décision
Option A.
- **Python ≥ 3.12, FastAPI, Pydantic v2, Uvicorn avec exactement un worker**, outillage `uv` (workspace `protocol`, `server`, `bridge`, avec lockfile). La commande `openblindysir-server` lance ce processus unique et n'offre aucune option pour en lancer plusieurs.
- **Une seule boucle d'événements.** Toutes les mutations d'état sont des fonctions **synchrones**, sans `await` au milieu. Les entrées/sorties (envois WebSocket, messages au Bridge) ont lieu après la mutation. L'ordre de traitement des messages est l'ordre officiel. Il n'y a donc ni verrou ni course entre les mutations.
- **Tout l'état vit en RAM** dans ce processus : session, joueurs et tokens hachés, partie, rounds, réponses, journal `ScoreEvent`, brouillons, catalogues des Bridges, cache audio ([0005](0005-no-database-v01.md)).
- Le cœur du jeu (`openblindysir_server.game`) est **pur** : il n'importe ni FastAPI ni WebSocket, reçoit des commandes et une **horloge injectée**, et produit le nouvel état.
- L'horloge de référence est `time.monotonic_ns()`, lue **à l'entrée** des handlers sensibles (`PING`, `ANSWER_SUBMIT`), avant tout `await`.
- Rien de lourd ni de bloquant dans la boucle : le serveur ne lit jamais de fichier audio et ne lance jamais FFmpeg (§5.2) ; les uploads sont lus en flux.

## Conséquences
- Ordre de validation déterministe, commandes hôte idempotentes, cœur de jeu testable sans réseau avec une horloge simulée (§20.1).
- Déploiement minimal : un conteneur `app` plus Caddy (§17) ; 512 Mo de RAM suffisent.
- Reconnexion simple : l'état est déjà en place, il suffit d'envoyer la vue du client ([0006](0006-full-state-snapshots-over-websocket.md)).
- **Pas de montée en charge horizontale**, par choix. La charge se vérifie à la main avec 50 bots (`tools/bots.py`) : RAM et latence des `PONG`.
- **Plusieurs parties simultanées sont impossibles**, par conception : rooms et multi-session sont exclues définitivement (§24).
- **Un redémarrage ou un crash du conteneur perd la session.** Risque documenté (§7.6), atténué par `restart: unless-stopped` ; un snapshot JSON est candidat pour la V0.2 ([0005](0005-no-database-v01.md)).
- **Bloquer la boucle fausse à la fois les `PONG` et les horodatages des réponses** (risque MEDIUM, §27). Règle de code : aucune I/O synchrone ni calcul long dans un handler ; la latence de la boucle est surveillée dans les logs.
- Lancer plusieurs workers (par exemple via Gunicorn) serait un bug : chaque worker aurait son propre état. Ni le Dockerfile ni la documentation de déploiement ne le proposent.
- Une réécriture du seul Bridge en Go reste envisageable en V1+ si sa distribution pose un vrai problème (§11) ; elle ne remettrait pas cette ADR en cause.
- À réviser, par une nouvelle ADR, seulement si un besoin réel apparaît : plusieurs parties simultanées, ou une survie aux crashs qu'un snapshot ne suffirait pas à assurer.
