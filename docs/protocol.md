# OpenBlindySir — Protocole réseau 13 — V0.5 développement

Ce document fait autorité pour le §8 de l'architecture. Le paquet Pydantic est
la définition exécutable ; `protocol/schema.lock.json` et le TypeScript généré
doivent correspondre. Mettre à jour serveur, Bridge et client ensemble. Toute
modification ultérieure de schéma impose un nouveau `PROTOCOL_VERSION`.

## 8.1 HTTP

### Évolutions du protocole 13

`SelectionPreviewRequest` accepte les `scoring_criteria` du brouillon (liste bornée
des cinq clés musicales) et `allow_repeats`. La réponse privée inclut
`reference_eligible`, `reference_ready`, `missing_by_criterion` et jusqu'à six
`reference_issues`. Le contrôle emploie les mêmes références fiables et suppressions
explicites que la notation ; il ne modifie pas les réglages de la partie.

`FinalResults.unreviewed_answers` conserve le nombre de réponses non entièrement
notées lors de la publication. Zéro signifie complet ; `null` signifie inconnu
pour les archives anciennes. Cette valeur accompagne les résultats, l'historique
et les exports. Les snapshots passent au format **10** (lecture 1–10) et les
historiques au format **3** (migration 1/2). Un retour à une image antérieure exige
la sauvegarde privée réalisée avant migration ; ne pas lui présenter ces nouveaux
formats. Serveur, Bridge et interface doivent tous utiliser le protocole **13**.

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
| `GET /api/host/library/search` | Hôte hors IN_GAME ou MC ; `q`, `bridge`, `folder`, `ext`, `availability`, `activation=all|active|disabled`, `tag`, `linked_to`, `offset`, `limit` (1–100), `sort` (titre/artiste/fichier/dossier) et `descending` ; tri global avant pagination, 5/10/20 par page selon la hauteur et la largeur de l’interface. |
| `POST /api/host/library/selection` | Cookie hôte + Origin, même confidentialité que la recherche ; `{sources,selection_filter}`, ≤64 Kio ; aperçu borné, limitation de débit et recontrôle du rôle et de l’époque après traitement. |
| `POST /api/host/library/sources` | Hôte, `{bridge_id,folders}` ; 202 demande asynchrone, 503 Bridge hors ligne. `null` rescane les dossiers actuels, `[]` retire tous les dossiers, `""` désigne la racine. |
| `POST /api/host/metadata/import` | Permissions bibliothèque ; JSON versions 1/2/3, ≤1 Mio/10 000 lignes ; diagnostic par ligne. |
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
modifient pas les schémas de messages du protocole 10.
Un upload catalogue commencé sur une connexion remplacée/déconnectée est refusé
avant application, même si son jeton était valide au début du transfert.

La réécoute crée un transfert isolé, jamais un asset du jeu ni un `PLAY` ; deux
jobs maximum, un par hôte, 75 s. Mode complet : segments ≤30 s et accord local du
Bridge. Les uploads privés passent les mêmes contrôles avec un plafond fixe de 2 Mio, puis sont
libérés après la réponse/annulation. `X-Audio-Offset` indique le départ du segment.
Une déconnexion/remplacement du Bridge ou un upload rejeté libère immédiatement
le transfert concerné sans attendre le délai maximal ni un second message d'échec.

## 8.2 WebSocket joueur `/api/ws`

Cookie + Origin. `HELLO {client_version,protocol:13}` reçoit un `STATE` filtré.
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
| FINAL_SCORE_REVIEW | Scène `finale`, réponses de la manche présentée et classement provisoire partagé. | Même scène publique. | Navigation privée, review_rounds et final_review, toutes les corrections. |
| FINAL_RESULTS | Tous les résultats figés et récapitulatif des manches entendues. | Idem. | Historique et actions de fin. |

`review_rounds[]` : round_id, number, state, included, played, close_reason,
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
| B → S | HELLO avec bridge_id, name, version, protocol=13, catalog_hash, track_count, formats, allow_full_review (false par défaut). |
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

