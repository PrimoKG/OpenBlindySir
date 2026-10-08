# Livraison après le test filmé du 8 octobre

[English](2026-10-09-final-polish.en.md) · [Analyse initiale et horodatages](2026-10-08-test-video.md)

Les défauts de lisibilité, de préparation et de progression du final ont été
corrigés et vérifiés. Cette livraison ne constitue pas une certification de sortie
publique : l'écoute et la reprise audio sur de vrais iPhone/Android restent à
valider. La vidéo d'origine était silencieuse et ne permettait pas ce contrôle.

## Corrections et preuves

| Constat | Changement livré | Vérification |
| --- | --- | --- |
| V01 — Réponses écrasées | Une grille cohérente conserve toute la largeur du pseudo et de la réponse. Les critères passent en deux colonnes seulement si la carte est assez large ; les preuves détaillées se déplient. | Captures et mesures à 1366, 1093 et 390 px : cinq critères, références manquantes et réponses longues ; largeur utile supérieure à 75 % de la carte. |
| V02 — Auto-défilement | Une carte plus haute que le panneau devient un lot à elle seule. Le passage attend la confirmation serveur ; les marges du pied de page n'affectent plus le focus dans la liste. | Cartes développées, absences confirmées à zéro, 24 joueurs et plusieurs viewports. Pause manuelle et saisie en cours conservées. |
| V03 — Avertissement absent pendant la préparation | Le contrôle utilise les critères et filtres du brouillon. Le lancement demande une prise en compte explicite des références manquantes ; une modification invalide cet accord. | API et navigateur FR/EN, avant tout enregistrement ; les contrôles restent accessibles hors du pied de formulaire fixe. |
| V04 — Références trompeuses | Préparation et notation partagent le même résolveur de références fiables, variantes et suppressions explicites. Le nom de fichier seul n'est pas une réponse de référence. | Tests de sélection : manquants par critère, pistes jouables/inédites, exemples bornés et données effacées. Aucune métadonnée personnelle inventée. |
| V05 — Premier départ audio | Le clic de lancement prépare le contexte audio de l'hôte avant d'envoyer la commande. L'échec garde un message de récupération. | Chrome sous sa politique native exigeant un geste ; un seul contexte audio actif. |
| V06 — Récupération audio introuvable | « Tester mon audio » reste dans l'en-tête pendant le final. La réécoute collective prépare également l'audio au clic après un rechargement. | Hôte et joueur dans deux navigateurs, tests FR/EN avec contexte suspendu et défilement. Réserve matérielle ci-dessous. |
| V07 — Consigne de l'ancien thème | Récapitulatif permanent de la consigne et des critères. Un changement de raccourci retire la consigne générée « dessin animé » si elle est restée intacte, dans les deux langues. | Computer Use : génériques → pop efface la consigne générée ; une consigne personnalisée reste intacte lors du passage au rap. |
| V08 — Champ unique peu guidé | Les informations demandées sont indiquées auprès du champ ; ordre libre et réponse partielle explicités. | Modes de réponse, FR/EN et formulaire accessible sur petit écran. |
| V09 — Final trop vertical et chargé | Largeur desktop augmentée ; contexte et notation répartis selon l'espace ; preuves répétées repliées ; en-tête compact. | Computer Use à 1366 × 768 et contrôles 1093 px/mobile ; capture ci-dessous. |
| V10 — Faux guide | Les étapes décoratives deviennent des actions pour rejoindre les réponses restantes et le classement. | Navigation et destinations vérifiées ; le retour cible le joueur à noter sans cacher son nom derrière l'en-tête. |
| V11 — Préparation privée/public confondus | Manche notée et manche montrée sont nommées séparément ; « Représenter » indique un retour. Le contexte de notation reste dans la barre d'actions. | Présentations 2 → 3 → 1 → 2 → 3 en régression ; parcours réel 1 → 2 → 1 → 2, points conservés. |
| V12 — Podium proposé trop tôt | L'action principale rejoint les réponses restantes. Publier malgré des attributions incomplètes reste un choix explicite secondaire. | Notation complète/incomplète, focus de retour et dialogue de publication. |
| V13 — Notation partielle obscure | Compteur de critères décidés et action « Marquer le reste non trouvé », qui préserve les décisions déjà prises. | Partie réelle : un titre accordé puis les autres critères manqués, avec conservation du point ; progression et classement partagés. |
| V14 — « Enregistré » trompeur | Le bas de liste indique les réponses entièrement notées et le nombre restant, séparément des sauvegardes en attente. | Aucune décision, décision partielle, confirmation serveur et fin de notation. |
| V15 — Fausse fête à zéro/incomplète | Le serveur conserve le nombre de réponses non notées. Résultat incomplet et résultat entièrement nul utilisent une présentation neutre, sans confettis ni signal de victoire. | Quatre cas FR/EN, égalités et podium positif. Migration, historique et exports ; ancien historique : complétude inconnue, pas zéro inventé. |
| V16 — Relance enfouie | Les actions de nouvelle partie et fin de session suivent la cérémonie, avant les détails. Sur ordinateur, elles partagent une ligne si l'espace le permet. | Contrôle visuel des tailles de boutons, puis vraie relance : les deux navigateurs retrouvent le salon et les identités. |
| V17 — Final peu compréhensible | Révélation, décision partielle, confirmation et évolution du classement sont distinguées. Les effets de récompense correspondent aux points effectivement montrés. Les notifications se retraduisent au passage FR/EN. | Partie à deux navigateurs avec reprise, notes partielles, changement de leader et podium 6–5 identique. L'appréciation en soirée et la synchronisation acoustique restent des contrôles humains. |

