# OpenBlindySir — Protocole réseau 5 — V0.5 développement

Ce document fait autorité pour le §8 de l'architecture. Le paquet Pydantic est
la définition exécutable ; `protocol/schema.lock.json` et le TypeScript généré
doivent correspondre. Mettre à jour serveur, Bridge et client ensemble. Toute
modification ultérieure de schéma impose un nouveau `PROTOCOL_VERSION`.

## 8.1 HTTP

Cookie de session requis, hôte vérifié côté serveur, Origin obligatoire pour les
mutations navigateur. Les messages entrants sont stricts, `extra=forbid`.

| Route | Authentification et comportement |
|---|---|
| `POST /api/session/join` | `{password,nickname}` ; limitation de débit, verrou d'inscription. |
| `GET /api/session` | Cookie ; identité actuelle. |
| `GET /api/compatibility` | Publique ; version logiciel, protocole, plage admise, formats snapshot/historique. |
| `POST /api/session/host` | Cookie, `{host_password}`, limitation de débit. |
| `POST /api/session/leave` | Cookie ; révocation. |
| `POST /api/session/recovery-code` | Cookie ; code privé à six caractères, rotation du précédent. |
| `POST /api/session/recover` | `{password,code}`, cinq tentatives/minute partagées avec join ; code haché à usage unique, sessions précédentes révoquées, rôle player. |
| `GET /api/audio/{asset_id}` | Cookie ; seulement asset current/next servable, sinon 404. |
| `GET /api/host/library` | Hôte hors IN_GAME ou MC ; arborescence, sources scannées/erreur, disponibilités. |
| `GET /api/host/library/search` | Hôte hors IN_GAME ou MC ; `q`, `bridge`, `folder`, `ext`, `availability`, `offset` ; pages de 100 résultats au maximum. |
| `POST /api/host/library/sources` | Hôte, `{bridge_id,folders}` ; 202 demande asynchrone, 503 Bridge hors ligne. `null` rescane les dossiers actuels, `[]` retire tous les dossiers, `""` désigne la racine. |
| `POST /api/host/metadata/import` | Permissions bibliothèque ; JSON version 1, ≤1 Mio/10 000 lignes ; diagnostic par ligne. |
| `GET /api/host/metadata` | Permissions bibliothèque ; export des champs fusionnés et chemins connus. |
| `PUT /api/host/metadata` | Permissions bibliothèque ; `{bridge_id,track_id,metadata}`. |
| `GET /api/host/review/{round_id}/audio` | Hôte uniquement, FINAL_SCORE_REVIEW/FINAL_RESULTS et manche entendue ; `mode=excerpt|full`, offset fini ≥0 et avant fin de source. |
| `GET /api/host/diagnostics` | Cookie hôte ; diagnostic privé sans secret. Sources masquées à l'hôte joueur en IN_GAME. |
| `GET /api/host/history` et `/{game_id}` | Hôte hors IN_GAME ou MC ; liste résumée puis archive complète, format 2. |
| `DELETE /api/host/history` et `/{game_id}` | Mêmes permissions + Origin, `{confirm:true}` strict ; purge des deux snapshots, 503 si sauvegarde refusée. |
| `POST /api/host/bridges/{bridge_id}/revoke` | Cookie hôte + Origin, `{confirm:true}` strict ; révocation privée de ce seul UUID et fermeture de son lien. |
| `GET /healthz` | Publique ; santé agrégée. |
| `PUT /api/bridge/catalog` | Secret + jeton catalogue unique + `X-Bridge-Id`, gzip borné. |
| `PUT /api/bridge/assets/{asset_id}` | Jeton upload unique lié au job/propriétaire ; magic, taille et SHA-256. |

