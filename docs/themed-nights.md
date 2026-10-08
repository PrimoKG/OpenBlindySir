# Préparer une soirée à thème

Dans **Préparer la partie → Musique**, sélectionnez les dossiers puis utilisez
**Compose ta soirée**. Les raccourcis proposent les génériques de dessins animés,
Pop, Rap, français, anglais, 2012 et les années 2010. Ils remplacent les critères
précédents ; ajoutez ensuite vos autres critères dans les listes.

- **Rap + français + 2012** : genre Rap, langue français, début et fin à 2012.
- **Pop ou Rap, en anglais** : ajoutez Pop et Rap dans Genre, puis anglais dans Langue.
- **Génériques** : choisissez le dossier de génériques et le raccourci correspondant.
  Il propose de deviner le titre de la série, avec des extraits de 12 secondes.
- **Un univers précis** : ajoutez la série, le jeu ou l’anime dans Séries, jeux et univers.

Plusieurs choix d’une catégorie sont réunis ; les catégories se combinent. Les
mots-clés recherchent tous les mots, sans tenir compte de l’ordre, de la casse ou
des accents, dans les noms de fichiers et métadonnées. Les années sont inclusives.
Rap reconnaît également Hip-Hop ; les langues reconnaissent notamment `fr`,
Français, French, `en`, English et Anglais.

Le compteur et les exemples utilisent le même filtre que le tirage réel des
manches. Les morceaux désactivés, indisponibles ou sur un Bridge hors ligne ne
sont pas jouables. Les dossiers qui se chevauchent sont comptés une fois. Les
morceaux déjà entendus restent exclus, sauf si les répétitions sont autorisées.
Enregistrez un nom dans **Sélections enregistrées**, sous les filtres, pour retrouver
la préparation dans ce navigateur. **Enregistrer** conserve les paramètres dans la
session ; **Enregistrer et lancer** prépare puis démarre la partie.

## Classer et retrouver des morceaux

**Sources et recherche de bibliothèque** propose les mêmes raccourcis et des
filtres genre, langue et intervalle d’années, en plus des filtres existants. Triez
par titre, artiste, année, genre ou langue. Une année inconnue reste en fin de liste
dans les deux sens de tri. La liste reste paginée et adaptée à l’écran.

En dehors d’une partie en cours, **Utiliser ces filtres pour la prochaine partie**
transfère les critères thématiques et le dossier à la préparation. Les autres
filtres de consultation — extension, disponibilité, activation, qualité, état de
consommation — restent propres à la bibliothèque ; les morceaux désactivés et
indisponibles sont de toute façon exclus du jeu.

**Corriger les informations du morceau** permet de saisir le genre et la langue
sans modifier le fichier. Pour classer plusieurs morceaux, sélectionnez les cases
de la page puis ajoutez les genres, langues, tags ou univers dans les actions par
lot. Ces ajouts conservent les catégories existantes ; utilisez l’éditeur individuel
pour remplacer ou vider un champ. La préécoute privée de 15 secondes reste centrée
sur le milieu du morceau et ne consomme aucune manche.

## Métadonnées incomplètes

Une langue, un genre ou une année inconnus ne peuvent pas satisfaire un filtre
portant sur ce champ. Le compteur signale les morceaux à compléter. **Langue à
renseigner** sélectionne les langues inconnues ; un morceau instrumental peut
être marqué `zxx`. L’année correspond au morceau ou à sa version choisie,
pas automatiquement à l’année de création de la série. Renseignez des valeurs
vérifiées ; le nom du dossier ne prouve pas une langue, un genre ou une année.

Les anciens tags exactement reconnaissables, par exemple Rap ou Français,
fournissent un repli lorsqu’aucun genre ou langue explicite n’existe. Une liste
structurée vide bloque ce repli. Les métadonnées JSON version 3 acceptent
`genres` et `languages` ; les imports versions 1 et 2 restent acceptés.
Voir [le format des métadonnées](media-and-metadata.md).

## Mise à jour

Cette évolution utilise le protocole **11** et le snapshot **9**. Mettez à jour
serveur, Bridge et interface ensemble, après sauvegarde, puis rechargez les
onglets existants. Les snapshots 1 à 8 sont migrés. Pour revenir au protocole 10,
restaurez sa sauvegarde au format 8 ; une ancienne image ne peut pas lire le format 9.

Les chemins des fichiers déterminent leur identité. Pour organiser une soirée,
privilégiez les tags et les métadonnées de l’app : déplacer ou renommer les
fichiers nécessite un rescan et la réassociation de leurs métadonnées.
