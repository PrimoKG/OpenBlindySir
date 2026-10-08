# Analyse du test filmé du 8 octobre 2026

**Verdict : le parcours de final n'est pas au niveau annoncé dans les livraisons précédentes.** Un défaut de mise en page rend les réponses illisibles ; le contrôle avant lancement laisse démarrer une notation automatique avec des références manquantes ; plusieurs interactions et états entretiennent la confusion. La réussite des suites automatisées ne permettait pas d'affirmer que cette expérience était validée.

Ce rapport est une **analyse, pas une livraison de correctifs**. Les défauts ci-dessous restent ouverts. Aucun conteneur, volume, morceau ou état de session n'a été modifié pour cette analyse. Une modification CSS a uniquement été essayée dans une page synthétique isolée pour vérifier une cause. [English summary](2026-10-08-test-video.en.md).

## Source et méthode

- Source locale : **2026-10-08 20-06-24.mp4**, durée **8 min 34,63 s**, 1920 × 1080, 60 images/s.
- Vision de l'ensemble du déroulement à intervalles réguliers ; extraction d'une image par seconde ; examen plus dense de la préparation, des révélations, des retours entre manches, des confirmations et des deux podiums. Les horodatages visuels sont approximatifs à une seconde près.
- Confrontation avec le code du workspace, HEAD **22c6f6e9c21e7d6c9b7d28179e666d84211359e7**. La vidéo ne contient pas l'identité du bundle servi : l'analyse du code est une corroboration, pas une attestation de version à partir des pixels.
- Reproduction du conflit CSS avec les feuilles de style réelles, dans Chrome headless installé, à 1280, 1366 et 1920 px de largeur. HTML synthétique, carte de 623 px, cinq critères ; aucune connexion à la session réelle. Le réseau de cette page était bloqué.
- Analyse locale de toute la piste audio : **niveau moyen et maximum −91 dB**, silence détecté de 0 à 514,60 s. Le fichier n'a pas de son exploitable. Les alertes affichées sont analysables ; ce que les participants entendaient ne l'est pas.
- Captures, mesures et scripts conservés dans **.local/video-audit-20261008-200624/**, exclu du dépôt. La vidéo et les captures complètes, qui montrent également d'autres onglets du navigateur, ne sont pas ajoutées au dépôt.

**Niveaux de preuve :** « constat » signifie visible dans la vidéo ; « cause confirmée » signifie également reproduite ou directement établie par le code ; « à vérifier » désigne une conséquence possible qui n'est pas démontrée. P1 désigne une dégradation majeure du parcours ; P2 une difficulté importante de compréhension ou d'usage. Aucun de ces niveaux n'est une classification de vulnérabilité.

## Déroulement effectivement observé

| Temps | Événement | Interprétation retenue |
| --- | --- | --- |
| 00:00–00:51 | Préparation sur plusieurs onglets ; cinq critères activés ; titre à 3 points, autres critères à 1 point ; cinq manches de 12 s. | La première partie utilise l'attribution manuelle. Le dossier de génériques n'est pas sélectionné dans cette séquence. |
| 00:53–01:05 | Besoin d'un geste audio, puis « Son bloqué » pendant que le temps de réponse défile ; clic sur le test audio ; disparition de l'alerte. | Le lancement ne garantit pas la préparation audio de ce navigateur. La piste OBS silencieuse ne prouve pas une absence de musique après le clic. |
| 01:05–02:26 | Cinq manches ; réponses saisies dans un seul champ. | Rien ne démontre ici une erreur de seuil de similarité : la partie est manuelle. |
| 02:26–03:00 | Entrée dans le final, premières révélations, aucune attribution encore confirmée. | Beaucoup de place est occupée avant les réponses et les contrôles de notation. |
| 03:14–04:16 | Défilements, réécoute collective, choix privés de plusieurs manches, retour en arrière. | La manche sélectionnée pour travailler et celle présentée publiquement sont distinctes. Cette distinction existe, mais reste difficile à lire. |
| 04:22–04:25 | Clic pour présenter la manche 1 ; elle devient bien publique à 04:23 ; présentation de la manche 4 ensuite. | Le retour à la manche 1 fonctionne dans ce passage. Il ne faut pas diagnostiquer un saut fautif de 1 vers 4. |
| 04:31–04:58 | Toutes les manches révélées ; 15 attributions en attente ; plusieurs ouvertures du dialogue de podium ; publication explicite des scores actuels. | Le premier résultat à zéro suit un choix explicite de publier sans finir la notation, pas une perte de points démontrée. |
| 05:01–05:10 | Cérémonie à zéro point ; message dupliqué ; défilement vers les actions de nouvelle partie. | Le menu de relance fonctionne, mais sa place et la cérémonie ne sont pas adaptés à ce résultat incomplet. |
| 05:13–05:22 | Passage en automatique à 90 %, cinq critères conservés, lancement direct. | Aucun avertissement utile sur les références manquantes n'est visible dans ce parcours de modification. |
| 05:22–06:39 | Deuxième partie, certaines réponses validées, d'autres capturées à la fermeture. | La politique choisie laisse les brouillons capturés à l'appréciation de l'hôte. |
| 06:39–08:13 | Final automatique ; textes des joueurs verticaux ; références manquantes nombreuses ; attributions encore en attente. | Le défaut CSS et l'insuffisance du contrôle de qualité avant lancement se cumulent. |
| 08:17–08:18 | L'hôte valide le critère titre pour un joueur ; +3 points apparaît. | Les points sont enregistrés. Les quatre autres critères de cette réponse restent à décider. |
| 08:21–08:29 | Publication explicite avec dix attributions encore en attente ; podium avec 3 points pour le joueur corrigé. | Cohérence observée entre la correction et le résultat. Le résultat incomplet devrait être signalé comme tel. |

## Constats et corrections nécessaires

### V01 — P1 : les pseudos et les réponses deviennent illisibles

**06:39–08:18, particulièrement 06:48. Constat et cause confirmée.** Le pseudo et la réponse sont affichés lettre par lettre dans une colonne écrasée. Cela produit des cartes beaucoup trop hautes et empêche de rapprocher facilement la réponse de ses boutons de notation. Ce n'est pas un simple problème de préférence visuelle.

Dans [finale.css](../../web/src/finale.css), la carte déclare deux colonnes et des zones « player score / answer score / time score ». Une règle desktop de [refinements.css](../../web/src/refinements.css) ne conserve qu'une colonne déclarée, mais laisse les zones à deux colonnes. Une seconde colonne implicite subsiste ; les textes de reconnaissance automatique peuvent l'élargir au détriment du pseudo et de la réponse.

La reproduction isolée mesure **0 px** pour les zones du pseudo et de la réponse, **589,06 px** pour la notation et une carte de **841 px de haut**. Réinitialiser également les zones dans cette page rétablit une largeur utile de **597,56 px**. Ces dimensions appartiennent à la reproduction synthétique, pas à une mesure directe de la vidéo. Elles établissent la cause du défaut ; elles ne valident pas à elles seules une correction complète.

**Correction à faire :** redéfinir ensemble colonnes et zones, selon la largeur réelle de la carte ; permettre aux contenus longs de se replier sans écraser la réponse ; alléger les preuves répétées. **Acceptation :** pseudo et réponse lisibles avec cinq critères, longues raisons automatiques, noms longs, FR/EN, zoom et écrans de faible hauteur ; vérifier les largeurs utiles et la hauteur des cartes, pas seulement l'absence de débordement horizontal.

### V02 — P1 : le défaut de carte compromet aussi l'auto-défilement

**06:48–08:18. Constat de cartes tronquées ; conséquence établie dans le code.** Une carte peut dépasser la hauteur du panneau défilant. [ScoreScroll.tsx](../../web/src/ui/ScoreScroll.tsx) ne mémorise comme visibles que les lignes entièrement contenues dans le panneau. Si aucune carte n'y tient, la liste des joueurs visibles est vide ; le mécanisme « dernier joueur visible noté → lot suivant » n'a plus de joueur déclencheur.

Cela explique pourquoi corriger uniquement le scroll ne suffirait pas. Le défilement manuel nécessaire entraîne en outre sa mise en pause, explicitement affichée. La case cochée exprime la préférence d'auto-défilement ; le bouton de reprise indique une pause temporaire. Ce double état n'est pas, à lui seul, une case qui dysfonctionne.

**Correction à faire :** réparer V01, prévoir un comportement pour une carte plus haute que le panneau et rendre l'état actif/en pause plus immédiat. **Acceptation :** avancer après le dernier joueur effectivement présenté, même avec une carte développée ; préserver le focus d'une saisie en cours ; tester différentes hauteurs et une pause puis reprise manuelle sur chaque navigateur.

### V03 — P1 : le contrôle des références avant lancement disparaît pendant la modification

**05:13–05:22. Constat et cause confirmée.** On active la notation automatique et on lance directement la partie, sans avertissement utile sur les données nécessaires aux cinq critères. Les références manquantes seront découvertes au final.

[SetupPanel.tsx](../../web/src/host/SetupPanel.tsx) affiche le décompte d'erreurs seulement lorsque les réglages ne sont pas modifiés : condition **!dirty**. Le décompte reçu correspond aux réglages enregistrés. [ThemeSelector.tsx](../../web/src/host/ThemeSelector.tsx) transmet au contrôle de sélection les sources et filtres, sans les critères et le mode de notation du brouillon. Le lancement contrôle la capacité musicale et la validité des nombres, mais pas la préparation des références du nouveau choix.

**Correction à faire :** calculer la qualité sur le brouillon réel, sources et filtres compris, et la recalculer après modification ; présenter la couverture par critère avant « Enregistrer et lancer ». Donner des choix explicites : préparer les références, utiliser les morceaux compatibles ou accepter un complément manuel clairement annoncé. Ne pas transformer silencieusement une valeur inconnue en mauvaise réponse. **Acceptation :** passer de manuel à automatique, ajouter album/année/featuring et lancer sans enregistrer séparément ; l'avertissement doit rester exact, visible et exploitable.

### V04 — P1 : l'automatique est proposé sans références suffisantes pour tenir sa promesse

**06:48, 07:15, 07:23, 07:55, 08:04. Constat et mécanisme confirmé.** Certains morceaux ont un titre affichable, alors que les cinq références utilisées par le calcul sont absentes. D'autres ont un titre et un artiste, mais pas album, année et featuring. Certains titres restent encombrés d'informations de vidéo ou de version.

[rounds.py](../../server/src/openblindysir_server/game/rounds.py), fonction **build_auto_reference**, refuse intentionnellement de prendre le nom de fichier d'affichage pour une référence fiable. [auto_scoring.py](../../server/src/openblindysir_server/game/auto_scoring.py) laisse les références inconnues en attente. Cette prudence est justifiée ; son intégration au parcours ne l'est pas : l'hôte croit préparer une partie automatique, puis découvre une liste d'incertitudes qui lui rend la charge manuelle.

**Correction à faire :** rendre la préparation des références accessible depuis le contrôle V03, distinguer un libellé d'affichage d'une référence validée, nettoyer les titres et gérer les alias confirmés. Distinguer aussi « featuring inconnu » d'une absence de featuring réellement vérifiée, sans inventer de données. La vidéo ne justifie pas de modifier le seuil de 90 % : un seuil différent ne remplace pas une référence absente. **Acceptation :** bibliothèque mixte avec références complètes, partielles, nom de fichier seul, titre bruité et effacement volontaire ; traitement explicite de chaque situation, aucune validation fabriquée.

### V05 — P1 : la première manche démarre alors que le navigateur signale un son bloqué

**00:53–01:05. Constat.** « Son bloqué » apparaît alors que le temps de réponse défile déjà. Le test audio est actionné pendant la manche. Le message de reprise mentionne ensuite une arrivée en cours d'extrait. Cela donne à l'utilisateur une impression de départ raté et réduit le temps effectivement utile.

Le chemin **Enregistrer et lancer** de SetupPanel envoie la configuration sans appeler **engine.unlock()** pendant ce geste utilisateur. Ce point est confirmé dans le code, mais il ne suffit pas à attribuer tous les éventuels problèmes audio des téléphones à cette seule cause.

**Correction à faire :** profiter du geste de lancement pour préparer l'audio de l'hôte ; exposer clairement l'état de préparation local avant le compte à rebours ; prévoir un test/reprise pour les joueurs sans bloquer indéfiniment toute la salle à cause d'un absent. **Acceptation :** premier accès dans un navigateur vierge avec la politique d'autoplay native ; audio bloqué puis autorisé ; reprise après arrière-plan sur appareils physiques. Le démarrage doit raconter clairement ce qui est prêt et ce qui ne l'est pas.

### V06 — P2 : le test audio existe, mais se trouve hors écran pendant le travail de notation

**03:14 et 07:55–08:18. Constat de position.** Le bouton « Tester mon audio » est présent dans le header lorsque celui-ci est visible. Après défilement dans le final, il sort de l'écran. Cela répond imparfaitement à la demande précédente d'un moyen de rétablir le son pendant cette phase.

**Correction à faire :** maintenir une commande audio compacte accessible au point d'usage, avec état local et action de reprise ; distinguer préécoute privée, réécoute partagée et effets du final. **Acceptation :** pouvoir tester/reprendre sans quitter la carte en cours ni remonter la page, sur desktop et téléphone. La vidéo montre uniquement l'hôte : elle ne permet pas de conclure à l'absence du bouton chez un joueur précis.

### V07 — P2 : la préparation conserve une consigne devenue contradictoire

**00:00–00:51 et 05:13–05:22. Constat.** La consigne « Donne le nom du dessin animé ou de la série » reste enregistrée tandis que les sources choisies et les cinq critères demandés correspondent à une autre partie. La modal oblige à passer entre musique, règles et rythme ; le résumé du bas donne cinq manches, douze secondes et trois participants, mais ne met pas ce conflit en évidence.

La persistance d'une consigne personnalisée n'est pas un bug en soi. Le manque est un contrôle lisible de la configuration finale. **Correction à faire :** proposer une vérification de la consigne lors d'un changement de thème ou de critères, conserver les textes personnalisés sans les écraser, et afficher un récapitulatif cohérent des sources, critères, points, mode de notation et traitement des brouillons. Mieux utiliser la largeur desktop dans la modal. **Acceptation :** passer d'une soirée génériques à une partie pop/rap sans jouer avec une ancienne consigne par inadvertance.

### V08 — P2 : le champ unique n'aide pas suffisamment à répondre aux cinq critères

**01:05–02:26 et 05:22–06:39. Constat de présentation.** Les critères sont présents dans les règles, mais le formulaire reste générique. Un joueur doit retrouver ce qui est demandé et comment le combiner, sous une forte contrainte de temps. L'explication dans la préparation de l'hôte ne suffit pas à guider celui qui joue.

**Correction à faire :** conserver le champ unique demandé, afficher près de lui les critères actifs et leurs points, et un exemple de structure sans divulguer la réponse du morceau ; rendre « validé » et « brouillon capturé » immédiatement distincts. **Acceptation :** cinq critères dans un ordre libre, espaces inhabituels, accents, année exacte et saisie partielle ; consigne intelligible en FR et EN ; aucune obligation de découper la réponse en plusieurs champs.

### V09 — P2 : le final utilise la largeur sans résoudre la charge de lecture

**02:29–04:39 et 06:48–08:18. Constat.** Le titre, la scène publique, le rythme, le guide, le contexte, la liste et le sélecteur occupent beaucoup de hauteur avant les réponses. Le lecteur privé reste volumineux pour un extrait de douze secondes. La notation est comprimée, tandis que des zones restent vides autour du classement. Il faut jongler entre défilement de page et défilement de liste ; référence, réponse et actions sont souvent séparées. La barre fixe de bas de page concurrence le contenu.

**Correction à faire :** donner la priorité à la réponse et à la décision ; compacter le lecteur et la référence ; garder la manche publique et le classement en contexte ; déplier les outils avancés au besoin. L'adaptation doit dépendre de la largeur utile et de la hauteur, pas seulement d'un seuil « desktop ». Préserver l'espace nécessaire sous la barre fixe. **Acceptation :** sur 13 pouces et faible hauteur, lire la réponse et agir sans perdre son pseudo ou sa référence ; la disposition à trois colonnes n'est pas un objectif si elle dégrade ce parcours.

### V10 — P2 : le guide du final ressemble à un menu, mais ne pilote pas le parcours

**02:41–04:31. Constat de présentation et fonctionnement confirmé dans le code.** « Révéler », « Écouter si besoin », « Attribuer les points », « Voir le classement », « Manche suivante » ressemblent à des contrôles. Dans HostApp, ce sont des éléments de liste sans action. De plus, le calcul de l'étape active choisit 0, 1, 2 ou 4 : l'étape classement, indice 3, n'est jamais active.

**Correction à faire :** choisir un vrai comportement : actions de navigation utilisables et accessibles, ou indicateur passif dont l'apparence et l'état correspondent réellement au parcours. **Acceptation :** les cinq étapes ont un sens vérifiable ; un élément qui paraît cliquable agit ; navigation clavier et lecteurs d'écran cohérente. La vidéo ne permet pas d'affirmer qu'un clic précis sur chacune de ces étapes a été tenté.

### V11 — P2 : revenir sur une manche change le contexte privé, sans rendre la distinction publique assez évidente

**03:49–04:25 et 08:13–08:18. Constat.** Le choix d'une manche peut préparer ou noter la manche 1 pendant que les joueurs voient encore la manche 3 ou 5. C'est une séparation utile, mais l'hôte doit assembler plusieurs indices pour comprendre où il se trouve. « Présenter la manche X » sert également à revenir à une manche déjà présentée ; une fois cette action faite, le même emplacement peut proposer la prochaine manche non révélée.

**Correction à faire :** afficher de façon compacte et persistante « Tu notes la manche X / les joueurs voient Y », distinguer présenter, représenter et passer à la suivante, et conserver une destination explicite. **Acceptation :** séquence 1 → 2 → 3 → retour 1 → 4 → 5 → retour 4/5 ; sélection privée sans révélation accidentelle, reprise de présentation correcte, aucune attribution doublée. Le passage filmé à 04:23 fonctionne ; il ne démontre pas le vieux bug des deux dernières manches.

### V12 — P2 : révéler toutes les manches conduit au podium avant d'avoir fini de noter

**04:31–04:58 et 08:03–08:21. Constat.** La progression des révélations finit alors qu'il reste quinze, puis dix attributions. « Lancer le podium » devient l'action forte. Le dialogue empêche une publication incomplète silencieuse, ce qui est utile. Mais sa commande principale « Terminer les attributions » ne termine aucune attribution : elle referme le dialogue, sélectionne une manche en attente et fait défiler vers la notation. Les réouvertures répétées montrent que ce parcours ne règle pas le besoin immédiatement.

**Correction à faire :** afficher à chaque transition ce qui reste à décider et proposer d'aller directement aux réponses concernées ; nommer le bouton selon son effet, par exemple « Revenir aux 15 réponses à noter ». Conserver un choix volontaire de publication incomplète, clairement secondaire et expliqué. **Acceptation :** l'hôte sait avant le clic si le podium est complet ; le retour ouvre et cible une réponse encore en attente, sans donner l'impression d'enregistrer des décisions qu'il n'a pas prises.

### V13 — P2 : les décisions partielles ne sont pas racontées par la progression

**08:17–08:18. Constat et logique confirmée.** L'action « Titre : trouvé » attribue bien trois points. Le total monte, mais le nombre de réponses vérifiées et le compteur global restent inchangés : quatre autres critères de cette réponse sont encore indécis. Le calcul est cohérent ; l'interface laisse penser que le clic n'a pas terminé son travail.

**Correction à faire :** séparer points accordés, critères décidés et réponses entièrement vérifiées ; indiquer « 3 points accordés, 4 critères à décider » près de la carte. Faciliter les décisions restantes sans les transformer automatiquement en erreurs. **Acceptation :** après un seul critère, effet du clic et reste à faire sont immédiatement lisibles ; les compteurs se mettent à jour au bon niveau ; une révision manuelle et son annulation restent cohérentes.

### V14 — P2 : « Enregistré » ne dit pas si la notation est terminée

**03:14 et 08:18. Constat et cause confirmée.** Sous la liste, « Enregistré » est affiché même avec des réponses et critères encore en attente. ReviewRound affiche cet état dès qu'aucune requête de sauvegarde n'est en cours. Il signifie l'absence de sauvegarde en attente, pas la fin du travail de notation.

**Correction à faire :** distinguer confirmation d'une modification sauvegardée et avancement de la manche ; ne pas laisser un message de succès isolé suggérer une notation complète. **Acceptation :** aucune décision prise, décision partielle, sauvegarde en cours, sauvegarde échouée et manche totalement notée ont des états différents et compréhensibles.

### V15 — P2 : le podium mélange résultat incomplet, zéro point et victoire

**05:01 et 08:21–08:29. Constat et cause confirmée pour la cérémonie à zéro.** Le premier final affiche correctement « La partie est terminée » et « Aucun point cette fois », mais aussi trois premières places avec confettis et le même message répété. Le code conserve les styles de gagnant, les effets et le déclenchement de la cue de victoire au rang 1 lorsque tous les scores sont nuls. La cue existe dans le code ; elle n'est pas audible dans l'enregistrement.

Surtout, les résultats publiés avec quinze ou dix attributions en attente ne racontent pas clairement cet état dans la cérémonie. « Tout a été noté et personne n'a trouvé » et « l'hôte a publié avant la fin de la notation » sont deux résultats très différents.

**Correction à faire :** transmettre et afficher la complétude du résultat ; adapter la cérémonie aux états incomplet, complet sans point et gagnant(s) réel(s) ; retirer le message dupliqué et les signaux de victoire inadaptés. **Acceptation :** couvrir les trois états, les égalités et une vraie attribution positive ; l'historique et l'export conservent également le statut incomplet. Les deux publications filmées sont explicites : aucun résultat à zéro imposé à l'insu de l'hôte n'est démontré.

### V16 — P2 : l'après-partie oblige encore à chercher les actions utiles

**05:01–05:10 et 08:25–08:34. Constat.** Après la cérémonie, les classements et détails occupent la page avant les commandes de relance. Les mêmes résultats sont représentés à plusieurs endroits. Le passage vers la nouvelle partie fonctionne, mais demande de retrouver le bon endroit.

**Correction à faire :** placer les choix « rejouer avec les morceaux restants », « préparer une autre partie » et « terminer la session » près de la fin de cérémonie ; conserver détails et exports dans une zone secondaire. **Acceptation :** relancer ou terminer facilement sur petite hauteur ; ne pas confondre fin de partie et fin de session ; conservation des historiques et réglages attendus.

### V17 — P2 : le grand final comporte des animations, mais l'expérience reste dominée par la correction administrative

**02:26–04:58 et 06:39–08:29. Constat sur l'hôte ; expérience des joueurs à vérifier.** La réécoute collective, les vagues de points, l'activité du classement et la cérémonie existent. Affirmer qu'aucune animation n'a été faite serait faux. Pourtant, la combinaison d'incertitudes, de textes répétés et de contrôles envahissants prend le dessus. Sur la deuxième partie, les annonces autour de zéro point et des références inconnues ne créent pas un moment de récompense compréhensible.

**Correction à faire :** faire du final une succession claire : morceau révélé, réponse et crédits compréhensibles, points confirmés, changement de classement, puis prochaine manche. Préparer et regrouper les incertitudes côté hôte ; réserver les effets aux événements qui ont un sens. La qualité des données et la lisibilité sont des prérequis à la mise en scène, pas des détails à traiter après l'animation.

**Acceptation :** regarder simultanément un hôte et plusieurs joueurs, avec vrais téléphones et notes automatiques, manuelles, partielles, corrections et égalités ; comprendre ce qui se passe sans commentaire du développeur. La vidéo d'un seul navigateur ne valide pas le spectacle partagé ni sa synchronisation.

## Ce que je ne dois pas diagnostiquer abusivement

- **Pas de perte de points démontrée.** Le +3 manuel est conservé au second podium. Les zéros du premier suivent une publication volontaire avec les réponses non notées.
- **Pas de panne générale du rapprochement à 90 % démontrée.** L'absence de références et le traitement manuel des brouillons expliquent plusieurs attentes. Les saisies filmées ne constituent pas un jeu d'exemples complets et validés permettant de mesurer le seuil.
- **Pas de bug prouvé sur le nombre de manches.** Le réglage final de la préparation indique cinq manches, et cinq sont jouées.
- **Pas de panne démontrée du menu de relance.** Le retour à une nouvelle préparation est visible vers 05:10. Son ergonomie reste à améliorer.
- **Pas de régression démontrée du retour aux dernières manches.** Le passage détaillé montre un retour effectif à la manche 1 ; les confusions de contexte et de libellés restent réelles.
- **Pas de preuve sonore sur les téléphones.** La piste est silencieuse et les écrans des joueurs ne sont pas enregistrés. L'alerte initiale du navigateur hôte, elle, est visible.
- **Pas de diagnostic de qualité des génériques à partir de cette partie.** Le dossier correspondant n'est pas sélectionné. Cela ne retire pas l'obligation d'un contrôle des références pour toutes les sources.
- **Pas de validation de sécurité ou de publication à partir de cette vidéo.** Elle révèle des défauts d'usage ; elle ne remplace ni audit technique de sécurité ni essais d'installation.

## Pourquoi les vérifications précédentes ont laissé passer cela

1. **Les assertions de mise en page étaient insuffisantes.** Le helper layout de [ui.spec.ts](../../web/e2e/ui.spec.ts) vérifie le débordement global et des boutons d'au moins 44 × 44 px. Il ne vérifie pas la largeur utile du pseudo et de la réponse. Un texte cassé verticalement dans une colonne de 0 px peut passer ces assertions.
2. **Les données des fixtures étaient trop favorables.** Plusieurs scénarios de défilement utilisent des réponses absentes et aucune preuve automatique longue. Le scénario de vraie notation automatique de [game.spec.ts](../../web/e2e/game.spec.ts) prépare des métadonnées complètes sur les morceaux synthétiques. Cela valide le calcul avec de bonnes références, mais pas le lancement sur une bibliothèque mixte et incomplète.
3. **La préparation audio n'était pas validée comme un départ réel.** La configuration Chromium générale autorise l'autoplay sans geste. Un test spécifique plus strict existe ; il ne constitue pas une validation de tout le parcours « navigateur vierge → préparer → enregistrer et lancer → première manche », encore moins d'un téléphone réel.
4. **Les états étaient testés séparément.** Sélection privée, révélation, points, sauvegarde et podium peuvent chacun fonctionner tandis que leur enchaînement reste incompréhensible. Il manquait un scénario réaliste avec cinq critères, références imparfaites, retours en arrière, notation partielle et publication incomplète.
5. **Mes conclusions étaient trop larges par rapport aux preuves.** Dire que les tests passent, ou que des composants existent, ne permet pas de présenter le final desktop, l'accessibilité audio et la convivialité comme entièrement réglés. Le rapport précédent mentionnait des réserves physiques, mais cela ne compensait pas les affirmations trop fortes sur le parcours lui-même.

## Leçons et ordre de travail

**Premier lot : rendre le parcours utilisable.** V01/V02, contrôle de qualité vivant V03/V04, premier départ audio V05. Validation isolée sur une bibliothèque représentative, avec les références volontairement imparfaites ; aucune dépendance aux morceaux ou à l'état de production pour fabriquer un test réussi.

**Deuxième lot : rendre chaque décision compréhensible.** V06–V14 : configuration cohérente, champ unique guidé, final compact, vrai guide, contextes privés/publics lisibles, destinations explicites et progression par critère. La commande principale doit toujours dire ce qu'elle va faire, sans exiger de connaissance du modèle interne.

**Troisième lot : rendre la fin de soirée juste et agréable.** V15–V17 : cérémonie adaptée, complétude affichée, relance accessible, mise en scène autour des points réellement confirmés. Tester avec plusieurs participants ; une animation isolée ou une capture hôte ne suffit pas à juger l'ambiance.

Pour chaque lot, la preuve attendue est un **parcours complet lisible**, avec cas défavorables, FR/EN, petites hauteurs desktop, zoom, navigateurs natifs et téléphones physiques pour l'audio. Les tests automatiques servent à garder cette preuve stable ; leur nombre ne doit plus servir de substitut à l'observation. Aucun nouveau « prêt pour la sortie » ne doit être formulé tant que ces défauts et les réserves de publication ne sont pas réellement levés.
