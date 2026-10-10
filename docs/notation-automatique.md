# Notation automatique et grand final

[English](automatic-scoring.en.md). Développement V0.5, protocole **14**, snapshots **11**.
Mettre à jour ensemble serveur, interface et Bridge. Les anciennes sessions sont
migrées avec la notation manuelle par défaut ; aucun ancien score n'est recalculé.

## Activer et configurer

Dans les paramètres, onglet **Règles**, choisir **Attribution des points →
Automatique, avec corrections de l'hôte**. Le mode manuel reste disponible.
Les modes Titre, Artiste et Titre et artiste sont conservés. **Informations à
reconnaître** permet de choisir titre, artiste, album, année et featuring, chacun
avec ses points. Le barème total ne dépasse pas 1 000 points par manche.
Les consignes libres ne définissent pas ces critères ; le mode personnalisé reste manuel.

Le joueur écrit dans **un seul champ**, dans l'ordre qu'il souhaite. La limite
par défaut passe à 1 000 caractères pour pouvoir fournir plusieurs informations ;
`ANSWER_MAX_CHARS` permet 20 à 1 500 caractères. Cette limite est contrôlée côté
serveur et affichée au navigateur ; la borne absolue du protocole est 1 500.

Le seuil est **90 %**, réglable de 80 à 100 %. Il s'applique **à chaque information**,
jamais à la moyenne de la réponse. Une année incorrecte ne peut pas être compensée
par un bon titre. Les points de chaque critère réussi s'additionnent.

## Reconnaissance et limites

Le moteur local ignore la casse, les accents, la ponctuation et les espaces entre
les mots. Il repère des fragments correspondant à chaque référence, puis calcule
`100 × (1 − distance Indel / somme des longueurs)` (moteur version 2).
Une insertion ou suppression coûte une opération ; une substitution en coûte deux.
Ainsi « validé » / « validée » atteint 92,308 %, accepté à 90 %, à vérifier à 95 %.
Les références de trois caractères maximum et les années restent exactes.
Ce pourcentage mesure la ressemblance du texte, **pas une probabilité de vérité**.
Il n'y a ni service d'IA externe ni envoi de réponses pour la notation.

- Seuil atteint : points du critère attribués automatiquement.
- Sous le seuil, dans une bande de dix points : vérification humaine requise.
- Aucune correspondance suffisante : critère non reconnu, zéro point automatique.
- Référence manquante : critère à vérifier, aucun point automatique pour celui-ci.
- Année : correspondance exacte ; plusieurs années proposées rendent le critère ambigu.
  Un nombre déjà reconnu comme titre ou album (par exemple « 1989 ») ne compte pas
  comme une proposition d'année supplémentaire.
- Référence ou variante de trois caractères maximum : correspondance exacte.
- Le moteur cherche une combinaison de fragments compatibles entre les critères.
  Un chevauchement inévitable pour deux références différentes et les listes explicites
  de propositions (« ou », « or ») restent à vérifier. Les séparateurs `/`, `;` et `|`
  entre des informations correctes sont acceptés. Deux critères ayant exactement la même référence
  peuvent partager un fragment.

