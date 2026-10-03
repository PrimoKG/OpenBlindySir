# 0006 — Vues d'état complètes par destinataire sur WebSocket
Statut : Accepté ; contenu de revue remplacé par [0011](0011-global-review-and-private-replay.md) en V0.2 · Date : 2026-10-01

## Contexte
Chaque client OpenBlindySir (joueur, hôte en Host Player Mode, hôte en MC Mode) reçoit l'état de la partie par un WebSocket `/api/ws` authentifié par cookie. Le volumineux (catalogue, extraits) passe en HTTP (`docs/architecture.md` §3).

Contraintes :
- **reconnexions fréquentes** : rafraîchissement, téléphone verrouillé, onglet en arrière-plan, changement de réseau (§7.4, §9.6) ;
- **anti-spoiler** : ce que voit chaque client dépend de son rôle et de la phase (matrice du §6.8). En REVIEW, l'hôte voit toutes les réponses et leurs temps, pas les joueurs ; en MC Mode, l'hôte voit les métadonnées du morceau, pas en Player Mode ; en OPEN, les joueurs ne voient qu'un compteur anonyme ;
- la désynchronisation de l'état client après une reconnexion est un risque HIGH (§27) ;
- l'état est petit : une partie, une quinzaine de joueurs, quelques Ko.

## Options considérées
**A. Événements incrémentaux** (`player_joined`, `answer_locked`, `round_revealed`…) appliqués par le client.
- Pour : peu de bande passante.
- Contre : chaque type d'événement doit être filtré par rôle, ce qui multiplie les points de fuite ; une reconnexion exige un rejeu ou une resynchronisation ; risque élevé de désynchronisation ; logique d'état dupliquée côté client.

**B. Vue complète commune, masquage côté client.**
- Pour : un seul message pour tout le monde.
- Contre : tout ce qui est masqué reste lisible dans les DevTools. Inacceptable pour l'anti-spoiler.

**C. Vue complète filtrée par destinataire, poussée à chaque changement.**
- Pour : reconnexion triviale, un seul point de contrôle anti-spoiler, client sans logique de jeu.
- Contre : données redondantes d'un envoi à l'autre, une vue à calculer par client.

## Décision
Option C, complétée par quelques messages critiques.

- Le serveur envoie à chaque client `STATE {v, view}`, où `view = view_for(destinataire)` est sa **vue complète**, filtrée selon son rôle (joueur, hôte `player_mode`, hôte `mc`) et la phase.
- **`view_for()` est la seule fonction qui projette l'état vers un client.** C'est l'unique point de contrôle contre les fuites de spoilers : aucun autre chemin de code ne sérialise l'état vers un client.
- Une vue complète part en réponse au `HELLO` (connexion ou reconnexion), puis après chaque changement. Les diffusions sont **regroupées sur 50 à 100 ms**.
- Messages hors `STATE`, parce qu'ils sont critiques en temps ou ponctuels : `PLAY` (également présent dans `STATE` pour les arrivées tardives), `STOP`, `PONG` (immédiat), `ANSWER_ACK` (sans donnée temporelle), `ERROR`, codes de fermeture `4001 SUPERSEDED`, `4003 KICKED`, `4004 SESSION_ENDED`.
- Le client ne contient **aucune règle de jeu** : il garde la dernière vue (`useSyncExternalStore`), l'affiche et envoie des intentions.

**Règles portées par `view_for()`** (extraits ; la matrice complète est au §6.8) :
- avant REVEALED, aucune métadonnée du morceau pour un joueur ni pour l'hôte en Player Mode ; l'hôte en MC Mode voit le morceau courant et les suivants ;
- jamais de `relpath`, de `track_id` ni de `draft_last_changed_at` dans une vue joueur ;
- en OPEN, vue joueur et vue hôte en Player Mode : `progress {validated, expected}`, ou `null` si `expected < 3` ; l'hôte en MC Mode n'est pas compté dans `expected` ; `players[]` ne contient **aucun** champ lié à la réponse du round en cours ;
- en REVIEW, `answers[] {player_id, text, status, elapsed_ms, order, near_tie, late_start_ms}` uniquement dans la vue hôte ;
- en FINAL_SCORE_REVIEW, `final_review[]` uniquement dans la vue hôte ; les joueurs voient le dernier classement publié, figé, sans `draft_delta` ni `score_after`.

Le WebSocket du Bridge (`/api/bridge/ws`) n'est pas concerné : c'est un protocole de commandes fermé ([0002](0002-bridge-outbound-connection-and-sandbox.md)).

## Conséquences
- **Reconnexion triviale** : un `STATE` suffit, sans rejeu ; le brouillon de réponse du joueur revient avec la vue.
- **Fuites testables en un seul endroit** : le test 7 (§20.1) vérifie l'objet sérialisé **en entier** pour chaque rôle et chaque phase, ce qui détecte aussi un champ ajouté plus tard ; il vérifie notamment que `progress` vaut `null` sous 3 joueurs attendus et n'expose aucun identifiant.
- Toute nouvelle donnée destinée aux clients passe par `view_for()`, qui construit la vue par inclusion explicite des champs, jamais par sérialisation brute de l'état.
- Bande passante : quelques Ko par vue et par client, bornés par le regroupement ; le WebSocket représente moins de 5 Mo par soirée (§22).
- Coût CPU : une vue par client et par lot, attendu négligeable pour une quinzaine de joueurs ; à vérifier avec 50 bots (`tools/bots.py`, §20.2).
- `PLAY` et `PONG` ne passent jamais par le regroupement, pour ne pas dégrader la synchronisation (§9).
- Les messages sont des unions discriminées Pydantic dans `openblindysir_protocol`, avec `extra="forbid"` sur tout message entrant ; les types TypeScript en sont générés et leur dérive est vérifiée en CI (`protocol-drift`).
- Un entier `protocol` est échangé à la connexion ; en cas d'incompatibilité, le serveur le signale clairement et force le rechargement de l'interface.
