# Sources audio, vidéo et métadonnées

## Formats

Les extensions sont insensibles à la casse ; le contenu doit correspondre au
conteneur annoncé. Un codec absent du build FFmpeg peut encore rendre un fichier
illisible. Les playlists (`m3u`, `m3u8`, `pls`, `ffconcat`), les flux et les fichiers
de référence externes ne sont pas des sources autorisées.

| Démultiplexeur FFmpeg forcé | Extensions autorisées |
|---|---|
| mp3 | .mp3 |
| flac | .flac |
| wav | .wav |
| mov, références externes désactivées | .m4a, .mp4, .mov, .m4v, .3gp |
| ogg | .ogg, .oga, .opus |
| aiff | .aiff, .aif |
| asf | .wma, .wmv, .asf |
| aac | .aac |
| matroska | .mkv, .mka, .webm |
| avi | .avi |

Le Bridge choisit la **première piste audio**, même si une autre est marquée par
défaut. Vidéo, sous-titres et données sont ignorés. Les vidéos sans audio donnent
`NO_AUDIO`, puis le jeu cherche un autre morceau selon ses règles de remplacement.
Un fichier illisible donne `DECODE_ERROR`, moins de 8 s donne `TOO_SHORT` ; une
source de plus de 24 h est refusée. Les messages joueur ne contiennent aucun nom
de fichier ni détail FFmpeg. Les diagnostics privés de l'hôte expliquent les exclusions.

La sortie de production reste **AAC/M4A 128 kbit/s, 48 kHz, stéréo**. À ce débit,
20/25/30 s représentent environ 320/400/480 ko, plus le petit en-tête du conteneur ;
60 s environ 960 ko. Le serveur plafonne un upload à 2 Mio par défaut, son cache
partagé à 32 Mio. Opus/WebM est configurable ; les tests Chromium utilisent Opus.
La taille d'une vidéo source ne change pas la taille de l'extrait transféré.
Les fichiers protégés par DRM ou dont le codec n'est pas disponible ne sont pas pris
en charge. Safari/iPhone et les sorties acoustiques doivent encore être essayés
sur vrais appareils avant une release.

## Métadonnées facultatives

Dans **Sources et recherche de bibliothèque**, exportez d'abord le modèle pour retrouver UUID et
chemins exacts. Importez ensuite un fichier UTF-8 JSON, version 3 (les imports versions 1 et 2 restent acceptés) :

```json
{
  "version": 3,
  "rows": [
    {
      "bridge_id": "12345678-1234-1234-1234-123456789abc",
      "relpath": "Anime/OST/theme.mp4",
      "title": "Example theme",
      "artist": "Example artist",
      "featuring": "Example guest",
      "album": "Example soundtrack",
      "year": 2026,
      "genres": ["Pop"],
      "languages": ["en"],
      "tags": ["Jeux vidéo", "Années 2020"],
      "linked_to": ["Example game"],
      "enabled": false
    }
  ]
}
```

Les cinq champs musicaux peuvent manquer ou valoir `null`. Les chaînes font au
plus 256 caractères, sans contrôles ; année entière de 1000 à 9999. Chemins POSIX
NFC, sans `..`, `:`, chemin absolu, antislash ou segment vide. Le chemin inclut
l'extension. Deux Bridges portant les mêmes chemins ont des clés différentes.

Les genres `genres`, langues `languages`, catégories `tags` et œuvres `linked_to` acceptent chacune 32 libellés
de 256 caractères, sans contrôles. Les doublons sont regroupés sans distinction
de casse. Une liste vide efface ces catégories ; un champ omis conserve sa valeur.
`enabled: false` exclut le morceau des prochaines sélections, sans supprimer le
fichier ni changer une manche déjà préparée ou les archives.

Un import accepte au plus 10 000 lignes et 1 Mio. Un document/version invalide
est refusé ; une mauvaise ligne est signalée avec son numéro et les autres passent :
inconnue, doublon, ambiguïté NFC ou valeur invalide. Le premier doublon valide
connu est retenu. Les fichiers ambigus doivent être renommés et rescannés.

Priorité **par champ** : correction manuelle non vide → import → tags titre/artiste
du morceau préparé → titre/artistes/featuring extraits du nom du fichier. Les
marqueurs `feat.`/`ft.` et les séparateurs artiste - titre sont reconnus ; les
décorations « Official Video », « Lyrics » et extensions sont retirées. Album et
année ne sont pas devinés. Ces replis alimentent bibliothèque, précontrôle,
notation automatique et révélation. Un nom ambigu peut être corrigé par l’hôte. Rétablir l’héritage d’une correction rend son repli actif ; effacer explicitement
un champ bloque aussi les tags et le repli du nom de fichier. Les données persistent dans le snapshot privé de session ;
**Fin de session** les conserve avec les archives ; les joueurs et la partie sont réinitialisés. L'export fusionne import et corrections pour les
entrées encore connues, sans exporter les pistes, tags binaires ou pochettes.

La recherche utilise nom de fichier, titre et artiste importés/corrigés, tags
et œuvres liées. Les filtres combinent ces catégories, les sources et l’activation. Le Bridge
lit les tags locaux en amont avec un nombre limité de sondages simultanés et un cache. Les joueurs reçoivent les
métadonnées des morceaux à mesure que l’hôte les dévoile au grand final.

## Préécoute privée de la bibliothèque

Le bouton **Écouter 15 s** prépare un extrait privé centré sur le milieu :
`début = (durée totale − min(15 s, durée totale)) / 2`. Un fichier plus court
est joué en entier. La préécoute ne consomme pas le morceau, ne change pas
la sélection des manches et n’envoie aucun son aux joueurs. Une seule écoute
privée peut jouer à la fois ; changer de page, fermer la bibliothèque ou lancer
une écoute collective l’arrête. Les aperçus courts peuvent lire un fichier de
moins de 8 s, même si ce fichier reste trop court pour une manche normale.

## Références techniques

[Formats FFmpeg](https://ffmpeg.org/ffmpeg-formats.html),
[sélection de pistes FFmpeg](https://ffmpeg.org/ffmpeg.html#Stream-selection),
[formats audio pour le Web](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Audio_codecs).
Décisions : [ADR 0011](adr/0011-global-review-and-private-replay.md),
[ADR 0012](adr/0012-dynamic-sources-and-metadata.md).

## Soirées à thème

[Préparer une sélection réutilisable](themed-nights.md) / [English guide](themed-nights.en.md). Les filtres genre, langue, année, tags et univers pilotent le tirage réel, en plus des dossiers. Les valeurs inconnues sont exclues lorsqu’un filtre porte sur le champ concerné.