Audio : `Cache-Control: no-store, private`, pas de nom de fichier ni Content-Disposition.
La réponse 202 d'une demande de scan contient `scan_revision`, la révision du
catalogue à la réception de la commande. `GET /api/host/library` fournit l'en-tête
`X-Catalog-Revisions`, objet JSON UUID → révision. Une nouvelle réception de
catalogue incrémente cette révision même si son hash reste identique. L'interface
attend une révision supérieure et les dossiers demandés, ou une erreur de scan,
avant d'autoriser une autre modification. Vérification pendant 75 s au maximum,
avec intervalles de 1, 2 puis 4 s. Ces informations HTTP supplémentaires ne
modifient pas les schémas de messages du protocole 5.
Un upload catalogue commencé sur une connexion remplacée/déconnectée est refusé
avant application, même si son jeton était valide au début du transfert.

La réécoute crée un transfert isolé, jamais un asset du jeu ni un `PLAY` ; deux
jobs maximum, un par hôte, 75 s. Mode complet : segments ≤30 s et accord local du
Bridge. Les uploads privés passent les mêmes contrôles avec un plafond fixe de 2 Mio, puis sont
libérés après la réponse/annulation. `X-Audio-Offset` indique le départ du segment.
Une déconnexion/remplacement du Bridge ou un upload rejeté libère immédiatement
le transfert concerné sans attendre le délai maximal ni un second message d'échec.

## 8.2 WebSocket joueur `/api/ws`

Cookie + Origin. `HELLO {client_version,protocol:5}` reçoit un `STATE` filtré.
`PING {c}` reçoit `PONG {c,s}`. `AUDIO_STATUS` et `PLAYBACK_REPORT` sont des
diagnostics, sans influence sur la notation.

`ANSWER_DRAFT {round_id,text}` sauvegarde le brouillon et sa réception serveur.
`ANSWER_SUBMIT {round_id,text}` valide définitivement : le serveur calcule temps
et rang. Aucun timestamp client accepté. `ANSWER_ACK` contient statut et raison,
jamais de temps. Fermeture : brouillon non vide → CAPTURED, sans rang/temps officiel.

`HOST {cmd,round_id?,expected_phase?,args}` : clés exclusives selon la commande.

- Partie : configure, set_mode, start_game, new_game, end_game, end_session.
- Choix MC : `select_track {round_number:1..100, expected_revision:>=0,
  bridge_id:UUID|null, track_id:ID|null}` avec expected_phase LOBBY/IN_GAME.
  Les deux identifiants sont présents ensemble, ou null pour revenir au hasard.
  Hôte MC uniquement ; sources/répétitions/réservations contrôlées atomiquement.
  La révision différente est `stale_command`, la cible déjà préparée `invalid_state`.
- Lecture/manche : next, force_start, replay, stop, pause, resume, skip, add_time, close.
- Revue globale : score_draft, track_metadata, final_set, final_reset, final_validate.
- Participants : kick, rename, participation (lobby), join_lock.
- Compatibilité de schéma : publish, undo_publish, adjust sont toujours refusées.

`configure.start_game=true` applique réglages et lancement atomiquement.
`score_draft` et `track_metadata` désignent **n'importe quelle manche entendue de
la partie actuelle**, uniquement en FINAL_SCORE_REVIEW. Les manches annulées
refusent les points. Points/deltas : entiers ±1000, valeurs absolues remplacées.
`final_set` fixe une correction, pas un incrément. `final_validate.args.confirm_unreviewed`
vaut false ; les réponses non vérifiées provoquent `unreviewed_scores`. Une note
zéro marque une décision explicite. La validation append tous les événements non
nuls de manches et corrections, puis fige le journal.

`end_game` accepte round_id ou expected_phase (exactement une clé). `args.current_round`
vaut score ou abandon. En revue finale/résultats, une répétition est sans effet.
Avant le premier départ, elle exclut la manche ; en OPEN, ferme et conserve les
réponses ou les exclut des points selon le mode. `join_lock {locked}` utilise la
phase attendue ; la reconnexion d'une identité existante reste autorisée.

