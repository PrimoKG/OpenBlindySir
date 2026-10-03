# Parcours UX/UI — V0.5, 2026-10-03

Protocole 4. Décisions : [ADR 0011](adr/0011-global-review-and-private-replay.md),
[ADR 0012](adr/0012-dynamic-sources-and-metadata.md),
[ADR 0013](adr/0013-bridge-distribution.md) et
[ADR 0014](adr/0014-manual-mc-selection.md). Les règles et permissions
viennent du serveur ; le navigateur affiche les actions permises.

## Préparer et gérer les sources

La sélection de dossiers affiche total/disponible/neuf et élimine le double
comptage parent/enfant. Recherche d'arbre au clavier, presets locaux, barème/consigne,
équipes/spectateurs, QR privé sans mot de passe, réglages et lancement atomique.
La bibliothèque repliable distingue montage accessible, dossiers scannés et
sélection de partie. Ajout/retrait/rescan par Bridge, retours de demande puis
comptes reçus, filtre Bridge/dossier/type/disponibilité, recherche, pagination,
états vide/chargement/erreur et diagnostics d'import par ligne.

Le scan ne peut pas étendre la racine autorisée ; le message d'un dossier
inaccessible explique le montage et la recréation du seul Bridge. L'hôte joueur
perd l'accès aux noms de morceaux à venir pendant IN_GAME. Le MC voit les réponses
en direct et ne participe pas au score.

## Choisir une manche en animateur

Dans la bibliothèque, choisir un numéro de manche puis rechercher/filtrer les
pistes. Chaque résultat montre sa source, son dossier, ses métadonnées disponibles,
son format et sa durée mesurée, ainsi que les états joué/réservé/indisponible.
Un choix manuel contourne explicitement l'alternance aléatoire des dossiers ;
les règles de répétition et de sources restent appliquées.

Le choix attend l'accusé serveur avec une échéance fixe de dix secondes.
Pendant cette attente, les commandes de lancement restent désactivées. La liste
numérotée affiche ensuite « Choix enregistré » ; une manche manuelle prête attend
« Lancer maintenant ». L'extrait demandé verrouille le choix, y compris en
préchargement. Un échec conserve le choix et propose remplacement, retour au
hasard, passage ou arrêt. Aucun remplacement n'est automatique.

La liste et la recherche réutilisent composants, labels et focus visibles sur
mobile. Les contrôles sont testés au clavier à 320 px, avec confirmation,
verrouillage, expiration de l'accusé et traduction anglaise. Ces informations
restent dans la vue MC ; joueurs et hôte joueur ne les reçoivent pas en jeu.

## Configurer et diagnostiquer le Bridge

Une seule entrée CLI pour uvx et les archives. L'assistant français demande serveur,
racine musicale, secret masqué et nom, puis résume les champs sans révéler le secret.
Il demande confirmation pour sauvegarder, puis annonce et demande les contrôles
FFmpeg, le scan des noms et l'enregistrement hors partie. Aucun extrait n'est créé.
Une configuration existante reçoit une sauvegarde privée avant remplacement.

Aide/version/check-config ne créent rien ; doctor local ne scanne pas. Le test de
connexion explicite se ferme ensuite et indique de lancer run. Les erreurs donnent
un code stable, une action et le guide. Les sorties guidées s'adaptent aux terminaux
étroits ; un terminal sans saisie masquée refuse l'assistant. Les diagnostics JSON
copiables excluent adresse, UUID, chemins, noms de fichiers et secrets.

## Jouer et terminer

Pause/reprise synchronisées, distinction fin de son/deadline, validation définitive
et propre réponse restaurée. Chaque fermeture garde les réponses sans notation ni
reveal. L'arrêt confirmé reste visible dans toutes les phases, préserve les manches
entendues et mène à la revue globale ; aucun point n'est publié automatiquement.
Les commandes obsolètes de publication par manche sont refusées.

## Revue globale

Navigation par manche avec titre, numéro et progression de vérification, recherche,
précédent/suivant ; colonne dédiée sur ordinateur et liste compacte sur mobile.
Le morceau garde son contexte, les réponses leurs statuts, réception serveur,
temps/rang validés et retard audio. Les absences restent explicites. Une manche
entendue annulée est conservée avec points désactivés.

Boutons rapides et entier signé ±1000, zéro explicite, sauvegarde après Entrée ou
sortie du champ. La navigation/publication attend le serveur ; timeout et échec
affichés avec possibilité de nouvelle saisie. Les totaux provisoires par joueur
et équipe et corrections finales se mettent à jour avec les vues autoritaires.
La confirmation finale récapitule totaux et lignes non vérifiées. Les résultats
figent les notes et alimentent récapitulatif, historique et CSV/JSON.

Le lecteur privé charge seulement à la demande ; pause, progression, durée,
navigation, volume et erreurs accessibles. Extrait exact vérifié par hash,
mode complet explicite avec retour à l'extrait, segments ≤30 s. Aucun message
de lecture aux joueurs ; changer de manche annule le transfert et libère le Blob.

## Préférences et récupération

Français/English et latence manuelle ±500 ms persistées localement. Latence positive
avance la prochaine lecture, n'affecte pas celle en cours ni le timing officiel.
Code de récupération privé à six caractères, avec mot de passe, usage unique,
sans élévation hôte. Verrou d'inscription distinct de la reconnexion.
Snapshots : notes et bibliothèque retrouvées ; interruption signalée, audio régénéré.

## Accessibilité et limites

Boutons natifs, labels, focus visible, dialogues de confirmation, statuts textuels
et régions de notification ; styles communs papier/encre/terre cuite. Les tableaux
s'adaptent au mobile, cibles 44 px minimum, navigation utilisable au clavier.
Tests sur 320, 390 et 1280 px, textes longs, confirmations, anti-spoiler et erreurs.
Voir [DEVLOG](DEVLOG.md) pour les checks réellement exécutés. Les navigateurs
headless ne valident ni une sortie sonore physique ni la synchro acoustique ;
WebKit Windows ne remplace pas un iPhone. Aucun audit WCAG complet revendiqué.

## Parcours et accessibilité V0.5

Historique privé chargé à la demande : liste datée, archive, export, suppression et
purge confirmées, états chargement/vide/erreur/sauvegarde indisponible. Bridges :
connexion/capacités/erreurs par UUID, consignes hors ligne et révocation ciblée.
Les noms de sources et archives restent masqués à l'hôte joueur pendant IN_GAME.
Le diagnostic contient des informations privées : avertir avant toute copie publique.

Liens d'évitement vers la scène et commandes hôte, annonces discrètes de phase,
focus après transition seulement si le contrôle actif disparaît, libellés explicites
du volume et de la position audio. Confirmations : focus initial sur Annuler,
Échap annule, retour au déclencheur connecté. Focus visible, retours à la ligne,
contrastes existants conservés, mouvements réduits et boutons adaptés au tactile.
Tests navigateur : clavier/Échap, focus, rôle/nom/état, 320 px et texte à 200 %.
Recette manuelle NVDA/VoiceOver, zoom navigateur et appareils physiques à terminer ;
ne pas présenter les contrôles automatisés comme une certification WCAG.
