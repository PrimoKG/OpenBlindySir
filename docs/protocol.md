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
| `GET /api/host/library` | cookie hôte | Arborescence des dossiers et nombre de morceaux, sans noms de fichiers |
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
- Round : `next`, `force_start`, `replay`, `stop`, `skip`, `add_time`, `close`
- Notation : `score_draft {player_id, points}`, `publish`, `undo_publish`, `adjust {player_id, delta, round_id?, note?}`
- Fin de partie : `to_final_review`, `final_set {player_id, delta}` (fixe la valeur, ce n'est pas un incrément), `final_reset`, `final_validate {expected_phase: "FINAL_SCORE_REVIEW"}`
- Joueurs : `kick`, `rename`

**Serveur → Client**
| Message | Rôle |
|---|---|
| `STATE {v, view}` | **Vue complète filtrée par `view_for()`** selon la matrice du §6.8 : phase, round, deadline (temps serveur), joueurs et statuts, sa propre réponse, progression, classement, `audio.current/next {asset_id, url}`, `play` en cours. Vue joueur et vue hôte en Player Mode pendant OPEN : `progress {validated, expected} \| null`, à `null` si `expected < 3`. La liste `players[]` ne contient **aucun** champ lié à la réponse du round en cours. Hôte en REVIEW : `answers[] {player_id, text, status, elapsed_ms, order, near_tie, late_start_ms}`. Hôte en vérification finale : `final_review[] {player_id, score_before, draft_delta, score_after, history[]}`. |
| `PONG {c, s}` | Horloge serveur |
| `PLAY {play_id, asset_id, start_at, clip_offset}` | Ordre de lecture, critique en temps. Également présent dans `STATE` pour les arrivées tardives. |
| `STOP {play_id}` | Arrêt immédiat |
| `ANSWER_ACK {round_id, status: accepted\|rejected, reason?}` | **Aucune donnée temporelle.** Le client affiche « ✓ Réponse enregistrée ». |
| `ERROR {code}` | Codes traduits côté client |
| Codes de fermeture `4001 SUPERSEDED`, `4003 KICKED`, `4004 SESSION_ENDED` | Fin de connexion explicite |

### 8.3 WebSocket Bridge `/api/bridge/ws` (`Authorization: Bearer BRIDGE_SECRET` à l'ouverture)
| Sens | Message | Rôle |
|---|---|---|
| B → S | `HELLO {bridge_id, name, version, protocol, catalog_hash, track_count, formats}` | Identification |
| S → B | `WELCOME {clip_format, bitrate, limits, catalog_needed, catalog_upload_token?}` | Format et limites demandés. **Le Bridge les plafonne à ses propres maxima.** |
| B → S | `CATALOG_CHANGED {catalog_hash}` | Après un rescan |
| S → B | `PREPARE {job_id, track_id, start_fraction, duration, upload_url, upload_token}` | La seule commande métier. Aucun chemin, aucun argument FFmpeg. |
| S → B | `CANCEL {job_id}` | Annulation |
| B → S | `JOB_PROGRESS {job_id, stage}` | Suivi |
| B → S | `JOB_DONE {job_id, actual_start, clip_duration, track_duration, bytes, sha256, tags?:{title, artist}}` | Les tags servent **uniquement au reveal** |
| B → S | `JOB_FAILED {job_id, code}` | Code normalisé, **jamais de chemin absolu** |
| ↔ | `PING` / `PONG` | Heartbeat |
