# Audit ciblé — notation automatique, final et HTTPS LAN

Date : 2026-10-06. V0.5 développement, protocole **9**, snapshot **7**.

## Livraison et périmètre

Notation automatique optionnelle dans un seul champ : titre, artiste, album, année et featuring, barèmes distincts, seuil par critère (90 % par défaut, 80–100 %). Variantes explicites, références figées, décisions incertaines à vérifier, priorité des corrections humaines et recalcul explicite de la manche. Points privés pendant le jeu, révélations par vagues et classement synchronisé. Interface et guides FR/EN.

L’installation existante reste en **LAN privé**. Le guide d’approbation du certificat local est fourni en FR/EN ; aucun domaine, aucune ouverture Internet et aucune installation automatique d’autorité sur les appareils des participants n’ont été réalisés.

## Bugs et contrôles de sécurité applicative

| Point | Correction / contrôle |
| --- | --- |
| Calcul excessif sur des réponses longues | Budget déterministe de 2 000 000 unités de travail pour la distance ; références normalisées dédupliquées, recherche exacte prioritaire dans tout le champ. Si le budget est épuisé : vérification humaine, aucun zéro définitif arbitraire. Cas adversarial à 1 498 caractères mesuré à environ 22 ms sur cette machine après correction ; mesure indicative, pas un SLA. |
| Chiffres Unicode | Normalisation avant extraction des années ; contrôle décimal avant conversion, années full-width/arabe/superscript et symboles numériques inhabituels testés. |
| Divulgation avant révélation | Tests moteur et partie réelle : ACK sans points, aucune preuve automatique dans les vues joueur, standings à zéro avant présentation ; décisions et scores masqués pendant la vague pour les joueurs encore non révélés. |
| Corrections et double attribution | Contrôle des révisions, priorité des décisions manuelles, recalcul explicite, retour sur une manche sans doublon, journal définitif écrit à la validation. |
| Redémarrage | Références, règles, preuves et progression des vagues persistées ; migration de la session manuelle existante sans recalcul. |
| Interface mobile EN | Correction du débordement du panneau de recalcul ; variantes nommées distinctement pour les lecteurs d’écran. |
| Classement lors du défilement | Animation seulement lors d’un changement d’ordre ; mesures relatives au document, pas au défilement du navigateur. Limite de cinq joueurs visibles conservée. |
| Entrées et dépendances | Réponses : défaut 1000, plafond protocole 1500. Variantes : huit par champ, 256 caractères chacune. Métadonnées validées côté serveur, échappement React ; aucun service d’IA, regex utilisateur, commande shell ou accès réseau pour noter. RapidFuzz 3.14.6 verrouillé. |
| Certificat local | Export de la seule autorité publique root.crt avec empreinte de fichier SHA-256 ; guides Windows/iOS/Android, confiance explicite et retrait. Les clés privées restent dans les volumes existants. |

## Vérifications exécutées

| Vérification | Résultat |
| --- | --- |
| Suite Python finale | **1052 réussites**, 46 skips de plateforme/FFmpeg absent du PATH initial, 11 tests d’intégration sélectionnés séparément |
| Tests FFmpeg séparés | **44 réussites**, exécutés avec les outils locaux existants et des médias synthétiques |
| Intégration serveur/Bridge réels | **11 réussites** |
| Tests Web unitaires | **47 réussites** |
| Interface Chromium | **91 réussites** ; quatre parcours nouveaux FR/EN revérifiés après enrichissement des fixtures avec album/année |
| Parties réelles Chromium | **4 réussites** (desktop, téléphone, MC, QR/reconnexion/récupération/préécoute) |
| Nouvelle partie automatique réelle | **1 réussite**, rejouée sur un serveur neuf démarré avec le code final : exemple demandé accepté, quatre points calculés puis révélés, correction à six points visible chez le joueur, publication du podium |
| Contrôles statiques | Ruff, format Python, Pyright, TypeScript, Biome, générateur de types/verrou de schéma et build Web réussis |
| Construction Bridge | FFmpeg 9.0.2 signé, codecs audio et protocoles limités à file vérifiés à la construction |
| Installation finale | App/Caddy sains, Bridge en ligne ; HTTPS vérifié avec l’autorité locale, build Web attendu servi, protocole 9 / snapshot 7 |

