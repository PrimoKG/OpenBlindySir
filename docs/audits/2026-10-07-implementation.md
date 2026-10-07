# Livraison du plan et vérification — 7 octobre 2026

Le plan en huit lots est implémenté et l’installation LAN a été relancée. Les sept bugs A01–A07 de l’audit complémentaire sont corrigés avec des régressions. Les constats de la vidéo ont été repris dans les changements de notation, de final et de bibliothèque. Ce rapport distingue les vérifications réussies des réserves de publication. [English report](2026-10-07-implementation.en.md).

## Changements livrés

| Lot | Résultat |
| --- | --- |
| 1. Notation cohérente | Un brouillon régi par « l’hôte décide » reste en attente, même s’il est reconnu ; les preuves sont conservées. Les listes de propositions numériques inconnues deviennent ambiguës. Un champ unique reconnaît les critères configurés, avec seuil par critère et année exacte. La référence figée utilisée par la notation est celle affichée à l’hôte ; une modification ultérieure est signalée et la réévaluation reste explicite. Les corrections manuelles sont préservées. |
| 2. Audio et connexions | Téléchargements et temporisations obsolètes annulés, résultats tardifs ignorés, erreurs de préchargement séparées de la lecture. Une seule connexion en cours ; fermeture pendant HTTP et événements d’une ancienne socket ne recréent pas une connexion. Sortir du jeu libère audio, requêtes, abonnements et écouteurs. Un contexte définitivement fermé est recréé sur un geste utilisateur. Les tests audio restent accessibles pendant le final. |
| 3. Final desktop et défilement | Selon la largeur, contexte musical à gauche, notation au centre et classement à droite. Contrôles plus compacts avec cibles de 44 px. Chaque navigateur mesure ses listes ; le dernier joueur visible noté fait avancer le lot. La pause manuelle reste distincte de la préférence d’auto-défilement. Classement limité à cinq lignes visibles, sans bande minuscule à faible effectif : sa hauteur exclut les transformations des animations et tient compte des arrondis WebKit. |
| 4. États et validation | Préparation privée distincte de la manche présentée publiquement. La confirmation du podium propose d’abord de terminer les attributions en attente ; publier les scores actuels reste un choix explicite. L’activité est remise à zéro au changement de manche. Un final sans attribution ne prétend pas désigner un gagnant. Les invitations sont nettoyées après les différentes connexions réussies. |
| 5. Animation partagée | Parcours guidé révéler → écouter → attribuer → classement → manche suivante. Rythme rapide facultatif, critères reconnus, gains et corrections visibles, variations du classement et ex æquo. Son et animations réglables localement, réduction des animations système respectée. Annulation de la dernière correction déjà confirmée avec contrôle de révision ; elle restaure les valeurs de points et critères, sans effacer l’historique. |
| 6. Bibliothèque | Morceaux au premier plan, gestion des sources dans les outils avancés. Filtres de qualité et des sources sélectionnées pour préparer les corrections. Éditeur sous le morceau, pagination adaptative, tags, œuvres liées, désactivation et préécoute privée centrée de 15 s. Hériter d’une référence et l’effacer sont distincts. Conflit d’édition signalé sans perdre le brouillon. Exports JSON bornés à 1 Mio et packs ZIP réimportables bornés à 8 Mio/10 000 lignes, avec suites explicites pour les grosses bibliothèques. Import ZIP sans extraction, tailles décompressées bornées et seuls stockage/Deflate acceptés. |
| 7. Sécurité et installation | Proxy Caddy reconstruit avec zlib 1.3.2-r1. Scan local des trois images exactes, de FFmpeg compilé et des dépendances npm verrouillées, sans transmission d’inventaire. Pack précompilé Linux/amd64, manifeste d’identités et SHA-256, chargement vérifié, assistant Windows, sauvegarde privée, mise à jour et retour arrière explicite. Approbation de la CA LAN guidée ; aucune installation silencieuse. Compatibilité PowerShell 5.1/7 des empreintes et encodage FR corrigés. |
| 8. Vérifications et documentation | Suites moteur, HTTP, sockets, audio, navigateur et intégration ; dictionnaires FR/EN et guides actualisés. Migration protocole 10/snapshot 8 contrôlée sur la session locale. Aucune release publique ni installateur natif signé créé par cette passe. |

