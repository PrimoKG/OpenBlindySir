# ADR 0015 — V0.5 : identité privée, archives et versions explicites

- Statut : accepté pour la version de développement V0.5
- Date : 2026-10-03
- Complète : ADR 0001, 0007, 0009, 0011, 0012, 0014
- Remplace : le report des secrets individuels à V1 dans ADR 0012

## Contexte

V0.2 possède déjà des propriétaires UUID et des jobs/tokens liés. Le secret
partagé ne prouve pas l’identité HELLO. Les archives sauvegardées sont transmises
dans STATE sans administration/retention temporelle explicite. V0.3 n’a pas gelé
le réseau. V0.5 doit renforcer ces frontières sans comptes, base de données ou cloud.

## Décisions

1. Registre privé versionné des hashes de secrets aléatoires liés aux UUID,
   révocables/remplaçables par l’opérateur. Bootstrap ancien lié à un seul UUID.
   Secret brut livré dans un fichier privé, jamais dans l’interface/logs.
   Revalidation après attente réseau et pour les connexions actives. Limites :
   64 identités, 8 connexions, 200 000 entrées de catalogue cumulées.
   Les écritures CLI/hôte acquièrent un verrou système non bloquant, puis relisent
   le registre avant mutation. Collision : échec/réessai ; échec d’écriture :
   rollback mémoire et invalidation du cache pour suivre le disque. Émission
   privée exclusive, nettoyage si la mutation échoue, noms d’état réservés refusés.
2. Les sources hors ligne ne participent pas aux nouveaux tirages. Attente d’un
   choix aléatoire : 45 s ; choix MC : décision explicite. Les extraits préparés
   continuent. Sources privées filtrées pour l’hôte joueur pendant IN_GAME.
3. Archive autonome format 2, sans audio/token ; 50 parties/90 jours/16 Mio.
   Consultation hôte HTTP à la demande, réservée au MC pendant IN_GAME.
   Suppression dans les deux snapshots, rollback RAM si échec. Résultats courants,
   exports et backups externes sont des copies aux limites expliquées à l’hôte.
4. Scores append-only et figés dans la partie active. Nouvelle partie libère
   journal/assets anciens ; les archives sont l’audit des soirées passées.
   Les IDs d’événements sont locaux au journal actif ; les archives référencent
   partie/joueur/manche. Renommer ou rescanner ne réécrit pas ces archives.
5. Logiciel 0.5.0.dev0, réseau 5 (5..5), snapshot 4, archives 2. Lecture snapshots
   1/2/3/4 et archives 1/2. Version inconnue : refus de reprise, pas de retour à
   un ancien résultat. Corruption : copie validée de secours. Rotation Bridge
   indépendante des cookies format 4. Rupture future : incrément, migration,
   plage et dépréciation explicites ; aucun gel du protocole.
   JSON privé sans clés dupliquées ; types/index/session/journal validés avant
   application. Une corruption connue choisit un secours validé sans modifier
   partiellement l’état ; les migrations légitimes restent prises en charge.
6. Accessibilité : évitement, focus conservé/restauré, états textuels/audio nommés,
   annonces sobres, clavier, reflow et mouvement réduit. Les tests automatiques
   sont distingués des lecteurs d’écran/appareils absents ; aucune certification.
7. Toutes les inscriptions : 60/IP/minute et 600/serveur/minute, y compris les
   succès. État limité à 1 000 identités, retirées comprises ; refus `game_full`.
   Nouvelle partie libère les identités retirées après archivage autonome ;
   Fin de session libère toutes les identités. `MAX_PLAYERS` garde son rôle de
   plafond simultané.

## Conséquences et limites

Un processus, une partie active, snapshots privés limités à 64 Mio chacun.
Pseudonymes/réponses/chemins privés : accès et sauvegardes sous responsabilité
opérateur. La rotation peut interrompre un extrait non préparé. Un secret volé
permet l’usurpation de son seul propriétaire. Le confinement conserve ses limites
TOCTOU. Stockage local avec verrous/liens physiques (NTFS/ext4/APFS, par exemple) ;
ne jamais supprimer `bridge-credentials.lock` pendant le fonctionnement. Le verrou
est libéré à la terminaison du processus. Restaurer le registre pour conserver
les révocations. Ces contrôles ne permettent pas plusieurs processus serveur ou
une instance distribuée. Downgrade avec installation et backup avant migration.
Aucune publication, V1.0, multi-room ou compte utilisateur ajouté.

Les contrats, migrations, permissions, propriétaires et suppressions sont testés.
Des processus réels FFmpeg couvrent deux UUID, mêmes IDs locaux, scores, kill et
reprise. Les guides [FR](../v0.5.md) / [EN](../v0.5.en.md) décrivent les commandes
et contrôles manuels.
