# ADR 0012 — Sources dynamiques, conteneurs audio et métadonnées

- Statut : Accepté
- Date : 2026-10-03
- Étend ADR 0002 et ADR 0008.

## Contexte

La bibliothèque doit évoluer pendant une soirée et contenir des fichiers vidéo
utilisés exclusivement pour leur audio. L'hôte veut rechercher et corriger les
métadonnées sans révéler la bibliothèque aux joueurs.

## Décision

Une seule politique `protocol/media.py` définit extensions et démultiplexeurs.
FFmpeg et ffprobe forcent le démultiplexeur correspondant à l'extension et la liste
blanche ; seul le protocole `file` est autorisé. MOV désactive explicitement les
références externes et chemins absolus. La première piste audio (`a:0`) est toujours
retenue, indépendamment de sa disposition « default ». Vidéo, sous-titres, données,
chapitres, tags musicaux et pochettes sont supprimés. Aucun argument de shell,
filtre libre, URL réseau ou playlist n'est accepté. `NO_AUDIO` est distinct d'un
fichier illisible. AAC/M4A, 128 kbit/s, 48 kHz stéréo reste la sortie par défaut.

Chaque Bridge conserve une racine autorisée localement. `SCAN_SOURCES` accepte
uniquement jusqu'à 64 sous-dossiers relatifs NFC ou une demande de rafraîchissement.
La racine et tous ses parents, puis chaque sous-dossier, sont contrôlés pour les
liens/junctions. Le catalogue est rescanné sans doublonner les sélections superposées
(limites : profondeur 32, 200 000 fichiers). Les collisions NFC/ID excluent les
deux fichiers et produisent un diagnostic. Une racine inaccessible conserve le
catalogue précédent avec une erreur. Le scan actuel parcourt la racine une fois
avant de filtrer : aucun audit FFmpeg global n'est effectué.

Jusqu'à huit Bridges distincts coexistent avec le secret de déploiement existant.
Seule une reconnexion du même UUID remplace le lien correspondant. Jobs et jetons
de catalogue sont liés au Bridge propriétaire. Un secret par Bridge reste V1.
L'identité `(bridge_id, track_id)` est stable ; les manches gardent leur entrée
et nom de Bridge d'origine même si le catalogue change.

Le format de métadonnées choisi est JSON `{version:1, rows:[...]}`, ≤1 Mio et
10 000 lignes. Clé : UUID du Bridge et chemin relatif POSIX NFC exact. Titre,
artiste, featuring, album, année sont facultatifs. Les diagnostics `invalid`,
`duplicate`, `unknown`, `ambiguous` sont individuels ; les lignes valides passent.
Priorité par champ : correction manuelle non vide, import, puis tags title/artist
ou nom de fichier lors de la préparation du morceau. Les autres champs n'ont pas
de repli FFprobe. Réimporter ne remplace pas une correction manuelle ; effacer un
champ manuel rétablit son repli. Snapshot privé et export JSON des valeurs fusionnées.

Recherche/édition de bibliothèque : hôte seulement au lobby, en revue finale,
aux résultats, ou animateur pendant le jeu. Les hôtes joueurs n'ont pas les noms
des pistes à venir pendant la partie. Les archives et extraits restent sans tags.

## Conséquences

Ajouter un fichier sous un montage existant demande seulement un rescan. Ajouter
un emplacement hors racine nécessite un choix local de racine ou un montage
Docker en lecture seule et la recréation du seul Bridge ; l'interface ne peut pas
créer un montage sur l'hôte Docker. Plusieurs machines peuvent chacun avoir leur
Bridge et leur UUID persistant. La sélection manuelle de morceaux reste V0.3 ;
l'équilibrage par dossier et les réponses en direct du MC sont bien V0.2.

## Validation

Fichiers synthétiques FFmpeg : MP4/MOV/MKV/AVI, piste absente, pistes multiples,
vidéo volumineuse, playlist déguisée ; chemins/junctions Windows, deux Bridges,
imports partiels, priorité manuelle et snapshots. Voir le DEVLOG pour les checks.

## Complément V0.5

Le report des secrets individuels à V1 est remplacé par
[ADR 0015](0015-v05-private-bridges-history-compatibility.md) : UUID/secret distincts,
registre privé de hashes/révocations, bootstrap mono-identité et contrôle de chaque
propriétaire. La déduplication musicale entre bibliothèques reste future.