**Vues `STATE {v,view}`** : version propre à chaque connexion, uniquement lorsque
sa vue change. Les racines PlayerView/HostPlayerModeView/HostMcView empêchent la
présence structurelle de champs réservés à l'hôte.

`McPanel.manual_choices[]` et `selection_revision` sont strictement réservés à
HostMcView au lobby/en jeu. Chaque choix expose numéro, identifiants opaques,
nom de fichier/Bridge/dossier et métadonnées disponibles, locked/manual/error.
Ces champs ne sont jamais dans HostPanel commun ni les vues joueur/hôte joueur.
Verrou dès demande d'extrait ; une manche manuelle attend force_start explicite.
Une erreur garde la référence, permet remplacement/retour hasard, ne substitue
pas automatiquement une piste. Le préchargement réserve des numéros de manche.

`LibraryTrack` ajoute bridge_name, duration_ms (si mesurée), played, reserved et
in_pool. La recherche reste privée et bornée ; sa disponibilité indicative ne
remplace pas la validation serveur de select_track. Aucun chemin absolu envoyé.

| Phase | Joueur / hôte joueur | MC | Panneau privé de l'hôte |
|---|---|---|---|
| IN_GAME / OPEN | Propre réponse ; progression anonyme si ≥3 attendus. | Morceau et réponses/statuts en direct, sans points. | Commandes et diagnostic, pas de revue globale. |
| IN_GAME / REVIEW | Propre réponse conservée ; aucun morceau ou point révélé. | Morceau, progression fermée. | Suivant/arrêt ; review_rounds vide. |
| FINAL_SCORE_REVIEW | Attente, classements vides. | Idem avec rôle hôte. | review_rounds et final_review, totaux provisoires. |
| FINAL_RESULTS | Tous les résultats figés et récapitulatif des manches entendues. | Idem. | Historique et actions de fin. |

`review_rounds[]` : round_id, number, state, included, close_reason,
recovery_interrupted, track (titre/artiste/featuring/album/année/nom/dossier),
excerpt_duration_ms, track_duration_ms, metadata_revision, answers[]. La révision
augmente lorsqu'une correction de métadonnées est appliquée, y compris pour
une valeur vide revenant à l'import ; l'éditeur attend cet accusé. Réponse : player_id, text,
status, elapsed_ms, order, near_tie, late_start_ms, received_at_wall_ms,
points_draft, reviewed, score_before. L'heure CAPTURED est celle du dernier
brouillon reçu ; elapsed/rang restent null. `final_review[]` contient les
historiques, corrections, score_before, draft_delta, score_after. `joins_locked`
est privé à l'hôte ; les nouveaux joins refusés reçoivent `join_locked`.

`PLAY {play_id,asset_id,start_at,clip_offset}` et `STOP {play_id,stop_at?}`
restent réservés à la lecture synchronisée. Replay et stop portent play_id ;
add_time porte expected_deadline. La latence manuelle est une préférence locale
appliquée au prochain PLAY et son STOP, sans changer les messages de réponse.
Fermetures : 4001 SUPERSEDED, 4003 KICKED, 4004 SESSION_ENDED ; autres codes standard.

## 8.3 WebSocket Bridge `/api/bridge/ws`

`Authorization: Bearer <secret de cet UUID>`. Huit UUID connectés maximum ; une
connexion du même UUID remplace uniquement ce lien après authentification. Le
registre privé stocke les hashes/révocations de 64 identités au maximum. Le secret
bootstrap historique se lie durablement au premier UUID et ne sert pas à un second.
L'identité est revérifiée après HELLO, chaque trame et les corps HTTP streamés.

