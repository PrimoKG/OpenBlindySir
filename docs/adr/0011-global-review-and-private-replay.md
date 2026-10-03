# ADR 0011 — Revue globale et réécoute privée

- Statut : Accepté
- Date : 2026-10-03
- Complète ADR 0007 et ADR 0009 ; remplace la publication par manche d'ADR 0010.

## Contexte

Noter à chaque manche ralentit la partie et révèle les morceaux aux hôtes joueurs.
La nouvelle expérience conserve toutes les réponses avant une correction globale.
Les fichiers sources restent sur les appareils équipés d'un Bridge.

## Décision

`REVIEW` signifie désormais « réponses fermées et conservées ». Aucun point ni
morceau n'est publié à ce stade. Après la dernière manche ou `end_game`, la partie
passe obligatoirement en `FINAL_SCORE_REVIEW`. La vue privée de l'hôte contient
toutes les manches entendues, les participants historiques, les réponses, statuts,
horodatages de réception serveur et décisions de notation. `CAPTURED` indique
l'heure du dernier brouillon reçu, sans temps de validation ni rang.

Les points par réponse et corrections finales sont des valeurs entières signées
bornées à ±1000, sauvegardées côté serveur. Zéro doit être choisi explicitement.
`final_validate` exige une confirmation des lignes non vérifiées et crée tous les
événements `round` puis `final_adjustment` avant de figer le journal. Les commandes
historiques `publish`, `undo_publish` et `adjust` sont refusées. Les résultats
incluent les manches entendues mais annulées, avec `included=false` et zéro point.

Un arrêt avant le départ officiel annule la manche sans la compter comme entendue.
En OPEN, le mode `score` ferme et capture les brouillons ; `abandon` conserve la
manche entendue et ses réponses mais l'exclut des points. Un arrêt en revue globale
est sans effet sur les brouillons. Aucun arrêt ne publie automatiquement.

La réécoute utilise une route HTTP privée, uniquement en revue globale ou résultats.
Elle ne produit pas de `PLAY`, ne modifie pas le round et ne remplit pas le cache
audio partagé. Deux transferts maximum, un par hôte, ≤2 Mio chacun par défaut ;
annulation à la déconnexion, au changement de partie ou après 75 secondes.

Le Bridge garde au plus **64 Mio d'extraits** dans son répertoire temporaire privé.
La réécoute exacte vérifie le SHA-256 original ; si nécessaire, une régénération
reprend départ, durée, normalisation et révision de source. Un encodage différent
est refusé. Une erreur du cache facultatif ne fait pas échouer la lecture du jeu.
L'écoute intégrale nécessite l'accord local `--allow-full-review` ou
`OPENBLINDYSIR_BRIDGE_ALLOW_FULL_REVIEW=true`. Elle réencode à la demande des
segments de **30 secondes maximum**, sans normalisation ni fondus. Un seul segment
reste dans le navigateur ; les anciens Blob URLs sont révoqués. Le fichier complet
et ses pistes vidéo ne sont jamais transférés ou stockés sur le serveur.

## Conséquences

Protocole 3 : mise à jour conjointe serveur, Bridge et client. Snapshot format 2,
avec lecture/migration du format 1 : les publications d'une partie inachevée
deviennent des brouillons et des événements `revoke` préservent l'audit. Les archives
déjà finales restent figées. Les horodatages muraux restent stables au redémarrage.

Sans Bridge disponible, la notation reste possible, la réécoute affiche une erreur
récupérable. Une source modifiée ou supprimée ne remplace jamais silencieusement
l'extrait entendu. Après redémarrage du Bridge, un muxage Opus régénéré peut avoir
un SHA différent et être indisponible. L'écoute intégrale peut marquer une attente
entre segments. La synchronisation acoustique sur vrais appareils reste à mesurer.

## Validation

Tests du cœur, matrice anti-fuite, snapshots anciens/nouveaux, fins anticipées dans
chaque phase, permissions HTTP et transfert éphémère, intégration et parcours web.