Logiciel `0.5.0.dev0`, `PROTOCOL_VERSION=13`, minimum/maximum admis 13/13.
`Compatibility` décrit version, protocole, plage et formats (snapshot 10, historique 3),
dans WELCOME, erreurs de protocole joueur, diagnostics et `/api/compatibility`.
Le Bridge refuse avec le code 4 et une plage numérique extraite du motif borné
`protocol_mismatch;required=13..13` ; aucun texte distant arbitraire n'est réaffiché.
Le client web recharge au plus une fois automatiquement, puis affiche une action
de mise à jour ; une connexion STATE réussie réinitialise ce garde-fou.
La dérive des schémas est vérifiée par `tools/gen_ts_types.py --check`.
Cette évolution non publiée ne constitue pas un gel de protocole.

Snapshot 10, lecture/migration 1–10 ; historique 3, migration ancien/versions 1 et 2.
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


## Rythme et correction — introduits au protocole 7

`configure` accepte `auto_advance` (true par défaut), `intermission_s` (0–10,
2 par défaut) et `custom_points` (0–1000). Pendant IN_GAME, seuls rythme,
auto_start et répétitions restent modifiables. Le total du barème actif est borné
à 1000. La vue REVIEW expose seulement `auto_advance_at` en plus de la propre
réponse ; les réponses privées/points restent réservés à FINAL_SCORE_REVIEW.
La pause suspend aussi cette minuterie ; le redémarrage la retire et attend l’hôte.

`new_game.args.reset_library` (false par défaut) remet à zéro les exclusions sans
effacer joueurs/équipes/settings/métadonnées/archives. Les morceaux alloués puis
annulés restent consommés ; le préchargement ne consomme pas la réserve.

`score_draft.args` conserve points/player_id et ajoute `judgement` (manual ou
criteria), `title_correct`, `artist_correct`, `custom_correct` (bool/null) et
`expected_revision`. En criteria, le serveur vérifie la somme des poids actifs.
Une décision incomplète reste non vérifiée. Une révision périmée est refusée sans
mutation. Les vues et récapitulatifs conservent les décisions sémantiques.

`final_set.args.note` (120 caractères maximum) est sauvegardé atomiquement avec
delta ; `expected_delta`/`expected_note` protègent la saisie concurrente. Un delta
zéro ou final_reset efface montant/motif. Le motif reste privé avant publication,
puis figure dans les événements, résultats et archives. Snapshot 5 lit les formats
1–4 ; les archives de format 2 restent compatibles avec les champs ajoutés par défaut.

## Grand final partagé — protocole 7

`finale_reveal {expected_phase:FINAL_SCORE_REVIEW,args:{round_id}}` est réservé
aux hôtes et sélectionne une manche entendue. Le choix privé dans l’interface
n’émet pas cette commande. La vue `finale` de tous les destinataires contient la
manche présentée, ses réponses fermées et décisions/points confirmés, les identifiants
déjà dévoilés, la progression et les classements provisoires individuels/équipes.
Les temps de réception et diagnostics restent dans le panneau privé. Les autres
manches ne sont pas révélées. Les totaux additionnent le journal, les brouillons
des manches incluses déjà dévoilées et les ajustements finaux ; revisiter une manche
ne double pas ses points. Un zéro vérifié est distinct d’une décision absente.

`POST /api/host/finale/{round_id}/listen` exige cookie hôte, Origin autorisée,
phase finale et manche présentée. L’extrait original en RAM est réutilisé ou
réencodé par le transfert privé borné existant avec SHA-256/révision de source.
Après vérification, un `PLAY` commun et les URLs audio filtrées normales assurent
la lecture synchronisée. `finale_stop` (phase finale) arrête la lecture et invalide
toute préparation antérieure. Un changement de manche/phase fait de même.

`final_validate` conserve la validation explicite et le gel du journal ; aucun
point n’est attribué par vitesse. `FinalResults.podium_started_at` est l’instant
monotone serveur de validation +800 ms. Le web révèle chaque rang distinct ≤3
en ordre décroissant toutes les 1800 ms, ex æquo ensemble. La reconnexion reprend
l’étape calculée depuis l’horloge serveur. Les scènes/scores survivent au snapshot ;
au redémarrage, lecture et horodatage de cérémonie sont retirés pour éviter leur
relancement. Les anciens snapshots/archives restent compatibles par valeurs par défaut.


## Invitations et bibliothèque — protocole 10

