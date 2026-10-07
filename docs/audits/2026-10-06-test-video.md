# Analyse du test vidéo du 6 octobre 2026

Source : `2026-10-06 20-35-05.mp4`, durée 8 min 20 s, capture 1920 × 1080.

Analyse visuelle du parcours complet, avec images à une seconde d'intervalle et inspection des passages importants en pleine résolution. Les observations ont été confrontées au code de la notation automatique, des références musicales, du final et du défilement. Quatre appels directs au moteur de reconnaissance ont complété cette analyse. Aucun changement applicatif ni redémarrage n'a été effectué pour cette analyse.

## Conclusion

Le parcours atteint bien le podium et conserve les scores visibles pendant les retours entre manches. L'arrêt puis le redémarrage fonctionnent dans ce test. Les problèmes principaux concernent la fiabilité perçue de la notation automatique et l'ergonomie du final : références affichées et références de notation peuvent différer, les raisons de non-attribution sont peu visibles, et l'hôte doit parcourir trop de panneaux pour retrouver les réponses.

La capture ne permet pas de certifier la restitution sonore sur les téléphones, la synchronisation entre appareils, les reconnexions, l'anglais ou la sécurité de l'installation. Le navigateur apparaît à une échelle réduite ; son zoom réel n'a pas été mesuré. La dominante grise touche aussi le navigateur et ne suffit pas à conclure à un défaut de contraste de l'application.

## Constats et corrections proposées

P1 : à traiter avant de présenter le parcours comme prêt pour le public. P2 : amélioration importante de confort ou de compréhension. Une priorité ne signifie pas qu'une corruption de données a été prouvée.

