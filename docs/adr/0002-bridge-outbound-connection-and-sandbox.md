# 0002 — Bridge : connexion sortante et bac à sable
Statut : Accepté   ·   Date : 2026-10-01

## Contexte
La bibliothèque musicale (des dizaines, voire des centaines de gigaoctets) reste sur le PC qui la contient, derrière une box ou un NAT. Le serveur OpenBlindySir tourne sur un VPS et a besoin, à chaque round, d'un **extrait de 20 à 30 s** d'un morceau de cette bibliothèque. **Les fichiers complets ne doivent jamais quitter le PC** (`docs/architecture.md` §1).

Le projet est public : OpenBlindySir Bridge (« le Bridge ») est une **frontière de sécurité**. Il considère le serveur comme **non fiable**, ce qui prépare aussi le cas de plusieurs Bridges appartenant à des personnes différentes (§2, §11).

Menaces à couvrir (§12) : path traversal depuis le serveur, évasion par lien symbolique ou junction Windows, serveur malveillant qui chercherait à lire des fichiers, à exécuter du code ou à saturer le PC, faux Bridge muni d'un secret volé.

## Options considérées
**A. Monter la bibliothèque sur le VPS (SSHFS, SMB).**
- Pour : aucun logiciel spécifique à écrire pour le PC.
- Contre : expose tout le système de fichiers au serveur ; exige un port entrant ou un VPN ; les fichiers complets traversent le réseau. Contraire au but.

**B. Bridge qui écoute sur un port entrant.**
- Pour : modèle client/serveur classique, le VPS appelle le PC.
- Contre : redirection de port sur la box, échec derrière un CGNAT, surface d'attaque exposée sur le réseau domestique.

**C. FFmpeg sur le VPS, le Bridge envoie le fichier source.**
- Pour : Bridge réduit à un simple serveur de fichiers.
- Contre : le fichier complet quitte le PC (70 Mo pour un FLAC) ; image serveur alourdie ; transcodage sur un VPS minimal ; débit montant domestique saturé.

**D. Bridge sortant, catalogue indexé par identifiant, FFmpeg local à gabarit fixe.**
- Pour : aucun port entrant ; le serveur ne peut jamais désigner un chemin ; seul un extrait d'environ 400 Ko sans métadonnées quitte le PC.
- Contre : un programme et FFmpeg à installer sur le PC ; l'arborescence fuit via le catalogue.

## Décision
Option D, avec les règles suivantes.

**Connexions sortantes uniquement**
- Contrôle : WSS `/api/bridge/ws`, `Authorization: Bearer BRIDGE_SECRET` à l'ouverture, heartbeat toutes les 15 s, reconnexion sans fin (backoff 1→30 s avec jitter).
- Volume : HTTPS `PUT /api/bridge/catalog` (JSON gzip) et `PUT /api/bridge/assets/{asset_id}` (upload token à usage unique, valable 2 min).
- `ws://` et `http://` refusés sauf vers `localhost`. **Vérification TLS toujours active**, sans option pour la désactiver.

**Catalogue indexé par `track_id`**
- `track_id = "t_" + sha256(relpath)[:16]` : stable et opaque. Entrées `track_id, relpath, folder, ext, size` ; `catalog_hash` calculé sur les entrées triées ; le catalogue n'est renvoyé que s'il a changé.
- Côté Bridge, `track_id` est une **clé de dictionnaire, jamais un chemin**. Un identifiant inconnu donne une erreur.

**Protocole fermé**
- Messages acceptés par le Bridge, liste exhaustive : `WELCOME`, `PREPARE`, `CANCEL`, `PING`. Il n'existe ni « lister », ni « lire un fichier », ni « rescanner un chemin », ni argument FFmpeg libre.
- `PREPARE {job_id, track_id, start_fraction, duration, upload_url, upload_token}` est la seule commande métier. Format, débit et durée demandés sont **plafonnés par les maxima du Bridge**.
- `JOB_FAILED` porte un code normalisé, **jamais un chemin absolu**. Le Bridge ignore tout des règles du jeu.

