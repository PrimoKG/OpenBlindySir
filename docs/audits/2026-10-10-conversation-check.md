# Vérification des demandes de la conversation — 10 octobre 2026

[English](2026-10-10-conversation-check.en.md).

Cette passe rapproche les demandes successives des fonctions présentes et des
preuves de test. Elle complète la [correction des quinze constats de la dernière
vidéo](2026-10-10-video-fixes.md). Les rapports précédents restent des documents
datés : leurs anciens compteurs et versions ne décrivent pas la livraison actuelle.

## Écarts trouvés et corrigés pendant cette passe

1. Le générateur du pack refusait toute image dont le protocole n'était pas 13,
   alors que l'application utilise 14. Il compare désormais la version réellement
   contenue dans chaque image à la constante du protocole. Le manifeste expose
   aussi la compatibilité. Quatre tests couvrent les versions acceptée, ancienne,
   future et invalide.
2. Les guides de soirées à thème annonçaient encore protocole 12/snapshot 9.
   Ils indiquent maintenant 14/11, sans réécrire les anciens rapports historiques.
3. Sur un PC de 1280 × 720, les filtres de bibliothèque occupaient presque toute
   la fenêtre avant les morceaux. Recherche et tri restent visibles ; tous les
   autres filtres et raccourcis sont regroupés dans un panneau repliable avec
   compteur. Les commandes utilisent la largeur disponible. La pagination ne
   recouvre plus les morceaux.
4. « Effacer les filtres » ne remettait à zéro que les critères thématiques.
   Il efface maintenant aussi source, dossier, format, disponibilité, activation,
   qualité et limitation aux sources sélectionnées. L'ordre de tri est conservé.
5. Le pack emporte les guides utilisateur FR/EN et les rapports récents ; il ne
   repose plus uniquement sur les instructions du 8 octobre.
6. Computer Use a reproduit un blocage après sauvegarde des métadonnées : le
   formulaire se fermait avant de libérer l'état occupé de son parent. Les filtres,
   la désactivation et la fermeture devenaient inopérants. Le démontage libère
   maintenant cet état ; deux régressions FR/EN et le parcours manuel complet
   (sauvegarder → filtrer → désactiver → réactiver → effacer → fermer) le vérifient.

## Matrice de couverture

« Couvert » signifie code présent et scénarios vérifiés ; cela ne signifie pas
absence garantie de défaut sur tout appareil. Les essais Computer Use précédents
du même jour sont identifiés explicitement, sans prétendre les avoir tous refaits.

