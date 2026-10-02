# Utiliser OpenBlindySir

OpenBlindySir permet de jouer à un blind test entre amis, chacun dans son
navigateur. Une instance accueille une seule partie à la fois. Le serveur peut
tourner sur le PC de l'hôte ou sur un serveur distant :
[préparer l'hébergement](deployment.md). Aucun compte à créer.
Pour éviter d'installer Python, Node.js ou FFmpeg sur le PC, utilisez le
[lancement complet Docker](docker.md) : il ouvre aussi la page hôte automatiquement.

## Avant la soirée

La personne qui héberge prépare le serveur, le Bridge et son dossier musical.
Elle envoie aux joueurs **l'adresse de la partie et le mot de passe de la partie**.
Elle garde pour elle le mot de passe hôte et le secret du Bridge.

Pour un jeu à distance par VPN privé, les participants doivent d'abord rejoindre
le même réseau VPN. Pour une partie sur réseau local, les appareils doivent
pouvoir atteindre le PC hôte ; un Wi-Fi invité peut empêcher cette communication.
Sur un réseau privé, approuver le certificat fourni par l'hôte est une étape de
préparation expliquée dans le guide d'hébergement.

Chacun écoute dans son propre navigateur, même sur le même Wi-Fi. Utilisez un
casque si vous êtes ensemble ou dans un appel vocal pour éviter que plusieurs
extraits se superposent. Le navigateur doit rester actif pendant le jeu.

## Rejoindre et vérifier le son

1. Ouvrez l'adresse envoyée par l'hôte.
2. Choisissez un **Pseudo**, de 24 caractères au maximum, et saisissez le
   **Mot de passe de la partie**. Cliquez sur **Entrer**.
3. Dans le lobby, cliquez sur **Tester mon audio**. Vous devez entendre un bip.
4. Cliquez sur **Je l'entends ✓** après avoir réellement entendu le bip. Ajustez
   le volume avec le curseur ; vérifiez aussi le volume de l'appareil et du casque.
5. Attendez le lancement par l'hôte. La liste indique qui a rejoint la partie.

Si le bip ne démarre pas, utilisez le bouton de reprise audio et vérifiez la sortie
sonore. Le jeu reste accessible pendant une erreur audio. Sur les navigateurs
mobiles, un geste peut être nécessaire à nouveau après une interruption.

## Jouer une manche

- **Préparation de l'extrait…** : le Bridge prépare le morceau.
- **Chargement de l'extrait…** : les navigateurs téléchargent et décodent le son.
- Le **compte à rebours** annonce le départ. Pendant la lecture, le disque tourne
  et la progression de l'extrait est visible.
- Saisissez librement le titre, l'artiste ou ce que votre groupe attend dans
  **Ta réponse**. Le texte reste un brouillon : vous pouvez le modifier.
- Cliquez sur **VALIDER**, ou appuyez sur Entrée dans le champ, quand vous êtes
  sûr. **Cette validation est définitive pour la manche.** Une réponse vide ne
  peut pas être validée. Attendez **✓ Réponse enregistrée**.

**Extrait terminé** signifie que le son est terminé ou a été arrêté. Tant que le
champ reste ouvert, vous pouvez encore répondre pendant le délai restant.
L'hôte peut fermer les réponses ; le serveur décide toujours de la fin de la
manche, y compris si un message arrive trop tard.

Avant la révélation, vous ne voyez pas les réponses, les temps ni les rangs de
réponse des autres joueurs. Le compteur « n/m ont validé » est anonyme ; il
n'apparaît pas quand moins de trois joueurs sont attendus. L'absence du compteur
n'est donc pas une panne.

Si la manche se ferme avec un brouillon non validé, l'hôte peut voir ce texte
capturé et choisir de lui attribuer des points. Il est marqué **(non validée)**,
sans temps de réponse validée. Votre propre réponse reste visible pendant l'attente.

## Révélation et résultats

Pendant **L'hôte note les réponses…**, attendez : rien n'est encore publié.
Après publication, l'écran affiche le morceau, les réponses, les temps, les points
et le classement. Le signe **≈** indique des réponses très proches dans le temps ;
la vitesse n'attribue jamais automatiquement des points.

Après la dernière manche, **L'hôte vérifie les scores…** annonce la vérification
finale. Le classement affiché reste celui déjà publié pendant que l'hôte prépare
ses corrections. Ensuite apparaissent le podium, les totaux et les ajustements
finaux. Des joueurs ex æquo partagent leur rang.

## Animer en tant qu'hôte

### Préparer la partie

1. Rejoignez la partie comme les autres, puis utilisez **Accès hôte** ou l'adresse
   de la partie suivie de `/host`. Saisissez le **Mot de passe hôte**.
2. Ouvrez **Commandes hôte** si le panneau est replié. Sur téléphone, le lien du
   même nom dans l'en-tête permet d'y accéder rapidement.
3. Choisissez votre rôle via **Changer de rôle**, quand le changement est autorisé :
   **Hôte joueur** pour répondre, **Animateur** pour animer sans jouer.
4. Vérifiez **Bibliothèque connectée** et choisissez les dossiers musicaux. Si
   aucun Bridge n'est connecté, démarrez-le avant de lancer la partie.
5. Réglez **Nombre de manches**, **Durée des extraits (s)** et le temps pour
   répondre après l'extrait. Choisissez la consigne, le barème et la politique des
   brouillons non validés. Le compteur indique les morceaux neufs disponibles.
6. Utilisez **Enregistrer et lancer** pour appliquer les réglages et démarrer
   ensemble, ou **Enregistrer** puis **Lancer la partie**. Sans répétitions, réduisez
   le nombre de manches si la réserve est insuffisante.

L'hôte joueur conserve la surprise du morceau pendant le jeu et répond comme les
autres. Le MC voit le morceau et peut consulter **À venir** ; pendant la saisie il
voit qui a validé, sans lire les textes avant la revue.

### Diriger et noter les manches

Les commandes disponibles suivent l'étape du jeu. Pendant la préparation, le
compteur audio indique combien de joueurs sont prêts ; **Lancer quand même**
apparaît si le serveur autorise ce choix. Pendant une manche, vous pouvez arrêter
ou rejouer l'extrait, ajouter du temps ou fermer les réponses selon les commandes
affichées.

Lors de la revue, lisez les réponses et attribuez les points manuellement. Les
boutons **0 / +1 / +2 / +3** sont des raccourcis ; le champ numérique permet aussi
d'autres valeurs, y compris négatives. Une indication de retard audio aide à
interpréter le temps. En mode joueur, notez également votre propre réponse.
Cliquez sur **Publier** quand les scores de la manche sont prêts. Cette action
révèle le morceau et les réponses à tous. Passez ensuite à la manche suivante.

**Autres actions sur la manche** regroupe le saut d'une manche, l'annulation de
publication quand elle est encore permise et la fin anticipée. Terminer en notant
la manche mène à sa revue ; terminer en l'abandonnant n'en attribue pas les points.
Dans les deux cas, la vérification finale reste obligatoire.

**Ajuster** permet une correction manuelle supplémentaire avec confirmation.
**Participants et connexion** affiche les états audio et réseau et permet de
retirer un joueur. **Diagnostic** fournit les informations techniques et leur
copie pour le dépannage ; ces outils restent secondaires au déroulement du jeu.

### Vérifier et terminer

La revue affiche le titre et l'artiste **uniquement aux hôtes**, après fermeture des
réponses. **Corriger le titre et l’artiste** permet de préparer un reveal propre.
Chaque ligne est **À vérifier** jusqu'à une décision explicite, même si elle vaut zéro.
Le champ ±N conserve votre saisie jusqu'à Entrée ou sortie du champ ; attendez la
sauvegarde serveur avant de publier. Si des lignes restent non vérifiées, une confirmation
indique leur nombre. Le total publié et le total provisoire sont affichés séparément.

Dans **VÉRIFICATION FINALE DES SCORES**, comparez le score actuel, la correction
et le nouveau score. Utilisez les boutons −/+ ou le champ numérique, consultez
le détail, et réinitialisez les corrections si nécessaire. Les joueurs ne voient
pas ce brouillon. Cliquez sur **VALIDER LES SCORES ET AFFICHER LES RÉSULTATS**,
relisez le récapitulatif et confirmez.

Après les résultats, **Nouvelle partie** retourne au lobby. **Fin de session**,
après confirmation, renvoie tout le monde à l'entrée. Une nouvelle session sur
`/host` demande de nouveau l'élévation hôte. Le serveur sauvegarde la session
localement. Après redémarrage, scores et
réponses sont récupérés ; une manche interrompue revient en correction. Le statut
de récupération ou d'échec de sauvegarde est affiché dans les commandes hôte.

## Si quelque chose se passe mal

**Nouvelle partie** remet les scores à zéro et garde les morceaux déjà entendus exclus.
Pour continuer avec une petite bibliothèque, autorisez les répétitions ou réduisez le
nombre de manches. Une réserve épuisée propose ces choix explicitement.

Au lobby, **Inviter les joueurs** crée un lien et un QR code depuis l'adresse réseau
que vous choisissez. Le mot de passe se partage séparément. **Équipes et spectateurs**
permet de regrouper les scores individuels ou d'écouter sans répondre. Les sélections
enregistrées restent dans ce navigateur.

**Mettre en pause** suspend son et réponses. **Reprendre la manche** les relance ensemble,
sans compter la suspension dans les temps de réponse. Les résultats contiennent un
récapitulatif par joueur et les exports CSV/JSON ; l'hôte retrouve les parties terminées
dans l'historique. Les fichiers illisibles/silencieux rencontrés sont listés dans
**Fichiers écartés pendant cette partie**. Les options volume/silence sont dans les
réglages avancés et nécessitent un Bridge à jour.

| Situation | Que faire |
|---|---|
| Mot de passe incorrect | Vérifier le mot de passe de partie avec l'hôte ; le mot de passe hôte est distinct. |
| Serveur injoignable | Utiliser Réessayer ; vérifier que le PC hôte est allumé, que le lanceur tourne et que le VPN/réseau est accessible. |
| Erreur audio | Réactiver ou réessayer le son ; vérifier le volume, le casque et la connexion. |
| Reconnexion… | Garder l'onglet ouvert. Une validation en attente n'est acquise qu'après l'accusé du serveur. |
| Page rechargée | La session et le dernier brouillon reçu par le serveur sont restaurés si la session est encore valide. Du texte non transmis peut être perdu. |
| Ouvert ailleurs — reprendre ici | Cliquer Reprendre ici dans l'onglet qui doit jouer ; un seul onglet actif par joueur. |
| Retiré de la partie | Contacter l'hôte : celui-ci a retiré le joueur de la session. |
| Certificat refusé | Faire vérifier l'adresse et installer correctement le certificat privé prévu ; ne pas désactiver la vérification TLS. |

L'application est encore en développement. Les parcours Chromium et l'affichage
WebKit sont vérifiés sur des tailles de téléphone. Ce moteur WebKit Windows ne
valide pas la lecture audio. Pour Safari et les vrais appareils iOS/Android,
faites un essai avant la soirée. Les mesures acoustiques restent à réaliser.
