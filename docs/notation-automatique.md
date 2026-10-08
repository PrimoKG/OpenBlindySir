# Notation automatique et grand final

[English](automatic-scoring.en.md). Développement V0.5, protocole **12**, snapshots **9**.
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
`100 × (1 − distance / longueur maximale)` avec la distance Damerau-Levenshtein.
Une suppression, insertion, substitution ou inversion de lettres coûte une opération.
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

Le lobby signale le nombre de morceaux sélectionnés dont les références connues
sont incomplètes, une fois les réglages enregistrés. Les tags du fichier peuvent
n'être connus qu'après préparation de l'extrait. Un nom de fichier seul n'est pas
une référence automatiquement fiable ; les critères manquants restent manuels.

Les règles, le seuil, les références et les variantes sont figés au premier lancement
de la manche. Modifier la bibliothèque ne change pas silencieusement sa notation.
Dans le final, modifier les références puis cocher **Recalculer cette manche avec
les nouvelles références** permet un recalcul explicite. Seule cette manche est
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
