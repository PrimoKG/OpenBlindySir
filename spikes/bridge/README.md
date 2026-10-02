# Spike S1 — Bridge (`spike/bridge`)

> Code **jetable** (spec §19.5) : cette branche n'est jamais fusionnée dans `main`. Seuls des
> outils réutilisables (générateur de fixtures synthétiques, sonde de sandbox) seront
> réintégrés proprement plus tard. Notes techniques internes, en français ; code en anglais.

## Objectif

Valider la porte **G2** (spec §26, étape 2) avant d'écrire le vrai Bridge :

1. **préparation + upload < 5 s au p95**, mesuré côté serveur de `PREPARE` envoyé à upload
   reçu et vérifié ;
2. **aucun fichier hors de la racine accessible** (liens symboliques, junctions Windows,
   substitutions après le scan, `track_id` forgés, fichiers « playlist » qui font ouvrir
   d'autres fichiers à FFmpeg).

Le périmètre du spike (§26) : scan d'une **vraie** bibliothèque, junction Windows, FFmpeg sur
FLAC, MP3, MP3 VBR et M4A avec `moov` en fin de fichier, **WSS sortant à travers une box
domestique**, **PUT vers un vrai VPS**. Ces deux derniers points et la vraie bibliothèque ne
peuvent être mesurés que par le mainteneur : les outils ci-dessous lui sont destinés.

Spécification appliquée : §10 (pipeline, gabarit FFmpeg exact, règle du point de départ),
§11 / `docs/bridge-security.md` (scan, catalogue, sandbox, timeouts, console sans noms de
fichiers), §8.3 / `docs/protocol.md` (messages Bridge).

## Contenu

| Fichier | Rôle |
|---|---|
| `bridge_common.py` | Code partagé (stdlib) : scan §11, catalogue, contrôle à l'ouverture, ffprobe, règle du départ, gabarit FFmpeg §10. Importé par les scripts voisins. |
| `fixtures.py` | Génère une bibliothèque **synthétique** (chirps `ffmpeg -f lavfi`) avec tous les cas limites. |
| `scan_bench.py` | Scanne une racine et affiche les statistiques, **jamais les noms de fichiers**. |
| `sandbox_probe.py` | Construit un arbre temporaire piégé (symlink, junction, substitutions, hard link, `track_id` forgés, playlists HLS/ffconcat) et affiche PASS/FAIL/SKIP/INFO par cas. |
| `ffmpeg_bench.py` | ffprobe → départ → gabarit FFmpeg exact, vérification du fichier produit, temps par codec, p50/p95, erreur de seek. |
| `relay_server.py` | **Autonome** (un seul fichier à copier sur le VPS) : FastAPI, WS `/bridge`, PUT `/catalog` et `/upload/{job_id}`, `/run`, `/poke`, `/stats`, verdict G2. |
| `bridge_client.py` | Client sortant : scan, HELLO, catalogue gzip, PREPARE → FFmpeg → PUT, heartbeat, reconnexion. |
| `_fixtures/`, `_out/` | Générés, **ignorés par Git** (`.gitignore` local). `_out/` contient des catalogues locaux avec de vrais noms de fichiers : ne jamais les partager. |

## Prérequis

- `uv` (chaque script porte ses dépendances en en-tête PEP 723 : `uv run script.py` suffit,
  aucun projet ni venv à créer). Python ≥ 3.12 (`os.path.isjunction`).
- FFmpeg ≥ 6 avec les encodeurs `aac` (et `libopus` en option). Si `ffmpeg` n'est pas dans le
  `PATH` : option `--ffmpeg CHEMIN` (ffprobe est cherché à côté) ou variables
  `OPENBLINDYSIR_FFMPEG` / `OPENBLINDYSIR_FFPROBE`.
- Ne **jamais** lancer ces outils en administrateur (spec §12).

Dans les exemples, `FF` désigne le dossier `bin` de FFmpeg. Sur le poste de développement :

```powershell
$FF = "C:\Users\primo\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
$env:OPENBLINDYSIR_FFMPEG = "$FF\ffmpeg.exe"   # évite de répéter --ffmpeg
```

Toutes les commandes se lancent depuis la racine du worktree.

## Utilisation de chaque script

### 1. Bibliothèque synthétique

```powershell
uv run spikes/bridge/fixtures.py --force            # ~320 Mo, ~45 s ; --quick sans les pistes de 6 min
```

Produit `spikes/bridge/_fixtures/library/` et `_fixtures/manifest.json` (résultat attendu par
fichier). Contenu : 8 formats (FLAC, MP3 CBR 192k, MP3 VBR `-q:a 2`, M4A AAC **sans
faststart** — position de `moov` vérifiée par lecture des atomes —, WAV, Ogg Vorbis, Opus,
AIFF) × 4 durées (5 s, 45 s, 3 min, 6 min), plus `.aac` ADTS, `.oga` FLAC et `.wma` ; tags
factices (« Synthetic Track N ») ; pochette jointe sur un MP3 et un FLAC ; dossiers Unicode
NFC **et** NFD avec une collision NFC volontaire ; nom commençant par `-` ; extension en
majuscules ; fichier caché (point), attributs Windows HIDDEN et SYSTEM ; fichier non audio ;
fichier vide ; « MP3 » en octets aléatoires ; FLAC tronqué ; arborescence profonde ; **MP3 VBR
sans en-tête Xing/VBRI** (`-q:a 0 -write_xing 0`, 30 s de silence puis le chirp) dont ffprobe
*estime* la durée à partir du débit (259 s annoncées pour 180 s réelles). Sous Linux/macOS, un
nom contenant `:` est ajouté (impossible sous Windows).

Deux fixtures ont une fraction de départ **imposée** dans le manifeste (`start_fraction`), que
`ffmpeg_bench.py` utilise à la place du tirage aléatoire : le MP3 sans Xing (0,95 : avec la règle
§10 seule, le départ tombe après la vraie fin → clip vide) et le FLAC tronqué (0,29 : la source
s'arrête ~27 s après le départ → ré-encodage, voir § 4).

Chaque piste est un chirp linéaire `f(t) = 200 + 5·t` Hz : la hauteur du son donne la position
réelle dans le morceau, ce qui permet de **mesurer l'erreur de seek** (`-ss` avant `-i`).

### 2. Scan

```powershell
uv run spikes/bridge/scan_bench.py D:\Music --repeat 3 --json-out spikes/bridge/_out/catalog-real.json
```

Affiche : fichiers retenus, taille totale, temps de scan (premier passage à froid puis médiane),
coût du `realpath` au scan (`--no-scan-realpath` pour comparer), histogramme par extension,
fichiers ignorés (liens, junctions, cachés, système, hors liste blanche, erreurs),
normalisations NFD → NFC et collisions, taille du catalogue JSON brut et gzip, `catalog_hash`.
`--json-out` écrit un catalogue **local** (avec les vrais chemins) pour `ffmpeg_bench.py`.
`--verbose-paths` : débogage seulement.

### 3. Sonde de sandbox

```powershell
uv run spikes/bridge/sandbox_probe.py                # --no-ffmpeg pour sauter les cas FFmpeg
```

Cas couverts : (a) lien symbolique fichier et dossier vers l'extérieur ; (b) **junction** vers
un dossier extérieur ; (c1) dossier remplacé par une junction **après** le scan (taille et
mtime identiques : seul le confinement `realpath` peut l'arrêter) ; (c2) fichier remplacé par
un symlink après le scan ; (c3) fichier modifié après le scan ; (d) hard link (INFO : résidu
accepté, indiscernable d'un fichier) ; (e) recherches avec `..`, chemins absolus, relpath au
lieu d'ID, ID inconnu, majuscules, types non chaîne ; (f) racine donnée via une junction ;
(g) faux `.mp3` contenant une playlist HLS ou `ffconcat` qui référence un fichier extérieur
par `../` ou un chemin absolu, avec le gabarit exact et avec `-format_whitelist` (durcissement
candidat, hors spec) ; **(g2)** une junction *à l'intérieur* de la racine (ignorée par le scan)
plus un faux `.mp3` `ffconcat` qui la traverse avec un nom relatif « sûr »
(`file jcat/long_secret.wav` + directive `duration`), variante sans `duration` en plus.

**Résultat attendu : 1 FAIL**, (g2) avec le gabarit exact. Le démultiplexeur `concat` est
choisi d'après le *contenu*, `-protocol_whitelist file` ne le bloque pas, son mode `safe`
accepte ce nom (ni `..` ni absolu) et l'OS suit la junction : FFmpeg produit un clip de 30 s du
fichier extérieur, que le contrôle de sortie accepte. **Le gabarit §10 seul ne satisfait donc
pas le critère 2 de G2.** Avec `-format_whitelist` le cas est refusé (« Format not on
whitelist »). Sans directive `duration`, ffprobe ouvre bien le fichier extérieur mais échoue
sur « no duration » : refus fragile, par accident. Proposition pour le §10 : ajouter
`-format_whitelist` (liste des démultiplexeurs audio de la liste blanche d'extensions) à
ffprobe **et** à ffmpeg, ou forcer le démultiplexeur d'après l'extension (`-f mp3`…, non testé
dans ce spike).

Sans le mode développeur Windows ni le privilège `SeCreateSymbolicLinkPrivilege`, la création
de symlinks échoue (WinError 1314) : les cas (a) et (c2) sont alors **SKIP**, honnêtement. Pour
les couvrir, activer le mode développeur (Paramètres → Système → Espace développeurs) et
relancer — sans passer administrateur.

### 4. Bench FFmpeg

```powershell
uv run spikes/bridge/ffmpeg_bench.py --fixtures --seek-ref                        # toutes les fixtures
uv run spikes/bridge/ffmpeg_bench.py --catalog spikes/bridge/_out/catalog-real.json -n 100 --seed 1 --seek-ref --json-out spikes/bridge/_out/ffmpeg-real.json
```

Pour chaque piste : contrôle à l'ouverture, ffprobe (10 s), règle du départ, **gabarit exact**
(30 s) dans `tempfile.mkdtemp(prefix="openblindysir-bridge-")`, puis vérification : magic bytes
`ftyp`, exactement 1 flux audio AAC 48 kHz stéréo, aucun flux vidéo (pochette), aucun tag
`title`/`artist`/`album`, durée ≈ demandée, `moov` avant `mdat`. Affiche une fois l'**argv
exact** (référence pour les futurs tests), puis un résumé par groupe (p50/p95 ffprobe et
encodage, taille, erreur de seek) et les échecs par code normalisé (`NOT_FOUND`,
`DECODE_ERROR`, `TOO_SHORT`, `TIMEOUT`). `--seek-ref` mesure l'erreur de seek sur **n'importe
quelle** piste (corrélation avec un décodage de référence), donc aussi sur la vraie
bibliothèque. Options : `--format opus`, `--hardened`, `--clip 20`, `--fraction 0.5`,
`--no-duration-measure` (règle §10 seule, pour voir le problème du MP3 sans Xing).

Le pipeline mesuré (`bridge_common.prepare_clip`, partagé avec le client) ajoute deux contrôles
au §10, issus du spike :

- **durée estimée** : ffprobe tourne en `-v warning` ; s'il écrit « Estimating duration from
  bitrate » (MP3 VBR sans Xing/VBRI, AAC ADTS), la vraie durée est mesurée par un démultiplexage
  complet sans décodage (`-c copy -f null -progress pipe:1`, ~45–65 ms ici) avant la règle du
  départ ;
- **contrôle de sortie** : le clip est sondé ; vide ou < 50 % de la durée prévue →
  `DECODE_ERROR` ; plus court que prévu de plus de 0,25 s (la source s'arrête avant : fichier
  tronqué, en-tête faux) → **ré-encodage** depuis la source avec la durée mesurée, pour que le
  fondu de sortie (`st=` = durée − 1,5 s) tombe sur la vraie fin au lieu d'une coupure sèche.

Le bench vérifie aussi le fondu : RMS des 50 dernières ms / RMS de la seconde du milieu (≈ 0,02
avec fondu, ≈ 1 sans) ; problème sur les chirps synthétiques au-delà de 0,2, simple
avertissement sur de la vraie musique. Deux tableaux de synthèse : temps par groupe (jobs OK) et
**tous les jobs par groupe** (OK, `DECODE_ERROR` et son taux, autres codes, durées estimées,
ré-encodages) — sur la vraie bibliothèque, un taux de `DECODE_ERROR` non nul sur un groupe de
fichiers lisibles est un constat à rapporter.

### 5. Relais (serveur) et 6. client Bridge

Secret partagé (≥ 32 caractères), jamais en argument de ligne de commande :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SPIKE_SECRET = "<la valeur>"
```

Serveur : `uv run spikes/bridge/relay_server.py serve --host 127.0.0.1 --port 8765`.

Client : `uv run spikes/bridge/bridge_client.py --server https://relay.example.org --root D:\Music --name Ayoub`.

- `ws://`/`http://` refusés sauf vers `localhost`/`127.0.0.1`/`::1` ; vérification TLS
  toujours active (magasin de certificats système) ; User-Agent `OpenBlindySir-Bridge/spike`.
- Messages serveur acceptés : `WELCOME`, `PREPARE`, `CANCEL`, `PING`. Tout le reste est
  journalisé (type seulement) et ignoré. Un `PREPARE` doit avoir **exactement** ses 7 champs ;
  `upload_url` doit revenir à la même origine que le serveur (sinon `JOB_FAILED
  INVALID_REQUEST`, avant tout accès disque).
- Durée et départ plafonnés par le Bridge (5–30 s, fraction dans [0, 1)) ; 1 job à la fois
  (`--jobs 2` au maximum), file de 4 (`BRIDGE_BUSY` au-delà) ; timeouts ffprobe 10 s, ffmpeg 30 s,
  upload 60 s ; dossiers temporaires purgés au démarrage. `upload_token` : ASCII imprimable
  uniquement (1–256 caractères), sinon `PREPARE` ignoré. Toute exception inattendue pendant un
  job (bogue, `OSError` sur le dossier temporaire, fichier verrouillé par un antivirus…) donne
  `JOB_FAILED INTERNAL` (code du spike, absent du §7.3) et le worker continue ; seule la classe
  de l'exception est affichée.
- **Clips de 30 s au maximum** : le Bridge du spike plafonne à 30 s toute demande plus longue,
  même si le serveur l'autorise (`trigger --duration 60` produit des clips de 30 s ; `/stats`
  l'indique). G2 est donc mesuré avec des clips ≤ 30 s. La spec est incohérente sur ce point
  (voir « Constats », point 8).
- Heartbeat : le serveur envoie `PING` toutes les 15 s, le Bridge répond `PONG` ; en plus,
  ping WebSocket natif toutes les 15 s (donne le RTT affiché). Sans message serveur pendant
  45 s, le Bridge se reconnecte. Reconnexion sans fin : backoff 1 → 30 s avec jitter.
- Ligne d'état sans nom de fichier : état, RTT, pistes, jobs OK/échecs, dernier `track_id`.

Commandes d'administration (même secret) depuis n'importe quel poste :

```powershell
uv run spikes/bridge/relay_server.py trigger --url https://relay.example.org -n 25 --crafted --json-out spikes/bridge/_out/g2-run1.json
uv run spikes/bridge/relay_server.py stats --url https://relay.example.org
uv run spikes/bridge/relay_server.py poke  --url https://relay.example.org
```

`trigger` = `POST /run?n=25&wait=1` puis `/stats?run=…&format=text`. `--crafted` ajoute 6
`track_id` forgés (`..`, `../../../../Windows/win.ini`, chemins absolus, `file:`, ID inconnu)
qui doivent tous revenir `NOT_FOUND` et ne comptent pas dans G2. `poke` envoie des messages
hostiles (types inconnus, `PREPARE` avec arguments FFmpeg en trop, champ manquant, `upload_url`
étrangère, chemin en guise de `track_id`, durée énorme et fraction négative **sur un vrai
`track_id`**, durée entière `10**400` qui déborde `float`, `upload_token` non ASCII, non-JSON,
trame binaire), puis un `PREPARE` valide de **vivacité** (`poke-alive`) : `worker_alive: true`
prouve que le worker du Bridge a survécu. Les `PREPARE` valides des pokes reviennent en
`JOB_FAILED INVALID_UPLOAD` (l'upload vers `upload/poke-…` est refusé, aucun job à ce nom) ou
avec un code de contenu ; lancer un `trigger` avant `poke`, pour qu'il réutilise une piste qui a
déjà produit un clip.

Ce que mesure `/stats` : pour chaque job, `total_ms` = **PREPARE envoyé → corps de l'upload
entièrement reçu et vérifié** (horloge du serveur seule), plus les temps rapportés par le
Bridge (lookup, ffprobe, mesure de durée, encodage, contrôle de sortie, upload). Verdict G2 :

- les échecs **de contenu** (`NOT_FOUND`, `TOO_SHORT`, `DECODE_ERROR` : le fichier lui-même)
  sont exclus de l'échantillon et listés à part ;
- tout **autre** échec (`TIMEOUT`, `BRIDGE_OFFLINE`, `INVALID_UPLOAD`, `BRIDGE_BUSY`,
  `CANCELLED`, `INTERNAL`…) compte comme un temps **infini** dans le p95 ;
- `FAIL` si ce p95 ≥ 5 000 ms ; sinon `INCONCLUSIVE` dès qu'il y a au moins un échec « infra »
  (à relancer après avoir corrigé la cause) ; sinon `PASS` si l'échantillon (OK + échecs infra)
  compte au moins 20 jobs, `PASS_SMALL_SAMPLE` en dessous.

La ligne du verdict rappelle toujours `OK x/n` et les codes d'échec. Un run de 25 jobs laisse
de la marge pour quelques pistes trop courtes. Les clips ne sont gardés qu'en RAM le temps de
la vérification, jamais écrits sur le disque du VPS.

## Protocole de mesure G2 (mainteneur)

### 0. Répétition locale (sans VPS, ~5 min)

Trois terminaux PowerShell dans le worktree, avec `$env:SPIKE_SECRET` défini dans chacun :

```powershell
# Terminal 1
uv run spikes/bridge/relay_server.py serve
# Terminal 2
uv run spikes/bridge/bridge_client.py --server http://127.0.0.1:8765 --root spikes/bridge/_fixtures/library
# Terminal 3
uv run spikes/bridge/relay_server.py trigger --url http://127.0.0.1:8765 -n 25 --crafted
uv run spikes/bridge/relay_server.py poke --url http://127.0.0.1:8765
```

### 1. Préparer le VPS

1. Un sous-domaine (ex. `relay.example.org`) pointant sur le VPS ; ports 80/443 ouverts.
2. Copier **uniquement** `relay_server.py` sur le VPS (il est autonome), installer `uv`.
3. Caddy en frontal (TLS automatique, WebSocket transparent) :
   ```
   relay.example.org {
       reverse_proxy 127.0.0.1:8765
   }
   ```
4. Lancer : `SPIKE_SECRET=... uv run relay_server.py serve --host 127.0.0.1 --port 8765`
   (dans `tmux`/`screen`). Le relais n'écoute qu'en local : seul Caddy est exposé.
5. Noter : fournisseur, offre (vCPU/RAM), région, distance approximative du domicile.

### 2. Préparer le PC (Windows, utilisateur standard)

1. Noter : CPU, disque de la bibliothèque (SSD/HDD/NAS/USB), version de Windows, FFmpeg
   (`ffmpeg -version`, première ligne), Python, connexion (fibre/ADSL/4G, débit **montant**
   mesuré le jour même), box (modèle), Wi-Fi ou Ethernet.
2. `uv run spikes/bridge/sandbox_probe.py` → copier la sortie. Si possible, activer
   temporairement le mode développeur et relancer pour couvrir les symlinks. Attendu : 1 FAIL
   connu, (g2) avec le gabarit exact (voir § 3) ; tout **autre** FAIL est un constat nouveau.
3. Scan à froid (après redémarrage, ou au moins à la première exécution du jour), puis à chaud :
   `uv run spikes/bridge/scan_bench.py D:\Music --repeat 3 --json-out spikes/bridge/_out/catalog-real.json`
4. Bench FFmpeg local (sans réseau) sur un échantillon reproductible :
   `uv run spikes/bridge/ffmpeg_bench.py --catalog spikes/bridge/_out/catalog-real.json -n 100 --seed 1 --seek-ref --json-out spikes/bridge/_out/ffmpeg-real.json`
   S'assurer que l'échantillon contient au moins quelques FLAC, MP3 (CBR et VBR) et M4A ; sinon
   augmenter `-n` ou changer `--seed`. Cibler une junction réelle si la bibliothèque en contient
   (elle doit apparaître dans « junctions skipped » et ses fichiers ne pas être listés).
   Recopier le tableau « per input group, ALL jobs » : taux de `DECODE_ERROR` par groupe,
   durées estimées (MP3 sans Xing, ADTS) et ré-encodages (sources qui finissent avant la durée
   annoncée).

### 3. Mesure G2 à travers la box

1. Sur le PC : `uv run spikes/bridge/bridge_client.py --server https://relay.example.org --root D:\Music --name <nom>`.
   Vérifier `ONLINE` et le RTT affiché.
2. Depuis n'importe quel poste : `trigger -n 25 --crafted` **trois fois** (`--seed 1`, `2`, `3`),
   avec `--json-out spikes/bridge/_out/g2-runN.json`, puis `poke` (vérifier `worker_alive: true`).
   Pour chaque run, recopier la ligne du verdict **avec** `OK x/n` et les codes d'échec ; un run
   `INCONCLUSIVE` (échec `TIMEOUT`, `BRIDGE_OFFLINE`…) se note tel quel, puis se relance après
   avoir compris la cause. Il faut au moins 20 jobs dans l'échantillon G2 de chaque run.
3. Variantes à noter si possible : PC en Wi-Fi puis en Ethernet ; un run pendant un usage
   normal du réseau (vidéo en streaming) ; `--duration 20` contre `30`. G2 se mesure avec des
   clips de **30 s au plus** (le Bridge plafonne : `--duration 60` donne des clips de 30 s) ;
   pour estimer le pire cas d'un clip de 60 s, voir « Constats », point 8.
4. Reconnexion : débrancher le réseau 30 s (ou redémarrer la box) pendant que le client tourne,
   puis rebrancher. Noter les états (`BACKOFF`, délais) et le temps de retour à `ONLINE` ; vérifier
   que le catalogue n'est **pas** renvoyé (`catalogue déjà connu`).
5. Arrêter le client (Ctrl+C) et le relais. Rien à nettoyer sur le VPS (clips en RAM).

### Ce qu'il faut consigner (et ne pas consigner)

- Les sorties texte des commandes, telles quelles. **Ne jamais coller** de noms de fichiers, de
  `relpath` ni le contenu de `_out/catalog-real.json` (bibliothèque privée) ; les `track_id`
  sont sans risque.
- Un résultat non mesuré reste vide ou marqué « non mesuré ». **Aucun chiffre inventé**, aucun
  chiffre recopié depuis l'essai local ci-dessous.

## Gabarit de résultats

```
### Spike S1 — mesures réelles du AAAA-MM-JJ
Matériel PC     : CPU …, disque bibliothèque …, Windows …, FFmpeg …, Python …
Réseau          : FAI …, box …, Wi-Fi/Ethernet …, montant mesuré … Mbit/s
VPS             : fournisseur …, offre …, région …, Caddy …

Sandbox (sandbox_probe.py)      : PASS … / FAIL … / SKIP … / INFO …  (mode développeur : oui/non)
Scan (scan_bench.py)            : … pistes, … Go, froid … s, chaud … s (médiane), realpath … s
  ignorés                       : liens …, junctions …, cachés …, système …, hors liste …, erreurs …
  NFD→NFC / collisions          : … / …
  catalogue                     : brut … Ko, gzip … Ko
FFmpeg (ffmpeg_bench.py -n …)   : OK … / échecs … (codes …)
  par groupe (p50/p95 encodage) : FLAC …/… ms, MP3 …/… ms, MP3 VBR …/… ms, M4A …/… ms, autres …
  prepare p95                   : … ms ; |erreur de seek| max … ms (groupe …)
  sortie                        : flux vidéo ou tag title/artist dans un clip : … (attendu 0)
FFmpeg par groupe, tous jobs    : DECODE_ERROR … % (groupe …), durées estimées …, ré-encodages …
G2 à travers la box (3 runs × 25, clips ≤ 30 s) :
  run 1 OK/total, codes         : …/… (codes …)   p95 G2 … ms (p50 …, max …)
  run 2 OK/total, codes         : …/… (codes …)   p95 G2 … ms (p50 …, max …)
  run 3 OK/total, codes         : …/… (codes …)   p95 G2 … ms (p50 …, max …)
  upload côté serveur p95       : … ms ; RTT applicatif p50 … ms ; taille max d'un clip … Ko
  verdict /stats (3 runs)       : … / … / …
  track_id forgés               : tous NOT_FOUND oui/non
  poke                          : réponses …, worker_alive oui/non, Bridge resté connecté oui/non
Reconnexion                     : coupure … s → ONLINE en … s, catalogue renvoyé oui/non
Verdict G2                      : PASS / FAIL — justification
Anomalies                       : …
```

## Alimenter le DEVLOG

Une fois les mesures faites, une entrée est ajoutée à `docs/DEVLOG.md` **sur `main`** (format
§19.11), sans jamais réécrire les entrées passées : objectif, décisions (ex. durcissement
`-format_whitelist` retenu ou non, Opus ou AAC), « Tests » = commandes réellement exécutées et
chiffres du gabarit ci-dessus, état (`DONE` si G2 passe, sinon `BLOCKED`/`PARTIAL` avec la cause),
problèmes connus, une seule prochaine étape. Les échecs sont écrits tels qu'ils se sont produits.
Les résultats de l'essai local (fixtures synthétiques, relais en `127.0.0.1`) peuvent y figurer
**à condition d'être étiquetés comme tels** : ils ne valident pas G2.

## Essai local du 2026-10-02 (poste de développement, fixtures synthétiques) — ne valide pas G2

Windows 11, 16 cœurs logiques, FFmpeg 9.0.2 (gyan.dev), Python 3.13.2 via `uv`, relais et
Bridge sur `127.0.0.1` (aucune box, aucun VPS, aucune vraie bibliothèque).

Premier passage (avant la revue) :

- `fixtures.py --force` : 59 fichiers, 319,2 Mo, 43,1 s ; 5 M4A, tous avec `moov` en fin.
- `scan_bench.py --repeat 3` : 52 pistes retenues (55 fichiers vus, 25 dossiers), 315,0 Mo,
  scan 0,014 s puis médiane 0,013 s ; ignorés : 2 fichiers « point », 1 HIDDEN, 1 SYSTEM,
  2 hors liste blanche ; 3 normalisations NFD → NFC, 1 collision écartée ; catalogue 6 744 o
  brut, 1 662 o gzip.
- `sandbox_probe.py` : 30 PASS, 0 FAIL, 3 SKIP (symlinks : WinError 1314, mode développeur
  inactif), 1 INFO (hard link). Junction ignorée au scan, dossier remplacé par une junction
  après le scan refusé à l'ouverture, playlists HLS/ffconcat refusées par FFmpeg.
- `ffmpeg_bench.py --fixtures --seek-ref` : 41 OK, 9 `TOO_SHORT`, 2 `DECODE_ERROR`, 0 écart
  au manifeste ; prepare p50 415 ms, p95 473 ms, max 536 ms ; encodage p95 par groupe
  375–476 ms ; aucun flux vidéo ni tag title/artist dans les clips ; |erreur de seek| ≤ 1,5 ms
  (FLAC, MP3 CBR/VBR, M4A moov en fin, Vorbis, Opus, WAV, AIFF).
- Relais + Bridge, `trigger -n 30 --seed 3 --crafted` : 21 OK, 9 `TOO_SHORT` (pistes de 3 et
  5 s voulues) ; PREPARE → upload reçu p50 467,7 ms, p95 523,0 ms, max 532,6 ms ; les 6
  `track_id` forgés → `NOT_FOUND`. `poke` : types inconnus, `PREPARE` avec champ en trop ou
  manquant, non-JSON et trame binaire ignorés ; `upload_url` étrangère → `INVALID_REQUEST` ;
  chemin en guise d'ID → `NOT_FOUND` ; Bridge resté connecté. Mauvais secret → HTTP 403 ;
  `http://` vers une IP non locale refusé ; certificat auto-signé → `SSLCertVerificationError`.
  Coupure du relais → `BACKOFF` puis reconnexion et renvoi du catalogue (le relais redémarré
  l'avait perdu) ; redémarrage du seul Bridge → « catalogue déjà connu ».

Second passage, après corrections de la revue (même jour, même poste) :

- `fixtures.py --force` : 60 fichiers (+ MP3 VBR sans Xing), 320,2 Mo, 42,2 s.
- `sandbox_probe.py` : 33 PASS, **1 FAIL**, 3 SKIP (symlinks), 1 INFO. Le FAIL est (g2) :
  `ffconcat` via une junction interne, gabarit exact → clip de 30 s d'un fichier **hors de la
  racine**, accepté par le contrôle de sortie ; refusé avec `-format_whitelist`.
- `ffmpeg_bench.py --fixtures --no-duration-measure` (règle §10 seule) : MP3 sans Xing à la
  fraction 0,95 → `DECODE_ERROR` (clip vide), 1 écart au manifeste.
- `ffmpeg_bench.py --fixtures --seek-ref` (pipeline du spike) : 42 OK, 9 `TOO_SHORT`,
  2 `DECODE_ERROR` (fichier vide, octets aléatoires), 0 écart au manifeste ; MP3 sans Xing :
  durée estimée 259,3 s → mesurée 180,0 s en 65 ms, départ 124,3 s, OK ; ADTS : 46,7 → 45,0 s ;
  FLAC tronqué à 0,29 : clip prévu 30 s, source finie à 27,2 s → ré-encodé, fondu présent ;
  RMS fin/milieu max 0,020 sur les 42 clips (contre 1,002 pour le même FLAC tronqué avec le
  gabarit seul) ; prepare (lookup + probe + encodage + contrôle de sortie) p50 532 ms, p95
  619 ms, max 967 ms (le FLAC ré-encodé).
- Relais + Bridge, `trigger -n 25 --seed 3 --crafted --duration 60` : OK 20/25, 5 `TOO_SHORT` ;
  p50 445,5 ms, p95 499,2 ms, max 510,7 ms ; verdict `PASS [OK 20/25, content failures
  {'TOO_SHORT': 5}]` ; clips plafonnés à 30,0 s (max 486 861 o), note affichée ; 6 forgés →
  `NOT_FOUND`. `poke` : poke-3 `INVALID_REQUEST`, poke-4 `NOT_FOUND`, poke-5 (durée 1e9,
  fraction −5), poke-6 (durée `10**400`) et poke-alive → `INVALID_UPLOAD` (clip produit, upload
  refusé comme prévu), poke-7 (jeton non ASCII) ignoré, `worker_alive: true`. Avec le client
  d'avant la correction, poke-6 tuait le worker : aucune réponse à poke-alive.
- Verdict G2 (test du relais avec jobs simulés) : 20 OK + 5 `TIMEOUT` → `FAIL` (p95 infini) ;
  24 OK + 1 `TIMEOUT` → `INCONCLUSIVE` ; 9 OK + 1 `TOO_SHORT` + 15 `BRIDGE_OFFLINE` → `FAIL`
  (le run de la revue affichait `PASS_SMALL_SAMPLE`) ; 20 OK + 5 `TOO_SHORT` → `PASS`.

Constats à reporter dans la spec ou le vrai Bridge :

1. **Source tronquée** (en-tête FLAC annonçant 180 s, données coupées à 40 %) : si le départ
   tombe après la fin réelle, FFmpeg sort un `.m4a` **valide mais vide** (257 o, magic bytes
   corrects) que le serveur aurait accepté. Le pipeline du spike sonde donc le clip produit
   (~40 ms) et le refuse (`DECODE_ERROR`) s'il dure moins de la moitié de l'extrait prévu ;
   s'il est plus court que prévu de plus de 0,25 s, il le **ré-encode** avec la durée mesurée,
   sinon le fondu de sortie (`st=` calculé sur la durée prévue) tombe après la fin et le clip
   se termine sèchement. À ajouter au §10 (contrôle de sortie).
2. Le gabarit laisse dans le clip des clés de conteneur sans information sur le morceau
   (`major_brand`, `encoder` = version de Lavf, `handler_name`…). `-fflags +bitexact` les
   réduirait ; à décider (hors spec actuelle).
3. WMA, AAC ADTS et MP3 sans Xing : décalage de 23 à 45 ms entre la position demandée et la
   position absolue (délai d'encodeur non signalé), sans effet sur le jeu.
4. **Le gabarit §10 ne satisfait pas seul le critère 2 de G2** : un `.mp3` qui contient une
   playlist `ffconcat` et une junction interne font lire à FFmpeg un fichier hors de la racine
   (cas (g2) de la sonde). Proposition : `-format_whitelist` sur ffprobe et ffmpeg (déjà dans
   `prepare_clip(hardened=True)` et `ffmpeg_bench.py --hardened`), ou démultiplexeur forcé
   d'après l'extension (non testé). À trancher avant le vrai Bridge.
5. **MP3 VBR sans en-tête Xing/VBRI** (vieux rips) : ffprobe estime la durée à partir du débit
   de la première trame (« Estimating duration from bitrate »), ici 259 s pour 180 s (la revue a
   vu 668 s sur un autre signal). La règle §10 place alors le départ après la vraie fin : clip
   vide, `DECODE_ERROR` sur un fichier valide. Mitigation du spike : ffprobe en `-v warning`, et
   sur ce message, mesure de la vraie durée par démultiplexage sans décodage (~45–65 ms). Autre
   piste non retenue : réessayer avec une fraction plus basse quand le clip sort vide. À ajouter
   au §10.
6. **Robustesse du worker** : toute exception non prévue (débordement `float` sur une durée
   entière géante, jeton non ASCII, `OSError` local) tuait la tâche du worker sans trace ; le
   Bridge restait `ONLINE` mais ne traitait plus rien (`BRIDGE_BUSY` ensuite). Corrigé :
   `JOB_FAILED INTERNAL` et la boucle continue. Le §7.3 ne liste ni `INTERNAL`, ni
   `BRIDGE_BUSY`, ni `INVALID_REQUEST` : codes à ajouter ou à replier sur des codes existants.
7. Verdict G2 : un p95 calculé sur les seuls succès masque les blocages ; le relais compte
   désormais les échecs hors contenu comme des temps infinis. À reprendre dans la définition
   de G2 (§26) : « p95 < 5 s, échecs de transport comptés comme > 5 s ».
8. **Durée maximale d'un clip incohérente dans la spec** : le §1 parle d'un extrait « de 20 à
   30 s », le §15 autorise `CLIP_MAX_S=60` côté serveur. Le Bridge du spike plafonne à 30 s, et
   G2 n'est mesuré qu'avec des clips ≤ 30 s. Effet d'un clip de 60 s en AAC 128 kbit/s : environ
   960 Ko, soit ~7,7 s d'upload à 1 Mbit/s montant, contre ~480 Ko et ~3,8 s pour 30 s (chiffres
   du §22) : **G2 (< 5 s) serait hors d'atteinte** sur ce type de liaison avec 60 s.
   Décision à prendre par le mainteneur : ramener `CLIP_MAX_S` à 30, ou accepter un budget G2
   dépendant de la durée.
