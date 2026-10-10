# Utiliser OpenBlindySir — V0.5 — développement

[English guide](user-guide.en.md). Une instance accueille une partie à la fois,
entre amis dans leur navigateur, sur LAN, VPN ou Internet. Aucun compte à créer.
Préparez [l'hébergement](deployment.md) ou le [lancement Docker](docker.md).
Mettez à jour serveur, Bridge et interface ensemble : **protocole 14**.
Aujourd’hui, utilisez Docker ou [l’installation du Bridge depuis le dépôt](bridge-installation.md).
Le parcours uvx/archive sera disponible après publication.

Accès rapide : [rejoindre et tester le son](#préparer-et-rejoindre-la-soirée),
[préparer comme hôte](#préparer-la-partie-comme-hôte),
[bibliothèque](#gérer-les-sources-et-rechercher), [grand final](#le-grand-final),
[arrêt et reprise](#arrêter-et-retrouver-la-session).

## Préparer et rejoindre la soirée

L’hôte partage le **QR ou lien d’invitation** depuis **Inviter les joueurs**.
Il peut aussi partager l’adresse simple et le **mot de passe de la partie**.
Le mot de passe hôte reste privé. Chaque propriétaire de Bridge reçoit son propre
[fichier d'identité privé](bridge-installation.md#première-configuration), à conserver
sur son appareil ; ne le partagez pas avec les joueurs. En LAN/VPN, préparez la confiance du certificat
selon le guide réseau. Chaque joueur écoute dans son navigateur, idéalement au casque.

1. Ouvrez le QR/lien d’invitation : saisissez seulement un pseudo (24 caractères
   maximum), puis **Entrer**. Avec l’adresse simple, saisissez aussi le mot de passe.
   Pour utiliser le code commun, ouvrez **Retrouver ma place** : un nouveau pseudo
   rejoint directement si les inscriptions sont ouvertes ; un pseudo existant
   suit la confirmation de l’hôte décrite ci-dessous.
2. Dans le lobby, **Tester mon audio**, puis **Je l'entends ✓** après le bip.
3. Ajustez le volume. Gardez le navigateur actif pendant les manches.

Le switch **FR / EN** reste dans le header, depuis l’accueil jusqu’aux résultats,
également sur l’écran d’accès hôte. Le changement est immédiat, sans rechargement,
sans couper l’audio ni perdre les saisies. Le choix est enregistré localement dans
ce navigateur et retrouvé à la prochaine visite ; chaque joueur choisit sa langue.
Si le navigateur bloque le stockage local, le switch fonctionne pour l’onglet courant.
Les pseudos, réponses, consignes personnalisées et informations musicales restent tels que saisis.

**Correction audio (ms)**
compense une sortie lente : une valeur positive avance la prochaine lecture,
une valeur négative la retarde (−500 à +500 ms). Commencez à zéro ; par exemple
+150 ms pour une sortie Bluetooth en retard de 150 ms. Le réglage n'interrompt
pas une lecture en cours, persiste dans ce navigateur et ne modifie jamais le
temps de réponse officiel ni les points. La compensation physique reste à mesurer.

Sur le même navigateur, le cookie reprend automatiquement votre place dans la
même session. Le **Code de session** est commun à tous les joueurs ; l’hôte le
retrouve dans **Inviter les joueurs**, y compris depuis **Paramètres** pendant une
partie, et peut le changer/régénérer. Le QR demande seulement un pseudo.
Régénérer invalide l’ancien code et le QR précédent, sans déconnecter les joueurs.

Pour changer de navigateur, **Retrouver ma place** demande le pseudo et le code
commun. Un pseudo existant nécessite une confirmation de l’hôte ; gardez l’écran
ouvert pendant cette demande (2 minutes maximum). Communiquez à l’hôte la
référence affichée pour qu’il identifie votre demande, surtout si plusieurs
navigateurs réclament le même pseudo. Vos points, réponses et équipe
restent conservés. Après confirmation, l’ancien navigateur est déconnecté ;
les droits hôte exigent à nouveau le mot de passe hôte. Les reprises de places
existantes restent possibles quand les nouvelles inscriptions sont verrouillées.
Un MC récupéré reste spectateur jusqu’à une nouvelle activation du mode hôte.
Si la sauvegarde de l’accès échoue, l’ancien accès reste valide et un message
invite à réessayer ; la demande reste ouverte jusqu’à son expiration.

## Jouer les manches

**Préparation**, **Chargement**, compte à rebours, puis lecture synchronisée.
Écrivez dans **Ta réponse** et utilisez **VALIDER** ou Entrée. La validation est
définitive ; attendez **✓ Réponse enregistrée**. Le texte non validé est un brouillon
synchronisé ; après fermeture, le dernier texte reçu devient **Brouillon capturé**.
Il n’a ni rang officiel ni temps de validation. En notation automatique, il est évalué à la fermeture si la politique des brouillons le permet ; la politique zéro impose zéro.

La fin du son ne ferme pas nécessairement les réponses : le délai restant est
affiché. L'hôte peut suspendre son et réponses, reprendre, rejouer, ajouter du temps
ou fermer. La pause n'entre pas dans les temps de réponse.

Après chaque manche, **Réponses conservées** confirme l’enregistrement. Par défaut,
la suivante arrive automatiquement après **2 secondes** ; fermer l’onglet hôte ne
bloque pas cette transition. La dernière manche ouvre directement la revue finale.
**Les morceaux, réponses des autres et points sont dévoilés par l’hôte pendant
le grand final.** Le compteur anonyme n/m est masqué lorsqu’il y a moins de
trois participants. L’animateur conserve ses informations privées.

Pendant le jeu, la barre hôte reste compacte. **Paramètres** ouvre une modale sans
mettre la partie en pause ; **Son** ouvre les réglages de volume et de correction
locale. **Mettre en pause / Reprendre** suspend aussi une transition entre manches.
Dans **Paramètres → Rythme**, réglez l’intervalle de 0 à 10 secondes ou désactivez
l’enchaînement automatique pour passer manuellement. Les actions exceptionnelles
(rejouer, arrêter le son, fermer les réponses, remplacer, terminer) sont dans
**Actions de la partie**. Les règles/barèmes/dossiers restent fixés pour la partie.

## Préparer la partie comme hôte

L’hôte peut lancer directement la partie quand ses réglages enregistrés sont prêts ;
**Préparer la partie** permet de les modifier.

Sur `/host` ou **Accès hôte**, entrez le mot de passe hôte, puis ouvrez
**Préparer la partie**. Choisissez **Hôte joueur** pour jouer avec les mêmes protections
anti-spoiler, ou **Animateur** pour voir morceaux à venir et réponses en direct.
Passer animateur en cours de partie est permis entre les manches ; revenir joueur
attend la prochaine partie. Les spectateurs écoutent et voient les résultats sans répondre.

La préparation utilise cinq onglets : **Musique**, **Règles**, **Rythme**,
**Joueurs et équipes**, **Avancé**. Choisissez les dossiers, consignes, barème,
rythme et participants. Le résumé et les boutons d’enregistrement/lancement restent
accessibles en bas de la modale. Fermer avec des modifications non enregistrées
demande de les abandonner explicitement. Cocher un dossier parent et son enfant ne
double pas les morceaux. Les comptes distinguent disponibles et non consommés.
**Enregistrer et lancer** applique le tout atomiquement. Une sélection trop petite
propose de réduire les manches ou d’autoriser les répétitions. Les favoris sont
locaux. Le total du barème par manche doit rester entre 0 et 1 000 points ; le mode
personnalisé possède son propre nombre de points pour une bonne réponse.

Dans **Avancé** : **Normaliser le volume**,
**Éviter les extraits silencieux** et **Équilibrer les dossiers**. L'équilibrage
alterne les dossiers sélectionnés, mélangés en interne, jusqu'à épuisement ; les
morceaux restent uniques. Pour une sélection de la racine, il utilise les dossiers
contenant les fichiers. Aucun barème de rapidité n'est automatique.

Configurez équipes et spectateurs dans **Joueurs et équipes** au lobby. **Fermer les inscriptions**
empêche de nouveaux joueurs d'entrer ; reconnexion et récupération restent possibles.
Le verrou peut être retiré depuis le panneau hôte, quelle que soit la phase.

## Gérer les sources et rechercher

La recherche et le tri restent visibles à l'ouverture. Dépliez **Filtres et thèmes**
pour retrouver les raccourcis Génériques/Pop/Rap/2012, les langues et tous les
critères détaillés. Le compteur indique les filtres actifs. **Effacer les filtres**
réinitialise aussi la source, le dossier, le format, la disponibilité, l'activation,
la qualité et la restriction aux sources sélectionnées ; l'ordre de tri est conservé.
La pagination reste sous les morceaux et ne recouvre pas leurs commandes.

Trois choix distincts :

1. **Dossier accessible** : racine locale autorisée au Bridge, ou montage Docker.
2. **Dossiers scannés** : sous-dossiers publiés dans son catalogue.
3. **Dossiers sélectionnés** : ceux cochés pour la prochaine partie.

Le bouton **Sources et recherche de bibliothèque** ouvre une modale. Dans celle-ci, ajoutez/retirez des sous-dossiers relatifs et
demandez **Actualiser**. Le scan est asynchrone : les commandes de dossier restent
bloquées jusqu'à réception du scan terminé, puis les comptes et dossiers se mettent
à jour. Si le scan n'est pas confirmé sous 75 s, actualisez la bibliothèque puis
réessayez. La racine entière est représentée
par un chemin vide ; retirez-la avant de limiter le scan à quelques sous-dossiers.
Plusieurs Bridges peuvent rester connectés (huit maximum), identifiés séparément.

Un dossier hors racine ne peut pas être ajouté depuis le navigateur. Sous Docker,
ajoutez un montage **en lecture seule** sous `/music`, puis recréez seulement le
Bridge ; gardez le serveur et son volume de session. Pour un fichier ajouté sous
un montage existant, un rescan suffit. Voir [les commandes Docker](docker.md#sources-dynamiques-et-réécoute).
Un chemin inaccessible affiche les étapes de montage ; le dernier catalogue valide reste conservé.

Recherchez par nom de fichier, titre ou artiste importé/corrigé. Filtrez par Bridge,
dossier, extension, disponibilité et morceaux encore inédits. La recherche de
dossiers garde les ancêtres dans l’arbre. Le tri par titre, artiste, fichier ou dossier
est appliqué au catalogue entier, avant pagination adaptée : **20 morceaux en deux colonnes de 10** sur écran large,
10 sur écran étroit et 5 par colonne si la hauteur est faible. Les filtres
et la page sont conservés à la fermeture de la modale. Les états distinguent réservé,
consommé/joué et consommé/annulé. Consulter les titres avant le lancement est permis
à l’hôte joueur, avec un avertissement sur la surprise. Cette bibliothèque reste réservée aux hôtes au lobby, en revue
finale et aux résultats, ou au MC pendant le jeu.

Les fichiers MP4/MOV/MKV/AVI et autres conteneurs autorisés fournissent **uniquement
leur première piste audio**. Aucune vidéo, pochette ou tag n'est envoyé aux joueurs.
Un fichier sans audio est écarté avec un diagnostic privé. Formats, tailles,
codec manquant et fichier facultatif de métadonnées : [guide des sources](media-and-metadata.md).

### Préécoute, catégories et activation

**Préécouter 15 s · milieu du morceau** démarre une écoute privée directement
sous le son choisi. **Arrêter la préécoute**, changer de morceau/page ou fermer la
bibliothèque l’arrête. Un extrait public reste prioritaire. Aucun morceau n’est
consommé par cette écoute. Si le navigateur ne peut pas lire l’extrait,
réessayez avec le bouton de préécoute : un extrait défectueux est rechargé. Un simple
blocage du démarrage audio conserve l’extrait pour la tentative suivante.
**Corriger les informations du morceau** ouvre l’éditeur
sur la même carte ; quitter avec des changements non enregistrés demande confirmation.

**Désactiver ce morceau** l’exclut des prochains choix sans effacer le fichier,
les parties passées ou un extrait déjà préparé. Réactivez-le depuis le filtre
**Activation → Désactivés**. Les **Tags** et **Lié à** acceptent plusieurs valeurs
séparées par des virgules : genre/époque/langue, jeu vidéo/anime/film, par exemple.
La recherche et les filtres les retrouvent. En animateur, filtrez un thème puis
choisissez les morceaux pour les manches souhaitées. Les cases de sélection et
**Appliquer aux morceaux sélectionnés** ajoutent des catégories ou changent
l’activation des morceaux de la page ; un compteur indique les modifications réussies.
Les anciennes catégories sont conservées. Export JSON v2, import v1/v2.

## Choisir un morceau comme animateur

Dans **Sources et recherche de bibliothèque**, le mode
Animateur affiche **Choisir les morceaux (animateur)**. Sélectionnez la **Manche
à préparer**, recherchez/filtrez le morceau, puis **Choisir pour la manche N**.
Les résultats montrent Bridge, dossier, nom de fichier, titre/artiste disponibles,
format, durée si mesurée, disponibilité, déjà joué et réservé. Seuls les dossiers
de la partie sont éligibles ; en dehors, cochez d'abord ces sources au lobby.

Attendez **Choix enregistré par le serveur** et **Choix confirmé** avant de lancer.
Pendant cette confirmation, les commandes de lancement attendent. Deux éditions
simultanées ne s'écrasent pas : actualisez et réessayez si la révision a changé.
Un choix manuel respecte les répétitions autorisées mais contourne l'alternance
aléatoire des dossiers. Une piste réservée ailleurs ne peut pas être doublonnée.

L'extrait se verrouille **dès sa demande de préparation**, y compris dans le
préchargement des une/deux manches suivantes. Planifiez au lobby ou choisissez
une manche future encore libre. Aucun remplacement pendant la lecture. Une
manche manuelle prête attend **Lancer maintenant**, même avec auto-start.

Si le fichier disparaît, devient illisible ou le Bridge se déconnecte, le MC
reçoit une erreur et peut remplacer, **Revenir au tirage aléatoire**, passer ou
arrêter. Le serveur ne remplace pas silencieusement votre choix. Un saut de la
manche actuelle ne consomme pas une réservation de la manche suivante.
Les joueurs et l'hôte joueur ne reçoivent pas ces informations avant le reveal.
[Dépannage](troubleshooting.md#extraction-et-choix-mc).

## Le grand final

La barre du bas propose une seule action selon l’étape : présenter, terminer la
notation de la manche affichée, passer à la suivante, puis lancer le podium.
**Options du final** regroupe le rythme rapide, l’arrêt et la publication anticipée.
**Toutes les manches** contient la sélection privée et la recherche.

Pour une réponse à noter, deux choix suffisent : **Trouvé / Manqué** s’il y a un
seul critère, **Tout bon / Tout faux** sinon. Dépliez **Noter chaque élément** pour
une réponse partielle. Une fois notée, la carte affiche les points ; **Modifier les
points** permet de revenir sur la décision. Les preuves automatiques, horaires
et points manuels sont accessibles dans **Détails**.

Sans métadonnées, un nom comme `Travis Scott - FE!N (feat. Playboi Carti).mp3`
fournit le titre, l’artiste et le featuring. Un titre seul reste utilisable sans
inventer un artiste. Les corrections, imports et tags ont priorité ; album et
année ne sont jamais déduits du nom. Les références des manches déjà jouées
restent figées : corrigez puis utilisez **Enregistrer et renoter** si nécessaire.

Sur ordinateur, la notation et le classement utilisent la largeur disponible. Les
cartes gardent le pseudo et la réponse lisibles même avec cinq critères ; les
justifications automatiques détaillées se déplient à la demande. Le bouton
**Tester mon audio** reste dans l'en-tête pendant le final, même après défilement.

**Tu notes la manche X** identifie votre sélection privée ; **Les joueurs voient
la manche Y** identifie la présentation publique. **Représenter** permet de revenir
sur une manche dévoilée sans attribuer une seconde fois ses points.

Chaque réponse indique combien de critères sont décidés. **Marquer le reste non
trouvé** termine uniquement les critères indécis et conserve ceux déjà accordés.
Le bouton **Noter les N réponses restantes** rejoint une réponse incomplète. Tant
qu'il en reste, cette action est mise en avant avant le podium.

Publier volontairement sans finir reste possible, mais le résultat porte alors
le nombre de réponses non entièrement notées, également conservé dans l'historique
et les exports. Un résultat incomplet ou entièrement à zéro ne déclenche pas une fête de
victoire. Après le podium, les actions de nouvelle partie et de fin de session
précèdent les classements détaillés.

La dernière manche ouvre **Le grand final**, partagé avec
les joueurs. Dans **Toutes les manches**, l’hôte utilise **Corriger une autre manche en privé** pour sa préparation privée, puis
**Présenter la manche N** dans la barre d’action persistante. Tous voient alors le morceau, les réponses et leur
notation en direct. Naviguer seul ne change pas la scène publique.

La scène indique la manche vue par les joueurs, séparément de celle préparée par
l’hôte. **Toutes les manches** ouvre la navigation détaillée et la recherche ;
chaque manche distingue « À présenter », « En scène », « Présentée » et « Terminée ».
La barre indique les présentations encore nécessaires avant le podium.

Le classement provisoire additionne les manches déjà dévoilées et les corrections
finales. Une manche revisitée n’ajoute pas ses points une seconde fois. Les réponses
en attente, partiellement notées et vérifiées ont des états distincts. Les joueurs
retrouvent leur total et les points de la manche ; les équipes partagent un classement.

**Réécouter ensemble** lance l’extrait exact du jeu en synchronisation pour tous.
À la fin de l’extrait, la réécoute privée redevient disponible automatiquement.
**Arrêter la réécoute** annule aussi une préparation en cours. Les informations du
morceau restent dans un panneau secondaire ; la réécoute privée est directement
accessible sous le morceau. L’hôte peut
préparer une autre manche sans la dévoiler et utiliser la recherche des manches.

Chaque réponse indique validation ou brouillon capturé, temps officiel/rang si
disponibles, heure de réception serveur et retard audio connu. Une donnée absente
reste « — ». Les joueurs retirés ayant participé restent dans cette revue.
Corrigez titre, artiste, featuring, album et année si nécessaire.

Utilisez **Trouvé / Manqué** pour le titre et/ou l’artiste, **Tout bon / Tout faux**,
ou ouvrez les points manuels entre −1 000 et +1 000. Les critères suivent le mode
et le barème enregistré : titre à 2 et artiste à 3 donnent 5 pour « Tout bon ».
En mode personnalisé, le critère est « Réponse ». Une décision manquante reste
**À vérifier**, distincte de Manqué. La notation manuelle reste le mode par défaut ;
la [notation automatique optionnelle](notation-automatique.md) reconnaît les critères
demandés dans un seul champ, au seuil de 90 % réglable de 80 à 100 %. Album, année
et featuring peuvent être demandés avec leur propre barème. Les cas incertains
restent à vérifier. La saisie manuelle est identifiée et remplace les critères.

Les filtres **Afficher les manches où il manque des attributions de points** et **Prochaine réponse à vérifier**
accélèrent la revue. **Noter les réponses absentes à zéro** ne touche pas aux
brouillons capturés. Attendez l’accusé serveur avant de changer de manche ou publier.
Une réponse absente occupe une ligne compacte : **Confirmer 0 point** confirme
la décision ; **Attribuer autrement** permet une exception manuelle. Les personnes
qui n’étaient pas participantes à cette manche ne sont pas ajoutées aux absences.
La référence attendue affiche titre/artiste selon le mode et signale les métadonnées
incomplètes. Un zéro confirmé apparaît aussi dans la dernière attribution publique.
Une erreur de sauvegarde reste visible ; vérifiez et renvoyez votre correction.
Les critères et notes enregistrés survivent à la reconnexion et aux snapshots,
et sont conservés dans les récapitulatifs publiés.

**Corriger les informations du morceau** conserve titre, artiste, featuring, album
et année pour **toutes les parties de la session**, même après réinitialisation de
la réserve. Cela ne modifie pas les fichiers musicaux ni les archives déjà publiées.
La recherche utilise les titres et artistes corrigés.

Les totaux détaillés de l’hôte additionnent toutes les manches et les corrections finales.
Les équipes additionnent les points individuels et passent en premier dans le podium,
les totaux de revue et l’historique. Le classement individuel reste disponible ; les
joueurs sans équipe y restent. Les ex æquo partagent leur rang. La politique de brouillons
`manual` permet une décision humaine ; `zero` impose zéro, à vérifier explicitement.
Les corrections finales −/+ sont facultatives ; un **Motif facultatif** peut expliquer
une correction (120 caractères maximum). Enregistrez-le avant publication : il est
privé pendant la revue, puis apparaît dans les résultats, historique et exports.
Montant et motif sont enregistrés ensemble ; **Réinitialiser les corrections**
réinitialise ces corrections, pas les notes par manche.
Ces raccourcis et la remise à zéro attendent aussi l'accusé serveur avant une
nouvelle modification ou la publication.

Après avoir dévoilé toutes les manches entendues, **Lancer le podium** demande une confirmation avec les
totaux et le nombre de réponses restant à vérifier. Confirmer celles-ci conserve
leurs valeurs actuelles, initialement zéro. La publication est unique et fige les
scores. Le podium dévoile les places du troisième au premier, ensemble et en tenant
compte des ex æquo. Une reconnexion reprend l’étape en cours ; après redémarrage,
les résultats restaurés s’affichent directement. Le classement détaillé et le
récapitulatif suivent ; les exports CSV/JSON reprennent ces résultats figés.

Les confettis respectent la préférence de mouvement réduit. Dans **Son**, l’option
**Ambiance sonore du final** active les ponctuations musicales ; elles utilisent le
volume habituel, nécessitent l’activation audio et ne couvrent pas une réécoute.
Les résultats apparaissent avant les actions permettant de relancer une partie.

**Tester mon audio** reste disponible pendant le final et dans le menu **Son**.
Si le téléphone suspend le son, utilisez **Touchez pour réactiver le son**, même
entre deux réécoutes. Un extrait partagé en cours reprend à sa position actuelle ;
un extrait terminé ne redémarre pas. Vérifiez également le volume et la sortie
audio choisie sur le téléphone.

### Défilement des joueurs et du classement

Pendant le final, les deux listes de notation défilent dans leur propre zone.
Après la dernière ligne visible confirmée, y compris zéro, **Défilement automatique**
amène le prochain joueur encore à noter, selon la taille de cet appareil. Une saisie
active ou un défilement manuel suspend ce déplacement ; le bouton du prochain joueur
permet de reprendre. Le classement affiche au maximum cinq lignes, moins si la
hauteur manque ; son défilement permet de retrouver les autres joueurs.

## Réécouter pendant la revue

**Écouter** charge l'extrait exact de la manche à la demande, avec pause, progression,
durée, navigation et volume indépendants. Ce lecteur n'envoie rien aux autres joueurs.
La réécoute est aussi autorisée après les résultats via l'API privée.

**Écouter le morceau complet** nécessite un Bridge connecté et l'option locale
`--allow-full-review` ou `OPENBLINDYSIR_BRIDGE_ALLOW_FULL_REVIEW=true`. Le mode complet
est clairement indiqué ; **Revenir à l'extrait** retrouve la version de jeu.
L'intégralité est réencodée en segments d'au plus 30 s, seulement lors de l'écoute
ou d'un déplacement. Il peut y avoir une attente entre segments. Le fichier
complet reste sur le Bridge ; les segments ne sont pas stockés durablement au serveur.

Si le Bridge est indisponible, la source a changé, ou l'extrait exact n'est plus
reproductible après redémarrage, le lecteur affiche une erreur et **Réessayer**.
Une réécoute en échec reprend à la position demandée. Une déconnexion du Bridge
ou un upload rejeté termine rapidement l'attente en cours.
La notation continue. Ne remplacez pas une source pendant la partie si vous voulez
la réécouter intégralement ensuite.

## Arrêter et retrouver la session

**Arrêter la partie** est disponible pendant le jeu et le final. La confirmation
propose de revenir aux attributions ou de terminer avec les points déjà attribués.
Terminer arrête l’audio, conserve réponses/brouillons et points, publie les résultats
une seule fois et affiche directement le menu pour rejouer ou terminer la session.
Les attributions manquantes gardent leur valeur actuelle, initialement zéro ;
les présentations restantes et l’animation du podium sont sautées.

Les manches entendues puis annulées apparaissent dans le récapitulatif avec zéro.
Deux choix après les résultats : **Nouvelle partie avec les morceaux restants**
garde les exclusions musicales ; **Recommencer avec toute la bibliothèque** les
réinitialise après confirmation. Les deux gardent joueurs, équipes, paramètres,
corrections de métadonnées et archives. Un morceau annulé dès son allocation reste
consommé, même avant la première note ; le simple préchargement ne le consomme pas.
Les joueurs retirés sont libérés, leurs résultats archivés restent lisibles.
**Fin de session** révoque les cookies/codes et vide joueurs/partie/réserve après
confirmation ; archives et métadonnées restent conservées.

Le snapshot privé restaure identité, réponses, notes, réglages, métadonnées,
catalogues et historique des 50 dernières parties. Le cache audio RAM est perdu.
Une manche ouverte interrompue ferme ses réponses et indique l'interruption ;
un départ encore futur revient en préparation. Les Bridges se reconnectent et
régénèrent les extraits nécessaires. Un échec de sauvegarde est visible pour l'hôte.

## Dépannage

Les inscriptions sont limitées à 60 par IP/minute et 600 par serveur/minute,
même avec le bon mot de passe : attendez une minute après `rate_limited`.
Le plafond de joueurs simultanés reste `MAX_PLAYERS`. L'état conserve au plus
1 000 identités, retirées comprises, pour les résultats courants. À ce plafond,
`game_full` refuse les inscriptions ; Nouvelle partie après archivage ou Fin de
session libèrent les anciennes identités.

| Situation | Action |
|---|---|
| Erreur audio/autoplay | Réactiver le son, vérifier volume/sortie, garder l'onglet actif. |
| Reconnexion | Attendre l'accusé du serveur ; le dernier brouillon reçu est restauré. |
| Ouvert ailleurs | « Reprendre ici » dans l'onglet voulu ; un onglet actif par identité. |
| Bibliothèque trop petite | Réduire les manches, rescanner ou autoriser les répétitions. |
| Fichier écarté | Consulter le diagnostic privé ; vérifier audio, codec, durée, silence et chemin. |
| Certificat refusé | Vérifier l'adresse et la confiance du certificat ; garder TLS actif. |
| Mot de passe/code incorrect | Vérifier le mot de passe de partie et le code privé non utilisé. |

L'application reste en développement. Les essais automatisés utilisent des sons
synthétiques et des navigateurs sans sortie sonore vérifiée ; ils ne remplacent
pas un essai Safari/iPhone/Android ni une mesure acoustique avant la soirée.
Voir [testing](testing.md) et les vérifications exécutées dans [DEVLOG](DEVLOG.md).

## Bridges privés et historique V0.5

Chaque Bridge possède un UUID stable, un nom et son propre secret. L'hôte prépare
un fichier d'identité privé ; le propriétaire conserve sa racine musicale et son
choix d'écoute complète. Voir [les commandes V0.5](v0.5.md). Le panneau Bridges
présente connexion, capacités et erreurs par propriétaire, puis permet de révoquer
une identité avec confirmation. En jeu, l'hôte joueur n'a pas accès aux noms de
sources, à la bibliothèque ou aux archives ; le MC garde ses accès privés.
Une source aléatoire non préparée attend au plus 45 s après déconnexion, puis tente
une autre source disponible. Un choix manuel conserve son erreur et propose
remplacement, retour au hasard, saut ou fin ; un extrait déjà préparé peut continuer.

Après validation finale, **Historique** charge à la demande les parties conservées,
avec les noms et équipes de l'époque, réglages, réponses, temps, révélations et
scores corrigés. Les changements de bibliothèque et les nouvelles parties ne les
modifient pas. L'hôte peut consulter, exporter, supprimer une archive ou purger
l'historique, avec confirmation. Politique : 50 parties, 90 jours, 16 Mio, sans audio.
L'avertissement de sauvegarde indique si l'état durable n'est pas disponible.
Une suppression retire l'archive des deux snapshots gérés ; exports et backups
externes restent à supprimer séparément. Les résultats de la partie courante restent
visibles jusqu'à Nouvelle partie ou Fin de session.

Les liens d'évitement, le clavier, les confirmations avec Échap/retour du focus et
les commandes audio ont des libellés accessibles. Les parcours automatisés incluent
320 px et texte à 200 %. La recette NVDA/VoiceOver et les appareils physiques reste
à effectuer ; ces tests ne constituent pas une certification d'accessibilité.

## Nouveautés : notation et certificat LAN

Voir le [guide complet de notation automatique](notation-automatique.md) pour les
variantes acceptées, les références figées, le recalcul explicite et les vagues
d’attribution du final. Les scores ne sont pas révélés pendant la saisie.
Pour éviter l’alerte HTTPS locale sur les téléphones, suivre le
[guide d’approbation du certificat](certificat-local.md). L’accès LAN est conservé.

## Corrections du final et préparation des références

Le final sur PC place le contexte musical à gauche des réponses et garde le classement à droite lorsque la largeur le permet. Les listes s’adaptent au navigateur, le classement montre au maximum cinq personnes, et le défilement automatique garde sa préférence lorsqu’une lecture manuelle le met en pause. **Reprendre le défilement** réactive la progression. Les boutons restent utilisables au clavier et mesurent au moins 44 px.

La référence affichée en mode automatique est celle qui a servi à la notation, même si les informations du morceau ont été corrigées depuis. **Réévaluer** utilise les nouvelles références sans écraser les corrections manuelles. Un brouillon capturé avec la politique « décision de l’hôte » reste une suggestion : aucun point n’est attribué automatiquement. Les nombres supplémentaires inconnus ne permettent pas de gagner un titre numérique. Le seuil de ressemblance reste appliqué à chaque critère ; l’année est exacte.

Les raisons des attentes sont visibles sur les cartes. L’hôte peut annuler sa dernière correction déjà enregistrée tant que sa révision n’a pas été modifiée par un autre écran. Le podium propose d’abord de terminer les attributions restantes ; publier malgré les réponses en attente est une action explicite. Une partie sans points est annoncée comme terminée. Le déroulé du final indique révélation, écoute facultative, points, classement et manche suivante. Le rythme rapide et les préférences d’animations sont mémorisés dans chaque navigateur ; son coupé et mouvement réduit sont respectés.

La bibliothèque s’ouvre sur les morceaux et actualise les données à chaque ouverture ; les sources restent dans les outils avancés. Le filtre de qualité indique les références prêtes ou manquantes pour les critères de cette partie ; le filtre des sources permet de limiter la file de correction aux dossiers sélectionnés. Une référence absente n’est pas devinée à partir du nom du fichier pour la notation automatique. **Hériter** retrouve la valeur des sources, **Remplacer** saisit une valeur confirmée et **Effacer la référence** empêche sa réapparition depuis les imports ou tags audio. Les corrections concurrentes sont refusées et le brouillon local reste disponible. L’activation et les modifications groupées sont également protégées : un lot s’arrête au premier conflit, affiche combien de morceaux ont été enregistrés et conserve l’explication. Actualiser, comparer puis reprendre les éléments restants.

L’export est un pack ZIP de fichiers JSON limités à 1 Mio et 10 000 lignes. Un pack reste limité à 8 Mio et 10 000 lignes. Si nécessaire, **Télécharger le pack suivant** termine l’export de toute la collection. Chaque pack se réimporte séparément, sans extraire de fichiers sur le disque. Les JSON historiques restent acceptés avec leur limite de 1 Mio. Les imports ZIP chiffrés, les chemins arbitraires et les compressions autres que stockée/Deflate sont refusés.

Le contexte audio fermé peut être recréé après une action de l’utilisateur. Les requêtes obsolètes, sockets remplacés et contrôleurs démontés sont nettoyés. Une erreur provenant d’un ancien morceau ne remplace plus l’état de lecture du morceau courant. L’écoute privée et collective partagent le volume du navigateur. **Tester mon audio** et la récupération restent accessibles pendant le final.

## Soirées à thème

Dans **Préparer la partie → Musique**, composez une sélection par genre, langue, année, tags et univers. Le compteur utilise les mêmes critères que les manches. Les raccourcis génériques, Pop, Rap, français, anglais et 2012 facilitent la préparation ; combinez ensuite les listes et enregistrez votre sélection sous les filtres. Voir [le guide des soirées à thème](themed-nights.md) pour les métadonnées et les exemples.

## Préparer et corriger plus simplement (10 octobre 2026)

Le Bridge lit localement les tags titre, artiste, album, date/année et featuring
avant la partie, en arrière-plan (deux lectures simultanées, cinq secondes maximum
par fichier, cache par taille/date). Aucun fichier musical n'est modifié. Actualiser
la bibliothèque après l'analyse ; les corrections explicites et les champs effacés
restent prioritaires. Aucun artiste n'est déduit d'une réponse de joueur.

En notation automatique, **Jouer uniquement les morceaux prêts pour ces critères**
exclut les morceaux incomplets de la sélection. Un featuring demandé mais absent
compte comme référence manquante : choisir uniquement les critères adaptés à la soirée.

Au final, **Enregistrer et recalculer cette manche** ferme le formulaire après
confirmation du serveur et recalcule les critères automatiques. **Enregistrer sans
recalculer les points** conserve les notes actuelles. Les décisions manuelles sont
protégées par critère ; un total numérique manuel reste entièrement protégé. Les
anciennes corrections globales restent protégées après migration.

Un brouillon reconnu propose ses points, avec **Accepter les éléments reconnus**.
Les critères sans référence peuvent être **neutralisés pour tous les joueurs** de
la manche, après confirmation : zéro point pour ces critères, sans bloquer les autres.
**Réactiver** remet ces critères dans la notation. Les totaux saisis manuellement
restent inchangés ; vérifier leur cohérence avant publication.

Les deux réponses d'une petite partie s'affichent côte à côte sur ordinateur.
Le bouton « Prochain joueur à noter » avance depuis le joueur consulté. Une pause
manuelle du défilement est explicite ; lire un diagnostic ne suspend pas cette avance.
La correction privée indique aussi la manche visible des joueurs. Avant un podium
incomplet, le récapitulatif donne accès aux manches, brouillons et références à terminer.
Le bouton de test audio reste accessible pendant le final et confirme le lancement du
signal. Cette confirmation ne prouve pas que le haut-parleur de l'appareil est audible.

Compatibilité : protocole 14, snapshot 11, historique 3. Mettre à jour ensemble
serveur, interface et Bridge. Sauvegarder les volumes à l'arrêt avant mise à jour ;
un retour à une ancienne image exige de restaurer sa sauvegarde compatible.