| ID | Priorité | Passage | Observation et impact | Correction proposée |
| --- | --- | --- | --- | --- |
| V01 | P1 | 00:20 | Le mode automatique est choisi à 90 %, alors que l'avertissement indique que 68 des 69 morceaux n'ont pas toutes les références demandées. Le parcours peut donc sembler automatique tout en exigeant beaucoup de vérifications manuelles. Ce nombre concerne la bibliothèque annoncée, pas nécessairement les cinq morceaux effectivement tirés. | Afficher un bilan des morceaux éligibles dans la sélection effective : prêts, partiellement documentés, sans références. Proposer de compléter les informations, de jouer seulement les morceaux prêts ou de poursuivre avec une vérification manuelle annoncée. |
| V02 | P1 | 06:19 ; 07:41 | « NINAO / GIMS » est affiché comme réponse attendue, mais la réponse envoyée « gims ninao » reste à vérifier sans points sélectionnés. Pour l'hôte, cela ressemble à une erreur évidente du moteur. | Afficher les références réellement utilisées pour noter, leur origine et leur état au début de la manche. Distinguer les informations déduites du nom de fichier des métadonnées confirmées. Après correction, permettre une nouvelle évaluation explicite sans écraser les décisions manuelles. |
| V03 | P1 | 05:37–08:09 | « À vérifier » ne dit pas immédiatement pourquoi. Les explications sont dans « Reconnaissance automatique », replié par défaut. Référence manquante, texte ambigu et absence de correspondance demandent pourtant des décisions différentes. | Donner une raison courte directement par critère, avec les détails de similarité en second niveau. Ajouter une action pertinente : compléter la référence, attribuer un critère ou réévaluer. |
| V04 | P1 | 05:37 ; 07:47 | « ciel gims » reçoit ses deux critères ; « ciel gims pilule bleue niska » reste à vérifier. Le seuil de 90 % ne suffit donc pas à expliquer le résultat, même lorsque les deux fragments sont exacts. | Expliquer les mots supplémentaires qui empêchent la validation. Définir clairement la politique : informations supplémentaires connues du morceau, ignorables ou contradictoires. Ne pas supprimer la protection contre les réponses qui accumulent des propositions au hasard. |
| V05 | P1 | 05:23–08:09 | Le final cumule la scène publique, la navigation, le choix de préparation, un grand lecteur, les références puis les réponses. De nombreux allers-retours verticaux sont nécessaires avec seulement deux participants. La barre d'actions fixe empiète visuellement sur les contrôles bas. | Sur ordinateur, mettre le contexte musical et un lecteur compact à côté de la notation. Garder le classement visible et réserver réellement la place de la barre d'actions. Faire tenir les informations essentielles d'une réponse dans une carte compacte ; déplier les réglages avancés au besoin. |
| V06 | P2 | 02:20 ; 05:23–08:09 | Le classement présente déjà une barre de défilement avec deux joueurs, alors que la carte paraît assez grande. La page, les réponses et le classement forment plusieurs zones de défilement concurrentes. | N'activer le défilement du classement que si le contenu dépasse l'espace disponible. Inclure les marges internes dans son calcul de hauteur ; conserver la limite de cinq joueurs. Réduire les zones imbriquées lorsque tous les joueurs tiennent à l'écran. |
| V07 | P1 | 06:11 ; 07:29–07:58 | L'hôte prépare une manche antérieure tandis que la manche 5 reste « En scène ». Cette séparation est prévue, mais les titres, la sélection et le bouton « Présenter la manche X » demandent un effort de compréhension. | Montrer deux états persistants : « Les joueurs voient : manche 5 » et « Tu prépares : manche 2 ». Donner au bouton principal une cible explicite. Distinguer représenter une manche et avancer vers la suivante ; ne pas diffuser automatiquement une sélection privée. |
| V08 | P2 | 06:19–08:09 | Une réponse peut être « Validée » tout en restant « À vérifier » ; une autre est « Vérifiée ». La proximité des mots brouille la différence entre envoi et notation. | Utiliser « Réponse envoyée », « Brouillon récupéré », puis « Points attribués » ou « À noter ». Réserver les statuts à une seule signification chacun. |
| V09 | P2 | 06:42 | La réponse laissée en brouillon « zoo kaaris niska » est récupérée à la fermeture et comptée parmi les réponses reçues. Le réglage annonce « L'hôte décide des points », mais la vidéo seule ne permet pas de vérifier son application. L'audit du 7 octobre reproduit une attribution automatique malgré ce réglage lorsque les références sont complètes. | Séparer les compteurs envoyées, récupérées et absentes. Rendre la politique affichée cohérente avec la notation ; voir A01 du nouvel audit. |
| V10 | P2 | 07:48–07:49 | La case « Défilement automatique » apparaît décochée après une interaction manuelle. Le code représente avec la même case la préférence enregistrée et une pause temporaire due au défilement. | Garder la préférence cochée et montrer « Défilement automatique en pause » avec « Reprendre ». Continuer à protéger la saisie et à mesurer le lot visible séparément dans chaque navigateur. |
| V11 | P2 | 06:19 ; 07:41 | Sous le classement, « Karim : 0 points confirmés » peut côtoyer son total de 2 points. Le zéro concerne la manche récente, mais le libellé ne le précise pas. | Ajouter le numéro de manche à l'activité : « Manche 2 : Karim +0 point ». Distinguer un zéro confirmé d'une attribution encore en attente et du total général. |
| V12 | P2 | 02:30 | La bibliothèque ouvre d'abord une interface de sources et de paramètres, avec beaucoup de contenu avant les morceaux. Cela détourne l'hôte de son besoin immédiat : retrouver et reconnaître un son. | Ouvrir par défaut l'onglet « Morceaux », avec recherche, filtres principaux et préécoute. Placer les sources dans un onglet avancé ; conserver les filtres et la pagination existants. Utiliser deux colonnes lorsque la largeur le permet. |
| V13 | P2 | 06:19–08:09 | L'écoute complète indisponible occupe un bouton désactivé et un message technique sur le Bridge, répétés dans un lecteur très haut même à l'arrêt. | Garder « Écouter l'extrait » visible dans une barre compacte. Mettre l'indisponibilité de l'écoute complète dans une aide contextuelle avec accès à son réglage si disponible. Réserver le lecteur détaillé à une ouverture volontaire. |
| V14 | P1 | 08:12 | La confirmation du podium avertit bien que huit réponses restent à vérifier, mais son tableau casse « Joueur », « ByeBye » et « Karim » sur plusieurs lignes. La fenêtre confirme néanmoins un classement construit avec des réponses non évaluées et leurs points actuels, zéro par défaut. | Corriger les largeurs du tableau et les retours à la ligne. Proposer d'abord « Vérifier les 8 réponses restantes », puis une action explicite « Publier avec les points actuels ». Rappeler que les réponses en attente ne sont pas des réponses jugées fausses. |
| V15 | P2 | 08:13–08:19 | Le suspense, les confettis et le podium sont présents. Le résultat reste toutefois un bloc assez statique, puis le classement est répété juste dessous. | Donner aux révélations de points une mise en scène lisible : joueur, critère trouvé, gain et déplacement dans le classement. Prévoir un mode de rythme rapide et un mode animé, respecter la réduction des animations. Sur le podium, donner accès au détail sans répéter immédiatement tout le classement. |
| V16 | P2 | 03:00 | Après l'arrêt du premier test sans points, l'interface célèbre des vainqueurs ex æquo à zéro. C'est compatible avec le classement, mais peu adapté à une partie arrêtée sans attribution. | Prévoir un état de résultat spécifique pour une partie interrompue ou sans points attribués, avec relance visible. Conserver les ex æquo ordinaires pour les parties effectivement évaluées. |
| V17 | P2 | 05:23 ; 08:18 | « Tester mon audio » est présent dans le header, mais devient inaccessible à l'écran quand l'hôte descend dans les réponses. La capture ne montre pas le téléphone du joueur. | Garder un accès compact à l'audio pendant toute la distribution. Vérifier séparément sur iOS et Android la reprise après verrouillage, changement d'application ou interruption audio. |

