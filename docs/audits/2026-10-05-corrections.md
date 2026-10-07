# Corrections après audit — 5 octobre 2026

**Actualisation ultérieure :** le [rapport de durcissement](2026-10-05-security-hardening.md)
décrit les nouvelles images audio limitées, leurs scans et leur activation LAN.
Les résultats de cette page restent attachés aux candidates historiques citées.

**Les neuf constats applicatifs de l’audit initial sont corrigés et validés.** La
candidate Docker a été reconstruite, testée et activée sur le LAN après accord
explicite du mainteneur, sauvegarde privée et vérification de la session restaurée.
Aucune release publique n’a été créée. Les résultats ci-dessous
concernent le worktree `0.5.0.dev0`, protocole 8, snapshot 6, sur la base
`e4aaff76b3848dc9d747728ebefd87b7c24cea52`, avec modifications non commitées.

L’[audit initial](2026-10-05-prepublication.md) reste le relevé historique des
défauts avant correction. Ce rapport donne leur état actuel, les preuves de
validation et les limites avant une publication officielle.

## Corrections validées

| Constat | Comportement corrigé | Validation ciblée |
| --- | --- | --- |
| S02 — changement d’accès malgré une sauvegarde échouée | Préparer les nouveaux jetons/identité/code dans un état candidat, l’écrire, puis appliquer la révocation. Un échec renvoie 503 `persistence_failed` ; ancien accès et demande approuvée restent utilisables. | Échec disque/taille, ancien WebSocket maintenu, redémarrage, nouvelle tentative, cookie nouvellement émis ; voies commune et individuelle. |
| S01 — erreur 500 avec un code Unicode | Contrôler les formats ASCII avant la comparaison constante des secrets. | Code/invitation Unicode, caractères nuls, formes pleine largeur, emoji et dépassement de longueur : refus 400/401. |
| S03 — saturation des demandes d’identité | Deux demandes actives par identité, huit par IP, capacité totale liée au nombre maximal de joueurs. Chaque demande affiche une référence non secrète côté joueur et hôte. | Les doublons n’annulent pas les demandes légitimes ; autre identité encore accessible ; référence et textes FR/EN visibles. |
| S04 — lecture du code réécrivant le snapshot | Le GET d’un code existant n’écrit plus sur disque. Sa création initiale est durable ; lectures limitées à 30/joueur/minute et 1 000 au total. | Plusieurs lectures produisent zéro sauvegarde ; quota et erreur de création contrôlés. |
| S05 — quota dépassé pendant la lecture du corps | Revérifier le quota d’échecs après l’attente du corps, avant de vérifier les accès. | Quota saturé pendant l’attente : réponse 429 et aucune nouvelle identité. |
| B01 — reprise d’un MC ajoutant un participant | Conserver la participation, équipe, réponses et points ; un ancien MC reste spectateur. Les privilèges hôte nécessitent toujours le mot de passe hôte. | Matrice de quatre phases, quatre rôles/modes et deux méthodes de récupération. |
| B02 — catalogue bloquant la boucle réseau | Capturer les conteneurs nécessaires, rechercher/trier/encoder dans un thread, ne construire que la page de résultats. Un seul calcul à la fois, quotas et revérification des permissions au retour. | Recherche pendant requête de santé, refus concurrent, modification de métadonnées, changement d’identité/session, nombre de modèles construits. |
| B03 — limite fixe de 20 WebSockets par IP | Authentifier avant les quotas ; deux connexions simultanées/en attente par identité, `2*MAX_PLAYERS+4` par IP et globalement. | 32 joueurs sur une IP, remplacement d’onglet, refus des excès par identité et au total. |
| B04 — documentation incohérente | Exemple `enabled:false`, références actuelles protocole 8/snapshot 6, récupération et nouvelles limites documentées en FR/EN. | Exemple JSON validé par le modèle et exclusion effective des futurs tirages ; vérification des guides actuels. |

Implémentations principales : [accès commun](../../server/src/openblindysir_server/auth/access_routes.py),
[transactions d’accès](../../server/src/openblindysir_server/runtime.py),
[recherche](../../server/src/openblindysir_server/library/management.py),
[connexions](../../server/src/openblindysir_server/ws/player_endpoint.py).
Les 58 cas adverses sont dans
[test_prepublication_regressions.py](../../server/tests/shell/test_prepublication_regressions.py).
Trois scénarios navigateur supplémentaires vérifient les références et la reprise
d’une sauvegarde en échec en français et en anglais.

