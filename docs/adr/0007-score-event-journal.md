# 0007 — Journal d'événements de score comme source de vérité
Statut : Accepté   ·   Date : 2026-10-01

## Contexte
Dans OpenBlindySir, la notation est entièrement humaine ([0003](0003-server-side-answer-timing.md)). L'hôte :
- note chaque round en brouillon pendant REVIEW, puis publie ;
- peut annuler la dernière publication, ou appliquer un ajustement ponctuel à tout moment pendant `IN_GAME` ;
- passe obligatoirement par une **vérification finale** (`FINAL_SCORE_REVIEW`) avant les résultats, où il peut corriger n'importe quel joueur, lui compris (`docs/architecture.md` §6.4 à §6.7).

Il faut donc des corrections **traçables et réversibles**, un historique par joueur (« ▸ détail ») pour repérer une erreur, des ajustements finaux affichés en toute transparence et des invariants vérifiables par des tests. Les brouillons doivent survivre à un rafraîchissement, une déconnexion ou un changement d'appareil de l'hôte, sans jamais compter tant qu'ils ne sont pas validés.

## Options considérées
**A. Compteur de score modifiable par joueur.**
- Pour : simple à lire.
- Contre : corrections silencieuses ; annuler suppose de mémoriser les anciennes valeurs ; aucun historique ; invariants impossibles à vérifier.

**B. Journal modifiable** (un undo supprime ou modifie un événement).
- Pour : journal compact.
- Contre : la trace d'une correction disparaît ; l'historique n'est plus fiable.

**C. Journal `ScoreEvent` en ajout seul, score calculé.**
- Pour : annulable, testable, traçable ; l'historique et les ajustements finaux se lisent directement.
- Contre : le score se recalcule à la demande.

## Décision
Option C. **Le journal `ScoreEvent` est l'unique source de vérité des scores.**

**Événement** (en ajout seul) : `id`, `game_id`, `player_id`, `round_id?`, `delta` (entier signé, borné à ±1000), `kind`, `by` (le joueur hôte), `at`, `note?`, `revokes?` (liste d'identifiants).

| `kind` | Créé par | `round_id` |
|---|---|---|
| `round` | `publish` : un événement par joueur dont le delta est non nul | oui |
| `adjustment` | `adjust` : correction ponctuelle pendant `IN_GAME`, après une confirmation courte | optionnel |
| `final_adjustment` | `final_validate` : un événement par joueur dont le delta est non nul | non |
| `revoke` | `undo_publish` : annule les événements `round` désignés | oui |

**Invariants**
- `score(joueur) = Σ delta des événements actifs`, c'est-à-dire non révoqués ; un `revoke` porte lui-même un delta de 0.
- **Aucun champ `score` n'est stocké**, nulle part.
- Les brouillons (`score_draft` d'un round, `final_draft` de la vérification finale) **ne sont jamais des événements**. Ils vivent côté serveur, ne sont visibles que de l'hôte et ne deviennent des faits que par une action explicite (`publish`, `final_validate`).
- Après `FINAL_RESULTS`, **aucun événement ne peut s'ajouter** pour ce `game_id` : les scores de la partie sont figés en V0.1.
- Aucun événement n'est créé automatiquement : la rapidité ne donne jamais de points ([0003](0003-server-side-answer-timing.md)).

**Cycle de vie**
- **REVIEW** : `score_draft {player_id, points}` (0, +1, +2, +3 ou ±N, hôte compris), puis `publish` crée les événements `round` et passe le round en REVEALED.
- **Annulation** : `undo_publish` n'est possible que sur le round REVEALED le plus récent, tant que le round suivant n'a pas atteint COUNTDOWN. Il crée des `revoke` et remet le round en REVIEW avec le brouillon précédent restauré.
- **Vérification finale obligatoire** : il n'existe **aucune transition `IN_GAME → FINAL_RESULTS`**. On y entre après le dernier round publié (`to_final_review`) ou par toute fin anticipée (`end_game`). Pour chaque joueur, l'hôte voit score actuel → ajustement en brouillon → score résultant, avec le détail round par round. `final_set {player_id, delta}` fixe la valeur du brouillon (ce n'est pas un incrément), `final_reset` l'efface. Après une confirmation qui récapitule les corrections, `final_validate {expected_phase: "FINAL_SCORE_REVIEW"}` crée les `final_adjustment`, puis seulement fait passer la partie en `FINAL_RESULTS`.
- Les commandes portent le `round_id` ou la phase attendue : elles sont **idempotentes** (double clic, deux appareils hôtes).

## Conséquences
- Une erreur de notation se corrige toujours sans effacer de trace : brouillon avant publication, annulation de la dernière publication, ajustement ponctuel ou ajustement final.
- Le détail par joueur et les ajustements finaux affichés dans `FINAL_RESULTS` (« ajustement final : Ayoub +2 ») se lisent directement dans le journal.
- Le classement final partage les rangs en cas d'égalité (1, 1, 3), sans départage automatique ; l'hôte peut départager pendant la vérification finale.
- Une nouvelle partie repart de zéro (nouveau `game_id`) en conservant les joueurs. Rouvrir la vérification finale après `FINAL_RESULTS` est hors MVP.
- Le score se recalcule à la demande sur quelques centaines d'événements au plus : coût négligeable.
- Le snapshot candidat de la V0.2 pourra rejouer le journal tel quel ([0005](0005-no-database-v01.md)).
- Événements de log associés : `round_published`, `publish_undone`, `score_adjusted`, `final_review_started`, `final_validated(corrections=n)`.
- Tests obligatoires (§20.1, points 4 et 5) : invariant vérifié après chaque opération ; `publish` crée un `round` par delta non nul ; `undo_publish` crée un `revoke`, restaure le brouillon et devient impossible une fois le round suivant en COUNTDOWN ; `adjust` fonctionne, hôte compris ; deltas négatifs et bornes respectés ; aucun brouillon ne crée d'événement ; `final_set` ne crée pas d'événement ; `final_validate` crée exactement un `final_adjustment` par delta non nul et reste idempotent ; brouillon conservé après la reconnexion de l'hôte ; tout ajout refusé après `FINAL_RESULTS`. Le test de permissions (point 6) couvre aussi `final_set` et `final_validate`.
