# 0009 — Restaurer la soirée par snapshots privés

Statut : Accepté · Date : 2026-10-03 · Remplace la décision de non-persistance de 0005.

## Contexte

Le retour sur les deux vidéos et le GO d'implémentation ajoutent la récupération
après crash, l'historique et les exports. La soirée doit pouvoir continuer après
un redémarrage sans perdre joueurs, réponses et journal des scores.

## Décision

Conserver le cœur synchrone et unique en RAM. La couche runtime écrit un snapshot
JSON versionné après les mutations et brouillons, à l'émission d'un cookie, au balayage
des sessions et à l'arrêt. Écriture temporaire, fsync puis remplacement atomique ;
la version précédente est conservée comme repli. La restauration réapplique le journal
et ses parties figées, décale les instants monotones, conserve les cookies hachés selon
leur TTL et invalide ces cookies si les secrets de configuration changent.

Ne sérialiser que des types autorisés. Refuser les fichiers de plus de 64 MiB et
arrêter le démarrage si aucun des deux snapshots n'est valide. Aucun pickle, audio
ni secret en clair. Le dossier contient néanmoins des réponses et des chemins relatifs
privés ; son accès et ses sauvegardes relèvent de l'hôte du serveur.

Une manche OPEN interrompue devient REVIEW : réponses verrouillées conservées,
brouillons capturés, avertissement explicite. Un extrait en préparation est régénéré.
Les connexions sont marquées hors ligne ; les clients reprennent avec leur cookie.
La RAM audio n'est jamais restaurée.

## Conséquences

`STATE_DIR=.local/state` en natif ; Compose monte `app_data:/data` et utilise `/data/state`.
Le conteneur reste en lecture seule hors de ce volume et de `/tmp`. Les 50 dernières
parties terminées sont archivées. Fin de session invalide les cookies et réinitialise
la partie et les morceaux entendus ; archives et corrections de métadonnées restent.

Une erreur d'écriture signale un risque de perte des dernières actions sans interrompre
la partie. Les écritures restent synchrones : ce choix convient au petit groupe prévu,
et la taille des catalogues/snapshots devra être surveillée sur la vraie bibliothèque.
Le format local ne promet pas de migration entre versions futures : conserver une
sauvegarde avant une mise à jour. Pas de SQLite ni de service supplémentaire.