Un défaut de harnais a aussi été corrigé : le scénario d’intégration de corruption
d’upload choisissait parfois un morceau synthétique trop court avant l’injection
de faute. Il utilise maintenant un dossier de sons suffisamment longs. Les
contrôles SHA-256 du produit restent actifs et le scénario passe de façon déterministe.

## Vérifications de la candidate

| Contrôle | Résultat |
| --- | --- |
| Python, sélection complète habituelle | **1 034 réussites**, 2 skips Windows, 11 intégrations désélectionnées |
| Intégration avec serveur, Bridge et FFmpeg réels | **11 réussites** |
| Chromium, UI et quatre parties complètes | **81 réussites** |
| Vitest | **44 réussites** |
| Bridge installé dans l’image Linux finale, FFmpeg 7.1.5 | **113 réussites**, 4 skips propres à la plateforme/environnement |
| Régressions d’accès et persistance dans l’image serveur Linux finale | **60 réussites** |
| Démarrage HTTP de l’image serveur | Réussi : build web, protocole, hôte, invitation, refus d’un code malformé, code commun et recherche |
| Ruff, format, Pyright, Biome, TypeScript et build web | Réussite ; 235 fichiers Python formatés, Pyright sans erreur, 62 fichiers Biome |
| Types générés et verrou de schéma | À jour ; aucune nouvelle version de protocole requise |
| Métadonnées de release | Cohérentes ; `.dev0` et checkout dirty, publication non validée |

Les essais restent locaux : audio synthétique, sortie navigateur muette et autoplay
autorisé dans les parcours de test. Ils ne valident pas l’audio physique, Safari/iOS
ou les performances du VPS. Les tests unitaires Linux utilisent les packages
installés de la candidate, avec dépendances de test temporaires ; elles n’entrent
pas dans les images finales.

### Réactivité sur grand catalogue

Essai TestClient sur 200 000 morceaux, sans persistance, 20 requêtes de santé par
cas. Les 64 catégories représentent 32 tags et 32 liens par morceau, dans les
bornes unitaires ; cet ensemble dense peut dépasser la borne de snapshot et ne
représente pas une soirée persistée de cette taille.

| Catégories/morceau | Recherche complète | Capture sur la boucle réseau | Santé, médiane / maximum |
| --- | --- | --- | --- |
| 64 | 3 866 ms | 4,60 ms | 0,56 / 4,00 ms |
| 0 | 1 830 ms | 1,91 ms | 0,64 / 1,85 ms |

La recherche reste proportionnelle à la taille du catalogue et peut prendre
plusieurs secondes. Son calcul ne monopolise plus la boucle réseau ; le thread
cède régulièrement le GIL. Ces nombres sont une mesure locale, pas une promesse
de temps réel sur toute machine.

## Images Docker et audit CVE local

Le choix de **ne transmettre aucun inventaire à Docker Scout** est respecté.
Grype **0.120.0** a analysé localement les archives des images, dans des conteneurs
avec **réseau désactivé**, racine en lecture seule et capacités supprimées. Aucun
socket Docker, volume de session, mot de passe ou dossier musical n’est monté dans
le scanner. Seul le téléchargement préalable de la base publique d’avis a utilisé
Internet, dans un conteneur séparé sans accès aux images ni au dépôt.