| Sens | Message |
|---|---|
| B → S | HELLO avec bridge_id, name, version, protocol=5, catalog_hash, track_count, formats, allow_full_review (false par défaut). |
| S → B | WELCOME avec clip_format, bitrate, limits, catalog_needed, catalog_upload_token si nécessaire, compatibility. |
| B → S | CATALOG_CHANGED ; provoque WELCOME + nouveau jeton, même si seul le choix de dossiers a changé. |
| S → B | SCAN_SOURCES `{folders:null|list}` ; sous-dossiers relatifs NFC autorisés localement uniquement. |
| S → B | PREPARE avec job_id, track_id, start_fraction, duration, upload_url, upload_token, normalize_audio, avoid_silence, exact_start?, review_mode?, replay_sha256?, expected_source_revision?. |
| S → B | CANCEL `{job_id}`. |
| B → S | JOB_PROGRESS `{job_id,stage}`. |
| B → S | JOB_DONE : job_id, actual_start, clip_duration, track_duration, bytes, sha256, tags?, input_duration?, source_revision?. |
| B → S | JOB_FAILED `{job_id,code}` : NO_AUDIO, DECODE_ERROR, TOO_SHORT, silent_audio, TIMEOUT, NOT_FOUND, INVALID_UPLOAD, CANCELLED, QUEUE_FULL. |
| S → B / B → S | PING/PONG : 15 s, déconnexion après 45 s sans trame. |

`upload_url` est strictement `/api/bridge/assets/a_…` sur le serveur configuré
localement. Aucun chemin absolu, URL tierce ou argument FFmpeg. `exact_start`
n'est honoré qu'en mode review. Mode complet plafonné localement à 30 s.
La révision de source hash taille/mtime, sans transférer le contenu complet.

Catalogue : JSON gzip ≤8 Mio compressé/32 Mio décompressé, ≤200 000 entrées par
Bridge et 200 000 pistes cumulées conservées, champs scanned_folders, source_error, ambiguous_paths. Identité de piste :
bridge_id + hash du chemin NFC. Tokens/jobs liés au propriétaire ; mauvais jeton
ou identité refusés sans consommer le bon jeton. Les noms ne vont jamais aux joueurs.

## 8.4 Compatibilité et persistance

Logiciel `0.5.0.dev0`, `PROTOCOL_VERSION=5`, minimum/maximum admis 5/5.
`Compatibility` décrit version, protocole, plage et formats (snapshot 4, historique 2),
dans WELCOME, erreurs de protocole joueur, diagnostics et `/api/compatibility`.
Le Bridge refuse avec le code 4 et une plage numérique extraite du motif borné
`protocol_mismatch;required=5..5` ; aucun texte distant arbitraire n'est réaffiché.
Le client web recharge au plus une fois automatiquement, puis affiche une action
de mise à jour ; une connexion STATE réussie réinitialise ce garde-fou.
La dérive des schémas est vérifiée par `tools/gen_ts_types.py --check`.
Cette évolution non publiée ne constitue pas un gel de protocole.

Snapshot 4, lecture/migration 1/2/3/4 ; historique 2, migration ancien/version 1.
Un format futur inconnu provoque un refus explicite sans repli sur un état plus ancien.
La corruption connue peut utiliser la précédente copie valide. Audio et jetons bruts
restent exclus. Les archives sont figées, sans audio, 50 parties/90 jours/16 Mio ;
`HostPanel.history` reste vide, `history_count` indique la liste chargée par HTTP.
L'hôte joueur en IN_GAME ne reçoit ni archives, ni détails de sources, ni dossiers
sélectionnés dans ses réglages. Le MC conserve ses permissions de bibliothèque.
Une sélection aléatoire non préparée attend son Bridge au plus 45 s, puis cherche
une autre source ; une sélection manuelle exige une décision explicite.
Publications anciennes d'une partie inachevée révoquées et restaurées en brouillons ;
archives finales conservées. Voir [ADR 0011](adr/0011-global-review-and-private-replay.md),
[ADR 0012](adr/0012-dynamic-sources-and-metadata.md),
[ADR 0015](adr/0015-v05-private-bridges-history-compatibility.md) et [V0.5](v0.5.md).
