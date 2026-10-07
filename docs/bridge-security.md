# OpenBlindySir — Bridge : fonctionnement et sécurité

Référence V0.5 développement, protocole 9 (plage 9 à 9). [Architecture](architecture.md),
[formats et métadonnées](media-and-metadata.md), [ADR 0011](adr/0011-global-review-and-private-replay.md)
et [ADR 0012](adr/0012-dynamic-sources-and-metadata.md).

## Configuration et racine autorisée

L'assistant local demande URL, racine musicale, secret masqué et nom. Le fichier
privé `config.toml` est dans `%APPDATA%\OpenBlindySir\bridge` sous Windows,
`$XDG_CONFIG_HOME/openblindysir/bridge` (sinon `~/.config/openblindysir/bridge`)
sous Linux, et `~/Library/Application Support/OpenBlindySir/bridge` sous macOS
(une configuration historique Linux déjà présente reste reconnue).
Le fichier et ses parents ne doivent pas être des liens/junctions ; la racine
est contrôlée dès `init`, `check-config` et `doctor`, avant le scan.
L'UUID `bridge_id` reste stable ;
chaque installation conserve son propre fichier/volume. Priorité CLI > variables
d'environnement > fichier. HTTP/WS est refusé hors localhost ; TLS reste vérifié.
Le serveur ne peut ni changer cette racine ni fournir une commande FFmpeg.

Le propriétaire peut activer `--allow-full-review`,
`OPENBLINDYSIR_BRIDGE_ALLOW_FULL_REVIEW=true`, ou `allow_full_review=true` dans
sa configuration. L'écoute intégrale est désactivée par défaut. Cette autorisation
locale permet des segments courts réencodés, jamais un upload du fichier original.

## Scan, sources dynamiques et catalogue

Parcours itératif `os.scandir`, maximum 200 000 fichiers et profondeur 32. La
racine et ses parents ne doivent pas être liens/junctions ; ceux rencontrés au
parcours, fichiers cachés et système sont ignorés. Le scan ne lance pas ffprobe.
Les extensions forment une liste blanche fermée commune au protocole et à FFmpeg,
décrite dans [les formats](media-and-metadata.md). Une extension acceptée ne
garantit pas qu'un fichier soit décodable ou contienne de l'audio.

