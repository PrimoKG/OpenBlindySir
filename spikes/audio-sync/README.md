# Spike S0 — synchro audio et formats

> **Code jetable** (branche `spike/audio-sync`, §19.5) : jamais fusionné dans `main`.
> Seuls `tools/sync_analyze.py` et `tools/calibration_clip.py` (+ leurs tests) seront
> réintégrés proprement plus tard.

## 1. Objectif

Lever les deux inconnues de l'étape 1 de §26 et fournir de quoi trancher la **porte G1** :

1. **Format** (ADR 0004) : `decodeAudioData` réussit-il sur AAC/M4A, Opus/WebM, Opus/Ogg
   (et MP3 en référence) sur un **vrai iPhone**, Android, Safari macOS, Firefox, Chrome ?
   Avec quel décalage de départ (délai d'encodeur mal compensé) ?
2. **Synchro** (§9, `docs/sync.md`) : l'algorithme d'horloge (θ, 3 RTT minimaux),
   la planification (`getOutputTimestamp`, repli `outputLatency`/`baseLatency`), la règle
   « T déjà passé » et les recettes de déverrouillage (§9.7) tiennent-ils **p90 ≤ 60 ms**
   mesuré **acoustiquement** sur 3 appareils hétérogènes (§20.5) ?

**Porte G1** : format choisi (ADR 0004 « Accepté »), p90 ≤ 60 ms sur 3 appareils
hétérogènes, recette iOS validée. Les mesures sont faites **par le mainteneur sur de vrais
appareils** ; rien dans ce dossier n'affirme un résultat d'appareil.

## 2. Contenu

| Fichier | Rôle |
|---|---|
| `server.py` | FastAPI (PEP 723). Génère les clips synthétiques au démarrage, sert la page joueur, la page admin, le WebSocket d'horloge et de commandes, collecte les rapports. |
| `static/index.html`, `static/app.js` | Page joueur (JS vanilla, modules ES, sans build). |
| `static/clock.js` | Maths pures de l'horloge et de la planification (§9.2, §9.5), testées par `static/clock.test.mjs`. |
| `static/measure.js` | Centroïde d'un burst dans un buffer décodé (mesure du décalage décodeur). |
| `static/admin.html`, `static/admin.js` | Page admin : clients, voix, θ, rtt_min, ε, rapports ; boutons de lecture. |
| `smoke_test.py` | Test de fumée sans navigateur d'un serveur lancé (HTTP, clips, WS, PLAY/STOP/SYNC, /report). |
| `make_fake_recording.py` | « Répétition à blanc » de la mesure acoustique : mixe les clips de calibration **décodés depuis l'AAC servi** avec des décalages connus, gains, écho, bruit. |
| `../../tools/calibration_clip.py` | Générateur réutilisable des clips de calibration (numpy + wave, encodage optionnel via ffmpeg). |
| `../../tools/sync_analyze.py` | Analyseur réutilisable (numpy seul) : enregistrement micro → décalages, dérive, p90, PASS/FAIL. |
| `../../tools/test_sync_analyze.py` | Tests de l'analyseur et du générateur (signaux synthétiques). |

Sorties générées, **jamais commitées** (`.gitignore` local + règles audio du dépôt) :
`_generated/` (clips), `_results/` (JSON collectés), `recordings/` (enregistrements micro).
Aucun son réel ni protégé : tout est synthétisé à l'exécution.

## 3. Lancer en local

Prérequis : `uv`, Node ≥ 20 (pour les tests JS), FFmpeg avec `aac` et `libopus`
(et `libmp3lame` pour la référence MP3).

```bash
# FFmpeg hors PATH : --ffmpeg, ou variables FFMPEG / FFPROBE (ffprobe est aussi cherché à côté de ffmpeg)
uv run spikes/audio-sync/server.py --host 0.0.0.0 --port 8077 --ffmpeg /chemin/vers/ffmpeg
```

Le serveur affiche, pour chaque clip, codec / fréquence / canaux / durée / tags (ffprobe) et
le décalage du marqueur après décodage par ffmpeg, puis les URL :

- joueur : `http://<ip>:8077/`
- admin : `http://<ip>:8077/admin` (avec `--admin-token T` ou `SPIKE_ADMIN_TOKEN`, ajouter `?token=T`)
- données : `http://<ip>:8077/results.json` (aussi écrit dans `_results/results-<date>.json`)

Horloge serveur : `time.monotonic_ns()/1e6` ; si la résolution de `monotonic` dépasse 1 ms
(Python < 3.13 sous Windows : 15,6 ms), repli automatique sur `perf_counter_ns`, annoncé au
démarrage.

### Clips générés (`_generated/clips/`)

- **Extrait test, 10 s** : marqueur (burst Hann 10 ms à 2 000 Hz, à 0,5 s) puis 8 notes
  synthétiques (fondamentale + 2 harmoniques), fondus 0,3 s / 1,5 s. Encodé avec le gabarit
  §10 (`-nostdin -hide_banner -loglevel error -threads 1 -protocol_whitelist file`,
  entrée `file:<chemin absolu>`, `-ss 0 … -t`, `-map 0:a:0 -vn -sn -dn`,
  `-map_metadata -1 -map_chapters -1`, `-ac 2 -ar 48000`, `afade`) en :
  `test_aac.m4a` (AAC-LC 128k, `+faststart`), `test_opus.webm` (Opus 96k),
  `test_opus.ogg` (Opus 96k), `test_mp3.mp3` (MP3 128k, référence).
- **Calibration, 30 s, une par voix** : `calib_v0.m4a` … `calib_v5.m4a` (AAC, même gabarit,
  sans fondu). Bursts Hann de 10 ms toutes les **500 ms**, premier burst à 1,0 s ; à 48 kHz,
  chaque début de burst tombe sur un échantillon entier (`48000 + 24000·n`) : les onsets du
  WAV source sont exacts à l'échantillon. Fréquences par voix :

  | voix | 0 | 1 | 2 | 3 | 4 | 5 |
  |---|---|---|---|---|---|---|
  | Hz | 1400 | 1800 | 2200 | 2600 | 3000 | 3400 |

  Choix : espacement de 400 Hz, et aucun harmonique 2 ou 3 d'une voix à moins de 200 Hz
  d'une autre voix (la distorsion d'un petit haut-parleur ne crée pas de faux bursts chez le
  voisin) ; tout reste dans la bande où les haut-parleurs de téléphone sont efficaces.
  Le serveur attribue une voix à chaque client à la connexion (conservée à la reconnexion
  grâce à l'identifiant client stocké localement). Si la même page se reconnecte avant que
  le serveur ait vu mourir l'ancien socket (retour d'arrière-plan, bascule Wi-Fi ↔ 4G), elle
  **reprend** son identité et sa voix (identifiant de page `tab` tiré à chaque chargement) et
  l'ancien socket est fermé ; un onglet dupliqué dont l'original est vivant reçoit une
  nouvelle identité. Un socket muet depuis `--stale-s` secondes (15 s par défaut ; le client
  pinge toutes les 5 s) est considéré mort : il ne garde plus sa voix et ne reçoit plus de PLAY.

