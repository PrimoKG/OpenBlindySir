# 0005 — Aucune base de données en V0.1
Statut : Accepté   ·   Date : 2026-10-01

## Contexte
Pour OpenBlindySir, l'unité de vie est **la soirée** : une session correspond à la durée de vie du processus serveur, qui est unique ([0001](0001-single-process-in-memory-server.md)). Les données manipulées (`docs/architecture.md` §13, §14) sont :
- les joueurs, leurs tokens hachés et leurs rôles ;
- la partie, les rounds, les réponses, le journal `ScoreEvent` et les brouillons de notation ;
- les catalogues des Bridges, que chaque Bridge renvoie automatiquement à sa reconnexion ;
- les extraits audio, temporaires par nature : 2 à 4 Mo utiles à un instant donné.

Il n'y a ni requête, ni relation, ni concurrence entre processus. Le besoin initial évoquait « éventuellement SQLite » pour ce qui mériterait vraiment d'être conservé. Le conteneur applicatif doit rester simple : lecture seule, sans volume.

## Options considérées
**A. Aucune persistance : tout en RAM, cache audio compris.**
- Pour : rien à migrer, sauvegarder ou nettoyer ; conteneur en lecture seule ; expiration naturelle des tokens.
- Contre : un crash ou un redémarrage en pleine soirée perd la partie.

**B. SQLite (ou PostgreSQL).**
- Pour : survit aux redémarrages ; outillage connu.
- Contre : schéma, migrations et volume sans aucune requête ni relation à servir : de la cérémonie. Une base ne résout rien qu'un snapshot ne résolve aussi.

**C. Snapshot JSON sur disque.**
- Pour : survit à un crash pour un coût faible ; le journal des scores se rejoue tel quel.
- Contre : volume et écriture atomique à gérer ; utilité à confirmer par une vraie soirée test.

**D. Cache audio sur disque ou en tmpfs.**
- Pour : ne consomme pas la RAM du processus.
- Contre : fichiers partiels et nettoyage à gérer, sans bénéfice pour quelques Mo.

## Décision
**Aucune persistance en V0.1.**

| Donnée | Emplacement | Après un redémarrage |
|---|---|---|
| Joueurs, tokens hachés, rôles | RAM | Perdus |
| Partie, rounds, réponses, journal des scores, brouillons | RAM | Perdus |
| Catalogues | RAM | Renvoyés par le Bridge à sa reconnexion |
| Assets audio | RAM | Perdus |
| Secrets et limites | `.env` | Source de vérité du déploiement |
| Réglages de partie | RAM, choisis par l'hôte | Valeurs par défaut du code, bornées par l'environnement |

Il n'y a pas non plus de fichier de configuration serveur : `.env` suffit (§15).

**Cache audio en RAM**
- Dictionnaire `asset_id → {bytes, mime, state, round_id, role}`.
- Plafond dur : **32 Mo au total** (`AUDIO_CACHE_MB=32`) et **2 Mo par extrait** (`MAX_CLIP_MB=2`).
- **Éviction selon le rôle** : on garde le précédent (réécoute après le reveal), le courant et le suivant (profondeur de préchargement 1, réglable à 2). Tout le reste est évincé.
- Cache plein : éviction de tout ce qui n'est ni courant ni suivant, puis refus du job avec un log.
- Seul un asset `STORED` est servi ; un upload partiel n'est jamais visible.

**Après la V0.1**
- **V0.2, candidat** à confirmer après la soirée test : snapshot `data/session.json`, écrit de façon atomique à chaque publication et à chaque `final_validate`, restauré s'il date de moins de 12 h.
- **V1** : historique des morceaux joués (`history.json`), pour éviter les répétitions d'une soirée à l'autre grâce aux `track_id` stables.
- **Pas de SQLite, V1 comprise.** Des statistiques sur plusieurs soirées feraient l'objet d'une décision séparée.

## Conséquences
- Conteneur `app` en `read_only: true`, avec `tmpfs: /tmp:size=16m` et **sans volume monté** (§17). Sur le VPS, il n'y a rien à sauvegarder hormis `.env` et le volume `caddy_data` de Caddy.
- Empreinte mémoire bornée : application de 80 à 120 Mo, cache audio de quelques Mo en pratique ; 512 Mo de RAM suffisent (§22).
- **Un redémarrage ou un crash du conteneur perd la session** : les clients reviennent à l'accueil, les joueurs doivent rejoindre à nouveau et les scores sont perdus. Risque documenté (§7.6), atténué par `restart: unless-stopped`.
- Les morceaux déjà joués peuvent revenir d'une soirée à l'autre jusqu'à la V1.
- Le modèle de données reste sérialisable (les objets de connexion en sont exclus, §13), pour que le snapshot de la V0.2 s'ajoute sans refonte ; le journal `ScoreEvent` se rejoue tel quel ([0007](0007-score-event-journal.md)).
- Ajouter ce snapshot imposera un volume pour `app` : cette décision sera prise dans une nouvelle ADR, qui remplacera celle-ci.
