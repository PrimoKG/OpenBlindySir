# OpenBlindySir — Protocole réseau

> Extrait de la spécification canonique (docs/architecture.md, §8). Ce document fait autorité pour cette section.

## 8. Protocole réseau

**Enveloppe** : `{ "t": "TYPE", ...champs }`. Union discriminée Pydantic avec **`extra="forbid"`** sur tous les messages entrants. Un entier `protocol` est échangé à la connexion ; en cas d'incompatibilité, le serveur renvoie un message clair et force le rechargement de la SPA.

### 8.1 HTTP
| Route | Auth | Rôle |
|---|---|---|
| `GET /` + statiques | aucune | SPA |
| `POST /api/session/join {password, nickname}` | limitation de débit | Crée le joueur et pose le cookie `__Host-openblindysir` |
| `GET /api/session` | cookie | « Qui suis-je ? » |
| `POST /api/session/host {host_password}` | cookie + limitation de débit | Élévation en hôte |
| `POST /api/session/leave` | cookie | Quitter, révoque le token |
| `GET /api/audio/{asset_id}` | cookie | Extrait courant ou suivant seulement. `Cache-Control: no-store, private`, aucun `Content-Disposition` |
| `GET /api/host/library` | cookie hôte | Arborescence avec total, disponibles et neufs ; fichiers écartés et codes d'erreur réservés aux hôtes |
| `GET /api/host/diagnostics` | cookie hôte | Diagnostic JSON (synchro, Bridge, brouillons non validés) |
| `GET /healthz` | aucune | Healthcheck |
| `PUT /api/bridge/catalog` | secret Bridge | Catalogue en JSON gzip |
| `PUT /api/bridge/assets/{asset_id}` | upload token à usage unique | Extrait audio |

### 8.2 WebSocket joueur `/api/ws` (cookie + vérification de l'`Origin`)
**Client → Serveur**
| Message | Rôle |
|---|---|
| `HELLO {client_version, protocol}` | Compatibilité. Le serveur répond par un `STATE` complet. |
| `PING {c}` | Synchro d'horloge et heartbeat |
| `AUDIO_STATUS {state, asset_id?, error?, clock:{offset, rtt_min}}` | Disponibilité de l'audio et diagnostic |
| `PLAYBACK_REPORT {play_id, late_ms, offset, rtt_min, out_latency, est_error_ms}` | Mesure de la synchro. **Informatif uniquement**, jamais utilisé pour le score. |
| `ANSWER_DRAFT {round_id, text}` | Brouillon. Met à jour `draft_last_changed_at`. |
| `ANSWER_SUBMIT {round_id, text}` | Validation définitive. **Horodatée par le serveur. Tout champ supplémentaire est rejeté.** |
| `HOST {cmd, round_id?, expected_phase?, args}` | Commandes hôte (liste ci-dessous) |