`SCAN_SOURCES` reçoit soit `null` (rafraîchir), soit au plus 64 sous-dossiers
relatifs POSIX NFC, chacun ≤1 024 caractères. `""` désigne la racine. Chemins
absolus, `..`, `.` intermédiaire, antislashs, contrôles, liens et dossiers absents
sont refusés. En cas d'échec, le catalogue précédent reste utilisable et l'erreur
est présentée à l'hôte. Une modification réussie est persistée localement. Les
rescans console et distants sont sérialisés et exécutés hors de la boucle réseau.
Un dossier non monté demande une modification du déploiement local :
[procédure Docker](docker.md#sources-dynamiques-et-réécoute).

Le chemin relatif à la racine reste stable lorsqu'on change la sélection scannée.
`track_id = "t_" + sha256(relpath NFC)[:16]`. Les dossiers superposés ne dupliquent
pas les pistes. Une collision NFC ou d'ID exclut toutes les entrées concernées et
produit un diagnostic de chemin ambigu ; aucun fichier arbitraire n'est choisi.
Le catalogue contient chemins relatifs, tailles et extensions ; les chemins
absolus restent locaux. Upload gzip ≤8 MiB, contenu brut ≤32 MiB, 200 000 pistes
maximum par Bridge. Le serveur connaît les noms de la bibliothèque : protéger
l'accès hôte et son snapshot privé.

## Connexion et commandes

WSS sortant, heartbeat 15 s, backoff 1–30 s avec jitter. `HELLO` porte l'UUID et
le hash du catalogue. À la reconnexion, un changement de hash déclenche son upload.
Un rescan force aussi l'actualisation des sources/diagnostics même si les fichiers
et leur hash sont inchangés.
Scans et uploads de catalogue s'exécutent hors du lecteur WebSocket : PONG et
CANCEL restent traités pendant une opération lente. Les scans sont sérialisés,
avec quatre commandes en attente au maximum. Un seul upload catalogue est actif ;
seul le dernier jeton en attente est conservé. À la déconnexion, ces tâches sont
annulées et les commandes en attente supprimées.
Les files de messages sortants du client et du serveur contiennent au plus 64
messages : une saturation ferme la connexion. Une panne du writer interrompt
le lecteur, et la reconnexion purge messages et ancien `WELCOME`. Le backoff
reste borné même après plus de 1 024 échecs consécutifs. Le serveur limite les
messages Bridge à un burst de 40 puis 20/s, avant leur analyse.
Liste exhaustive serveur → Bridge : `WELCOME`, `PREPARE`, `CANCEL`, `PING`,
`SCAN_SOURCES`. Aucun chemin de fichier à encoder, URL externe ou argument FFmpeg
libre n'est accepté. `track_id` est une clé du catalogue local, jamais un chemin.

Jusqu'à huit Bridges actifs coexistent. Un nouvel accès du même UUID remplace
uniquement sa connexion précédente. Jobs et tokens d'upload sont liés au Bridge
propriétaire ; un autre Bridge ne peut pas terminer le job ou utiliser son token.
Le serveur vérifie encore la connexion propriétaire après réception du catalogue.
Après un upload audio, il revérifie la connexion exacte, le job, l'expiration et
l'état de l'asset : une annulation, déconnexion ou reconnexion invalide un transfert
déjà commencé. Les corps HTTP ont un délai total de 60 s ; le gzip doit former
un unique flux complet, sans suffixe ni autre membre. Un ancien transfert ne peut
pas écraser celui d'un Bridge reconnecté.
Un catalogue en réception au plus par UUID, huit globalement, y compris les
anciennes connexions remplacées : les corps refusés en `429` ne sont ni lus ni
décompressés et leur token n'est pas consommé. Le Bridge retente ce refus
temporaire au plus trois fois (0,25/0,5/1 s), conserve le même token et donne
priorité au nouveau token si le serveur en émet un autre.
Chaque UUID utilise un secret distinct, stocké haché dans un registre privé avec
révocation durable. Le bootstrap ancien se lie au premier UUID seulement ; une
rotation/révocation de cet UUID le désactive. L'authentification est revérifiée
après HELLO, sur chaque trame et après les corps HTTP. Un secret d'un autre UUID
ne donne aucun droit sur ses jobs/catalogues/uploads/réécoutes. Plafonds : 64
identités, huit connexions, 200 000 pistes cumulées. La déduplication musicale
entre bibliothèques reste future. Sélection/arborescence : `(bridge_id, dossier)`.
L'hôte joueur en jeu n'accède ni aux noms de sources, ni aux archives, ni à la
bibliothèque HTTP ; le MC conserve ses permissions. Voir [V0.5](v0.5.md).

## Extraction bornée, audio uniquement

FFmpeg et ffprobe doivent désormais être identifiables et au moins en version
9.0.2, chacun vérifié séparément. L’image Docker utilise les sources officielles
signées et un build limité à l’audio/fichiers locaux ; les bibliothèques TIFF/XML,
protocoles réseau et décodeurs vidéo n’y sont pas inclus. Les dépendances natives
installées sur le PC demandent leurs propres mises à jour. Le
[rapport de durcissement](audits/2026-10-05-security-hardening.md) donne les preuves
et limites de l’analyse système.

Un job actif, file de quatre. ffprobe : 10 s ; ffmpeg : 30 s ; upload : 60 s.
Les processus sont tués et récoltés lors d'une annulation ou d'un dépassement.
stdout est plafonné à 128 KiB et stderr conserve au plus ses 8 derniers KiB.
Avant ouverture : nouvelle résolution réelle, fichier régulier, confinement dans
la racine, absence de lien/junction, comparaison taille/mtime au catalogue.
Une fenêtre TOCTOU locale reste possible : le propriétaire des fichiers doit
garder le contrôle de la machine et ne pas lancer le Bridge en administrateur.

Arguments fixes sans shell : `-protocol_whitelist file`, liste fermée
`mp3,flac,wav,mov,ogg,aiff,asf,aac,matroska,avi`, entrée `file:` résolue et
`-f` imposé selon l'extension. Pour MOV/MP4 seulement, `enable_drefs=0` et
`use_absolute_path=0` interdisent les références de données externes. Ces options
spécifiques au démultiplexeur ne sont pas passées aux autres formats.
Le démultiplexeur concat, HLS, DASH, les playlists et protocoles réseau sont
exclus, même lorsqu'ils sont déguisés avec une extension audio/vidéo.

La première piste audio `a:0` est sélectionnée, indépendamment du drapeau
« default ». `-map 0:a:0 -vn -sn -dn`, suppression des tags/chapitres : aucune
vidéo, pochette, sous-titre, donnée ou métadonnée musicale dans le résultat.
Absence d'audio : `NO_AUDIO` ; fichier illisible : `DECODE_ERROR`. Les détails
restent dans la console privée avec `--verbose-paths` ; les joueurs voient des
erreurs génériques. Durée source acceptée : finie, entre 8 s et 24 h.

La sortie commune reste AAC/M4A 128 kb/s par défaut, 48 kHz stéréo ; Opus/WebM
est configurable. Le Bridge borne les extraits à 60 s/4 MiB et les bitrates à
96/128/160/192 kb/s ; le serveur conserve son plafond de 2 MiB. Normalisation
`loudnorm=I=-16:TP=-1.5:LRA=11`, fondus et recherche de silence restent contrôlés
par des gabarits fixes. Trois fenêtres d'analyse maximum ; un extrait entièrement
silencieux échoue en `SILENT_AUDIO`. Un enregistrement faible n'est pas rejeté
pour sa seule amplitude. Aucun audit audio global au scan.

## Réécoute et fichiers temporaires

Les seuls extraits joués peuvent rester dans un cache privé du Bridge plafonné
à 64 MiB, éviction LRU. Une panne de copie du cache ne fait pas échouer un extrait
déjà uploadé ; les copies partielles sont supprimées. Le SHA-256 du résultat est
vérifié pour réécouter exactement l'extrait. Le cache permet même la réécoute
après suppression locale de la source. S'il est perdu, le Bridge peut régénérer
l'extrait ; le serveur refuse tout résultat dont les octets diffèrent.

Une écoute intégrale autorisée localement produit un segment ≤30 s à l'offset
demandé, sans fondus ni cache de fichier complet. Taille/mtime doivent correspondre
à la révision mémorisée pendant la manche ; un fichier modifié est refusé. Les
anciennes recettes sans révision ne permettent pas l'écoute intégrale. Aucun
fichier complet n'est transmis ou stocké. Le serveur limite la réécoute privée
à deux transferts simultanés, un par hôte, chacun ≤2 MiB, hors du cache partagé.

Répertoire privé `openblindysir-bridge-*`, marqueur `owner.pid`. Nettoyage au
quittement ; au démarrage, seuls les répertoires dont le propriétaire est prouvé
arrêté sont purgés. Instances actives, dossiers sans marqueur, liens/junctions
sont conservés. Sous Windows : `OpenProcess`/`GetExitCodeProcess`, jamais
`os.kill(pid, 0)`. La console masque les noms par défaut. Démo `--demo` synthétique
pour tests et essais. FFmpeg est installé localement en natif, inclus dans l'image
Bridge Docker ; la V0.3 fournit aussi les builds natifs et wheels/sdists indépendants.
La publication reste soumise aux contrôles de release et à la configuration PyPI
du mainteneur. Les contrôles refusent configurations/backups, liens, chemins
ambigus et contenus absents du manifeste ; voir [la procédure](releasing.md).
