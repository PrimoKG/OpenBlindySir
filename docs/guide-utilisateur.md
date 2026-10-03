# Utiliser OpenBlindySir — V0.5 — développement

[English guide](user-guide.en.md). Une instance accueille une partie à la fois,
entre amis dans leur navigateur, sur LAN, VPN ou Internet. Aucun compte à créer.
Préparez [l'hébergement](deployment.md) ou le [lancement Docker](docker.md).
Mettez à jour serveur, Bridge et interface ensemble : **protocole 5**.
Le Bridge s'installe sans clone après publication, par [uvx ou archive native](bridge-installation.md).

## Préparer et rejoindre la soirée

L'hôte partage l'adresse et le **mot de passe de la partie** ; il garde le mot de
passe hôte. Chaque propriétaire de Bridge reçoit son propre
[fichier d'identité privé](bridge-installation.md#première-configuration), à conserver
sur son appareil ; ne le partagez pas avec les joueurs. En LAN/VPN, préparez la confiance du certificat
selon le guide réseau. Chaque joueur écoute dans son navigateur, idéalement au casque.

1. Entrez un pseudo (24 caractères maximum) et le mot de passe, puis **Entrer**.
2. Dans le lobby, **Tester mon audio**, puis **Je l'entends ✓** après le bip.
3. Ajustez le volume. Gardez le navigateur actif pendant les manches.

Le choix Français/English est mémorisé localement. **Correction audio (ms)**
compense une sortie lente : une valeur positive avance la prochaine lecture,
une valeur négative la retarde (−500 à +500 ms). Commencez à zéro ; par exemple
+150 ms pour une sortie Bluetooth en retard de 150 ms. Le réglage n'interrompt
pas une lecture en cours, persiste dans ce navigateur et ne modifie jamais le
temps de réponse officiel ni les points. La compensation physique reste à mesurer.

**Créer un code de récupération** crée un code privé de six caractères.
Gardez-le pour changer d'appareil ou retrouver votre place si le cookie est perdu.
À l'entrée, **Retrouver ma place** demande le code et le mot de passe de partie.
Le code s'utilise une seule fois ; en recréer un invalide le précédent. Les anciens
onglets sont déconnectés. Vos réponses et votre identité restent conservées ;
un ancien hôte doit saisir à nouveau le mot de passe hôte. La récupération reste
possible lorsque les inscriptions sont verrouillées. Un joueur retiré ne peut pas revenir ainsi.

## Jouer les manches

**Préparation**, **Chargement**, compte à rebours, puis lecture synchronisée.
Écrivez dans **Ta réponse** et utilisez **VALIDER** ou Entrée. La validation est
définitive ; attendez **✓ Réponse enregistrée**. Le texte non validé est un brouillon
synchronisé ; après fermeture, le dernier texte reçu devient **Brouillon capturé**.
Il n'a ni rang officiel ni temps de validation, et ne reçoit aucun point automatique.

La fin du son ne ferme pas nécessairement les réponses : le délai restant est
affiché. L'hôte peut suspendre son et réponses, reprendre, rejouer, ajouter du temps
ou fermer. La pause n'entre pas dans les temps de réponse.

Après chaque manche, **Réponses conservées** confirme l'enregistrement. L'hôte
passe à la suivante. **Tous les morceaux et points sont révélés après la revue
globale de fin de partie**. Avant cela, vous ne voyez que votre propre réponse.
Le compteur anonyme n/m est masqué lorsque moins de trois joueurs sont attendus.

## Préparer la partie comme hôte

Sur `/host` ou **Accès hôte**, entrez le mot de passe hôte, puis ouvrez
**Commandes hôte**. Choisissez **Hôte joueur** pour jouer avec les mêmes protections
anti-spoiler, ou **Animateur** pour voir morceaux à venir et réponses en direct.
Passer animateur en cours de partie est permis entre les manches ; revenir joueur
attend la prochaine partie. Les spectateurs écoutent et voient les résultats sans répondre.

Choisissez les dossiers dans l'arborescence, le nombre de manches, la durée des
extraits, le délai de réponse, la consigne/barème et la politique des brouillons.
Cocher parent et enfant ne double pas les morceaux. Le compteur indique les
morceaux disponibles et encore inédits pendant la session. **Enregistrer et lancer**
applique le tout atomiquement. Une sélection trop petite propose de réduire les
manches ou d'autoriser les répétitions. Les sélections favorites restent locales.

Dans les options avancées : pause/reprise déjà disponible, **Normaliser le volume**,
**Éviter les extraits silencieux** et **Équilibrer les dossiers**. L'équilibrage
alterne les dossiers sélectionnés, mélangés en interne, jusqu'à épuisement ; les
morceaux restent uniques. Pour une sélection de la racine, il utilise les dossiers
contenant les fichiers. Aucun barème de rapidité n'est automatique.

Configurez équipes et spectateurs au lobby. **Fermer les inscriptions**
empêche de nouveaux joueurs d'entrer ; reconnexion et récupération restent possibles.
Le verrou peut être retiré depuis le panneau hôte, quelle que soit la phase.

## Gérer les sources et rechercher

Trois choix distincts :

1. **Dossier accessible** : racine locale autorisée au Bridge, ou montage Docker.
2. **Dossiers scannés** : sous-dossiers publiés dans son catalogue.
3. **Dossiers sélectionnés** : ceux cochés pour la prochaine partie.

Dans **Sources et recherche de bibliothèque**, ajoutez/retirez des sous-dossiers relatifs et
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
dossiers garde les ancêtres dans l'arbre ; les pages de morceaux contiennent au
plus 100 résultats. Cette bibliothèque reste réservée aux hôtes au lobby, en revue
finale et aux résultats, ou au MC pendant le jeu.

Les fichiers MP4/MOV/MKV/AVI et autres conteneurs autorisés fournissent **uniquement
leur première piste audio**. Aucune vidéo, pochette ou tag n'est envoyé aux joueurs.
Un fichier sans audio est écarté avec un diagnostic privé. Formats, tailles,
codec manquant et fichier facultatif de métadonnées : [guide des sources](media-and-metadata.md).

## Choisir un morceau comme animateur

Dans **Commandes hôte → Sources et recherche de bibliothèque**, le mode
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

## Revue globale et publication

La dernière manche ou **Arrêter la partie** ouvre **REVUE DE FIN DE PARTIE**.
La navigation affiche toutes les manches entendues : recherchez un morceau,
choisissez une manche ou utilisez précédent/suivant. Les joueurs attendent.

Chaque réponse indique validation ou brouillon capturé, temps officiel/rang si
disponibles, heure de réception serveur et retard audio connu. Une donnée absente
reste « — ». Les joueurs retirés ayant participé restent dans cette revue.
Corrigez titre, artiste, featuring, album et année si nécessaire.

Choisissez **0 / +1 / +2 / +3** ou un entier signé entre −1000 et +1000. Zéro choisi
est **Vérifié** ; zéro par défaut reste **À vérifier**. Entrée ou sortie du champ
envoie la note au serveur. Attendez **Enregistré** : la navigation et la validation
attendent la sauvegarde. Les notes reçues survivent au rafraîchissement, à la
reconnexion et aux snapshots. Du texte local non envoyé peut être perdu.

Les totaux provisoires additionnent toutes les manches et les corrections finales.
Les équipes additionnent les points individuels. La politique de brouillons
`manual` permet une décision humaine ; `zero` impose zéro, à vérifier explicitement.
Les corrections finales −/+ sont facultatives ; **Réinitialiser les corrections**
réinitialise ces corrections, pas les notes par manche.
Ces raccourcis et la remise à zéro attendent aussi l'accusé serveur avant une
nouvelle modification ou la publication.

**VALIDER LES SCORES ET AFFICHER LES RÉSULTATS** demande une confirmation avec les
totaux et le nombre de réponses restant à vérifier. Confirmer celles-ci conserve
leurs valeurs actuelles, initialement zéro. La publication est unique et fige les
scores. Tous voient alors morceaux, réponses, temps, points, classement, équipes
et récapitulatif ; les exports CSV/JSON reprennent exactement ces résultats.

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

**Arrêter la partie** reste accessible avant le premier morceau, pendant la
préparation, la lecture, la pause et la revue. La confirmation explique les effets :

| Moment | Conséquence |
|---|---|
| Lobby, avant tout morceau | Revue vide, puis validation finale possible. |
| Préparation/chargement/compte à rebours | Manche non entendue annulée, pas de points. |
| Lecture/saisie/pause | Son arrêté, validations et derniers brouillons conservés, manche à noter en revue globale. |
| Option « terminer sans noter cette manche » | Manche entendue conservée, annulée et exclue des points. |
| Réponses déjà fermées | Toutes les manches jouées conservées. |
| Revue globale déjà ouverte | Notes et corrections inchangées. |

Aucun arrêt ne publie les résultats. Un double clic est sans effet supplémentaire.
Les manches entendues puis annulées apparaissent dans le récapitulatif avec zéro.
**Nouvelle partie** garde les joueurs encore inscrits, la bibliothèque et les morceaux
déjà entendus pendant la soirée. Les identités des joueurs retirés sont libérées,
leurs résultats archivés restent lisibles. **Fin de session** révoque cookies/codes et vide joueurs, partie et morceaux
entendus, après confirmation. Les archives et métadonnées de bibliothèque restent conservées.

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