Le décalage décodeur se mesure en comparant le centre du marqueur décodé (navigateur :
`decodeAudioData` ; serveur : ffmpeg) à sa position théorique. Un décalage non nul et
constant pour un format signale un délai d'encodeur (priming / edit list / pre-skip) mal
compensé par ce décodeur : c'est un critère de l'ADR 0004.

## 4. Sur un VPS ou pour des appareils distants (HTTPS)

Web Audio fonctionne en `http://` sur le LAN, mais `navigator.audioSession` et certaines API
peuvent exiger un **contexte sécurisé**. Pour les mesures sur 4G ou depuis l'extérieur :

```bash
uv run spikes/audio-sync/server.py --host 127.0.0.1 --port 8077 --admin-token <secret>
caddy reverse-proxy --from spike.example.org --to localhost:8077
```

Caddy obtient le certificat et relaie le WebSocket sans configuration. Protéger l'admin avec
`--admin-token` dès que le serveur est joignable publiquement. Couper le serveur après la
session de mesure.

## 5. Page joueur — ce qu'elle fait

- **« Tester mon audio »** (geste utilisateur) : applique la recette choisie (§9.7),
  **puis** crée **un seul** `AudioContext` (`webkitAudioContext` en repli), `resume()` et joue
  un bip court, le tout dans le geste. Aucun `AudioContext` n'est créé avant ce geste : le
  préchargement du clip de calibration attend le déverrouillage, « Tester les formats »
  déverrouille d'abord si besoin, et un PLAY reçu avant le déverrouillage est gardé puis
  joué (règle « T déjà passé ») juste après. Recettes :
  - `auto` : `navigator.audioSession.type = "playback"` si l'API existe, sinon sur iOS un
    `<audio>` silencieux en boucle ;
  - `audioSession`, `silent-audio`, `both`, `none` : forcer une recette pour comparer.
  - Une recette appliquée ne se défait pas (`audioSession.type`, `<audio>` en boucle,
    contexte déjà déverrouillé) : **changer de recette recharge la page** (la recette est
    mémorisée), pour que chaque recette soit testée sur une page vierge.
