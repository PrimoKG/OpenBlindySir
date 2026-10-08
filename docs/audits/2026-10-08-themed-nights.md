# Soirées à thème — livraison du 8 octobre 2026

[English](2026-10-08-themed-nights.en.md).

Les filtres servent désormais au tirage réel des manches, avec un aperçu utilisant
le même moteur : dossiers, genres, langues, années, tags et univers. Les raccourcis,
les sélections locales enregistrées et le transfert depuis la bibliothèque
permettent de préparer puis réutiliser une soirée. L’édition individuelle et par
lot expose les nouveaux champs ; les tris et la pagination restent disponibles.
Les inconnues sont exclues des filtres stricts, sans inventer des métadonnées.
Voir [le parcours utilisateur](../themed-nights.md).

Le protocole passe à 11, le snapshot à 9 et les exports de métadonnées à 3.
Les snapshots antérieurs et imports JSON 1/2 sont migrés. Les listes et requêtes
sont bornées ; l’aperçu est réservé à l’hôte, vérifie Origin, le rôle et l’époque,
et utilise les limitations de travail de la recherche. Les titres de séries
confirmés contenant un tiret ne sont plus séparés comme des noms de fichiers.
Les paramètres thématiques ne changent pas pendant une partie en cours.

## Préparation et vérification locales

La bibliothèque de test réelle comprend 232 génériques et fichiers apparentés :
211 retenus, 21 désactivés logiquement, dont huit copies exactes et des épisodes,
compilations, extraits, promotions ou fichiers trop courts. Les titres sont
nettoyés, les séries associées et des variantes de réponse ajoutées. Les langues
ne sont renseignées que sur indices explicites ; aucun artiste ni millésime n’est
inventé. L’artiste est vidé pour empêcher le nom de l’uploader de devenir une
réponse attendue. Les fichiers musicaux n’ont pas été renommés, déplacés ou modifiés.

Le dossier est monté en lecture seule, en plus des sources existantes. Un dossier
vide servant de point de montage a été créé dans la racine musicale existante,
car Docker ne peut pas créer un sous-montage absent dans un parent en lecture seule.
Le scan expose 300 pistes au total ; la préparation de la prochaine partie cible
les 211 génériques, en mode titre avec des extraits de 12 secondes. La partie
précédente reste terminée et aucune nouvelle partie n’a été lancée automatiquement.

Sauvegarde native privée format 2 et empreintes vérifiées avant modification.
Serveur et Bridge reconstruits puis relancés. Les contrôles après restauration
confirment les deux identités de joueurs, 12 archives, scores, réponses, cookies,
code d’accès, configuration du Bridge et certificat HTTPS conservés. Les anciens
morceaux restent dans le catalogue. Les archives sont comparées après validation
du schéma pour tenir compte des nouveaux champs par défaut. Le nouvel aperçu
refuse toujours une requête anonyme. Aucun fichier audio ni inventaire privé
n’entre dans Git ou les images Docker.

## Validation

- 1 190 tests Python distincts réussis : 1 179 généraux et 11 intégrations,
  incluant restauration, filtres combinés, catalogue, sources, confidentialité et FFmpeg.
  Deux contrôles de permissions propres à Unix/liens sont sautés sur Windows.
- 53 tests Web réussis ; types, build, Biome, Ruff, format, Pyright et schéma vérifiés.
- Les huit nouveaux parcours de thèmes FR/EN passent sur Chromium/WebKit,
  avec vérification visuelle sur petit écran et mobile ; les années invalides
  sont signalées localement et ne déclenchent pas de requête de recherche.

La classification d’une bibliothèque inconnue reste limitée aux métadonnées
vérifiées et corrections de l’hôte. Les essais acoustiques sur téléphones réels
restent nécessaires. Cette livraison ne constitue pas une release publique signée
et ne remplace pas les limites du [précédent audit](2026-10-08-autofix.md).