Les navigateurs headless ne valident pas l’écoute acoustique réelle ni Safari/iOS physique. Une soirée sur appareils réels reste nécessaire pour les différences d’autoplay, de sortie audio et de mise en veille.

## Scan local des images activées

Scanner Grype 0.120.0, digest `sha256:5c88961f4130e830542d441c7ed6c78baa28e799163abac53d2be4923fb5ab7d`. Base publique v6.1.10 du 2026-10-05 à 06:45:38 UTC. Exécution sans réseau, sans socket Docker monté et sans volumes de session/musique. Aucun inventaire envoyé à Docker Scout.

| Image OCI activée | Critique | Élevée | Moyenne | Faible | Négligeable |
| --- | --- | --- | --- | --- | --- |
| app : `sha256:8a3a76e6dbaf5e2f5029dd8eb1fe4a81ade087766de9abdb303f7d988c398ab8` | 0 | 55 | 51 | 10 | 46 |
| bridge : `sha256:39c7a05c4aa69b516e1480dab83d11df42e2ad265ef9aaa8abfeec2a87cf39b3` | 0 | 55 | 51 | 10 | 46 |
| caddy : `sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9` | 0 | 1 | 4 | 0 | 0 |

Ces nombres bruts sont des correspondances paquet/avis, pas des exploits démontrés. Aucun filtre ne masque les résultats. Le scan ne rapporte pas de CVE associée au paquet RapidFuzz avec cette base ; ce résultat ne garantit pas l’absence de vulnérabilité.

**Nouvelle réserve de dépendance :** RapidFuzz ajoute du code C++ natif à l’app. La justification ancienne « libstdc++ non chargé » du rapport du 5 octobre ne s’applique donc plus à l’app. Les avis GCC/libstdc++ `CVE-2026-95619` (allocation alignée sur très grandes tailles) et `CVE-2026-102010` (erase_if d’une file prioritaire binaire) restent présents, sans version corrigée indiquée dans la base locale. Les chaînes et le calcul de distance sont fortement bornés et le code applicatif n’appelle pas erase_if ; cela réduit les chemins plausibles mais ne constitue pas un audit exhaustif du binaire natif. Les autres réserves des audits précédents restent à examiner lors du feu vert de publication.

Les images restent installées pour l’usage LAN demandé. Cette livraison fonctionnelle **ne certifie pas une release publique sans réserve**, ni un système sans vulnérabilités. Le scan local est daté ; refaire le contrôle des dépendances et des correctifs avant publication officielle.

## Sauvegarde, migration et reprise

Sauvegarde locale privée : `.local/backups/before-auto-scoring-20261006/state/`, images de retour arrière `openblindysir-server:before-auto-20261006` et `openblindysir-bridge:before-auto-20261006`. ACL de sauvegarde limitées à l’utilisateur courant. Les sauvegardes ne sont pas des artefacts publics.

Après redémarrage : **4 joueurs, 8 archives, 69 morceaux**, phase FINAL_RESULTS conservée. Identités/pseudos, réglages, événements de scores, métadonnées, archives après application des valeurs par défaut du nouveau schéma, empreinte d’authentification et codes d’accès déchiffrés comparés et identiques. La réécriture chiffre les accès avec un nouveau nonce : les ciphertexts diffèrent normalement. Les anciennes archives restent manuelles.

Un retour à l’ancien serveur exige de restaurer sa sauvegarde de format 6 : il ne sait pas lire le format 7. Recharger les onglets après mise à jour ; les Bridges externes doivent aussi passer au protocole 9.

Preuves locales : `.local/auto-scoring-scan-final-20261006/summary.json`, `.local/auto-deployment-facts.json` et journaux de tests `.local/auto-*.log`. Les inventaires et snapshots privés ne doivent pas être publiés.

Guides : [notation FR](../notation-automatique.md), [scoring EN](../automatic-scoring.en.md), [certificat FR](../certificat-local.md), [certificate EN](../local-certificate.en.md).