Exemple, avec les références titre « Sapés comme jamais », artiste « Maître Gims »,
année 2015 et album « Pilule bleue » (ou cette variante d'album explicitement autorisée) :

```text
Sapéscomme Ja m ais Maitre Gims 2015 ft niska   pilule bleue
```

Les quatre critères atteignent 100 % après normalisation, soit quatre points pour
un barème d'un point par critère. Le featuring est reconnu si Niska est demandé ;
sinon `ft Niska` ne pénalise pas la réponse si Niska figure dans les métadonnées ou
les variantes du featuring. Plusieurs informations supplémentaires connues sont
acceptées ensemble. Un préfixe `ft` n'autorise pas des noms ou propositions inconnus :
ces réponses nécessitent une vérification. Une année absente ou incorrecte ne dispense
pas du contrôle des propositions textuelles supplémentaires.
« Sapés comme jamias » atteint 93,75 % et passe au seuil de 90 %, mais requiert une
vérification au seuil de 95 %. Le moteur conservateur peut laisser à vérifier des
réponses complexes ; l'hôte garde toujours la correction finale.

## Préparer les références et les variantes

Dans la bibliothèque, **Corriger les informations du morceau → Variantes acceptées** :
une variante par ligne, jusqu'à huit pour titre, artiste, album et featuring,
256 caractères par variante. Exemples : un nom de scène, un titre alternatif ou
une édition d'album réellement équivalente. Les variantes sont importées/exportées
avec les métadonnées JSON version 2 dans `aliases` :

```json
{"artist": ["Maître Gims", "Gims"], "album": ["Pilule bleue"]}
```

La préparation vérifie les références **pendant la modification**, pour les critères,
dossiers, filtres et répétitions actuellement choisis. Elle indique le nombre de
morceaux prêts, les champs manquants et des exemples. Corrigez la bibliothèque ou
acceptez explicitement de noter les références manquantes à la main avant de lancer.
Changer les critères ou la sélection demande une nouvelle vérification ; les
réglages peuvent être enregistrés sans lancer. Les tags du fichier peuvent encore
être enrichis lors de la préparation audio. Si le titre ou les artistes manquent,
le serveur tente de les extraire du nom du fichier : `Niska - Réseaux.mp3` donne
« Réseaux » et « Niska », et `feat.`/`ft.` identifie les invités. Un nom seul comme
`FE!N.mp3` fournit le titre, sans inventer l’artiste, l’album ou l’année. Ces
références servent aussi à la notation automatique. Vérifiez les noms ambigus ;
les tags, imports et corrections de l’hôte restent prioritaires. Un champ
explicitement effacé ne reçoit pas de repli.

Les règles, le seuil, les références et les variantes sont figés au premier lancement
de la manche. Modifier la bibliothèque ne change pas silencieusement sa notation.
Dans le final, modifier les références puis choisir **Enregistrer et recalculer
cette manche** permet un recalcul explicite. Seule cette manche est
recalculée ; les corrections manuelles sont conservées. Des points déjà montrés
peuvent alors changer. Le détail de reconnaissance conserve les références réellement
utilisées, le fragment détecté, le pourcentage et le seuil. Une ancienne analyse
reste consultable après correction manuelle et porte la mention **Corrigé par l'hôte**.

## Points privés, révélation collective

Les réponses définitivement validées sont notées côté serveur dès leur réception.
Les brouillons capturés sont évalués à la fermeture ; la politique `zero` impose
zéro aux réponses non validées. Les réponses absentes sont confirmées à zéro.
L'accusé de réception ne contient jamais la correction ni les points.

Dans le grand final, **Présenter la manche** dévoile le morceau et les réponses.
Pour une manche automatiquement notée, les points arrivent ensuite par vagues de
trois joueurs : première vague après 1,5 seconde, suivantes toutes les secondes.
Le classement utilise uniquement les points déjà dévoilés. L'hôte peut **Dévoiler
tous les points maintenant**. Passer à une autre manche termine la vague précédente ;
revenir en arrière ne répète aucune attribution. Les corrections manuelles restent
visibles en direct. Les dépassements sont annoncés, les positions animées et les
critères réussis affichés aux joueurs. Une correction négative n'utilise pas le son
de gain de points. Les animations respectent le réglage de mouvement réduit.

L'écoute collective, l'écoute privée, les effets sonores désactivables et
**Tester mon audio** restent accessibles. Le podium normal attend la fin de la
vague ; **Arrêter la partie** permet toujours de terminer avec les points existants.
Reconnexions et redémarrages conservent scores, règles et progression de révélation.
Le journal définitif est écrit une seule fois à la validation finale.

La comparaison possède un budget de calcul déterministe ; une réponse trop complexe
reste à vérifier, sans refus arbitraire de points. Les correspondances exactes restent
recherchées dans tout le champ. L'affectation examine au maximum 4 096 combinaisons
de fragments ; le contrôle des informations supplémentaires est également borné.
Les corrections du moteur s'appliquent aux nouvelles évaluations ; les analyses
existantes et les corrections manuelles ne sont pas recalculées à la mise à jour.

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

## Un final centré sur les réponses

La barre du bas propose une seule étape : présenter, terminer la notation de la
manche affichée, passer à la suivante, puis lancer le podium. **Toutes les manches**
permet de revenir en arrière en privé. **Options du final** contient le rythme
rapide, l’arrêt et la publication anticipée.

Chaque carte montre la réponse et les points. Pour plusieurs critères, **Tout bon**
ou **Tout faux** suffit ; **Noter chaque élément** permet une attribution partielle.
Une réponse déjà notée se modifie avec **Modifier les points**. Les pourcentages,
le temps de réponse et les ajustements numériques restent accessibles dans
**Détails**. Les réglages de défilement apparaissent seulement si la liste déborde.
Les références des manches déjà lancées restent figées : après une mise à jour,
utilisez l’éditeur et **Enregistrer et recalculer cette manche** pour appliquer
les nouvelles informations à une ancienne manche.
