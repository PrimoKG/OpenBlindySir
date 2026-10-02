# OpenBlindySir — Bridge : fonctionnement et sécurité

> Extrait de la spécification canonique (docs/architecture.md, §11). Ce document fait autorité pour cette section.

## 11. Bridge

**Configuration**
- Assistant au premier lancement : URL du serveur, dossier, secret (saisie masquée), nom affiché du Bridge.
- **Emplacement unique du fichier `config.toml`** :
  - Windows : `%APPDATA%\OpenBlindySir\bridge\config.toml`
  - Linux et macOS : `~/.config/openblindysir/bridge/config.toml`
- Ce fichier contient aussi un `bridge_id` UUID, généré une seule fois.
- Ordre de priorité : arguments CLI, puis variables d'environnement, puis fichier.
- `ws://` et `http://` sont refusés sauf vers `localhost`. **La vérification TLS est toujours active**, sans option pour la désactiver.
- Les fichiers temporaires vont dans un dossier privé préfixé `openblindysir-bridge-`.
- Le User-Agent HTTP et WebSocket est `OpenBlindySir-Bridge/<version>`.

**Scan**
- Parcours itératif avec `os.scandir`.
- **Ne suit ni les liens symboliques ni les junctions**, avec des tests explicites `is_symlink()` et `os.path.isjunction()` (attention : `os.walk` suit les junctions sous Windows).
- Ignore les fichiers cachés et système.
- Liste blanche d'extensions réglable : `.mp3 .flac .wav .m4a .aac .ogg .oga .opus .aiff .wma`.
- Pour chaque fichier : `relpath` (séparateurs POSIX, NFC), taille, mtime. **Pas de ffprobe au moment du scan.**

**Catalogue**
- `track_id = "t_" + sha256(relpath)[:16]` : stable et opaque.
- `catalog_hash` calculé sur les entrées triées.
- Chaque entrée contient `track_id, relpath, folder, ext, size`.
- Envoi en gzip par HTTP, environ 600 Ko bruts pour 5 000 morceaux.

**Connexion** : WSS sortant, heartbeat toutes les 15 s, reconnexion sans fin (backoff 1→30 s avec jitter). À la reconnexion, `HELLO` transmet le `catalog_hash` et le serveur ne redemande le catalogue que s'il a changé.

**Commandes acceptées, liste exhaustive** : `WELCOME`, `PREPARE`, `CANCEL`, `PING`. Il n'existe ni « lister », ni « lire un fichier », ni « rescanner un chemin », ni argument FFmpeg libre.

**Exécution des jobs**
- 1 job à la fois (2 au maximum), file de 4, rejet au-delà.
- Timeouts : ffprobe 10 s, ffmpeg 30 s (processus tué), upload 60 s.
- Fichiers temporaires dans un répertoire privé (`tempfile.mkdtemp`, préfixe `openblindysir-bridge-`), supprimés après envoi et purgés au démarrage.

**Avant chaque ouverture de fichier**
- Nouvelle résolution de `realpath`.
- Vérification que `commonpath(real, root_real) == root_real`.
- Vérification qu'il s'agit d'un fichier régulier et que taille et mtime sont cohérents.

La fenêtre TOCTOU résiduelle est acceptée : il faudrait un attaquant déjà présent localement.

**Console**
- **Aucun nom de fichier par défaut**, seulement `track_id` et durées. L'option `--verbose-paths` sert au débogage.
- Affichage type :
  ```
  OpenBlindySir Bridge 0.1.0 — « Ayoub »
  Serveur : https://openblindysir.example.com   CONNECTÉ (RTT 32 ms)
  Dossier : D:\Music — 5 273 pistes (scan 4,2 s)
  Jobs    : 12 OK · 1 échec · dernier t_9f2c… 0,8 s
  [r] rescanner   [q] quitter
  ```

**Hors ligne** : le Bridge réessaie indéfiniment et affiche BACKOFF. Le serveur continue avec les assets déjà stockés.

