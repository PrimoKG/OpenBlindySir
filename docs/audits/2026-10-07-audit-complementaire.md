# Audit complémentaire et axes d'amélioration — 7 octobre 2026

## Résultat

**Sept nouveaux dysfonctionnements reproduits**, en complément des [17 constats de la vidéo](2026-10-06-test-video.md). Les points les plus urgents sont la politique des brouillons, les erreurs audio asynchrones et le cycle de vie des connexions. Les écarts entre références affichées et références de notation identifiés dans la vidéo restent également prioritaires.

Ce travail est un audit, sans correction applicative, modification des dépendances, déploiement, redémarrage des conteneurs ou publication Git. Les reproductions utilisent des sessions, musiques et identités synthétiques, séparées de l'installation LAN. Le build local et les documents ont été produits ; les scripts de preuve sont conservés dans `.local` et exclus du dépôt.

P1 : correction prioritaire avant sortie publique. P2 : défaut conditionnel ou de confort à corriger. Les sévérités concernent ici le produit ; elles ne constituent pas des scores de vulnérabilité CVSS.

## Nouveaux bugs confirmés

### A01 — Le réglage « L'hôte décide des points » n'est pas respecté pour les brouillons automatiques — P1

**Reproduction :** partie automatique demandant titre, artiste, album et année ; politique des brouillons `manual` ; bonne réponse laissée en brouillon jusqu'à la fermeture. Le moteur transforme la réponse en `CAPTURED`, lui attribue **quatre points** et la marque vérifiée sans décision de l'hôte.

La politique `zero` est traitée dans `grade_round`, mais la politique `manual` n'a pas de branche équivalente. Les libellés FR et EN promettent pourtant que l'hôte décide. La réponse récupérée de Zoo dans la vidéo restait en attente à cause d'informations insuffisantes ; cela ne prouve donc pas que cette politique fonctionnait.

Source : [auto_scoring.py](../../server/src/openblindysir_server/game/auto_scoring.py), fonction `grade_round`, lignes 303–357 ; [SetupPanel.tsx](../../web/src/host/SetupPanel.tsx), choix `captured_policy`.

**Correction :** conserver une suggestion et les preuves de reconnaissance pour un brouillon manuel, mais laisser ses points et sa validation à l'hôte. Distinguer explicitement trois comportements si souhaité : vérification humaine, notation automatique des brouillons, zéro obligatoire. Tester fermeture normale, arrêt et restauration de partie, puis réévaluation, sans écraser une décision manuelle.

### A02 — Une liste de propositions numériques peut obtenir des points automatiquement — P2

**Reproduction :** titre attendu `1989`, mode titre seul, seuil 90 %. La saisie `1989 1990 1991 1992 1993 1994` est acceptée à 100 % pour le titre.

Les fragments numériques non utilisés sont exclus du contrôle des mots supplémentaires. La vérification des années multiples protège le critère année lorsqu'il est demandé, mais pas un titre numérique en mode titre seul. Cela facilite les propositions multiples et nuit à l'équité de la notation ; aucun accès privilégié au serveur n'est impliqué.

Source : [auto_scoring.py](../../server/src/openblindysir_server/game/auto_scoring.py), construction de `leftovers` dans `match_answer`.

**Correction :** contrôler aussi les nombres non attribués à un critère. Autoriser une année supplémentaire réellement connue dans les métadonnées, mais classer une liste de nombres inconnus comme ambiguë. Préserver les titres et albums numériques légitimes, ainsi que les réponses partielles.

### A03 — Une ancienne erreur de téléchargement remplace l'état audio du morceau en cours — P1

**Reproduction :** lancement du téléchargement de l'extrait A ; changement de vue vers B ; B est téléchargé, décodé et passe à `PLAYING` ; A échoue après ses tentatives. L'état devient **`ERROR` pour A** alors que la source de B n'a pas été arrêtée.

`fetchDecode` conserve ses requêtes et temporisations, puis appelle `setState("ERROR", assetId, ...)` sans vérifier si cet extrait est encore pertinent. L'interface et le statut envoyé au serveur peuvent donc contredire la lecture réelle. Ce scénario est reproduit avec un contexte audio simulé ; il n'établit pas la cause du problème sonore sur le téléphone d'un joueur.

Source : [engine.ts](../../web/src/audio/engine.ts), `syncWithView` et `fetchDecode`, lignes 244–321.

**Correction :** annuler les téléchargements et délais devenus inutiles ; vérifier la génération, la vue active et le contexte avant d'appliquer un résultat. Séparer les erreurs de préchargement du prochain morceau de l'état du morceau joué. Tester succès et erreur tardifs, interruption du contexte, arrêt et changement de session.