`GET /api/host/session/access` (hôte, toutes phases) renvoie le code commun,
le jeton d’invitation et les demandes de reprise à confirmer. `POST` sur la même
route, avec Origin et `{code:null}` ou un code strict `[A-Z2-9]{6,16}`, change le
code et l’invitation, annule les demandes pendantes, mais conserve les cookies existants.
`GET /api/session/access-code` (cookie joueur) renvoie le même code commun.
Les anciens endpoints individuels restent réservés à la compatibilité de récupération ;
l’interface actuelle utilise uniquement le code commun.

`POST /api/session/access` reçoit `{nickname,code,invitation}` avec Origin.
Un jeton d’invitation valide (dans le fragment `#join=…` du QR) ou le code suffit :
pas de mot de passe. Une nouvelle identité respecte le verrou des inscriptions.
Un pseudo existant retourne 202, `request_id`, une référence publique `reference`
(8 caractères hexadécimaux) et un jeton privé, puis attend
`POST /api/host/session/access/decide {request_id,approve}`. Le nouveau navigateur
interroge `POST /api/session/access/poll {request_id,token}`. Approbation et jeton
valides sont nécessaires ; la demande expire après 120 s. La reprise révoque les
anciens cookies de cette identité, conserve ses points/équipe/réponses et donne
uniquement le rôle joueur, en conservant la participation : un ancien MC reste
spectateur. Les jetons ne sont ni journalisés ni exposés dans la vue publique.
Le cookie existant reprend directement la place sans ce parcours.

La référence apparaît dans la demande côté joueur et côté hôte pour distinguer
deux demandes visant le même pseudo ; elle ne permet pas de récupérer une place.
Au plus deux demandes actives par identité, huit par IP et `max(32,2*MAX_PLAYERS)`
au total. Rotation et transfert sont enregistrés avant confirmation/révocation :
un échec de persistance retourne HTTP 503 `{error:"persistence_failed"}`, conserve
l’ancien cookie/code et permet de réessayer la demande. La compatibilité de
récupération individuelle applique la même règle.
La lecture du code déjà créé n’écrit aucun snapshot ; elle est limitée à 30
lectures/joueur/minute et 1 000 au total. La création initiale reste durable.
Le quota des échecs d’accès est revérifié après réception du corps de requête.

`POST /api/host/game/finish {game_id,phase,confirm_unreviewed:true}` exige le cookie
hôte et Origin. Il refuse une phase/partie périmée, arrête la lecture, conserve les
brouillons et points attribués, valide une fois et passe aux résultats sans attendre
les présentations ou le podium. Les actions de nouvelle partie/fin de session sont accessibles.

`GET /api/host/library/{bridge_id}/{track_id}/preview` exige les permissions privées
bibliothèque. Il prépare un segment `review_mode=preview` de 15 s centré autour du
milieu : départ `(durée - min(15,durée))/2`. Les fichiers plus courts restent
écoutables. Un seul transfert privé par hôte, deux au total, annulation/limite 75 s,
`no-store, private` ; aucun PLAY public, consommation ou tirage aléatoire.

Les résultats de recherche comprennent `enabled`, `tags[]`, `linked_to[]`, et les
facettes `tags[]`/`linked_to[]`. Métadonnées partielles : champs omis conservés ;
listes vides effacent les catégories, `null` restaure l’import. Jusqu’à 32 valeurs
par liste, 256 caractères par valeur, dédoublonnage sans casse. Import v1/v2,
export v2, modification HTTP bornée à 24 Kio. Désactiver préserve fichiers,
historique et extraits déjà préparés ; les prochains tirages et réservations non
préparées excluent le morceau. Les totaux disponibles en tiennent compte.

Le snapshot **7** lit 1–7 et ajoute ces champs ainsi que l’accès commun chiffré
avec une clé dérivée des mots de passe de l’instance. Les demandes pendantes ne
survivent pas au redémarrage. Un retour à une version antérieure nécessite son
backup avant migration ; mettre à jour serveur et Bridge ensemble.


## Bornes de recherche et connexions joueur

La recherche privée capture les conteneurs de catalogue/métadonnées avant de
travailler dans un thread. Une seule recherche s’exécute à la fois ; les demandes
concurrentes reçoivent 429, ainsi qu’au-delà de 60/hôte/minute ou 300 au total.
Seule la page demandée est construite en modèles de réponse. Après le calcul,
le serveur revérifie cookie, rôle, phase et session avant de renvoyer les données.