## Vérifications dans le code

### Référence affichée et référence automatique

`server/src/openblindysir_server/game/rounds.py` construit la référence automatique avec `build_auto_reference`, sans utiliser le nom du fichier comme référence de secours. En revanche, `build_reveal` peut déduire titre et artiste du libellé du fichier. `web/src/host/ReviewRound.tsx` affiche ce second objet dans « Réponse attendue ».

Le mécanisme de divergence est confirmé. Pour le cas précis de NINAO, la capture ne contient pas l'état des références figées ni les traces serveur permettant d'attribuer définitivement le résultat à ce mécanisme. Une référence vide ou ancienne reste une explication à vérifier, plutôt qu'une erreur prouvée du calcul de similarité.

### Reproduction directe à 90 %

| Saisie | Référence fournie au moteur | Résultat |
| --- | --- | --- |
| `gims ninao` | titre NINAO, artiste GIMS | Les deux critères correspondent à 100 %. |
| `gims ninao` | aucune référence | Les deux critères ont une référence manquante. |
| `ciel gims` | titre CIEL, artiste GIMS | Les deux critères correspondent à 100 %. |
| `ciel gims pilule bleue niska` | titre CIEL, artiste GIMS, sans album ni featuring | Les deux fragments correspondent à 100 %, mais le résultat est ambigu à cause du texte supplémentaire non reconnu. |

Ces quatre appels vérifient le comportement local du moteur ; ils ne reconstituent pas l'état exact de chaque manche enregistrée. Le titre CIEL ne doit pas être confondu avec l'exemple précédent de Sapés comme jamais : les mêmes mots supplémentaires ne sont pas nécessairement justes pour ces deux morceaux.

### Défilement

Dans `web/src/ui/ScoreScroll.tsx`, l'interaction manuelle suspend l'automatisme et `checked={auto && !manual}` affiche alors la préférence comme décochée. C'est une ambiguïté de présentation confirmée par le code.

La hauteur maximale du classement est calculée sur les lignes, avec une compensation de deux pixels, alors que `.score-scroll` ajoute aussi des marges internes. Cette piste explique le petit débordement visible à deux joueurs ; la mesure DOM devra confirmer la correction dans le navigateur. Le retour entre manches ne prouve pas un saut automatique de page : le déplacement manuel, le changement de hauteur du contenu et l'ancrage du navigateur doivent être distingués.

## Ce qui fonctionne dans cet enregistrement

- Les deux séries de cinq manches s'enchaînent et atteignent le final.
- L'arrêt de partie, sa confirmation, l'arrivée aux résultats et le retour au salon sont visibles vers 02:59–03:03.
- Une réponse simple, `ciel gims`, reçoit les deux critères automatiquement.
- Un brouillon non envoyé est récupéré à la fermeture de sa manche.
- Après les retours aux manches précédentes, le classement visible reste Karim 2, ByeBye 0 ; aucune duplication de ces points n'est visible.
- La confirmation signale les huit réponses en attente avant le podium.
- Le podium se lance vers 08:13 et affiche ensuite Karim 2 points, ByeBye 0. Cela confirme l'application du classement publié, pas la justesse de toutes les réponses laissées sans évaluation.
- Le switch FR/EN et le bouton de test audio sont visibles ; seule la version française est parcourue.

## Ordre recommandé et critères de validation

1. **Références et notation** : utiliser une source explicite cohérente entre affichage et calcul ; distinguer les informations déduites ; rendre les raisons de révision visibles. Tester une réponse exacte dans les deux ordres, les espaces atypiques, les informations supplémentaires connues et contradictoires, une référence manquante, puis une correction des métadonnées avec conservation des décisions manuelles.
2. **Final sur ordinateur** : compacter lecteur et cartes, réduire les scrolls imbriqués, réparer le tableau de confirmation. Vérifier 1280 × 720 et 1366 × 768, plusieurs zooms, puis le téléphone déjà apprécié. Tester 2, 5 et 20 joueurs sans masquer une action ni créer un classement scrollable inutilement.
3. **États et navigation** : rendre préparation privée et scène publique immédiatement distinctes ; clarifier envoi, récupération, notation et activité par manche. Refaire la séquence avant-dernière → dernière → précédente → dernière sans double attribution ni changement involontaire de scène.
4. **Animation et audio** : scénariser les gains avant le podium et maintenir l'accès au test audio. Tester les deux langues, la réduction des animations, le son désactivé et la reprise audio sur de vrais téléphones.

Cet enregistrement est un test fonctionnel et ergonomique. Il ne constitue pas un nouvel audit de sécurité, de vulnérabilités des images ou de certificat HTTPS.

Complément du 7 octobre : [audit du code, reproductions et axes d'amélioration](2026-10-07-audit-complementaire.md), notamment la correction de l'interprétation de V09.