| Demande | État et preuve |
| --- | --- |
| Final partagé en temps réel | Couvert : révélation, réécoute collective, attributions, variations de classement et podium. Partie Computer Use hôte FR/joueur EN décrite dans le rapport vidéo ; scénarios `test_live_finale.py` et jeux Chrome. |
| Final moins administratif | Couvert : actions guidées, propositions de points en premier plan, diagnostics repliés, rythme rapide et animations/son réglables. Le plaisir et le suspense restent à évaluer en soirée réelle. |
| Utilisation de la largeur des PC, petits portables et mobile | Couvert : colonnes adaptatives, validation accessible, cartes de réponses lisibles. Tests UI de 320 à 1920 px et formats portables ; bibliothèque revue à 1280 × 720. |
| Écoute directe hors éditeur | Couvert : réécoute privée séparée de la correction des références et lecture collective explicite. Tests audio HTTP et UI. |
| Libellé « Afficher les manches où il manque des attributions de points » | Couvert dans les dictionnaires et le filtre de revue, avec équivalent anglais. |
| Représenter dernière/avant-dernière puis revenir | Couvert : sélection privée distincte de la présentation publique ; tests moteur contre les doubles vagues et points, parcours navigateur et retour 2 → 1 en Computer Use. |
| Arrêter la partie et retrouver relance/fin de session | Couvert : arrêt immédiat, résultats et commandes de suite. Jeu Chrome réel incluant l'arrêt, relance testée en Computer Use. |
| Défilement intelligent des réponses | Couvert : hauteur mesurée localement, avance après notation du dernier joueur visible, pause manuelle et prochain joueur. Tests de lots à plusieurs dimensions ; deux joueurs ne sont plus écrasés dans une bande étroite. |
| Classement défilant, cinq joueurs maximum visibles | Couvert : plafond de cinq lignes, moins sur écran court, accès à sa position. Tests UI de dimensionnement et ex æquo. |
| QR → pseudo sans mot de passe | Couvert : scénario Chrome avec vrai serveur. Le lien d'invitation autorise l'accès à cette session ; il reste privé. |
| Reconnexion par cookie | Couvert : reprise dans le même navigateur ; cookies sécurisés en production, sauvegarde et redémarrage testés. |
| Code commun, accessible à l'hôte et régénérable | Couvert : accès de session et rotation testés côté serveur. Reprise d'un pseudo existant soumise à confirmation de l'hôte pour éviter l'usurpation ; transfert réel testé dans Chrome. |
| Désactiver/réactiver un morceau | Couvert sans supprimer le fichier ; filtrage et opérations groupées disponibles, tests bibliothèque et thèmes. |
| Éditeur immédiatement sous le morceau | Couvert dans la bibliothèque. L'éditeur de la revue est un dialogue distinct, avec sauvegarde/recalcul explicites. |
| Tags, genres, langue, époque, « Lié à » | Couvert : métadonnées structurées, filtres combinables, tri et modifications groupées. Conservation des filtres source/dossier/format/qualité. |
| Pagination, deux colonnes de dix si l'espace le permet | Couvert : pagination adaptative, colonne unique sur petit écran, pages réduites si nécessaire ; les options ne disparaissent pas. Tests UI et contrôle visuel. |
| Préécoute de 15 s au milieu | Couvert : privée, centrée sur la durée mesurée, bornée pour les morceaux courts, sans consommer le morceau. Test HTTP `test_library_midpoint_preview_is_private_and_never_consumes_a_track` et jeu Chrome réel. |
| Soirée génériques | Vérification en lecture seule de la session réelle : **211 morceaux étiquetés Génériques, activés et dotés d'un titre**, dans un catalogue de 300. Raccourci et transfert des filtres vers la prochaine partie testés. Aucun déplacement de musique nécessaire dans cette passe. |
| Pop, rap, 2012, français, anglais | Couvert par filtres/raccourcis combinables ; seules les métadonnées renseignées permettent de classer correctement. L'application ne devine pas la langue, l'année ou le genre d'un fichier non renseigné. |
| Lecture/correction des métadonnées | Couvert : tags audio locaux, cache, imports, corrections prioritaires, distinction hériter/remplacer/effacer et conflits d'édition. Les tags embarqués ne certifient pas la vérité des informations. |
| Validation automatique facultative dans un champ unique | Couvert : critères demandés extraits indépendamment, ordre/espaces/accents tolérés, points par critère et corrections hôte conservées. |
| Exemple exact « Sapéscomme Ja m ais Maitre Gims 2015 ft niska   pilule bleue » | Régression explicite dans `server/tests/game/test_auto_scoring.py` avec titre/artiste/album/année ; acceptation vérifiée. |
| Seuil en pourcentage | Couvert : 90 % par défaut, configurable ; année et très courtes références exactes. « validé »/« validée » passe à 90 %, échoue à 95 %. Aucun score global ne masque un critère absent. |
| Brouillons, références absentes, recalcul | Couvert : propositions acceptables explicitement, références prêtes avant départ, neutralisation collective contrôlée, recalcul sans écraser les critères corrigés manuellement. Quinze régressions de la dernière vidéo documentées séparément. |
| Tester/récupérer le son pendant le final | Couvert : bouton accessible hors réécoute, contexte fermé recréé sur geste, retentative après téléchargement et connexion. Tests audio FR/EN et geste réel Computer Use. Une validation acoustique physique reste à faire. |
| Switch FR/EN local au navigateur | Couvert : choix persistant, changement sans perte de saisie ni interruption audio. Dictionnaires, tests FR/EN et hôte/joueur de langues différentes. |
| HTTPS LAN et avertissement « dangereux » | Choix conservé : autorité locale approuvée explicitement sur les clients, guide FR/EN. TLS vérifié avec cette autorité ; aucune désactivation de la vérification. Un navigateur non configuré affichera toujours son avertissement. |
| Audit de sécurité local | Réalisé : tests applicatifs, analyse des trois images et de FFmpeg sans transmettre d'inventaire à Docker Scout. Les alertes de dépendances restantes sont détaillées ci-dessous. |
| Installation plus simple | Pack Docker précompilé, contrôles SHA-256/identités, assistant Windows, démarrer/arrêter, sauvegarde, mise à jour et rollback présents. Pack régénéré après correction du générateur. Docker reste un prérequis. |
| Installateur natif signé/publication officielle | **Non livré** : piste de distribution future. Le pack local n'est pas signé et aucune release publique officielle n'est créée par cet audit. |
| README, installation et utilisation FR/EN | Guides mis à jour, rapport bilingue, compatibilité 14/11/3. Les journaux historiques conservent les informations de leur date. |
| Bon conteneur, conservation des données et livraison | Identité d'image, contenu JS/CSS servi, santé, TLS, volumes et données comparés après relance ; détails dans la section de livraison. |

## Validation de cette passe