## Vérifications exécutées

- **1 138 tests Python réussis**, deux exclusions Windows : permissions POSIX et création de lien symbolique. **11 intégrations réussies** séparément, dont partie réelle avec dix bots, reconnexion, pertes de Bridge, fichier supprimé après scan et arrêt en cours de manche.
- **52 tests Web réussis**. TypeScript, build, Biome, Ruff, format Ruff, Pyright avec l’interpréteur du projet et contrôle des types/protocole générés réussis.
- Suite complète **100 parcours Chromium réussis**. Après les derniers ajustements, les parcours de partie réelle, QR/cookie/transfert, bibliothèque, préécoute et reconnaissance ont été relancés ; les cas affectés de classement ont ensuite été vérifiés sur le build final.
- Dernière sélection commune : **16 parcours réussis** (9 Chromium, 7 WebKit), **2 tests audio WebKit ignorés** parce que ce runtime Windows n’expose pas `AudioContext`. Le parcours bibliothèque WebKit vérifie la pagination, l’édition et le message d’échec/réessai des médias ; sa lecture est vérifiée dans Chromium. Aucune validation acoustique ou sur iPhone physique n’est revendiquée.
- Vérifications adaptatives : petits téléphones, PC de faible hauteur, grandes listes, FR/EN, clavier et zoom ; focus et réponses conservés pendant les mises à jour. Régression dédiée aux classements de trois personnes durant une permutation animée.
- Pack réellement généré et rechargé avec contrôle des empreintes puis des identités Docker. Scripts PowerShell analysés, lanceur exécuté, sauvegarde de l’assistant réellement effectuée avec ACL privée. Le calcul SHA-256 utilise .NET et ne dépend pas de l’auto-chargement de `Get-FileHash` dans les sous-processus.

Les premières exécutions ont détecté les défauts corrigés suivants : libellés de tests devenus obsolètes, noms accessibles d’éditeurs, taille des cibles, duplication du titre Résultats, référence attendue des fixtures, hauteur mesurée pendant une animation et débordement fractionnaire WebKit. Les erreurs de test Web Audio sur WebKit Windows ont été identifiées dans les traces comme une absence de constructeur, puis déclarées explicitement comme limitation de ce runtime.

Les premiers jobs GitHub macOS ont ensuite détecté une version FFmpeg préinstallée trop ancienne et un encodeur Vorbis absent de la formule standard. La préparation CI Apple Silicon/Intel compile désormais la même source FFmpeg 9.0.2 vérifiée que Linux, avec les encodeurs des fixtures et une vérification SHA-256 portable. Le minimum de sécurité et les tests concernés sont conservés. La matrice distante couvre les deux architectures macOS avec Python 3.12–3.14, ainsi que leurs archives natives ; elle ne remplace pas les essais physiques.

**Quatre régressions supplémentaires du chargeur de pack réussies** : coexistence avec `sha256sum` BSD, archive altérée, ligne d’empreinte malformée et identité d’image inattendue. Un fichier altéré ou un manifeste malformé bloque avant toute commande Docker ; une image inattendue ne devient pas l’alias de configuration. `shasum` est préféré avec vérification stricte. Le générateur écrit les listes d’images et d’empreintes en LF, y compris depuis Windows, pour leur lecture sur Linux/macOS.

## Relance et conservation

Serveur, Bridge et proxy fonctionnent avec les images exactes scannées et le build Web final. HTTPS a été vérifié avec l’autorité locale existante ; HTML, JS et CSS servis sont identiques au build vérifié. Accès anonyme aux outils d’hôte refusé. Montages, configuration, secrets, identités, cookies, accès partagé, réponses, journal de scores, métadonnées et **12 archives** conservés. Snapshot **7 → 8** vérifié ; les horloges monotones sont recalées, les archives reçoivent le nouveau champ facultatif vide `cleared_fields`.

