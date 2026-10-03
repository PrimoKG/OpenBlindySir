# 0010 — Correction privée et commandes de soirée explicites

Statut : Accepté ; correction privée par manche remplacée par [0011](0011-global-review-and-private-replay.md) en V0.2 · Date : 2026-10-03

## Contexte

Les vidéos montrent une préparation sans issue, la confusion entre zéro et réponse
non vérifiée, et une correction difficile quand l'hôte joueur ne voit pas le morceau.
Le GO utilisateur autorise ces évolutions, y compris des fonctionnalités initialement
reportées dans la feuille de route.

## Décision

- Hôte joueur : morceau courant privé dès REVIEW, avec correction titre/artiste.
  Joueurs : métadonnées et réponses des autres après publication uniquement. Aucun
  morceau à venir dans la vue hôte joueur. Historique complet limité au lobby/résultats.
- Notation humaine : décision explicite pour chaque ligne, zéro compris. Confirmation
  requise avant publication de lignes non vérifiées. Saisie numérique locale jusqu'à
  Entrée/perte du focus, publication bloquée jusqu'à l'écho serveur.
- Consigne et barème titre/artiste partagés ; politique explicite des brouillons capturés.
  Aucun bonus de vitesse ni reconnaissance automatique des réponses.
- Préflight avec morceaux neufs/disponibles ; lancement et nouveaux réglages atomiques.
  Sans répétitions, une nouvelle partie garde la liste des morceaux entendus de la session.
  Réserve épuisée : choix explicite entre répétitions et vérification finale.
- Pause/reprise commune au son et aux réponses ; temps suspendu exclu des mesures.
- Équipes par somme des points individuels ; spectateurs hors réponses/ready check/scores.
  Configuration au lobby. Sélections locales au navigateur, QR sans mot de passe,
  récapitulatifs CSV/JSON et historique de 50 parties.
- Bridge : normalisation loudnorm et recherche bornée d'extraits audibles, activées par
  défaut et désactivables. Gabarits FFmpeg fixes et sandbox conservés. Fichiers écartés
  explicités aux hôtes lorsqu'un échec est rencontré ; pas d'audit intégral préventif.

## Conséquences

Protocole 2 : serveur, Bridge et navigateur doivent être mis à jour ensemble. Les tests
anti-fuite couvrent l'exception REVIEW réservée aux hôtes et le récapitulatif publié.
Les tableaux restent sémantiques et deviennent des lignes lisibles sur mobile ; le
panneau hôte suit le défilement de page. Les seuils audio et la synchronisation réelle
restent à valider sur la bibliothèque et les appareils du mainteneur (G1/G2).
