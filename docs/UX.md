# Parcours UX/UI — retour vidéo du 2026-10-03

Cette passe applique le GO d'implémentation après l'analyse des deux parties
enregistrées. Elle modifie le web, le serveur, le Bridge et le protocole, qui passe
à la version 2. Les décisions sont consignées dans
[ADR 0010](adr/0010-game-night-ux.md) et la restauration dans
[ADR 0009](adr/0009-session-snapshots.md).

## Préparer une partie

L'hôte voit les dossiers, les morceaux disponibles et ceux encore inédits pendant
la soirée. Sélectionner un dossier parent et son enfant ne compte pas deux fois
les mêmes morceaux. Une sélection insuffisante propose de réduire les manches
ou d'autoriser les répétitions. « Enregistrer et lancer » applique les réglages
et lance la partie dans une seule commande serveur ; un échec conserve la
configuration précédente.

La consigne, la réponse attendue (titre, artiste, les deux ou personnalisée), les
points associés et le traitement des brouillons sont visibles par tous. Les
points restent attribués manuellement. Les sélections favorites sont enregistrées
dans le navigateur de l'hôte. Le QR code contient seulement l'URL ; le mot de
passe de la partie se partage séparément. En lobby, l'hôte peut affecter une
équipe ou le rôle spectateur. Le score d'équipe additionne les scores individuels.

## Répondre et animer

Le bandeau de phase est compact. Le temps de réponse est affiché séparément de la
lecture : la fin de l'extrait ne ferme pas nécessairement les réponses. À cinq
secondes de l'échéance, le repère devient plus visible. Le focus arrive sur la
réponse sur ordinateur ; le clavier du téléphone ne s'ouvre pas automatiquement.
La pause suspend le son et le délai, bloque la saisie à la frontière synchronisée
et exclut sa durée du temps de réponse. La reprise poursuit le même extrait.

Le rôle suit les permissions du serveur : passage d'hôte joueur à animateur
pendant la partie lorsque les réponses sont fermées ; retour joueur à la
prochaine partie. Un spectateur écoute et consulte les résultats, sans réponse,
score ni effet sur les joueurs attendus au chargement.

## Noter et publier

En REVIEW, l'hôte dispose du titre et de l'artiste du morceau courant, ainsi que
d'un éditeur pour corriger les métadonnées. Cette information reste privée avant
la publication. Le joueur voit seulement sa propre réponse ; l'animateur peut
voir les métadonnées selon son rôle, sans réponses en direct pendant OPEN.

Les points en cours de saisie restent locaux. Entrée ou sortie du champ envoie
la modification ; la publication attend l'accusé serveur. Une valeur nulle
explicitement vérifiée se distingue d'une ligne encore à vérifier. Le compteur
des réponses vérifiées, le score publié et le total provisoire rendent la revue
lisible. Publier avec des lignes non vérifiées demande une confirmation. Les
brouillons capturés suivent la règle annoncée ; aucune notation automatique ni
bonus de vitesse n'est ajouté.

## Terminer et retrouver la soirée

Les résultats détaillent chaque manche : titre, artiste, réponse, statut, temps,
ordre, points et corrections. Les exports JSON et CSV utilisent ces résultats
publiés. Le CSV protège les cellules interprétables comme formules. L'hôte
retrouve les 50 dernières parties terminées en lobby ou après les résultats.

Une nouvelle partie remet les scores à zéro en gardant les morceaux entendus
pendant la soirée. Une réserve épuisée affiche des choix de récupération.
Les snapshots privés conservent joueurs, réponses, réglages et scores après
redémarrage. Une manche OPEN interrompue passe en revue avec un avertissement,
les brouillons étant capturés. L'audio est régénéré ; une erreur d'écriture de
snapshot avertit l'hôte sans bloquer le jeu.

## Affichage et audio

La palette papier, encre sombre et terre cuite reste commune à tous les écrans.
Les tableaux deviennent des lignes adaptées au mobile et les commandes utilisent
des cibles d'au moins 44 × 44 px. Le panneau hôte suit le défilement de la page.
Les options avancées et diagnostics sont repliables. Les erreurs de connexion,
bibliothèque et audio indiquent une action de récupération. Les dictionnaires
français et anglais couvrent les nouveaux parcours.

Le Bridge peut normaliser les extraits et chercher une fenêtre sans silence.
Ces opérations utilisent des filtres fixes et des limites de temps. Les fichiers
écartés au cours de la préparation apparaissent dans le diagnostic privé de
la bibliothèque. Le scan initial n'analyse pas l'audio de tous les fichiers.

## Validation et limites

Les tests couvrent 320, 390 et 1280 px, les textes longs, le focus, les cibles
tactiles, les confirmations, les permissions et l'absence de débordement.
Les couleurs textuelles principales satisfont le contrôle numérique 4,5:1 ;
ce contrôle ne constitue pas un audit WCAG complet. Les captures de test sont
ignorées par Git et utilisent seulement des données synthétiques.

Chromium exécute aussi trois parcours avec serveur et Bridge réels. Les tests
WebKit d'interface passent ; ce build Windows ne fournit pas `AudioContext`,
donc quatre scénarios nécessitant Web Audio sont explicitement ignorés.
Cela ne valide pas Safari sur iPhone, l'AAC de production, les sorties physiques
ni la synchronisation acoustique. Voir les résultats exacts dans
[DEVLOG](DEVLOG.md) et les essais manuels dans [testing](testing.md).

G1 et G2 restent `PENDING USER MEASUREMENT`.