Le rescannage du Bridge a fait passer le catalogue de 69 à **68 fichiers** : une ancienne entrée n’a plus de fichier physique dans les montages conservés, même après comparaison des noms normalisés Unicode. Aucun fichier musical n’a été modifié ; les métadonnées persistées et résultats historiques sont conservés.

Les sauvegardes, traces et preuves privées restent dans `.local`, exclues du dépôt. Les serveurs temporaires créés pour les tests ont été arrêtés ; le serveur de développement préexistant a été conservé. Le retour à l’image précédente de protocole 9 exige la sauvegarde de snapshot 7 : ne pas lui donner directement un snapshot 8.

## Scan de sécurité local

Scanner Grype fixé par digest, base **v6.1.10 construite le 7 octobre à 06:31:48 UTC**. Les scans s’exécutent avec `--network none` ; seul le téléchargement préalable de la base d’avis utilise le réseau. Les inventaires, musiques, volumes et secrets n’ont pas été transmis à Docker Scout ni à un autre service de scan.

| Image | Critiques | Élevées | Moyennes | Faibles | Négligeables |
| --- | ---: | ---: | ---: | ---: | ---: |
| Serveur | 0 | 55 | 50 | 10 | 46 |
| Bridge | 0 | 55 | 50 | 10 | 46 |
| Proxy Caddy | 0 | 8 | 14 | 8 | 0 |

Il s’agit de **correspondances paquet/avis**, pas d’un nombre de chemins d’exploitation démontrés. Serveur et Bridge partagent une base et beaucoup de correspondances. Le correctif zlib retire l’alerte élevée `CVE-2026-85091` présente auparavant dans le proxy ; aucune correspondance zlib ne subsiste dans son scan final. Le supplément FFmpeg 9.0.2, lié à l’image et au hash des sources embarquées, n’a aucune correspondance dans cette base.

Le scan local du verrou npm compte **32 composants de production** et **100 composants de développement**, sans correspondance d’avis dans cette base. Il n’utilise pas `npm audit` connecté. Ce résultat et celui de FFmpeg ne prouvent pas l’absence de vulnérabilité inconnue.

Les correspondances élevées restantes n’annoncent pas de version corrigée compatible dans cette base. Deux avis Python moyens annoncent une correction dans une autre branche : `CVE-2025-15367` (3.15.0a6) et `CVE-2026-12345` (3.15.0). La production utilise Python **3.13.16** ; les versions annoncées ne sont pas un correctif applicable directement à cette branche et le projet borne Python à `<3.15`. Ces avis restent ouverts ; ils ne sont pas classés arbitrairement comme faux positifs. L’import de métadonnées refuse Bzip2/LZMA pour réduire les surfaces de décompression. La [release officielle Python 3.13.16](https://www.python.org/downloads/release/python-31316/) documente la version utilisée ; le scan local fait foi pour les correspondances relevées ici.

Identités des images livrées :

```text
server sha256:7661635985ecd6ef39c14a36d63a54feec43691558502ec186cf048e6109e09f
bridge sha256:335ddad9e59a689ecbcc4709f2e624d4e17c364753cbcfe9e5a48b247ce509f2
caddy  sha256:b2877ff4fb23df45e83eb48e5dad0756b72b74468222f4cea6a1afc412506193
```

## Réserves avant publication officielle

Pas de nouveau contournement de rôle démontré dans les contrôles réalisés ; pas de pentest exhaustif. **La sortie publique officielle reste sous réserve** du triage des alertes élevées, des essais Safari/iPhone et Android physiques (verrouillage/retour au premier plan/audio), et de la validation manuelle de l’assistant sur une installation vierge. La restauration destructive et le parcours de mise à jour entre deux machines ne sont pas validés de bout en bout sur la session réelle. Leur code protège l’intégrité, l’identité du volume, les anciennes images et crée une sauvegarde préalable ; cela ne remplace pas cet essai.

Le pack est un **candidat local non signé**, testé Linux/amd64. Les autres architectures, la signature et l’installateur natif restent des étapes de distribution. `SHA256SUMS` vérifie l’intégrité ; une empreinte reçue avec le même téléchargement n’authentifie pas son auteur. Aucun changement de niveau global d’exécution PowerShell et aucune importation silencieuse de CA ne sont demandés.