### A04 — Fermeture et reconnexion peuvent laisser des sockets concurrents — P1

Deux reproductions avec réponse HTTP de session retardée :

- `connect()` démarre ; `close()` intervient ; la réponse HTTP arrive ensuite : un nouveau WebSocket est tout de même créé et reste ouvert.
- Deux `connect()` simultanés créent deux WebSockets ; `close()` ne ferme que celui conservé dans `this.ws`.

Les événements d'une ancienne connexion peuvent également atteindre les mêmes gestionnaires, sans vérification de génération. Les deux créations de socket sont prouvées ; la réception d'un faux état « session remplacée » sur un téléphone réel n'a pas été reproduite dans cet audit.

Source : [socket.ts](../../web/src/net/socket.ts), `connect`, `onClose`, `ensureConnected`, `resume`, `close`.

**Correction :** une seule tentative en cours, génération invalidée à la fermeture, vérification après chaque attente, fermeture de tout socket remplacé et gestionnaires associés à leur connexion. Tester retour au premier plan pendant une reconnexion, fermeture pendant la requête HTTP et événements tardifs de l'ancien socket.

### A05 — Quitter l'écran de jeu ne libère pas l'audio ni les écouteurs du contrôleur — P1

**Reproduction :** un `GameController` joue un extrait ; appel au nettoyage actuellement utilisé au démontage de `Game`, `game.socket.close()`. L'état audio reste `PLAYING` et l'écouteur `visibilitychange` reste enregistré.

Le contrôleur conserve aussi son abonnement au magasin de vues. Lors de nouvelles entrées dans le jeu, les anciens objets peuvent rester retenus par le document. L'audio peut continuer jusqu'à la fin de sa source malgré le départ de l'écran. La preuve vérifie le nettoyage du contrôleur avec une source simulée ; elle ne mesure pas une fuite mémoire après des heures de jeu sur téléphone.

Source : [App.tsx](../../web/src/app/App.tsx), nettoyage de `Game` ligne 84 ; [controller.ts](../../web/src/app/controller.ts), abonnements du constructeur ; [engine.ts](../../web/src/audio/engine.ts), absence de méthode de destruction.

**Correction :** ajouter un nettoyage complet du contrôleur : socket, lecture, requêtes, temporisations, abonnements et écouteurs. Libérer les ressources audio selon leur propriétaire, y compris le mécanisme de déverrouillage mobile si aucune session ne l'utilise. Tester sortie pendant la lecture, fin de session, reconnexion et entrées successives sans multiplier les contextes.

### A06 — Un contexte audio fermé ne peut pas être récupéré par « réessayer » — P2

**Reproduction conditionnelle :** le contexte passe à `closed`. `unlock()` rappelle `resume()` sur le même contexte fermé ; le refus est capturé, puis l'état reste `LOCKED`. Une nouvelle tentative donne le même résultat.

La récupération d'un contexte suspendu passe dans les tests Chromium existants. La fermeture définitive est un autre cas : il faut actuellement recharger la page. Aucun appareil physique n'a été utilisé pour prouver à quelle fréquence ce cas survient.

Source : [engine.ts](../../web/src/audio/engine.ts), `unlock` et `onContextState`.

**Correction :** conserver le même contexte pendant son fonctionnement normal ; si sa fermeture est définitive, proposer une réinitialisation audio lors d'un geste utilisateur, ou expliquer clairement le rechargement nécessaire. Invalider les anciennes sources et opérations avant de reprendre la position actuelle du serveur.

### A07 — Un export de métadonnées valide peut être impossible à réimporter — P2

**Reproduction HTTP réelle sur serveur de test isolé :** 700 morceaux avec des métadonnées valides produisent un export de **2 342 222 octets**, HTTP 200. La réimportation du même contenu renvoie **HTTP 413, `payload_too_large`**. L'interface refuse également les fichiers supérieurs à 1 Mio. L'export téléchargé par l'interface est en outre formaté avec indentation.

L'export n'a pas de borne correspondant à la limite d'import de 1 Mio ni à celle de 10 000 lignes. Le catalogue accepte beaucoup plus de morceaux. Le problème ne supprime pas les métadonnées existantes ; il rend l'export impropre à la restauration attendue.

Source : [management.py](../../server/src/openblindysir_server/library/management.py), `import_metadata` et `export_metadata` ; [LibraryManager.tsx](../../web/src/host/LibraryManager.tsx), import et export.

**Correction :** produire des fichiers réimportables, découpés selon les limites, ou un format d'archive importé par lots bornés. Conserver les protections de taille et de durée ; ne pas simplement accepter un corps JSON illimité. Tester l'aller-retour à proximité des limites et les bibliothèques importantes.