**Commandes `HOST`** : rejetées si la session n'est pas hôte. Toutes sont idempotentes grâce à `round_id` ou `expected_phase`.
- Configuration et partie : `configure`, `set_mode`, `start_game`, `new_game`, `end_game {current_round: "score"|"abandon"}`, `end_session`
- Round : `next`, `force_start`, `replay`, `stop`, `skip`, `add_time`, `close`, `pause`, `resume`
- Notation : `score_draft {player_id, points}`, `publish`, `undo_publish`, `adjust {player_id, delta, round_id?, note?}`
- Fin de partie : `to_final_review`, `final_set {player_id, delta}` (fixe la valeur, ce n'est pas un incrément), `final_reset`, `final_validate {expected_phase: "FINAL_SCORE_REVIEW"}`
- Joueurs : `kick`, `rename`, `participation {player_id, spectator, team?}` (lobby uniquement)
- Métadonnées : `track_metadata {title?, artist?}` (REVIEW, morceau courant uniquement)

`configure` accepte `start_game:true` dans l'enveloppe : validation atomique des nouveaux
réglages et du lancement, avec retour aux anciens réglages en cas de refus.
`publish.args.confirm_unreviewed` vaut false par défaut ; les lignes non vérifiées
déclenchent `unreviewed_scores`. `score_draft` marque une décision explicite, y compris zéro.

**Serveur → Client**
| Message | Rôle |
|---|---|
| `STATE {v, view}` | **Vue complète filtrée par `view_for()`** selon la matrice du §6.8 : phase, round, deadline (temps serveur), joueurs et statuts, sa propre réponse, progression, classement, `audio.current/next {asset_id, url}`, `play` en cours. Vue joueur et vue hôte en Player Mode pendant OPEN : `progress {validated, expected} \| null`, à `null` si `expected < 3`. La liste `players[]` ne contient **aucun** champ lié à la réponse du round en cours. Hôte en REVIEW : `answers[] {player_id, text, status, elapsed_ms, order, near_tie, late_start_ms}`. Hôte en vérification finale : `final_review[] {player_id, score_before, draft_delta, score_after, history[]}`. |
| `PONG {c, s}` | Horloge serveur |
| `PLAY {play_id, asset_id, start_at, clip_offset}` | Ordre de lecture, critique en temps. Également présent dans `STATE` pour les arrivées tardives. |
| `STOP {play_id, stop_at?}` | Arrêt immédiat ou planifié à l'instant serveur pour la pause |
| `ANSWER_ACK {round_id, status: accepted\|rejected, reason?}` | **Aucune donnée temporelle.** Le client affiche « ✓ Réponse enregistrée ». |
| `ERROR {code}` | Codes traduits côté client |
| Codes de fermeture `4001 SUPERSEDED`, `4003 KICKED`, `4004 SESSION_ENDED` | Fin de connexion explicite |

### 8.3 WebSocket Bridge `/api/bridge/ws` (`Authorization: Bearer BRIDGE_SECRET` à l'ouverture)
| Sens | Message | Rôle |
|---|---|---|
| B → S | `HELLO {bridge_id, name, version, protocol, catalog_hash, track_count, formats}` | Identification |
| S → B | `WELCOME {clip_format, bitrate, limits, catalog_needed, catalog_upload_token?}` | Format et limites demandés. **Le Bridge les plafonne à ses propres maxima.** |
| B → S | `CATALOG_CHANGED {catalog_hash}` | Après un rescan |
| S → B | `PREPARE {job_id, track_id, start_fraction, duration, upload_url, upload_token, normalize_audio?, avoid_silence?}` | La seule commande métier. Aucun chemin, aucun argument FFmpeg. |
| S → B | `CANCEL {job_id}` | Annulation |
| B → S | `JOB_PROGRESS {job_id, stage}` | Suivi |
| B → S | `JOB_DONE {job_id, actual_start, clip_duration, track_duration, bytes, sha256, tags?:{title, artist}}` | Tags pour la correction privée REVIEW puis le reveal |
| B → S | `JOB_FAILED {job_id, code}` | Code normalisé, **jamais de chemin absolu** |
| ↔ | `PING` / `PONG` | Heartbeat |

## 8.4 Registre des choix d'implémentation

La spec fixe les noms de messages, l'enveloppe et les arguments de `end_game`, `score_draft`, `adjust`, `final_set` et `final_validate`. Les choix ci-dessous complètent ce qu'elle laisse ouvert ; ils sont implémentés dans le paquet `openblindysir_protocol` (version de protocole 2). Toute modification du schéma impose d'incrémenter `PROTOCOL_VERSION` (`protocol/schema.lock.json`, vérifié en CI).

| Élément | Choix | Raison |
|---|---|---|
| `replay.args.play_id`, `stop.args.play_id` | Dernier `play_id` vu par l'hôte | Idempotence (§7.6) : `round_id` seul ne distingue pas un double clic sur « Rejouer ». |
| `add_time.args.expected_deadline` | Deadline vue par l'hôte | Un double clic ne doit pas ajouter 30 s. |
| `adjust.args.op_id` (en plus de `{player_id, delta, round_id?, note?}`) | Clé générée par le client, appliquée une seule fois par partie | `adjust` est le seul incrément sans transition d'état ; le §7.6 exige l'idempotence. |
| Enveloppe de `set_mode`, `kick`, `rename`, `end_session` | `expected_phase` (n'importe quelle phase) | « Toutes idempotentes grâce à `round_id` ou `expected_phase` » (§8.2), appliqué à la lettre : chaque commande porte exactement une des deux clés. |
| `undo_publish`, `round_id` | Round REVEALED le plus récent (`host.undo_round_id`), pas le round courant | La fenêtre du §6.5 couvre le moment où le round suivant est déjà courant en QUEUED/PREPARING/LOADING. |
| Unité de `PLAY.clip_offset` | Secondes | Unité de `AudioBufferSourceNode.start`. |
| Valeurs de `ANSWER_ACK.reason` | `closed`, `not_open`, `wrong_round`, `already_locked`, `not_participant`, `empty`, `too_long` | Le §8.2 prévoit `reason?` sans liste. Une seconde validation reçoit `already_locked` (« ignorée », §6.2). |
| Codes de fermeture hors 4001/4003/4004 | Codes standard 1000, 1001, 1008, 1009 uniquement | Aucun nouveau code applicatif. Un Bridge remplacé est fermé en `1000 "replaced"`. |
| Tableau de l'hôte en REVIEW | `answers[]` comme au §8.2, chaque élément `{player_id, text, status, elapsed_ms, order, near_tie, late_start_ms}` **plus `points_draft`, `reviewed` et `score_before`** ; le round porte aussi `ending`, `track` (morceau courant privé) et `recovery_interrupted` | Le brouillon de notation doit survivre à un rafraîchissement de l'hôte (§6.4). |
| Éléments de `final_review[]` | Champs du §8.2 **plus `adjustments[]`** (événements `adjustment` actifs) | « ▸ détail » du §6.6 liste les corrections. |
| `STATE.v` | Compteur propre à chaque connexion, incrémenté seulement quand la vue de ce destinataire change | Une version globale révélerait les validations des autres joueurs. |
| `PlayerOps.late_ms`, `DiagPlayer.browser_family` | Ajouts réservés aux hôtes | Décision de rejouer pendant OPEN (§9.4) ; panneau Diagnostic (§21). |
| Vues | Trois modèles racine distincts : `PlayerView`, `HostPlayerModeView`, `HostMcView` | Une donnée interdite à une audience n'a aucun champ pour exister dans sa vue ; vérifié sur le JSON Schema (`protocol/tests/test_views_schema_reachability.py`). |
| Messages serveur → Bridge | Validés côté Bridge comme des entrées non fiables (`extra="forbid"`, mode strict) | Le Bridge considère le serveur comme non fiable (§2, principe 6). |
| `SessionInfo.recovered`, `persistence_status` | Reprise signalée, état `disabled`, `ready` ou `failed` | Le runtime informe l'hôte d'une sauvegarde indisponible. |
| `rules`, `paused`, `team_standings` | Consigne/barème publics, frontière de pause et temps restant, sommes des points par équipe | Les navigateurs reçoivent les données autoritaires sans recalculer les règles de jeu. |
| `ViewPlayer.spectator`, `team` | Participation et équipe publiques, modifiées au lobby | Le spectateur reste hors réponses, ready check et scores. |
| `host.pool`, arborescence de bibliothèque | Comptes total, neuf, entendu, indisponible/réservé ; disponibles/neufs par dossier | Préparation et récupération d'une sélection insuffisante. |
| `host.history`, `final_results.recap` | 50 archives hôte au lobby/résultats ; réponses, points, corrections et métadonnées des manches publiées dans les résultats | Historique et exports sans révéler la manche courante ou suivante avant publication. |
| `PREPARE.upload_url` | Chemin `/api/bridge/assets/a_…` uniquement ; le Bridge le joint à **sa propre** URL de serveur | Un serveur malveillant ne peut pas rediriger un upload vers un autre hôte. |
| Réponse à `CATALOG_CHANGED` | Un nouveau `WELCOME` avec `catalog_needed=true` et un jeton d'upload neuf | Pas de nouveau type de message. |
| Heartbeat du Bridge | Seul le serveur envoie `PING{c}` (toutes les 15 s), le Bridge répond `PONG{c}` ; lien considéré mort après 45 s sans trame | La liste des commandes acceptées par le Bridge reste exactement WELCOME/PREPARE/CANCEL/PING. |
