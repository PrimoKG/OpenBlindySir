# OpenBlindySir — Synchronisation audio

> Extrait de la spécification canonique (docs/architecture.md, §9). Ce document fait autorité pour cette section.

## 9. Synchronisation audio

### 9.1 Précision visée
| Source d'erreur | Ordre de grandeur |
|---|---|
| Offset d'horloge (meilleurs RTT sur 8 à 10 échantillons) | 2 à 20 ms en fibre ou Wi-Fi ; 20 à 50 ms en 4G |
| Planification Web Audio | < 3 ms |
| Latence de sortie connue et compensée | 5 à 30 ms résiduels |
| **Bluetooth non signalé** | **100 à 300 ms** |
| Dérive d'horloge sur 60 s | environ 6 ms, négligeable |

**Objectifs**
- **Écart p90 entre joueurs ≤ 60 ms** sur appareils filaires ou haut-parleur.
- **≤ 150 ms** en incluant la 4G et les mobiles.
- Bluetooth documenté ; curseur manuel en V0.2.
- **Plus de 250 ms hors Bluetooth est un bug.**

Chercher mieux que 50 ms n'a pas d'intérêt : on joue avec un chat vocal en parallèle, et l'horodatage des réponses suit sa propre règle (§6.3).

### 9.2 Synchronisation d'horloge
- **Horloge serveur** : `time.monotonic_ns()` exprimée en ms. Le `PONG` part immédiatement, sans `await` avant la lecture de l'horloge.
- **Un échantillon** : `t0 = performance.now()`, envoi de `PING{c:t0}`, réception de `PONG{c, s}` à `t1`. Alors `rtt = t1 − t0` et `θ = s − (t0+t1)/2` (temps serveur = temps local + θ).
- **Estimation** : on garde les 30 derniers échantillons ; l'estimation est la **médiane des θ des 3 échantillons de plus petit RTT**. Incertitude ε ≈ `rtt_min/2`.
- **Rafale de 8 pings espacés de 50 ms** : à la connexion, à la reconnexion, au retour au premier plan (`visibilitychange`), à chaque LOADING.
- **Entretien** : un ping toutes les 5 s, qui sert aussi de heartbeat.
- `θ` et `rtt_min` sont remontés dans `AUDIO_STATUS` pour le diagnostic.

### 9.3 Mise en mémoire tampon et READY
1. `audio.next` apparaît dans la vue.
2. Le client fait un `fetch` vers un `ArrayBuffer`, puis `decodeAudioData` vers un `AudioBuffer` gardé en mémoire.
3. Il envoie `AUDIO_STATUS READY(asset_id)`. Le serveur note `ready_received_at`, qui sert au calcul de `late_start_ms`.

Comme le préchargement a lieu pendant REVIEW, tout le monde est généralement prêt avant que l'hôte clique « Suivant ».

### 9.4 Ready check
- Le serveur attend les joueurs **en ligne dont l'audio est déverrouillé**. Les joueurs hors ligne ou en `LOCKED` ne sont pas attendus, mais l'hôte les voit.
- **Départ automatique** quand tous ces joueurs sont prêts. Activé par défaut ; indispensable en Host Player Mode.
- **`READY_TIMEOUT` = 10 s** : au-delà, on démarre quand même.
- **« Lancer quand même »** est disponible pour l'hôte dès qu'au moins un joueur est prêt.
- **Joueur lent** : il démarre dès qu'il est prêt, à la bonne position, avec « Tu as rejoint en cours (−2,3 s) ». L'hôte voit le retard au moment de noter (`late_start_ms`) et peut faire rejouer l'extrait pour tout le monde.

### 9.5 Départ et planification
1. Le serveur fixe `start_at = now_server + LEAD` (LEAD = 3 000 ms, qui correspond au compte à rebours, minimum 1 500 ms). Le premier `start_at` du round devient `official_start_at`. Il diffuse `PLAY{play_id, asset_id, start_at, clip_offset:0}`.
2. Côté client :
   - `t_local = start_at − θ − latence_manuelle` ;
   - avec `ts = ctx.getOutputTimestamp()`, on calcule `T = ts.contextTime + (t_local − ts.performanceTime)/1000`. Ce calcul **inclut la latence de sortie que connaît le navigateur** ;
   - repli si l'API est absente ou renvoie 0 : `T = ctx.currentTime + (t_local − performance.now())/1000 − (ctx.outputLatency ?? ctx.baseLatency ?? 0)`.
3. Si `T` est dans le futur : `source.start(T, clip_offset)`. Sinon, `retard = now − T`, puis `source.start(now + 0,05, clip_offset + retard + 0,05)`, sauf si le retard dépasse la durée de l'extrait.
4. Le compte à rebours affiché suit `requestAnimationFrame`. Il est purement visuel : le son est planifié sur le thread audio et **n'est pas ralenti** quand les timers sont bridés en arrière-plan.
5. Après le départ, le client envoie `PLAYBACK_REPORT`.

### 9.6 Reconnexion et resynchronisation
- **Aucune resynchronisation pendant la lecture** : la dérive est négligeable sur moins de 60 s, et une correction serait audible.
- En cas de (re)connexion pendant OPEN : rafale de synchro, téléchargement et décodage si nécessaire, puis règle « `T` passé ». Le joueur retombe sur la bonne position.
- Un réveil de téléphone pendant la lecture suit le même chemin.
- Le stop ordinaire est immédiat ; le replay envoie un nouveau `PLAY`.
- La pause planifie `STOP {stop_at}` à un instant serveur proche et mémorise la
  position audio et le temps de réponse restant. Les réponses sont suspendues à cet
  instant. La reprise planifie un nouveau `PLAY` à cette position, déplace la deadline
  et exclut toute la suspension de `elapsed_ms`. Départ et arrêt utilisent la même
  conversion d'horloge et de latence de sortie. La précision acoustique reste à mesurer.
- Après redémarrage du serveur, aucun audio RAM n'est rejoué. Une manche OPEN est
  récupérée en REVIEW avec ses réponses ; une préparation est régénérée via le Bridge.

### 9.7 Déverrouillage audio selon le navigateur
Comportements à confirmer au spike S0 sur les versions réelles.

| Navigateur | Contrainte | Stratégie |
|---|---|---|
| Chrome desktop | `AudioContext` « suspended » sans geste utilisateur. Une fois repris, il le reste. | Bouton « Tester mon audio » : `resume()` et bip |
| Firefox | Bloque l'audio audible sans geste. `outputLatency` est supporté. | Idem |
| Safari macOS | Geste requis. `outputLatency` probablement absent. | Idem, avec repli sur `getOutputTimestamp` ou `baseLatency` |
| **iOS Safari** (tous les navigateurs iOS) | Geste requis. **Web Audio coupé par le bouton silencieux.** État « interrupted » quand l'écran se verrouille, en cas d'appel ou de changement d'application. WebSocket fermé en arrière-plan. | Au moment du geste : `navigator.audioSession.type = "playback"` si disponible, sinon un `<audio>` silencieux en boucle. Overlay de réactivation. Conseil « garde l'écran allumé ». |
| Chrome Android | Geste requis. Économiseurs de batterie ; WebSocket coupé après un long passage en arrière-plan. | Overlay, reconnexion, rattrapage |

Règles générales :
- Un seul `AudioContext` par page, jamais recréé.
- Le client écoute `onstatechange` et signale `LOCKED` au serveur dès que le contexte n'est plus `running`.
- L'état audio de chaque joueur est visible par l'hôte en permanence.