**Bac à sable**
- Une seule racine autorisée. Scan itératif par `os.scandir`, qui **ne suit ni les liens symboliques ni les junctions** : tests explicites `is_symlink()` et `os.path.isjunction()`, car `os.walk` suit les junctions sous Windows. Fichiers cachés et système ignorés, liste blanche d'extensions.
- **Avant chaque ouverture** : nouvelle résolution `realpath`, vérification `os.path.commonpath([real, root_real]) == root_real`, fichier régulier, taille et mtime cohérents avec le catalogue.

**FFmpeg à gabarit fixe**
- Arguments passés en liste, **jamais via un shell** : `-nostdin -hide_banner -loglevel error -threads 1`, `-protocol_whitelist file`, entrée préfixée `file:` suivie du chemin absolu résolu, `-ss` avant `-i`, `-t`, `-map 0:a:0 -vn -sn -dn`, `-map_metadata -1 -map_chapters -1`, `-ac 2 -ar 48000`, `afade`, encodeur pris dans une liste fixe ([0004](0004-audio-format.md)).
- Seules variables : le chemin (issu du catalogue), le départ et la durée (flottants bornés par le Bridge), le format (une valeur d'une liste fixe).
- Limites : 1 job à la fois (2 au maximum), file de 4, rejet au-delà ; timeouts ffprobe 10 s, ffmpeg 30 s (processus tué), upload 60 s ; fichiers temporaires dans un répertoire privé préfixé `openblindysir-bridge-`, supprimés après envoi et purgés au démarrage.

**Discrétion** : console et logs sans nom de fichier par défaut, seulement `track_id` et durées ; `--verbose-paths` sert au débogage.

**Contrepartie côté serveur** : upload accepté seulement pour un job en attente, corps lu en flux et coupé au-delà de 2 Mo, magic bytes et sha256 vérifiés ; seul un asset `STORED` est servi (§5.3).

## Conséquences
- Fonctionne derrière n'importe quelle box, NAT ou CGNAT, sans configuration réseau.
- Un serveur compromis ne peut ni lire hors de la racine, ni faire exécuter une commande, ni saturer le PC au-delà des bornes du Bridge.
- Les fichiers complets ne quittent jamais le PC ; l'image serveur ne contient pas FFmpeg.
- **Fuite résiduelle acceptée et documentée** : le serveur connaît l'arborescence et les noms de fichiers (`relpath`), nécessaires à la sélection par dossier et au reveal.
- **Fenêtre TOCTOU résiduelle acceptée** entre la vérification et l'ouverture : l'exploiter suppose un attaquant déjà présent sur le PC.
- Un fichier piégé visant FFmpeg reste un risque faible (fichiers fournis par l'utilisateur) : version de FFmpeg vérifiée, timeouts, consigne de ne jamais lancer le Bridge en administrateur.
- L'utilisateur installe FFmpeg lui-même (winget, brew, apt) : il **n'est pas embarqué en V0.x**, pour éviter les obligations liées aux builds GPL. Version et encodeurs sont vérifiés au démarrage.
- Bridge hors ligne : les assets déjà `STORED` (1 à 2 rounds d'avance) restent jouables, puis le round suivant attend en PREPARING.
- Tests obligatoires (§20.1, points 9 et 10) : `..`, chemins absolus, ID inconnu, lien symbolique vers l'extérieur, **junction Windows sur un runner Windows**, fichier remplacé par un lien après le scan, NFC/NFD, noms commençant par `-` ou contenant `:` ; tests golden sur la liste exacte d'arguments FFmpeg, bornes appliquées même si le serveur demande 3 600 s. Jobs CI `bridge-linux` et `bridge-windows`.
- Plusieurs Bridges sont préparés à coût quasi nul : références `(bridge_id, track_id)`, catalogues indexés par `bridge_id`, jobs routés vers le Bridge propriétaire. En V0.1, un second Bridge remplace le premier ; un secret par Bridge arrive en V1.
