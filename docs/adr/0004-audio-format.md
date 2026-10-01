# 0004 — Format des extraits audio
Statut : Proposé   ·   Date : 2026-10-01

## Contexte
Chaque round d'OpenBlindySir joue un extrait de 20 à 30 s produit par le Bridge avec FFmpeg ([0002](0002-bridge-outbound-connection-and-sandbox.md)), stocké en RAM sur le VPS (2 Mo au plus, [0005](0005-no-database-v01.md)), **téléchargé en entier** par chaque navigateur, décodé par `decodeAudioData` en `AudioBuffer`, puis planifié avec Web Audio à l'instant `start_at` (`docs/architecture.md` §9, §10).

Exigences :
- **décodable par `decodeAudioData` sur toutes les cibles** : Chrome, Firefox, Safari macOS, iOS Safari (donc tous les navigateurs iOS), Chrome Android ;
- départ précis : le délai d'encodeur doit être traité de façon homogène par les décodeurs ;
- extrait sans tags ni pochette (anti-spoiler) ;
- encodeur présent dans les builds FFmpeg courants, puisque FFmpeg n'est pas embarqué dans le Bridge ;
- taille raisonnable : jusqu'à 15 joueurs téléchargent chaque extrait (§22).

Le support d'Opus via Web Audio sur Safari et iOS dépend des versions : il doit être **mesuré sur de vrais appareils**, pas affirmé. C'est un risque HIGH (§27).

## Options considérées
**A. AAC-LC 128 kbps, 48 kHz stéréo, conteneur MP4 (.m4a) faststart.**
- Pour : se décode partout via `decodeAudioData`, y compris sur des iOS anciens ; encodeur `aac` natif présent dans tous les builds FFmpeg ; en-tête reconnaissable (`ftyp`).
- Contre : débit plus élevé qu'Opus pour une qualité comparable (environ 480 Ko pour 30 s).

**B. Opus 96 kbps en WebM.**
- Pour : meilleure qualité par octet (environ 360 Ko pour 30 s).
- Contre : support Safari et iOS dépendant des versions ; `libopus` absent de certains builds FFmpeg.

**C. Opus en Ogg.**
- Pour : conteneur simple (`OggS`).
- Contre : support Safari historiquement absent ou récent. Mesuré au spike pour comparaison.

**D. MP3.**
- Contre : moins efficace par octet ; délai d'encodeur et padding traités de façon hétérogène selon les décodeurs, donc départ moins précis.

## Décision
**Format par défaut, provisoire : AAC-LC 128 kbps, 48 kHz stéréo, conteneur MP4 (.m4a) avec `-movflags +faststart`.**
- **Opus/WebM 96 kbps** (`libopus 96k`) reste candidat.
- **MP3 est écarté.**
- **Un seul format à la fois**, réglé par la configuration serveur (`CLIP_FORMAT=aac`, `CLIP_BITRATE=128`) et transmis au Bridge dans `WELCOME`. Le Bridge choisit l'encodeur dans une liste fixe et plafonne le débit à ses propres maxima.
- Quel que soit le format : première piste audio seulement, **aucune métadonnée ni pochette** (`-map_metadata -1 -map_chapters -1`, `-vn -sn -dn`), fondu d'entrée et de sortie.

**Le choix final est reporté aux mesures du spike S0 (porte G1, §26).** Le spike teste `decodeAudioData` sur AAC/M4A, Opus/WebM et Opus/Ogg sur **un vrai iPhone**, Android, Safari, Firefox et Chrome, ainsi que le déverrouillage audio, le bouton silencieux et `getOutputTimestamp`, avec une mesure acoustique de la synchronisation (G1 exige aussi p90 ≤ 60 ms sur 3 appareils hétérogènes).

Critères proposés pour trancher :
1. éliminatoire : décodage réussi sur toute la matrice cible, iPhone réel compris ;
2. encodeur disponible dans les builds FFmpeg courants (winget, brew, apt) ;
3. à compatibilité égale, le format le plus léger.

**Cette ADR reste « Proposé » jusqu'au spike S0. Son statut ne passe à « Accepté » qu'après la porte G1** : on y ajoute alors les mesures (appareils, versions des navigateurs, résultat par format), puis on confirme ou on réécrit la Décision avant de changer le statut et la date.

## Conséquences
- Le format est une valeur de configuration : le gabarit FFmpeg du Bridge, la validation des uploads côté serveur et le décodage côté web peuvent s'écrire avant G1 sans dépendre du résultat.
- Le serveur reconnaît les magic bytes des formats candidats (`ftyp`, `OggS`, en-tête EBML) et sert le type MIME correspondant.
- Tailles indicatives (§22) : 20 s ≈ 320 Ko et 30 s ≈ 480 Ko à 128 kbps ; 240 et 360 Ko à 96 kbps. Le cache RAM de 32 Mo et la limite de 2 Mo par extrait couvrent les deux formats.
- Côté client, un `AudioBuffer` décodé occupe environ 11,5 Mo pour 30 s, quel que soit le format d'origine.
- Une soirée consomme moins de 0,1 % d'un quota de trafic typique (§22) : le gain de bande passante d'Opus est secondaire, la compatibilité mesurée prime.
- Le Bridge vérifie au démarrage les encodeurs disponibles (`aac` est toujours présent, `libopus` manque dans certains builds) et signale clairement l'absence de celui qui est demandé.
- Les tests golden de la commande FFmpeg (§20.1, point 10) couvrent la variante AAC et, tant qu'elle reste candidate, la variante Opus.
- Si S0 retient Opus, la Décision est réécrite avant l'acceptation. Une fois l'ADR acceptée, tout changement de format passe par une nouvelle ADR qui la remplace.