**FFmpeg**
- Recherché dans le PATH ou indiqué par `--ffmpeg`.
- Vérification de la version et des encodeurs disponibles au démarrage.
- S'il manque, message clair avec la commande winget, brew ou apt.
- **FFmpeg n'est pas embarqué en V0.x**, pour éviter les obligations liées aux builds GPL.
- Gabarit fixe sans shell. `ffprobe` et `ffmpeg` reçoivent tous les deux `-protocol_whitelist file`, `-format_whitelist mp3,flac,wav,mov,ogg,aiff,asf,aac` et l'entrée `file:` + chemin résolu. Le serveur ne fournit jamais d'argument FFmpeg.
- FFmpeg détecte le format par le contenu, pas par l'extension. Sans la liste de démultiplexeurs, une playlist `ffconcat` ou HLS nommée `.mp3` pourrait lire d'autres fichiers, y compris hors de la racine. Voir [ADR 0008](adr/0008-ffmpeg-demuxer-whitelist.md) et les tests de régression associés.

**Mode `--demo`** : catalogue virtuel de morceaux synthétiques (sinusoïdes, mélodies de bips, clics générés par `ffmpeg -f lavfi`). Il sert au développement, à la CI, aux tests E2E et à essayer un déploiement **sans aucun contenu protégé**.

**Packaging**
| Étape | Option |
|---|---|
| V0.1 | `uv run openblindysir-bridge` depuis le dépôt |
| V0.3 | Distribution `openblindysir-bridge` (PyPI), lancée avec `uvx openblindysir-bridge`. Binaires PyInstaller **onedir** zippés produits par la CI (Windows, macOS, Linux), nommés `OpenBlindySir-Bridge-<version>-<os>-<arch>.zip`, non signés, avec la procédure SmartScreen/Gatekeeper documentée. |
| Écarté | Nuitka (builds lourds, mêmes alertes antivirus) ; zipapp (exige Python installé) |
| V1+ | Réécriture en Go, seulement si la distribution pose un vrai problème |

La publication sur PyPI n'est pas figée avant la V0.3 ; seul le nom est réservé conceptuellement.

**Plusieurs Bridges**
- **Dès maintenant**, pour un coût quasi nul :
  - références de morceau `(bridge_id, track_id)` ;
  - catalogues indexés par `bridge_id` ;
  - `bridge_id` et `name` transmis dans `HELLO` ;
  - jobs envoyés au Bridge propriétaire ;
  - arborescence préfixée par le nom du Bridge ;
  - serveur considéré comme non fiable.
- En V0.1, un second Bridge remplace le premier.
- **Reporté en V1** : un secret par Bridge, la pondération entre bibliothèques, la déduplication, une interface de gestion des Bridges.

## Menaces concernant le Bridge (extrait du §12)

| Menace | Impact | Mitigation | Quand |
|---|---|---|---|
| Path traversal depuis le serveur | Lecture de fichiers hors du dossier | `track_id` sert de **clé de dictionnaire, jamais de chemin**. ID inconnu : erreur. | V0.1 |
| Évasion par symlink ou junction | Idem | Liens ignorés au scan, `realpath` et confinement vérifiés au scan **et** à l'ouverture, tests sur un runner Windows. | V0.1 |
| Serveur malveillant vu du Bridge | Lecture de fichiers, exécution, saturation du PC | Protocole fermé de 4 messages, aucun argument FFmpeg libre, bornes fixées par le Bridge, file limitée, timeouts, préfixe `file:`, `protocol_whitelist` et `format_whitelist` (§10), contrôle de la durée produite. Fuite résiduelle (documentée) : arborescence et noms de fichiers. | V0.1 |
| Faux Bridge (secret volé) | Diffusion d'audio choisi par l'attaquant, saturation | Secret fort, upload uniquement pour un job en attente (token à usage unique), ≤ 2 Mo, magic bytes, un seul Bridge actif. Rotation par `.env`. Un secret par Bridge en V1. | V0.1 / V1 |
| Fichier piégé visant FFmpeg | Exécution de code sur le PC | Fichiers fournis par l'utilisateur (risque faible), vérification de la version de FFmpeg, timeouts, et consigne de ne pas lancer le Bridge en administrateur. | V0.1 (doc) |
| MITM / absence de TLS | Vol des secrets | HTTPS obligatoire (Caddy + HSTS), cookie Secure, le Bridge refuse toute connexion non TLS hors localhost. | V0.1 |