## Points de la vidéo toujours à traiter

- Références effectivement figées pour la notation, informations déduites du nom du fichier et « Réponse attendue » ne doivent pas être confondues. La divergence possible est confirmée dans le code ; la cause précise du cas NINAO enregistré reste à confirmer avec son état de manche.
- Les raisons de mise en attente doivent apparaître sans ouvrir chaque menu de reconnaissance. Le score de similarité doit rester présenté comme une mesure de ressemblance, pas une certitude.
- Le final sur ordinateur doit réduire le lecteur, les cartes et les défilements imbriqués ; garder les actions visibles sans recouvrir le contenu.
- Préparation privée et scène publique, réponse envoyée et points attribués, préférence de défilement et pause manuelle demandent des états distincts.
- Le tableau de confirmation du podium doit conserver les pseudos sur une ligne lorsque la largeur le permet, et proposer d'abord de terminer les réponses en attente.

Les parcours ciblés de retour entre les deux dernières manches passent. Cela ne contredit pas la difficulté de compréhension observée : comportement moteur correct et présentation claire sont deux critères différents.

## Autres axes proposés et leur plus-value

| Axe | Proposition concrète | Plus-value |
| --- | --- | --- |
| Préparer la bibliothèque pour l'automatique | Afficher la qualité des références par critère dans les sources réellement sélectionnées ; filtrer les morceaux prêts ; proposer une file de corrections. Les suggestions déduites des fichiers restent à confirmer. | Éviter une partie prétendument automatique qui devient une longue correction manuelle ; améliorer progressivement la bibliothèque. |
| Mode soirée et mode animateur | En mode soirée, mettre en avant la manche, les réponses et la prochaine action. Placer sources, maintenance et diagnostics dans les outils avancés. Sur PC, utiliser le contexte musical à gauche, la notation au centre et le classement à droite selon la largeur. | Rendre le parcours convivial tout en gardant les capacités d'administration disponibles. |
| Final guidé | Proposer une progression explicite : révéler le morceau, écouter si besoin, attribuer ou dévoiler les points, voir le mouvement du classement, passer à la manche suivante. Conserver la consultation privée d'une autre manche. | Faire de la distribution une séquence compréhensible pour l'hôte et un moment partagé pour les joueurs. |
| Spectacle réglable | Offrir un rythme rapide ou animé ; annoncer le critère trouvé et le gain, puis la variation du rang. Regrouper les ex æquo et respecter son désactivé et réduction des animations. | Ajouter suspense et satisfaction sans ralentir les groupes qui préfèrent jouer vite. |
| Diagnostics audio accessibles | Maintenir « Tester mon audio » à portée pendant le final. Distinguer volume nul, contexte bloqué, téléchargement, décodage, connexion et autorisation HTTPS. Proposer l'action adaptée. | Réduire les interruptions de soirée et éviter de demander à l'hôte de diagnostiquer chaque téléphone. |
| Explication et historique des décisions | Sur une réponse, montrer l'origine des points, automatique ou hôte, et les critères validés. Ajouter une annulation contrôlée de la dernière correction et rendre les conflits entre deux écrans d'hôte explicites. | Renforcer la confiance dans le classement et accélérer la résolution des contestations. |
| Effacer ou hériter d'une métadonnée | Aujourd'hui, vider un champ manuel rétablit la valeur importée : comportement reproduit et annoncé par la fusion des sources. Proposer séparément « Utiliser la valeur importée », « Remplacer » et « Effacer la référence ». | Permettre de supprimer une mauvaise information importée sans la voir réapparaître ; résoudre une limite actuelle plutôt que modifier silencieusement l'héritage. |
| Reprise de session expliquée | Afficher l'état de connexion et la récupération du brouillon avec des messages courts. Nettoyer l'invitation dans l'URL après toutes les formes de connexion réussie, et guider la reprise sur un autre appareil. | Réduire les réponses perdues en apparence et la confusion entre une nouvelle place et la récupération de son identité. |
| Accessibilité et échelles d'affichage | Tester clavier, zoom 125/150 %, 1280 × 720, 1366 × 768, petits téléphones et grandes listes. Limiter les annonces vocales aux événements utiles et conserver le focus lors des mises à jour. | Garder les actions lisibles sur les petits PC et utilisables sans souris, sans dégrader le téléphone. |
| Distribution publique vérifiable | Préparer un paquet précompilé versionné, des contrôles d'intégrité et un assistant local pour démarrer, arrêter et diagnostiquer. Garder l'approbation de la CA LAN explicite et mettre les instructions FR/EN au même niveau. | Réduire les erreurs de setup et rendre l'installation plus reproductible pour les nouveaux utilisateurs. |