![Carte avec cinq critères et réponse longue, à 1366 × 768, données synthétiques](assets/2026-10-09-final-1366.png)

## Validation exécutée

- **1 200 tests Python réussis** ; deux cas exclus sous Windows (permissions Unix
  et création de liens symboliques), onze intégrations exécutées séparément.
- **11 intégrations réussies** : vrais processus serveur/Bridge, dix joueurs
  simulés, reconnexion, préparation manuelle, plusieurs Bridges et historique.
- **55 tests unitaires web réussis** ; TypeScript, Biome, Ruff, Pyright, génération
  de protocole et contrôle d'hygiène réussis.
- **117 scénarios d'interface Chromium réussis dans la passe finale**. Les cinq
  parcours de jeu de la suite complète ont également réussi : desktop, 320 px,
  animateur, invitation/reprise et notation automatique. La passe intermédiaire
  a découvert le conflit de marges du défilement mobile, corrigé puis retesté.
- **Computer Use** : une vraie partie isolée, deux navigateurs/cookies, deux
  manches, cinq critères, références incomplètes, validation des réponses, notes
  partielles, retours, réécoute après recharge, classement, podium et relance.
  Interface joueur anglaise et vérification à 390 × 844. Aucun participant ni
  morceau réel n'a été utilisé pour fabriquer les résultats des tests.
- **Images Linux candidates** : application et Bridge non privilégiés, système
  de fichiers en lecture seule, audio AAC synthétique, trois clients simulés et
  deux manches jusqu'aux résultats complets ; snapshot 10 produit.
- La compilation conserve un avertissement sur le bundle JavaScript d'environ
  520 ko avant compression. Ce n'est pas masqué ; le découpage du bundle reste une
  optimisation distincte.

Les rapports et captures de tests complets sont privés dans `.local/polish-*` et
`web/test-results`. La capture publiée ci-dessus ne contient que des fixtures.
La CI distante et WebKit ne sont pas inclus dans ces résultats locaux.

## Livraison et migration

Serveur, Bridge et web utilisent le **protocole 13**, les snapshots **10** et
l'historique **3**. Mise à jour effectuée après sauvegarde privée à l'arrêt et
conservation des images précédentes. Le certificat LAN et les paramètres réseau
n'ont pas changé. Les guides FR/EN, le protocole et les consignes de retour arrière
sont mis à jour : revenir à une image antérieure exige sa sauvegarde compatible.

Contrôle de l'installation après redémarrage : les trois services sont sains,
Bridge connecté, **3 joueurs, 14 parties archivées et 300 morceaux** conservés.
Scores, réponses, métadonnées, sessions navigateur, accès, montages et
configuration sont identiques. Le snapshot est passé de 9 à 10. Le HTTPS a été
vérifié avec l'autorité locale ; les fichiers web servis correspondent exactement
au build contrôlé. Aucun jeu de test n'a été lancé dans cette installation.

Images vérifiées :

- Application : `sha256:b15c0cc6a51dd6088ca4024914b9d6c35297e8957e691d2dfcb12abc5c6fcce7`
- Bridge : `sha256:f934419a9a768ad0cec8564d3a027272f82e5b5a1b18ac23b6c942d8d5ddf092`

## Réserves avant publication officielle

1. Tester réellement iPhone/Safari et Android/Chrome : première connexion,
   verrouillage/réveil, retour d'arrière-plan, perte/reprise réseau et réécoute du
   final. Un contexte audio déclaré actif ne prouve pas que le haut-parleur joue.
2. Regarder une soirée avec plusieurs personnes : compréhension des critères,
   visibilité des cartes et rythme des vagues. Cette passe apporte une preuve
   fonctionnelle ; elle ne remplace pas leur expérience.
3. Conserver les portes de publication existantes : CI multi-plateforme, essais
   d'installation et contrôles sécurité de release. Cette passe ne refait pas
   l'inventaire CVE des images et n'a transmis aucun inventaire à Docker Scout.
   Le passage au protocole 13 ne vaut pas levée des réserves de sécurité déjà
   documentées.
