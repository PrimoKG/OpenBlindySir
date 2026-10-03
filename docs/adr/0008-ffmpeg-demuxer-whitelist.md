# 0008 — FFmpeg : liste blanche de démultiplexeurs
Statut : Accepté   ·   Date : 2026-10-02

## Contexte
Le Bridge ouvre avec FFmpeg des fichiers choisis par le serveur, via un `track_id`, dans une bibliothèque fournie par l'utilisateur ([0002](0002-bridge-outbound-connection-and-sandbox.md)). Le gabarit initial imposait déjà `-protocol_whitelist file` et le préfixe `file:`.

Le spike S1 (voir `docs/DEVLOG.md`, entrée des spikes) a montré que ce n'était pas suffisant. FFmpeg choisit le démultiplexeur d'après le **contenu** du fichier, pas d'après son extension. Un fichier texte nommé `trap.mp3` et contenant une playlist `ffconcat` est donc accepté comme concaténation. Le démultiplexeur ouvre alors **d'autres fichiers** par le protocole `file`, qui reste autorisé.

Le bac à sable n'a vérifié que `trap.mp3`. La playlist peut désigner un fichier situé hors de la racine, par un chemin absolu ou à travers une junction. L'extrait produit contient alors l'audio d'un fichier que le Bridge n'aurait jamais dû lire. HLS (`.m3u8`) et les autres formats de playlist présentent le même risque.

## Options considérées
**A. Vérifier l'extension, ou les premiers octets, avant d'appeler FFmpeg.**
- Pour : simple.
- Contre : FFmpeg reconnaît des dizaines de formats ; une liste noire de signatures reste incomplète. L'extension ne prouve rien.

**B. Forcer le démultiplexeur selon l'extension (`-f mp3`, `-f flac`…).**
- Pour : le format est imposé.
- Contre : refuse des fichiers légitimes mal nommés (un `.mp3` qui est en réalité de l'AAC) ; correspondance extension → démultiplexeur à maintenir.

**C. `-format_whitelist` limité aux démultiplexeurs des extensions acceptées par le scanner.**
- Pour : la sonde de contenu de FFmpeg reste active pour les fichiers légitimes. Tout démultiplexeur hors liste est refusé avant toute lecture secondaire : concat, hls, image2, tty, lavfi, etc.
- Contre : la liste doit suivre la liste blanche d'extensions du scanner.

## Décision
Option C. `ffprobe` et `ffmpeg` reçoivent tous les deux :

- `-protocol_whitelist file` ;
- `-format_whitelist mp3,flac,wav,mov,ogg,aiff,asf,aac`, défini dans `openblindysir_bridge.ffmpeg.DEMUXER_WHITELIST`, qui couvre mp3, flac, wav, m4a/mp4/aac, ogg/opus, aiff et wma ;
- l'entrée sous la forme `file:` + chemin absolu résolu par le bac à sable.

Le **serveur ne contrôle jamais un argument FFmpeg**. Le gabarit est fixe, les arguments sont passés en liste, sans shell. La sortie est contrôlée elle aussi : la durée de l'extrait produit est mesurée, et un extrait trop court (FLAC tronqué, par exemple) est un `DECODE_ERROR`.

## Conséquences
- Une playlist déguisée en audio échoue en `DECODE_ERROR`, qu'elle pointe dans la racine ou en dehors. Aucun octet n'est envoyé.
- Ajouter une extension au scanner impose d'ajouter son démultiplexeur ici. Un test golden fige la liste exacte d'arguments.
- Tests de régression :
  - ffconcat hors racine via une junction, sur un runner Windows ;
  - ffconcat et HLS dans la racine, multiplateforme ;
  - noms de fichiers contenant des métacaractères de shell ;
  - fichiers supprimés, renommés ou remplacés après le scan (`bridge/tests/runtime/test_jobs_ffmpeg.py`).
- Un test de mutation manuel a été fait : en retirant `-format_whitelist`, les deux tests ffconcat échouent.
- Risque résiduel inchangé : une faille d'un décodeur autorisé, exploitée par un fichier piégé de l'utilisateur. Il est atténué par la vérification de version, les timeouts et l'exécution sans droits administrateur.

## Évolution V0.2

Les règles de revue/notation/réécoute sont précisées par [ADR 0011](0011-global-review-and-private-replay.md).
Les sources, formats et métadonnées sont précisés par [ADR 0012](0012-dynamic-sources-and-metadata.md).
Les décisions historiques restent conservées ; ces deux ADR font autorité pour les changements V0.2.