## Sécurité : contrôles et réserves

Les suites Python couvrent les rôles, les origines, les cookies, les accès aux médias, les corps de requêtes bornés, les chemins, la restauration et la révocation. Elles passent dans cette exécution. La lecture ciblée confirme les protections de cookie de production (`Secure`, `HttpOnly`, `SameSite=Strict`), les origines exactes et les contrôles d'hôte avant et après plusieurs attentes asynchrones.

**Aucun nouveau contournement de rôle ou fuite de secret n'a été démontré dans cette passe.** Ce résultat est limité au code relu et aux scénarios exécutés ; ce n'est pas un pentest exhaustif. Les défauts de socket et de nettoyage audio affectent la fiabilité du client et doivent être corrigés, sans être présentés comme une compromission prouvée du serveur.

Les dépendances et images n'ont pas fait l'objet d'un nouveau scan d'avis de vulnérabilité. Le [dernier rapport local](2026-10-06-autofix-2.md) signalait **0 correspondance critique et 55 élevées** pour l'image applicative, avec une base d'avis datée du 5 octobre et sans correctif annoncé pour ces correspondances dans cette base. Ce sont des résultats historiques, pas une mesure actualisée au 7 octobre. Les réserves de ce rapport restent ouvertes ; aucune validation de sortie publique sans réserve n'est donnée ici. Aucun inventaire n'a été transmis à Docker Scout ni à un service de sécurité cloud.

## Vérifications de cette passe

- **1 081 tests Python réussis** dans la suite sans intégrations ; 44 tests FFmpeg initialement ignorés car le PATH n'était pas transmis comme attendu au processus Python ont été relancés avec le chemin fixé dans ce processus : **44 réussis**, soit **1 125 au total**. Deux autres exclusions : permissions POSIX et création de lien indisponible. Onze intégrations séparées non relancées.
- **47 tests Web réussis** ; TypeScript et build réussis ; Biome réussi.
- **Sept parcours Chromium réussis** : partie réelle avec réponse multiforme automatique, récupération audio du final FR/EN, bibliothèque adaptative et préécoute, retour entre les deux dernières manches, reconnaissance/réévaluation/vagues FR/EN. Les musiques sont synthétiques ; aucune validation acoustique ou sur Safari/iPhone physique n'est revendiquée.
- **Cinq sondes client** reproduisent les mauvaises transitions audio, les deux courses de connexion, l'échec de récupération d'un contexte fermé et le nettoyage incomplet. Elles affirment le comportement défectueux actuel pour documenter la preuve ; leur réussite ne signifie pas que ces bugs ont été corrigés.
- Sondes moteur/HTTP : quatre points sur brouillon manuel, acceptation de propositions numériques, réapparition d'une métadonnée importée après effacement manuel, export puis refus de réimportation.
- Ruff et contrôle d'hygiène réussis ; ce dernier porte sur **323 fichiers suivis**.

Les premières tentatives de vérification ont rencontré des problèmes d'environnement : cache pytest inaccessible, FFmpeg absent du PATH Python et chemin par défaut du navigateur Playwright vide. Les exécutions utiles ont ensuite été faites sans cache pytest, avec FFmpeg local et le navigateur déjà installé dans `.local/playwright-browsers`, sans téléchargement. Les serveurs temporaires de test sur 8879 et 8880 ont nécessité un nettoyage de leurs arbres de processus après les scénarios ; ils sont arrêtés, le serveur préexistant sur 8765 a été conservé. Aucun conteneur de l'installation LAN n'a été arrêté.

Preuves privées et reproductibles : `.local/audit-20261007/probe_engine.py`, `web/.local/audit-20261007/client.probe.ts`, sa configuration Vitest, `.local/audit-20261007/browser-results/` et `.local/audit-20261007-python.log`.

## Ordre de travail recommandé

1. Rendre les références et les politiques de notation cohérentes ; corriger A01/A02, puis expliquer chaque attribution ou attente.
2. Fiabiliser les interruptions audio et les reconnexions : A03–A06, avec tests de courses asynchrones et vérification sur téléphones.
3. Refaire le final desktop et ses états, en conservant le rendu mobile apprécié ; corriger les tableaux et le classement à faible effectif.
4. Garantir les exports réimportables, préciser l'effacement des métadonnées et améliorer la préparation de la bibliothèque.
5. Ajouter le final guidé et le spectacle réglable, puis vérifier FR/EN, grandes listes, zoom et clavier.
6. Actualiser séparément les avis de sécurité et revalider le paquet d'installation avant la décision de publication.
