# Passe UX/UI — 2026-10-02

Cette intervention améliore l'application existante selon les contraintes de
[la spécification](architecture.md), sans modifier le protocole, les permissions,
les scores, les transitions métier ou le moteur audio. Aucune dépendance ajoutée.

## Inspection et frictions

Le frontend repose sur React, des composants locaux (`Button`, `AudioBadge`,
`LiveRegion`, `ConfirmDialog`, `Toast`) et une feuille CSS commune. Les écrans
suivent déjà les vues filtrées du serveur. Il n'existe pas de bibliothèque de
composants à remplacer ni de système d'icônes à étendre.

Les frictions retenues sont la juxtaposition des commandes hôte et des réglages
techniques, la faible hiérarchie entre les états d'une manche, le déverrouillage
audio qui recouvre le jeu, les tableaux difficiles à lire sur téléphone et le
manque de repères lors d'une erreur ou d'une reconnexion.

## Direction visuelle et plan appliqué

1. Définir une grammaire dans le CSS commun et factoriser les repères utiles.
2. Prioriser l'entrée, le test audio et le cycle de réponse du joueur.
3. Placer les commandes hôte dans le contexte de la manche, avec la notation et
   la publication au premier plan lors de la revue.
4. Regrouper les réglages, options de manche et diagnostics dans des disclosures
   natifs, puis vérifier les parcours réels et les cas limites d'affichage.

La palette associe un fond papier `#f6f3eb`, des surfaces blanches, une encre sombre
`#292c26` et un accent terre cuite `#b74728`. L'accent signale l'action principale
et le focus. Les erreurs et avertissements disposent aussi d'un texte explicite.
Le corps est à 17 px ; les titres utilisent Georgia, présente sur le système.
Un disque dessiné en CSS sert de signature commune à l'entrée, à l'audio et à la
révélation. Son animation cesse avec `prefers-reduced-motion`.

Le jeu occupe une surface principale. Sur ordinateur, l'hôte conserve ses
commandes à côté du jeu ; sur téléphone elles suivent le jeu avec un lien
d'accès direct. La revue et la vérification finale prennent toute la largeur.
Les tableaux restent sémantiques, avec des lignes réorganisées pour le mobile.
Les boutons visibles ont une cible d'au moins 44 × 44 px. Les confirmations
utilisent le dialogue natif, un titre accessible et un focus initial sur Annuler.

## Parcours et informations autorisées

| Étape | Joueur | Hôte joueur / MC |
|---|---|---|
| Entrée | Pseudo, mot de passe partagé, erreur explicite, attente de connexion | Accès hôte et formulaire d'élévation distincts |
| Lobby | Test sonore, confirmation entendue, volume, participants et attente | Réglages essentiels et dossiers ; lancement après enregistrement |
| Préparation / chargement | État et consigne d'attente | État du jeu et commandes permises ; démarrage forcé si autorisé |
| Compte à rebours | Départ annoncé visuellement et au lecteur d'écran | Même repère temporel |
| OPEN | Lecture ou fin de l'extrait, délai restant, brouillon modifiable et validation définitive | Hôte joueur : même saisie ; MC : progression par joueur sans texte de réponse |
| REVIEW | Sa propre réponse seulement, mention du brouillon capturé, attente | Réponses, temps, quasi-ex æquo, retard audio et notation manuelle ; publier après la table |
| REVEALED | Morceau, réponses, temps, points et classement reçu du serveur | Suite de la partie selon les commandes disponibles |
| Vérification finale | Attente et classement publié, sans brouillon de correction | Score actuel, correction, résultat, détail et confirmation |
| Résultats / fin | Podium utilisant les rangs du serveur, totaux et corrections | Nouvelle partie ou fin de session confirmée |

Le compteur anonyme est affiché seulement si la vue serveur le fournit. Le test
réel MC avec deux compétiteurs confirme son absence. Les réponses, temps et
métadonnées restent absents des trames joueur avant la révélation. Les réglages
techniques, les connexions, l'exclusion, les ajustements manuels, le replay, l'arrêt,
le délai supplémentaire, le saut, l'annulation de publication et la fin anticipée
gardent leurs commandes existantes et leurs contrôles de permission.

Les erreurs de session, de bibliothèque et de diagnostic proposent une relance.
Une erreur audio laisse la réponse et les commandes hôte accessibles. La
reconnexion explique l'attente et désactive les mutations hôte jusqu'au retour du
transport. La reprise d'une session ouverte ailleurs et l'exclusion disposent
d'un écran explicite.

## Zones modifiées

- `web/src/styles.css` et `web/src/ui/components.tsx` : grammaire, repères,
  confirmations et états communs.
- `web/src/app/{App,JoinScreen}.tsx` : entrée, élévation, session et erreurs.
- `web/src/player/{PlayerApp.tsx,presentation.ts}` : phases, audio et réponses.
- `web/src/host/HostApp.tsx` : préparation, revue, corrections et commandes.
- `web/src/i18n/{fr,en}.ts` : textes fonctionnels dans les deux dictionnaires.
- `web/tests/presentation.test.ts`, `web/e2e/{game,ui}.spec.ts` : progression de
  l'extrait, parcours réels, affichage et états dégradés.

## Vérifications

Les largeurs 320, 390 et 1280 px sont contrôlées sous Chromium. Les assertions
portent sur les titres par phase, les informations autorisées, les cibles tactiles,
le focus, les dialogues, les textes longs, les tableaux, les réglages son avec
pseudos courts et longs et l'absence de débordement horizontal. Une vérification
numérique couvre les contrastes des paires de couleurs textuelles principales
(au moins 4,5:1). Ce contrôle n'est pas un audit WCAG complet.

La suite Chromium comprend trois parcours avec le vrai serveur et le Bridge démo
(deux parties de deux manches, une partie MC) et seize scénarios d'interface avec
vues synthétiques injectées. Ces derniers complètent les tests réels ; ils ne
modifient aucune règle dans l'application. Les captures sont produites dans
`web/test-results/`, ignoré par Git, et relues visuellement.

Le [DEVLOG](DEVLOG.md) consigne les commandes, les nombres exacts et les défauts
corrigés. Les extraits de test sont synthétiques et en Opus : Chromium headless
ne valide pas le format AAC de production ni la synchronisation acoustique.

WebKit et les appareils iOS/Android réels restent à valider. G1 et G2 demeurent
`PENDING USER MEASUREMENT`. Le problème connu du compteur sous WebKit Linux n'a
pas été analysé ici ; l'isolation des sessions de test a toutefois été améliorée
pour les relances. Le déploiement et la release restent hors de cette intervention.