Les connexions WebSocket joueur sont authentifiées avant de consommer leur quota.
Au plus deux connexions simultanées/en attente par identité autorisent le
remplacement d’un onglet ; la borne par IP et globale vaut `2*MAX_PLAYERS+4`.
Cela accueille les joueurs d’une même soirée derrière un NAT sans conserver
l’ancien plafond fixe de 20. Les quotas d’inscription et `MAX_PLAYERS` restent
indépendants.

## Notation optionnelle et vagues — protocole 10

`GameSettings`/`SettingsPatch` ajoutent `scoring_mode` (`manual`/`auto`),
`acceptance_threshold` (80–100), `answer_fields` (title/artist/album/year/featuring)
et les barèmes album/year/featuring. `answer_mode=fields` sélectionne ces critères.
Les consignes personnalisées restent manuelles. `GameRules.answer_max_chars`
communique la limite effective (défaut 1000 ; borne protocole 1500).

`MusicalMetadata.aliases` accepte au plus huit variantes de 256 caractères pour
chaque champ textuel autorisé. Les vues de correction et la bibliothèque incluent
ces variantes. `TrackMetadataArgs.regrade_auto=true` est un recalcul explicite de
la manche sélectionnée, conservant les décisions humaines. `ScoreDraftArgs` et les
récapitulatifs ajoutent album/year/featuring_correct. `ReviewRow.auto_evidence`
(critère, référence, fragment, similarité, seuil, statut) et `auto_overridden`
restent privés. `HostPanel.auto_missing_references` signale les références absentes.

`FinaleRevealArgs.fast_forward=true` termine la vague de la manche présentée.
`FinaleRound.awards_pending` annonce une révélation en cours. Les vues publiques
n’incluent que les points et critères déjà dévoilés. Snapshot 8 lit les formats 1–8
et conserve la progression des vagues ; les anciennes sessions restent manuelles.

## Références et packs — protocole 10

`cleared_fields` distingue héritage et suppression des références. `ReviewRound.scoring_reference` est privé à l’hôte et décrit la référence automatique figée ; `reference_changed` signale une modification non réévaluée. `expected_revision` protège les éditions de métadonnées, en HTTP et par commande de manche. `LibraryTrack` expose une révision et les références manquantes. Le filtre HTTP `quality=all|ready|missing` et `pool_only` prépare la correction. Les exports JSON utilisent `X-Next-Offset` lorsque la limite de réimport est atteinte. `/api/host/metadata/export` fournit des packs ZIP ; `/api/host/metadata/import-archive` accepte un pack de 8 Mio au maximum, 16 fichiers, 10 000 lignes, avec recontrôle de rôle et d’époque après le travail asynchrone. Aucun membre n’est extrait. Le snapshot 8 lit également le format 7 ; un retour à une ancienne image impose sa sauvegarde compatible.


## Soirées à thème — protocole 12

`GameSettings.selection_filter` et `SettingsPatch.selection_filter` contiennent
`query`, `genres`, `languages`, `tags`, `linked_to`, `year_min`, `year_max`.
Les listes acceptent 16 choix de 256 caractères ; mots-clés limités à 256 caractères,
années 1000–9999 dans l'ordre, sans contrôles. OU entre valeurs d'un champ, ET
entre champs. La recherche et le tirage partagent la normalisation et le moteur
thématique. Les filtres musicaux restent immuables pendant IN_GAME.

`LibraryTrack` ajoute `genres` et `languages`. `LibrarySearch` fournit les facettes
`genres`, `languages`, `years`. La recherche accepte `genre`, `language`,
`year_min`, `year_max` et les tris `year`, `genre`, `language`. `SelectionPreview`
fournit matching/available/fresh/unclassified, les facettes des dossiers choisis
et six exemples au maximum. Les listes de facettes sont bornées à 512 valeurs ;
un choix personnalisé peut sélectionner une valeur absente de la liste.
Aucun aperçu privé n'est transmis aux joueurs avant révélation.

`MetadataDocument` exporte la version 3 et continue de lire 1/2/3 ; genres et
langues sont facultatifs, 32 libellés de 256 caractères chacun. Le snapshot 9
lit 1–9 et ajoute les filtres et catégories ; les anciens paramètres restaurés
reçoivent un filtre vide. Pour un downgrade, restaurer le backup compatible.
