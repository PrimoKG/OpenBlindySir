# ADR 0013 — Distribution native et Python du Bridge

- Statut : Accepté
- Date : 2026-10-03
- Étend ADR 0002 ; ne change pas sa frontière de confiance ni les licences FFmpeg.

## Décision

Le CLI `openblindysir-bridge` est l'unique entrée du wheel, uvx et PyInstaller
onedir. CPython 3.12–3.14 est la matrice Python. VERSION est copié dans un module
de version local à chaque paquet : sdists et wheels ne lisent jamais hors du
paquet. Le Bridge dépend exactement de sa version du protocole ; aucun code
serveur n'est embarqué. FFmpeg est séparé des paquets/archives et vérifié avant
travail. AAC est obligatoire, Opus facultatif.

Les archives natives sont construites sur leurs OS : Windows x64, Linux x64
glibc ≥2.35, macOS 15 Intel/arm64. Pas de cross compilation ou de onefile.
Chaque archive garde Python, _internal, instructions, licences/notices, version,
commit et manifest de hashes. Les archives sont non signées/non notariées ;
aucune désactivation des protections système n'est recommandée.

Configuration durable indépendante du cache/dossier d'installation : écriture
atomique privée (Unix 600 / ACL Windows), confirmation et sauvegarde lors de
l'assistant, UUID stable. Aide/version/check-config ne créent rien. Doctor local
n'effectue pas de scan. Un test réseau explicite annonce scan/enregistrement,
remplace la connexion du même UUID puis la ferme ; aucun extrait ni source
complète n'est transféré. Rapports copiables par liste blanche sans secrets/paths.

CI de validation et publication distinctes. La publication ne vient que d'un tag
vX.Y.Z ou vX.Y.Z-rc.N correspondant à VERSION/commit/changelog. Elle reprend les
artefacts validés du même run, exige les quatre targets et vérifie leurs hashes.
PyPI utilise OIDC dans un environnement protégé ; noms des deux projets et
Trusted Publishers doivent être configurés par le mainteneur avant release.
Les tools et dépendances de build sont verrouillés ; ZIP ordonné et timestamps
normalisés au commit. Cette reproductibilité de procédure ne promet pas des
binaires identiques octet pour octet entre compilateurs/patches/runners.

## Conséquences

Un poste sans Python peut utiliser l'archive ; il reste responsable de FFmpeg.
Les runners doivent valider les plateformes, et les alertes SmartScreen/Gatekeeper
et tests matériels restent distincts du smoke CLI. Un correctif reçoit une
nouvelle version ; aucun remplacement silencieux d'un fichier déjà publié.
