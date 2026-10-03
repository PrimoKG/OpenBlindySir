# ADR 0014 — Choix manuel de la manche par le MC

- Statut : Accepté
- Date : 2026-10-03
- Étend ADR 0012 (tirage équilibré) et ADR 0006 (vues privées).

## Décision

Seul l'hôte animateur peut envoyer `select_track` au lobby ou en jeu, avec numéro
de manche et révision attendue. La cible doit appartenir aux sources sélectionnées,
être en ligne et respecter la politique de répétition. Une piste réservée pour
une autre manche n'est pas réservable deux fois. Le choix explicite contourne
l'alternance aléatoire des dossiers ; l'interface l'indique. Les autres manches
gardent le tirage mélangé/équilibré et l'inédit prioritaire.

Une piste n'est modifiable que **tant qu'aucun extrait n'a été demandé** pour sa
manche. Le préchargement peut donc verrouiller une manche future. Les choix sont
numérotés ; passer la manche N ne consomme pas le choix de N+1. La vue MC confirme
la révision et le morceau avant lancement. L'interface bloque le lancement
pendant l'accusé ; le serveur refuse les révisions concurrentes. Une manche
manuelle préparée attend un lancement explicite, même si auto-start est actif.

Une sélection en échec conserve sa référence et diagnostic privé ; pas de
substitution silencieuse. Remplacement ou retour au hasard est autorisé après
libération de l'asset échoué ; passer/fin de jeu restent disponibles. Un Bridge
qui revient ne déclenche pas spontanément un choix manuel en échec.

Les références et informations de choix sont uniquement dans `McPanel`, jamais
HostPanel partagé ou vues joueur/hôte joueur. Aucune nouvelle URL de lecture
arbitraire ; préparation via les jobs bornés existants. Les vues/recherches
privées appliquent les permissions existantes. Protocole **4** obligatoire et
snapshot **3** ; lecture formats 1/2 avec champs neutres. Les futures réservations
sont persistées, prunées lors d'un changement de sources/manches au lobby, et
supprimées si le MC revient hôte joueur au lobby.

## Conséquences

Le MC doit planifier avant le préchargement (une ou deux manches). Les joueurs
gardent toutes leurs protections et l'attribution des points reste humaine.
Les critères disponibilité/réservations de la recherche sont indicatifs : la
validation atomique serveur prévaut. Un downgrade restaure le backup d'avant
migration, car l'ancienne version ne lit pas le snapshot 3.