Scanner fixé par digest :
`sha256:5c88961f4130e830542d441c7ed6c78baa28e799163abac53d2be4923fb5ab7d`.
Base d’avis **v6.1.10**, construite le **2026-10-05 à 06:45:38 UTC** ; SHA-256 de
l’archive : `97459838f3b53ba97e4562fb3d5d2fd92422cd44c179f59268f0c0d404c00e7a`.
Méthode : [scan d’archives Grype](https://oss.anchore.com/docs/guides/vulnerability/scan-targets/).

Les images app et Bridge passent à **Debian 13 stable**, toujours avec CPython
**3.13.16**. Les paquets système sont mis à jour au build ; le Bridge utilise
FFmpeg **7.1.5**. Caddy passe de **2.11.4 à 2.11.6**, avec digest fixé dans Compose.
La correction PCRE2 est confirmée par le
[suivi Debian CVE-2026-103111](https://security-tracker.debian.org/tracker/CVE-2026-103111).
La base est fixée par digest ; les mises à jour APT évoluent : identifier et
rescanner l’artefact effectivement construit reste obligatoire avant publication.

Le contexte Docker embarquait les descendants de répertoires réautorisés,
notamment `web/node_modules`. La liste d’inclusion a été corrigée avec exclusions
intermédiaires et exclusions finales des caches. Le build réel passe d’environ
**984 Mo à 569 Ko**, et se termine avec uniquement les fichiers nécessaires.
L’image serveur reconstruite sert le même build web validé. C’est une
correction supplémentaire à l’audit initial, sans ajout de données privées.

### Résultats bruts avant / après

Les nombres ci-dessous sont des **correspondances paquet/avis**, pas des CVE
uniques ni des exploitations démontrées. Une même CVE FFmpeg est attribuée à
plusieurs bibliothèques. Les résultats bruts sont conservés, sans suppression
d’alertes dans le scanner.

| Image | Critique | Élevée | Moyenne | Faible | Négligeable | Inconnue |
| --- | --- | --- | --- | --- | --- | --- |
| App initiale | 8 | 65 | 88 | 16 | 64 | 16 |
| App candidate | **0** | 55 | 51 | 10 | 46 | 0 |
| Bridge initial | 25 | 333 | 290 | 57 | 180 | 35 |
| Bridge candidate | **11** | 274 | 169 | 19 | 143 | 16 |
| Caddy initial | 0 | 13 | 11 | 4 | 0 | 0 |
| Caddy candidate | 0 | **1** | 4 | 0 | 0 | 0 |

### Alertes restantes et portée

- **Bridge, CVE-2026-75143** : neuf correspondances critiques renvoient à la même
  faille du lecteur réseau RIST. Debian stable ne fournit pas encore le correctif
  de cette branche. Le Bridge impose `-protocol_whitelist file` et un démuxeur
  d’une liste fermée ; `async:rist://` n’est pas un chemin offert par l’application.
  C’est une restriction du chemin d’attaque, **pas une correction du binaire**.
  [Suivi Debian](https://security-tracker.debian.org/tracker/CVE-2026-75143).
- **Bridge, libtiff/libxml2** : les deux autres correspondances critiques visent
  `tiffcrop` et un parseur XML. Le produit n’invoque pas `tiffcrop` ; les sources
  audio sont soumises au confinement et à la liste fermée des formats. Cette
  lecture limite les chemins apparents, sans constituer une analyse exhaustive
  des appels des bibliothèques natives. Les alertes restent à traiter avant une
  publication publique. [libtiff](https://security-tracker.debian.org/tracker/CVE-2026-52490),
  [libxml2](https://security-tracker.debian.org/tracker/CVE-2026-6653).
- **Python, CVE-2026-12345** : le scanner signale 3.13.16, mais le
  [registre de la PSF](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/12xxx/CVE-2026-12345.json)
  mis à jour le 3 octobre classe comme affectées les versions antérieures à
  3.12.15 et certaines préversions 3.15. L’interprétation actuelle est un mauvais
  rapprochement de version pour cette image. Le JSON brut est conservé ; aucune
  migration vers une préversion Python n’est appliquée pour satisfaire le scanner.
- **Python, CVE-2025-15367** : avis sur `poplib`, que serveur et Bridge n’utilisent
  pas. Le défaut de bibliothèque demeure ; aucun chemin POP3 n’est fourni par
  le produit. [Avis PSF dans le registre CVE](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2025/15xxx/CVE-2025-15367.json).
- **Caddy** : aucun avis sur les composants Go n’est retourné pour la nouvelle
  image. Restent une correspondance élevée zlib et quatre moyennes sur nghttp2
  / BusyBox. Le proxy principal est Go ; le healthcheck BusyBox utilise une URL
  locale constante. Ces observations ne remplacent pas une analyse des chemins
  natifs et ne permettent pas d’annoncer « zéro vulnérabilité ».
- **Autres avis Debian** : nombreuses correspondances élevées/moyennes marquées
  sans correctif ou sans correction prévue dans la base du scanner. Leur
  applicabilité doit être rapprochée des avis Debian et des fonctions réellement
  utilisées. Aucun risque résiduel n’est fermé uniquement parce que le conteneur
  est non-root ou parce que les tests passent.

La migration corrige notamment les versions glibc/SQLite anciennes qui restaient
signalées dans Bookworm :
[glibc](https://security-tracker.debian.org/tracker/CVE-2026-5450),
[SQLite](https://security-tracker.debian.org/tracker/CVE-2025-7458).
Les 70 versions PyPI et 132 dépendances npm déjà contrôlées le même jour ne sont
pas modifiées par ces corrections ; aucun avis n’avait été retourné par OSV/npm.

## Activation et conditions avant publication

**LAN : corrections actives et vérifiées.** Le contrôle automatique avait d’abord
refusé l’arrêt/remplacement des services ; le mainteneur l’a ensuite explicitement
autorisé après explication des risques. La phase `FINAL_RESULTS` a été confirmée
avant le changement. Une sauvegarde privée cohérente de l’app, du Bridge et des
données/configuration Caddy a été effectuée avant activation ; les anciennes
images et un override de retour arrière sont conservés.

Le contrôle HTTPS valide les mêmes JS/CSS que le build testé, l’app et Caddy
sains, le Bridge en ligne, protocole 8 et snapshot 6 restauré sans échec de
persistance. Comparaison avec la sauvegarde : **3 joueurs, 7 archives et 24
morceaux** conservés, ainsi que cookies, identités/rôles/équipes, journal et
scores, réponses, réglages, catalogues, métadonnées, configuration Bridge et
montages. Le code commun et le jeton QR chiffrés ont aussi été comparés localement
et sont conservés ; les secrets de l’instance restent inchangés. Aucune valeur
d’accès privée n’a été imprimée. Caddy actif annonce **2.11.6**, avec le digest
examiné par le scan.

Avant le tag public :

1. Traiter les alertes système résiduelles : version corrigée ou analyse
   d’applicabilité sourcée et acceptation explicite des risques maintenus.
2. Figer une révision propre et relancer les checks/revue sur les artefacts exacts
   de release ; les hashes de cette candidate ne valent pas pour une image future.
3. Terminer les recettes physiques Safari/iOS/Android et petits PC, le contrôle
   du final avec plusieurs joueurs, la mesure acoustique G1 et la mesure VPS G2.
4. Valider la matrice de distribution native et les préparatifs de publication
   décrits dans [releasing.md](../releasing.md).

## Preuves locales

Les preuves ignorées par Git restent dans `.local` :

- `postfix-library-perf-20261005.json` : mesures du grand catalogue.
- `postfix-chromium-20261005.log` : suite complète de 81 scénarios.
- `audit-trixie-linux-tests.log` et `audit-trixie-linux-app-tests.log` : tests des packages installés.
- `audit-trixie-app-build.log` / `audit-trixie-bridge-build.log` : builds et digests.
- `security-scan/output/*-before.json`, `app-trixie-verified.json`,
  `bridge-trixie-verified.json`, `caddy-after-verified.json` : scans bruts.
- `security-scan/summary.json` : correspondances avant/après et identifiants des images.
- `audit-lan-activation-20261005.json` : état synthétique de l’activation et
  conservation de la session ; sauvegarde privée distincte dans `.local/docker`.
- `postfix-worktree-20261005.json` : SHA-256 des **341 fichiers** courants suivis et
  nouveaux non ignorés, contrôlés sans signal d’hygiène ; `postfix-summary-20261005.json`
  : synthèse structurée des résultats. Les lockfiles restent identiques à ceux
  du contrôle OSV/npm du même jour.

Les digests ci-dessous identifient les images de la candidate d’audit testée et scannée :

| Image | Digest de la candidate |
| --- | --- |
| App, index OCI | `sha256:8b7ed57c34998cfd8501aa79769c4f2b1d04448781bbd47d15b96d8e46e8de90` |
| Bridge, index OCI | `sha256:8ae2dde15b20d07d4a66273eb64ce4b308e8fb8535dc491ada81666416b3002b` |
| Caddy officiel | `sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9` |

Une suppression des fichiers temporaires de scan ne doit pas effacer ces résultats
JSON ou les sauvegardes privées. Les inventaires bruts restent locaux selon le
choix du mainteneur.

## Actualisation ultérieure : interface FR/EN

Le switch permanent et le changement de langue sans rechargement sont ensuite
activés sur le LAN. L’app utilise désormais l’index OCI
`sha256:d114a0033598823b1c52e9709d3ae1510b02edced0ad31c9cafc28be1d0bcfe2`.
Les images Bridge/Caddy, les bases runtime et les lockfiles restent identiques.
La nouvelle interface est validée par 47 Vitest, 85 tests UI Chromium, les quatre
scénarios de partie complète et une comparaison des assets réellement servis.
La session et ses accès sont comparés à une nouvelle sauvegarde privée ; preuve
locale dans `language-validation-20261005.json`. Détails dans le [DEVLOG](../DEVLOG.md).

Cette image app n’a pas reçu un nouveau scan Grype ; les résultats détaillés de
ce rapport restent attachés aux digests de la candidate d’audit ci-dessus. Les
alertes résiduelles et la validation des artefacts exacts avant release restent
à traiter. Aucune publication officielle n’est annoncée.