- **Horloge** (§9.2) : échantillon θ = s − (t0+t1)/2, 30 derniers échantillons, estimation =
  médiane des θ des 3 échantillons de plus faible RTT, ε = rtt_min/2. Rafale de 8 PING
  espacés de 50 ms à la connexion, à la reconnexion, sur `visibilitychange` et avant chaque
  lecture ; keepalive toutes les 5 s. Affichage en direct (θ, rtt_min, ε, nombre d'échantillons).
- **AudioContext** : `state`, `sampleRate`, `baseLatency`, `outputLatency`, présence de
  `getOutputTimestamp`, latence effective utilisée.
- **Lecture sur PLAY{play_id, clip, start_at}** (§9.5) : conversion de `start_at` (horloge
  serveur) en temps `AudioContext` via `getOutputTimestamp()` si disponible et valide, sinon
  repli `outputLatency` puis `baseLatency` ; latence manuelle ajoutable (ms). Si T est déjà
  passé : `start(now + 0.05, offset + late + 0.05)`. Un STOP ou un PLAY plus récent reçu
  pendant l'attente (rafale de synchro, décodage) annule la lecture en cours de préparation
  (journal : « superseded »). Puis POST `/report` avec `late_ms`,
  `offset`, `rtt_min`, `out_latency`, `est_error_ms`, `api_used`.
- **Perte d'audio** : `onstatechange` → statut `LOCKED` envoyé au serveur et overlay
  « Touchez pour réactiver le son ».
- **Formats** : « Tester les formats » télécharge chaque extrait test, `decodeAudioData`,
  note succès/erreur, durée décodée, temps de décodage et décalage du marqueur, puis POST
  `/report`.
- Volume (GainNode), environnement (UA, plateforme, API présentes), journal.

## 6. Checklist appareils et navigateurs (§9.7, §26)

Pour chaque ligne : ouvrir la page, « Tester mon audio », « Tester les formats », noter.

- [ ] **Vrai iPhone**, Safari — bouton silencieux **activé** : le son sort-il ? (recette `auto`, puis `silent-audio`, puis `none` ; **recharger la page entre deux recettes** — fait automatiquement au changement de recette, vérifier que le journal repart de zéro — puis « Tester mon audio »)
- [ ] Vrai iPhone, Safari — bouton silencieux désactivé
- [ ] Vrai iPhone — **verrouillage écran** pendant une lecture, puis retour : overlay affiché, statut `LOCKED` visible côté admin, retour au son après toucher
- [ ] Vrai iPhone — passage en arrière-plan / autre onglet puis retour (rafale `visibilitychange`)
- [ ] iPhone — un navigateur tiers (Chrome ou Firefox iOS, même moteur WebKit) : contrôle rapide
- [ ] Android, Chrome
- [ ] Android, Firefox (si disponible)
- [ ] Safari macOS
- [ ] Firefox desktop
- [ ] Chrome (ou Edge) desktop
- [ ] Pour chaque appareil : `getOutputTimestamp` présent ? `outputLatency` non nul ? `navigator.audioSession` présent ?
- [ ] Casque Bluetooth sur au moins un appareil (latence élevée attendue ; noter, ne compte pas pour G1)

## 7. Mesure acoustique pas à pas (§20.5)

Matériel : 3 ou 4 appareils hétérogènes (dont l'iPhone), un enregistreur (téléphone ou PC
avec micro) qui enregistre en **WAV**, une pièce calme.

1. **Réseaux différents** (au moins 3) :
   - fibre / Ethernet ;
   - **4G** (Wi-Fi coupé sur le téléphone) ;
   - **Wi-Fi dégradé** : sous Linux sur la passerelle ou un PC relais
     `sudo tc qdisc add dev <iface> root netem delay 80ms 30ms distribution normal loss 2%`
     (retirer avec `sudo tc qdisc del dev <iface> root`) ; sous Windows, **Clumsy** sur
     l'appareil client (lag 80 ms, drop 2 %, filtre `tcp and tcp.DstPort == 443` ou le port du serveur).
   Noter les réglages exacts.
2. Lancer le serveur derrière HTTPS (§4) ; ouvrir `/admin` sur un poste à part.
3. Sur chaque appareil : ouvrir la page, « Tester mon audio », vérifier dans l'admin la
   voix attribuée, θ, rtt_min et le statut `READY` (clip de calibration préchargé).
   Volume des appareils à un niveau proche ; écran allumé.
4. **Placement** : tous les haut-parleurs **à la même distance** du micro (± 10 cm ;
   le son parcourt ~2,9 ms par mètre), micro au centre, appareils non collés les uns aux autres.
5. Lancer l'enregistrement **WAV** (mono ou stéréo, toute fréquence d'échantillonnage).
   Éviter les applis qui compressent (AAC/Opus) ; à défaut, convertir en WAV avec ffmpeg
   et le noter.
