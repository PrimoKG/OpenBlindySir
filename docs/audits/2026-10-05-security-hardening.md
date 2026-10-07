# Durcissement de sécurité avant publication — 5 octobre 2026

**Les nouvelles images sont testées, scannées localement et actives sur le LAN.**
Actualisation ultérieure : la correction d'interface décrite dans le
[DEVLOG](../DEVLOG.md#2026-10-05--liste-des-joueurs-et-reprise-audio-du-final)
remplace les fichiers web du serveur sur ce même runtime. La nouvelle image app
`sha256:79c8f715ec196a2a9f7548a9e2a38988b176f7109fa92de332425cce879d3657`
est rescannée hors réseau avec la même base : résultats bruts identiques.
Bridge et Caddy conservent les identités ci-dessous. Les scans initiaux restent
des preuves historiques distinctes de cette activation.

Les trois images ne retournent plus de correspondance critique dans Grype. Les
avis système restants ont une [matrice d’applicabilité](2026-10-05-security-applicability.md)
et un [relevé structuré](2026-10-05-security-assessment.json). Aucun inventaire
n’a été envoyé à Docker Scout et aucune release publique n’a été créée.

Ce rapport actualise le [rapport précédent](2026-10-05-corrections.md), dont les
scans et images restent des preuves historiques. Le dépôt est toujours en
`0.5.0.dev0`, protocole 8, snapshot 6, sur la base Git `e4aaff7` avec modifications
locales non commitées. Les constats ci-dessous ne valident pas une future image.

## Corrections effectuées

| Point | Correction | Preuve |
| --- | --- | --- |
| FFmpeg Debian complet embarquant réseau, vidéo, images et XML | FFmpeg **9.0.2** officiel compilé avec les démultiplexeurs locaux autorisés, les décodeurs audio et les filtres utilisés ; aucun protocole autre que `file`, aucun décodeur vidéo/sous-titre, pas d’iconv. | Contrôle obligatoire au build sous UID 10001 ; capacités, dépendances et imports ELF inspectés. |
| RIST, libtiff et libxml2 critiques dans le Bridge | Nouvelle version FFmpeg ; RIST exclu du build, libtiff/libxml2 et leurs dépendances inutilisées retirés de l’image finale. | Scan brut : **11 → 0** correspondances critiques ; dépendances FFmpeg limitées à libc, libm et libopus. |
| Anciennes versions FFmpeg encore acceptées en natif | Minimum **9.0.2**, vérifié séparément pour FFmpeg et ffprobe avec précision du patch. Versions non identifiables et couples mixant une ancienne version refusés. | Tests des seuils, versions mixtes, builds non identifiables et versions suivantes. Guides FR/EN et prérequis mis à jour. |
| CI Linux installant un FFmpeg trop ancien via APT | Recette de compilation FFmpeg 9.0.2 pour les fixtures et vérifications natives, source fixée par SHA-256. Workflows application, nightly et distribution adaptés. | Recette complète exécutée avec succès dans Ubuntu 22.04 ; actionlint et YAML valides. Les jobs GitHub de cette révision restent à exécuter après push. |
| Authenticité et distribution des sources | Archive, signature et clé fixées par SHA-256 ; empreinte de la clé officielle contrôlée et signature vérifiée avant compilation. Sources exactes, licence LGPL, recette et configuration incluses dans l’image. | `gpgv` : signature valide ; contrôle du hash de la source dans l’image sous l’utilisateur du Bridge. |
| Crash du résolveur glibc avec un domaine de recherche trop long | `LOCALDOMAIN=.` dans les images app/Bridge ; URLs de déploiement utilisant IP ou nom pleinement qualifié. | Domaine DNS valide de 218 caractères fourni au conteneur hors réseau : pas d’abort dans les deux images. **C’est une atténuation de configuration, pas une correction de glibc.** |
| FFmpeg compilé absent de l’inventaire automatique | Scan CycloneDX supplémentaire pour FFmpeg 9.0.2 ; sa version et le hash des sources sont rapprochés du binaire/de l’archive de l’image immuable. | Zéro correspondance dans le supplément ; tests refusant une version, source ou déclaration ambiguë. |
| Preuves de scan pouvant viser un tag modifié | [Outil local](../../tools/scan_runtime_images.py) sauvegardant l’image par identité immuable et rapprochant le résultat Grype du hash réel de sa configuration. | Trois scans vérifiés ; refus des archives contenant plusieurs images ou aucune image. |

La génération synthétique du mode démo reste disponible via `lavfi` limité aux
sources audio. Aucun périphérique de capture réseau/vidéo n’est ajouté. AAC/M4A
et Opus/WebM, préécoute au milieu, normalisation, fondus et extraction de l’audio
des conteneurs vidéo restent fonctionnels. Les formats sont conservés ; des codecs
audio rares absents de cette sélection peuvent être refusés proprement.

Sources primaires : [FFmpeg officiel et clé de signature](https://ffmpeg.org/download.html),
[avis RIST et version corrigée](https://security-tracker.debian.org/tracker/CVE-2026-75143),
[libtiff](https://security-tracker.debian.org/tracker/CVE-2026-52490),
[libxml2](https://security-tracker.debian.org/tracker/CVE-2026-6653),
[résolveur glibc](https://security-tracker.debian.org/tracker/CVE-2026-8674).

## Résultats bruts des images finales

Grype **0.120.0**, digest
`sha256:5c88961f4130e830542d441c7ed6c78baa28e799163abac53d2be4923fb5ab7d`,
base publique **v6.1.10**, construite le **2026-10-05 à 06:45:38 UTC**.
Le scanner tourne sans réseau, sans socket Docker et sans volumes de session,
de configuration ou de musique. Les résultats ne filtrent aucune CVE.

| Image | Critique | Élevée | Moyenne | Faible | Négligeable | Inconnue |
| --- | --- | --- | --- | --- | --- | --- |
| App finale | **0** | 55 | 51 | 10 | 46 | 0 |
| Bridge, avant ce chantier | 11 | 274 | 169 | 19 | 143 | 16 |
| Bridge final | **0** | 55 | 51 | 10 | 46 | 0 |
| Caddy, inchangé | **0** | 1 | 4 | 0 | 0 | 0 |
| Supplément FFmpeg compilé | **0** | 0 | 0 | 0 | 0 | 0 |

Ce sont des correspondances paquet/avis, pas des vulnérabilités uniques ni des
exploitations démontrées. Les images finales partagent **72 avis uniques**, dont
**14 élevés**. Les élevés et moyens sont examinés individuellement dans la
matrice. Exemples : fonctions d’impression DNS et monnaie non importées,
opérations libstdc++ sans dépendance C++ chargée, outils Perl/montage/PAM non
utilisés ; proxy nghttpx absent et Caddy statique. La justification de chaque
avis est conservée, sans modifier la sortie du scanner.

Une collecte ciblée des avis a été refusée par le contrôle automatique, car elle
aurait envoyé les CVE dérivées des images. La solution retenue télécharge la
**base publique Debian complète depuis une URL fixe**, puis sélectionne les avis
localement. Aucun inventaire ni liste ciblée n’a été transmis.

## Artefacts exacts et validation

| Image | Identité OCI de l’image testée, scannée et activée |
| --- | --- |
| App | `sha256:5f85500230c8e6a064706e43f6b00950e23d82149c26918e68e0e54201441c2d` |
| Bridge | `sha256:dea4f464907e21074a3a94f9fe76e85a3bdb29351181a269bb158a572b9f69be` |
| Caddy | `sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9` |

| Contrôle réellement exécuté | Résultat |
| --- | --- |
| Bridge installé Linux final, fixtures synthétiques séparées | **143 réussites**, 4 skips de plateforme/environnement |
| Accès, quotas, credentials et persistance dans l’image serveur Linux finale | **126 réussites** |
| Régressions de sécurité applicative sur Windows | **124 réussites** |
| Seuils de versions et intégrité des preuves de scan | **35 réussites** |
| Formats audio | **16 combinaisons** testées : MP3, FLAC, WAV PCM/ADPCM, AIFF, Ogg/Vorbis, Opus, AAC, M4A AAC/ALAC, WMA, MP4, MOV, MKV, WebM et AVI ; sortie AAC audio seule et sortie Opus validées |
| Mode démo dans l'image finale isolée | **12 sons synthétiques** générés avec le FFmpeg audio de production, sans réseau ni volume privé |
| Recette CI FFmpeg complète | Build FFmpeg/ffprobe 9.0.2 réussi dans Ubuntu 22.04 |
| Ruff / format / Pyright / actionlint | Vérifications réussies ; Pyright utilise explicitement l’interpréteur du venv |
| Hygiène et documentation | 350 fichiers actuels suivis/non ignorés contrôlés sans constat ; lockfiles identiques à l'audit de dépendances du jour ; 124 liens locaux valides dans 13 documents |
| HTTPS LAN et conservation de la session | Réussite : assets FR/EN inchangés, services sains, Bridge en ligne et état conservé |

L’outil FFmpeg complet des fixtures est séparé des binaires et bibliothèques de
production ; les extractions des tests utilisent la candidate audio. Les
dépendances de test sont installées dans des images temporaires distinctes,
jamais dans les images finales. Les warnings de pytest concernent le harnais
Linux isolé sans configuration racine et une dépréciation TestClient.

## Activation LAN et preuves locales

Le lobby a été vérifié avant remplacement, puis à nouveau sur la sauvegarde
froide. Sauvegarde privée de l’app, du Bridge, des données/configuration Caddy et
des fichiers de lancement ; images précédentes et override de retour arrière
conservés. Les trois services partageant le réseau sont recréés ensemble.

Comparaison après activation : **3 joueurs, 7 archives, 24 morceaux**, identités,
rôles, équipes, cookies, réglages, réponses, scores, catalogues, métadonnées,
montages, code commun et invitation QR conservés. TLS est vérifié avec la même
autorité locale. Aucune valeur d’accès ni réponse privée n’est affichée.

Preuves ignorées par Git :

- `.local/security-release-20261005-bound/summary.json` et `output/*.json` : scans bruts, identités immuables, configuration réelle et supplément lié à l’image.
- `.local/security-scan/runtime-facts.json`, `native-facts.json`, `resolver-hardening.json` et `advisories/*` : versions, capacités, imports et sources primaires.
- `.local/security-audio-build-release.log`, `security-ci-ffmpeg-recipe.log`, `security-audio-linux-tests-release.log`, `security-release-linux-server-tests.log`, `security-audio-application-tests.log` : builds et tests.
- `.local/security-lan-activation-20261005.json` : activation et vérification de conservation ; sauvegarde privée distincte référencée localement.
- `.local/security-release-demo.log` : génération des douze sons de démonstration dans l'image finale.
- `.local/security-worktree-20261005.json` : empreintes du contenu actuel destiné au dépôt et contrôle d'hygiène, incluant les nouveaux fichiers.

## Conditions restantes avant publication

Les alertes natives de la base système ne sont pas toutes corrigées dans leurs
binaires. Une qualification « fonction hors parcours » n’est pas une acceptation
implicite du risque résiduel. Avant une release officielle, le mainteneur doit
examiner cette matrice et décider explicitement des risques conservés ; les
faibles/négligeables restent suivies et ne sont pas toutes clôturées ici.

Cette analyse concerne ces images Docker et leur configuration. Les installations
natives restent dépendantes de leur OS, Python, fournisseur FFmpeg et mises à
jour. Le nouveau minimum FFmpeg protège contre l’usage des anciennes versions
identifiées, sans promettre qu’une version future n’aura aucune vulnérabilité.

Les autres critères de [publication](../releasing.md) restent requis : révision
propre et poussée, CI complète sur cette révision, scans des artefacts exacts de
release, matrice native et recettes physiques/audio/VPS. Aucun tag, push ou
publication n’a été effectué pendant ce chantier.
