# 0003 — Mesure du temps de réponse côté serveur
Statut : Accepté   ·   Date : 2026-10-01

## Contexte
Dans OpenBlindySir, **la notation est entièrement humaine** : le serveur ne connaît pas la bonne réponse et n'évalue jamais le contenu d'une réponse. L'hôte attribue les points (+N, 0, −N) avec le barème de son choix : +3 au premier bon, +2 au deuxième, +1 aux autres, ou +1 à tout le monde (`docs/architecture.md` §1, §6.3).

Pour décider, l'hôte a besoin de chaque réponse, de son temps, de l'ordre de validation, d'une indication de quasi-égalité et d'un éventuel retard audio du joueur. Ces données doivent être **impossibles à falsifier par un client**, simples et explicables.

Les joueurs sont à distance. Sources d'erreur sur un temps de réponse : latence aller (10 à 200 ms), synchronisation audio (environ ±60 ms, §9.1), Bluetooth (100 à 300 ms) et surtout temps de réaction humain (plusieurs secondes).

Le round ne doit pas devenir un jeu de réaction chronométré : pendant le round, le joueur voit seulement « ✓ Réponse enregistrée ».

## Options considérées
**A. Timestamp fourni par le client.** Pour : mesure au plus près de l'écoute. Contre : falsifiable avec les DevTools ; dépend de la synchronisation d'horloge du client.

**B. Horodatage serveur avec compensation RTT** (soustraire une estimation de la latence aller). Pour : corrige en partie la latence réseau. Contre : ne corrige qu'une source d'erreur, et seulement en partie ; ouvre une triche (gonfler son RTT) ; difficile à expliquer.

**C. Ordre d'arrivée seul, sans temps.** Pour : minimal. Contre : l'hôte ne voit ni les écarts ni les quasi-égalités ; insuffisant pour un barème fondé sur la rapidité.

**D. Horodatage serveur brut, horloge monotone, sans compensation.** Pour : infalsifiable, déterministe, explicable en une phrase. Contre : un joueur loin du serveur paie sa latence aller.

**E. Barème de vitesse automatique** (points pré-remplis, bouton « appliquer 3/2/1 »). Contre : contraire à une notation entièrement humaine. Exclu définitivement (§24).

## Décision
Option D. **La rapidité est mesurée et affichée, mais elle n'est jamais convertie automatiquement en points.**

**Mesure**
```
elapsed = answer_received_at_server − official_start_at
```
- `answer_received_at_server` : horloge **monotone** du serveur (`time.monotonic_ns()`), lue **à l'entrée du handler** `ANSWER_SUBMIT`, avant tout `await` ou toute validation coûteuse.
- `official_start_at` : le `start_at` du **premier** `PLAY` du round. Il ne change jamais, ni sur un replay, ni après un stop. La pause (V0.2) exclura le temps passé en pause.
- **Aucun timestamp client** : `ANSWER_SUBMIT {round_id, text}` est déclaré avec `extra="forbid"` ; tout champ supplémentaire est rejeté par le schéma.
- **Aucune compensation RTT ni réseau.** `PLAYBACK_REPORT` est informatif et n'entre jamais dans le score.

**Données produites pour chaque réponse validée (`LOCKED`)**
| Donnée | Définition |
|---|---|
| `elapsed_ms` | Mesure ci-dessus |
| `order` | Rang de validation 1, 2, 3…, strict et déterministe car les messages sont traités en série ([0001](0001-single-process-in-memory-server.md)). Seules les réponses `LOCKED` ont un rang. |
| `near_tie` | Vrai si l'écart avec la validation précédente est inférieur à `NEAR_TIE_MS` (300 ms par défaut, réglable). Affiché « 2≈ » : l'ordre n'est pas significatif. |
| `late_start_ms` | Mesure serveur : `max(0, ready_received_at − official_start_at)`. Vaut aussi la durée d'une déconnexion pendant la lecture. |

**Brouillon non validé**
- À la fermeture, un brouillon non vide devient `CAPTURED` : **ni rang ni temps**, il ne compte pas comme une réponse et ne déclenche rien. L'hôte peut quand même lui donner des points.
- `draft_last_changed_at` (heure monotone de réception du dernier `ANSWER_DRAFT`, précise à environ 0,5 s à cause du debounce) est conservé **pour le diagnostic uniquement** : aucun rang, aucun bonus, aucun calcul. En V0.1, il n'apparaît que dans le panneau Diagnostic de l'hôte.
- Validation reçue après la fermeture : rejetée (`ANSWER_ACK` avec `rejected: closed`) ; le dernier brouillon reçu reste `CAPTURED`. La décision ne dépend que de l'ordre de traitement.

**Visibilité et affichage**
- `ANSWER_ACK` ne porte **aucune donnée temporelle**. Temps et rangs sont visibles de l'hôte en REVIEW, puis de tous au reveal (§6.8).
- Affichage au dixième de seconde, avec une virgule en français : « 4,2 s ».
- Le serveur n'applique aucun barème, ne pré-remplit aucun point et ne propose aucun bouton du type « appliquer 3/2/1 ».

## Conséquences
- Un client ne peut pas améliorer son temps : seul compte l'instant où le serveur traite son message.
- Ordre et temps sont reproductibles en test avec une horloge injectée.
- Un joueur en 4G ou loin du VPS perd quelques dizaines de millisecondes, au pire 200 ms : c'est négligeable devant le temps de réaction humain, et `near_tie` signale les ordres non significatifs. L'hôte tranche.
- Le Bluetooth et les départs audio tardifs ne sont pas compensés : `late_start_ms` (« ⚠ audio +2,3 s ») informe l'hôte, qui peut faire rejouer l'extrait pour tout le monde.
- Bloquer la boucle d'événements fausserait les horodatages : mutations synchrones et lecture de l'horloge à l'entrée du handler sont obligatoires ([0001](0001-single-process-in-memory-server.md)).
- Les logs contiennent `answer_locked(player_id, order, elapsed_ms)`, jamais le contenu de la réponse (seulement sa longueur).
- `received_at_wall` (horodatage ISO) sert uniquement à l'export et aux logs, jamais au calcul.
- Tests obligatoires (§20.1, point 3) : `elapsed` calculé depuis `official_start_at` et inchangé après un replay ou un stop ; `ANSWER_SUBMIT` contenant un champ de timestamp rejeté ; ordre strict pour 10 validations traitées dans la même itération de la boucle ; `near_tie` vrai sous le seuil et faux au-dessus ; `late_start_ms` calculé depuis `ready_received_at` ; `draft_last_changed_at` sans effet sur `order` ni sur les points ; arrondi d'affichage (4,237 s donne « 4,2 s ») testé côté web.