6. Dans l'admin : « Jouer la calibration pour tous » avec départ dans 3 s. Chaque appareil
   joue 30 s de bursts sur sa voix. Répéter 2 à 3 fois (avec une rafale de synchro entre
   deux), puis au moins une fois avec un départ ≤ 0 s pour tester la règle « T déjà passé ».
   **Attendre la fin de chaque lecture (30 s) et laisser au moins 5 s de silence avant la
   suivante** : l'analyseur découpe l'enregistrement en *runs* sur les silences de plus de
   2 s et calcule dérive, jitter et p90 **par run** (une ligne du tableau 10.3 par run).
   Noter l'ordre des lectures (normale / T passé). Variante plus simple : un WAV par lecture.
   L'enregistrement doit couvrir **chaque lecture en entier** (du premier au dernier burst).
7. Arrêter l'enregistrement, copier le WAV dans `spikes/audio-sync/recordings/` (ignoré par Git).
8. Analyser (§8) avec `--expect N` (N = nombre d'appareils qui ont joué). Pour un run
   « T passé », le réanalyser seul avec la fenêtre affichée par le rapport et `--anchor end`
   (les appareils démarrent en cours de clip, voir §8). Récupérer aussi `results.json`
   (rapports déclarés par les clients) pour comparer l'erreur déclarée (§20.5 point 1) à
   l'erreur mesurée.

Répétition à blanc sans appareil (vérifie toute la chaîne clip AAC → mix → analyse) :

```bash
uv run spikes/audio-sync/make_fake_recording.py --offsets 0,23,-41,110 --echo --ffmpeg /chemin/ffmpeg -o spikes/audio-sync/recordings/fake.wav
uv run tools/sync_analyze.py spikes/audio-sync/recordings/fake.wav --reference 0 --expect 4
# plusieurs lectures dans un seul WAV (--runs 3 --gap 5), et un appareil en retard d'une période
uv run spikes/audio-sync/make_fake_recording.py --offsets 0,23,-41,110 --runs 3 --ffmpeg /chemin/ffmpeg -o spikes/audio-sync/recordings/fake3.wav
uv run spikes/audio-sync/make_fake_recording.py --offsets 0,480,10 --ffmpeg /chemin/ffmpeg -o spikes/audio-sync/recordings/late.wav
```

## 8. `tools/sync_analyze.py`

```bash
uv run tools/sync_analyze.py recordings/session1.wav --expect 3
uv run tools/sync_analyze.py recordings/session1.wav --expect 3 --reference 0 --threshold-ms 60 --json recordings/session1.json
uv run tools/sync_analyze.py rec.wav --start 2 --end 33 --channel 0   # fenêtre et canal
uv run tools/sync_analyze.py rec.wav --start 70 --end 102 --expect 3 --anchor end   # run « T passé »
```

Principe : filtre adapté complexe par voix (gabarit Hann 10 ms à la fréquence de la voix),
détection des bursts au-dessus du bruit, affinage sur le front montant (moins sensible à la
réverbération), découpage en **runs** (une lecture = un run, coupure sur 2 s sans aucun burst,
`--split-gap`), puis, par run : numérotation des bursts de chaque voix, régression
`t = a + b·n` (dérive en ppm, jitter), appariement des bursts **de même numéro**,
décalage = t(B) − t(A) (> 0 : B en retard), **périodes entières comprises** (un appareil en
retard de 480 ms donne +480 ms, pas −20 ms).

**Ancrage** (`--anchor`) : tous les bursts se ressemblent ; pour savoir que le burst n de A
correspond au burst n de B, il faut que les voix commencent (ou finissent) au même burst du
clip. Par défaut (`both`), chaque voix bien détectée doit couvrir le même nombre de bursts ;
sinon le run est **AMBIGUOUS** (code 2) au lieu d'afficher un décalage faux de k × 500 ms.
Causes : appareil parti ou arrêté une période trop tôt/tard, premier ou dernier burst non
détecté, enregistrement qui ne couvre pas toute la lecture, ou lecture « T passé »/rejoin
(les appareils démarrent en cours de clip : `--anchor end`, numérotation depuis le dernier
burst, valable si l'enregistrement couvre la fin des clips). `--anchor start` : l'inverse.

**Couverture** : une voix détectée sur moins de 80 % des bursts du run (`--min-coverage`)
est signalée (WARNING) et rend le run **INCOMPLETE** (code 2) : appareil trop faible, masqué
ou arrêté. Avec `--expect N`, un run qui a moins de N voix bien détectées est INCOMPLETE
(appareil qui n'a pas joué : LOCKED, PLAY manqué). **Toujours passer `--expect` pour G1.**

Sortie : tableau des voix (bursts, niveau, SNR) sur tout le fichier, puis pour chaque run :
fenêtre `--start/--end` pour le réanalyser seul, tableau des voix (bursts, couverture,
premier/dernier burst, dérive ppm, jitter), décalages par rapport à la référence et pour
toutes les paires (n, médiane, moyenne, écart-type, p90 |d|, max |d|), **p90 des |décalages|
du run** et verdict `RUN k: PASS|FAIL|AMBIGUOUS|INCOMPLETE` ; enfin `RESULT:` global.
Code de sortie : 0 si tous les runs sont PASS, 1 si un run est FAIL, 2 sinon (erreur
d'usage, run AMBIGUOUS ou INCOMPLETE, moins de deux voix). Un FAIL l'emporte : un p90 au-delà
du seuil sur les voix présentes est un échec même si le run est par ailleurs incomplet.

## 9. Tests réalisables sans appareil

```bash
# maths d'horloge et de planification (node --test)
cd spikes/audio-sync && node --test
# analyseur + générateur (sous Windows sandboxé, ajouter --basetemp <dossier inscriptible>)
uv run --with numpy --with pytest pytest tools/test_sync_analyze.py
# serveur + test de fumée (dans deux terminaux)
uv run spikes/audio-sync/server.py --port 8077 --ffmpeg /chemin/ffmpeg
uv run spikes/audio-sync/smoke_test.py --base http://127.0.0.1:8077
# (serveur lancé avec --stale-s 2 : le test vérifie aussi la purge des sockets muets)
# vérification des clips : codec, 48 kHz, 2 canaux, aucun tag title/artist
ffprobe -v error -show_format -show_streams spikes/audio-sync/_generated/clips/test_aac.m4a
```

Observation sur les métadonnées : avec le gabarit §10 tel quel, ffprobe ne montre **aucun
tag title/artist/album**, mais le muxer écrit encore des tags techniques
(`encoder=Lavf…` en MP4/MP3/WebM, `encoder=Lavc… libopus` dans le flux Opus, plus
`major_brand`, `handler_name`). Ajouter `-fflags +bitexact -flags:a +bitexact` supprime le
tag `encoder` du MP4 (il reste `Lavf`/`Lavc libopus` sans version en WebM/Ogg). À discuter
pour le gabarit définitif ; non appliqué ici pour rester conforme à §10.

## 10. Gabarit de résultats (à remplir par le mainteneur)

**Ne jamais inventer un résultat** : une case non mesurée reste vide ou « non testé ».

### 10.1 Formats (`decodeAudioData`)

Valeur : ✅ / ❌ (message d'erreur) · durée décodée · décalage marqueur (ms).

| Appareil · OS · navigateur (version) | AAC/M4A | Opus/WebM | Opus/Ogg | MP3 (réf.) | getOutputTimestamp | outputLatency (ms) | audioSession |
|---|---|---|---|---|---|---|---|
| iPhone … · iOS … · Safari … | | | | | | | |
| Android … · Chrome … | | | | | | | |
| Mac … · Safari … | | | | | | | |
| PC · Firefox … | | | | | | | |
| PC · Chrome … | | | | | | | |

### 10.2 Recette iOS (§9.7)

Recharger la page entre deux recettes (automatique au changement de recette).

| iPhone · iOS | Recette | Bouton silencieux activé : son ? | Verrouillage écran → LOCKED + overlay ? | Retour au son après toucher ? | Remarques |
|---|---|---|---|---|---|
| | auto | | | | |
| | silent-audio | | | | |
| | none | | | | |

### 10.3 Mesure acoustique

Une ligne par **run** (`RUN k` du rapport ; « Dérive max » = plus grande |dérive| des voix
de ce run ; verdict tel qu'affiché, y compris AMBIGUOUS/INCOMPLETE).

| Session | Appareils (voix · réseau · réglage netem/Clumsy) | Enregistreur | Départ (s) | p90 global (ms) | max (ms) | Dérive max (ppm) | Verdict | Fichier JSON |
|---|---|---|---|---|---|---|---|---|
| 1 | | | 3 | | | | | |
| 2 | | | 3 | | | | | |
| 3 (T passé) | | | ≤ 0 | | | | | |

Erreur déclarée par les clients (admin / `results.json`) vs mesurée : …

## 11. De la mesure à la porte G1

1. Remplir §10 avec les mesures réelles.
2. **Format** : retenir le format qui décode partout (iPhone compris) avec un décalage de
   départ homogène ; mettre à jour `docs/adr/0004-audio-format.md` → statut **Accepté**, en
   citant les mesures (appareils, versions, résultats, y compris les échecs).
3. **Synchro** : G1 exige **p90 ≤ 60 ms sur 3 appareils hétérogènes** (`sync_analyze.py`
   PASS sur au moins une session représentative, les autres sessions rapportées telles quelles).
4. **Recette iOS** validée sur un vrai iPhone (bouton silencieux, verrouillage).
5. Ajouter une entrée au `docs/DEVLOG.md` au format §19.11 : commandes réellement
   exécutées, appareils, résultats et échecs tels qu'ils se sont produits ; état
   DONE / PARTIAL / BLOCKED.
6. Si une condition n'est pas remplie : G1 n'est pas franchie ; l'écrire dans le DEVLOG et
   décider (autre recette, autre format, ajustement de §9) avant l'étape 2.