- 1 217 tests Python réussis, 2 ignorés et 11 intégrations exécutées séparément :
  les 11 réussissent. 55 tests unitaires web, 121 scénarios UI finaux et cinq
  parcours Chrome avec vrai serveur réussis. Les cinq parties précèdent la
  dernière correction de l'éditeur ; les 121 scénarios UI la suivent.
- Computer Use réel à 1280 × 720 : bibliothèque FR puis EN, préécoute, édition,
  sauvegarde, filtrage, désactivation/réactivation, effacement et fermeture.
  [Capture synthétique](assets/2026-10-10-library-1280-fr.png). Les tailles mobiles
  de cette passe sont automatisées ; aucune écoute sur téléphone physique n'est revendiquée.
- Images Linux candidates : deux manches, trois joueurs simulés, AAC, résultats
  complets ; même parcours via HTTPS/WSS et autorité locale vérifiée après la
  correction du proxy. Profils Caddy privé/public validés.
- Ruff, Pyright, Biome, TypeScript, génération du protocole et build réussis.
  Six tests du contexte Docker et du pack réussissent après ajout des verrous Go.

### Livraison déployée

Protocole 14, snapshot 11, historique 3. Identités Docker vérifiées :

| Service | SHA-256 de l'image |
| --- | --- |
| Application | `2c14aac3ae5ec3ea55d5b58682b7137125c1a9e8565b499649e92cf1e3dfe992` |
| Bridge | `7ad31ac1c79bd4e5fc3727a45d337dab8be8fc651d62d2d19bddbf862263a083` |
| Caddy | `ef592848af939a06c37c0afb18f34f3747046ffcdaaa2d6e940583b772ac66e3` |

Conteneurs relancés après sauvegarde privée dans
`.local/backup-conversation-20261010-023039` ; tags de retour arrière conservés.
La comparaison confirme quatre joueurs, 15 archives, 300 morceaux, scores,
métadonnées, cookies, accès, configuration et montages conservés. Bridge connecté,
TLS vérifié et fichiers HTML/JS/CSS servis identiques au build testé.

Pack local `.local/offline-pack-20261010-checked` régénéré avec ces trois images.
Le chargeur PowerShell a vérifié les SHA-256, chargé les images et confirmé leurs
identités. Il n'a pas démarré une nouvelle session ni modifié les volumes actifs.

## Sécurité et limites avant publication

Le scan reste local : seule la base publique d'avis de sécurité est téléchargée.
Ni volumes, ni mots de passe, ni catalogue musical ne sont envoyés à un service
d'analyse. Une alerte de paquet n'est pas une preuve d'exploitabilité, et l'absence
de correctif disponible n'est pas une preuve d'innocuité.

Le nouveau scan a aussi révélé 18 alertes Go/x/net dans le proxy officiel : elles
ont été supprimées du scan final en reconstruisant Caddy 2.11.7 avec Go 1.26.9 et
x/net 0.60.0. Sources, outil de compilation et dépendances sont verrouillés ; le
proxy livré annonce `v2.11.7-openblindysir.1`. Le scan des images exactes utilise
la base Grype construite le 9 octobre 2026, sans transfert d'inventaire.

| Image | Critiques | Hautes | Moyennes | Basses | Négligeables |
| --- | ---: | ---: | ---: | ---: | ---: |
| Application | 0 | 55 | 50 | 10 | 46 |
| Bridge | 0 | 55 | 50 | 10 | 46 |
| Caddy corrigé | 0 | 8 | 14 | 8 | 0 |

Ces nombres comptent des correspondances paquet/avis, pas des failles uniques
exploitables. Pour chaque image Python, 54 alertes hautes sont classées
`wont-fix` et une `not-fixed`. Les deux avis moyens Python marqués corrigés
référencent seulement des versions 3.15 préliminaires ; aucune migration forcée
vers un runtime instable n'a été faite. Les huit alertes hautes du proxy concernent
les paquets libcrypto/libssl, avec état de correction inconnu. Elles restent
ouvertes ; compiler Caddy sans CGO ne démontre pas l'innocuité de toute l'image.
FFmpeg 9.0.2, analysé séparément avec sa version/source vérifiées, ne présente
aucune correspondance dans cette base. [Résumé reproductible du scan](2026-10-10-image-scan.json).

La validation iOS/Android physiques après verrouillage et changement de sortie
Bluetooth reste nécessaire. Le redimensionnement du navigateur ne la remplace pas.
L'assistant Windows et ses scripts ne constituent pas un installateur natif signé.
Le bundle JavaScript dépasse encore le seuil d'avertissement de 500 ko minifiés.
Ces réserves empêchent de présenter cette passe comme une certification générale
de sécurité ou de compatibilité universelle.
