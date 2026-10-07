# Audit de bugs et de sécurité avant publication — 5 octobre 2026

**État initial, avant corrections : différer la publication officielle.** Les tests existants passent, mais neuf constats ont été confirmés par lecture du code et reproductions locales ciblées. Le plus préoccupant concerne la durabilité des changements d'accès : un succès annoncé peut être annulé au redémarrage après un échec de sauvegarde. Les constats étaient ouverts à la clôture de cet audit initial ; les corrections ultérieures sont documentées ci-dessous.

**Mise à jour après corrections :** les neuf constats ci-dessous ont depuis été
corrigés et validés. Le [rapport de corrections](2026-10-05-corrections.md)
fait foi pour leur état actuel et complète le scan CVE local des images.
Le présent document conserve les résultats et descriptions de l’audit initial.

## 1. Périmètre et niveau de confiance

| Élément | Révision examinée |
| --- | --- |
| Application | OpenBlindySir `0.5.0.dev0` |
| Protocole / snapshot | 8 / 6 |
| Commit de base | `e4aaff76b3848dc9d747728ebefd87b7c24cea52` |
| État du checkout | Modifications et nouveaux fichiers non commités |
| Plateforme de l'audit | Windows ; Python du venv ; Chromium ; Docker local |
| Source de vérité | Contenu courant des fichiers, y compris les nouveaux fichiers non ignorés |

L'audit couvre serveur HTTP/WebSocket, authentification, QR et reprise d'identité, autorisations, moteur de partie et finale, bibliothèque et métadonnées, préécoute, Bridge/FFmpeg, persistance, exports, interface responsive, dépendances et procédure de distribution. Il combine revue des protections, suites automatisées et essais adverses bornés avec données synthétiques.

Les reproductions utilisent des instances temporaires et des pseudos fictifs. Aucun test de saturation n'a été lancé sur la partie active. Les conteneurs existants ont seulement été inspectés en lecture ; ils n'ont été ni redémarrés ni modifiés pendant l'audit. Aucun mot de passe réel, cookie réel, réponse de joueur ou fichier musical privé n'est inclus dans ce rapport.

Ce rapport décrit les preuves obtenues sur cette révision. Il ne constitue pas une certification de sécurité, un pentest exhaustif de l'hébergement public ou une garantie d'absence de vulnérabilités. Les timings locaux ne prédisent pas les performances de toutes les machines.

## 2. Vérifications exécutées

| Contrôle | Résultat de cet audit | Limite utile |
| --- | --- | --- |
| Pytest, sélection habituelle | **976 réussites**, 2 skips, 11 tests d'intégration désélectionnés | Les skips portent sur permissions Unix et création de symlink sous Windows |
| Pytest, intégration séparée | **11 réussites**, 978 désélectionnés | Exécution locale, FFmpeg réel ; répertoire temporaire propre |
| Playwright Chromium | **78 réussites** : 74 scénarios UI et 4 parcours complets | Serveur/Bridge synthétiques, audio Opus ; sortie muette, autoplay autorisé par le harnais |
| Vitest | **44 réussites** | Tests unitaires web |
| Ruff / format Python | Réussite ; **233 fichiers** conformes au format | Analyse statique et format |
| Pyright | **0 erreur**, avec l'interpréteur du venv | Typage statique |
| Biome / TypeScript | Réussite ; **62 fichiers** vérifiés par Biome | Qualité du code web et typage |
| Types générés / verrou de schéma | À jour | Cohérence protocole ↔ client |
| Build web de production | Réussite | Compilation locale ; ne vaut pas recette sur appareils physiques |
| Vérification des métadonnées de release | Réussite en développement | Version `.dev0` et checkout dirty : publication non validée |
| Hygiène du worktree | **337 fichiers** examinés, aucun signal du contrôleur | Contenus courants suivis + nouveaux non ignorés ; hors fichiers privés ignorés et historique Git complet |
| Avis de vulnérabilités Python | **70 versions PyPI**, aucun avis retourné par OSV | Packages verrouillés ; pas les paquets système ni les binaires externes |
| npm audit | **132 dépendances au total**, aucun avis retourné | Base d'avis npm ; catégories prod/dev/optional se recoupent |
| Isolation Docker | App/Bridge non-root, systèmes de fichiers en lecture seule, capacités supprimées | Inventaire local ; couverture CVE système incomplète |

La vérification des dépendances a été effectuée le **5 octobre 2026 à 12:08 UTC** à partir des noms et versions des lockfiles. L'absence d'avis connu ne démontre pas l'absence de défaut. Méthodes de référence : [requêtes groupées OSV](https://google.github.io/osv.dev/post-v1-querybatch/) et [npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit/).

Le premier lancement d'intégration a rencontré un problème d'accès au répertoire temporaire Windows. La relance avec un nouveau répertoire isolé a réussi : ce problème d'environnement n'est pas compté comme bug du produit. Quelques fermetures de connexions de test ont produit du bruit `WinError 10054`, sans assertion en échec.

## 3. Registre des constats confirmés

Les niveaux indiquent une priorité de traitement dans le contexte de cette application, sans prétendre calculer un score CVSS. « Sécurité » inclut la résistance aux abus et la cohérence des accès. Aucun constat ci-dessous ne démontre une exécution de code à distance ou une prise de contrôle automatique de l'hôte.

| ID | Sujet | Domaine | Priorité | État |
| --- | --- | --- | --- | --- |
| S02 | Succès des changements d'accès malgré une sauvegarde échouée | Sécurité | **Élevée** | Confirmé, ouvert |
| S01 | Code / invitation Unicode provoquant une erreur 500 | Sécurité / robustesse | Moyenne | Confirmé, ouvert |
| S03 | Saturation et ambiguïté des demandes de reprise d'identité | Sécurité / disponibilité | Moyenne | Confirmé, ouvert |
| S04 | Lecture du code commun réécrivant tout le snapshot | Sécurité / disponibilité | Moyenne | Confirmé, ouvert |
| S05 | Quota d'échecs non revérifié après réception du corps | Sécurité | Moyenne | Confirmé, ouvert |
| B01 | Reprise d'un MC modifiant sa participation | Fonctionnement | Moyenne | Confirmé, ouvert |
| B02 | Recherche d'une grande bibliothèque sur la boucle réseau | Performance | Moyenne | Confirmé, ouvert |
| B03 | Capacité WebSocket incohérente derrière une même IP | Fonctionnement | Moyenne | Confirmé, ouvert |
| B04 | Documentation de métadonnées et versions incohérente | Documentation | Faible | Confirmé, ouvert |

### S02 — Révocation et rotation non durables en cas d'échec de sauvegarde

**Conditions :** persistance activée, échec d'écriture du snapshot, puis redémarrage avant une sauvegarde ultérieure réussie. Il ne s'agit pas d'un contournement direct du mot de passe hôte ; le risque vient d'une opération légitime dont le succès est annoncé trop tôt.

**Preuve :** en injectant une `OSError` dans l'écriture, la rotation retourne HTTP 200 et change le code en mémoire, alors que le disque conserve l'ancien. Pour un transfert approuvé, le navigateur précédent devient bien invalide en mémoire (401), mais redevient valide après redémarrage (200) ; le nouveau navigateur obtient alors 401. L'état global de persistance passe à `failed`, sans empêcher les réponses de succès de ces opérations.

**Impact :** une révocation annoncée peut être annulée ; un QR/code remplacé peut redevenir utilisable ; le joueur transféré perd sa reprise. Un avertissement général de sauvegarde ne rend pas la révocation durable.

**Cause :** mutation des accès et des jetons avant une sauvegarde dont l'erreur est absorbée. Voir [rotation d'accès](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:83), [transfert](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:176) et [sauvegarde](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/runtime.py:104).

**Correction attendue :** transaction cohérente entre accès, jetons, identité et snapshot. Ne confirmer l'opération et ne fermer définitivement l'ancienne connexion qu'après un enregistrement durable ; sur échec, conserver l'état antérieur et répondre par une erreur exploitable par l'interface. Préparer puis écrire un état candidat évite une annulation incomplète après mutation.

**Critère de fermeture :** tests disque plein / permissions / `OSError` / redémarrage, démontrant qu'un succès ne restaure jamais un ancien accès et qu'un échec ne prive pas le joueur de son accès antérieur.

### S01 — Entrées Unicode non maîtrisées sur l'accès QR/code

**Conditions :** appel non authentifié de `/api/session/access`, avec un Origin accepté et un code ou une invitation contenant par exemple `é`.

**Preuve :** chacun des deux champs provoque HTTP **500**. Le comparateur de chaînes constant en temps reçoit une chaîne non ASCII ; le modèle borne la longueur mais ne valide pas le format. Le serveur continue de fonctionner : la preuve porte sur la requête en erreur, pas sur un arrêt global.

**Impact :** erreur serveur déclenchable par une simple saisie, mauvais retour utilisateur et bruit de logs ; ces échecs n'empruntent pas le traitement normal des identifiants invalides.

**Sources :** [validation d'accès](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access.py:40), [modèle d'entrée](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:26).

**Correction attendue :** valider les formats avant comparaison, ou comparer des octets encodés de manière cohérente ; renvoyer un 4xx documenté. **Critère de fermeture :** codes et invitations Unicode, caractères de contrôle, valeurs vides et limites de longueur ne produisent aucun 500 ni acceptation indue.

### S03 — Demandes de reprise saturables et difficiles à distinguer

**Conditions :** connaître le code commun ou l'invitation de la session. Le code est partagé volontairement avec les participants ; il ne suffit pas à reprendre une identité existante sans accord de l'hôte.

**Preuve :** 32 demandes pour un seul pseudo reçoivent 202 depuis la même IP ; une demande concernant un autre joueur reçoit ensuite 429. L'hôte voit 32 demandes avec **un seul nom distinct**. Le plafond global est 32 et l'expiration est de 120 secondes ; aucune limite par identité cible n'empêche un participant de monopoliser les places.

**Impact :** blocage temporaire des reprises légitimes et risque de valider la mauvaise demande lorsque plusieurs navigateurs réclament le même pseudo. Une usurpation sans validation de l'hôte n'a pas été démontrée.

**Sources :** [création des demandes](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access.py:48), [liste présentée à l'hôte](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:58), interface `PartyTools.tsx`.

**Correction attendue :** quota par cible et demandeur, traitement des doublons, et courte référence de confirmation affichée à la fois sur le navigateur demandeur et chez l'hôte. Une nouvelle demande ne doit pas pouvoir invalider arbitrairement une demande légitime. Conserver expiration, limite globale et suppression des autres demandes après transfert.

**Critère de fermeture :** un spam sur un pseudo n'empêche pas les autres joueurs de reprendre ; l'hôte peut faire correspondre sans ambiguïté une demande au navigateur voulu.

### S04 — Une lecture du code déclenche une sauvegarde complète

**Conditions :** disposer d'un cookie joueur valide. Avec persistance activée, l'appel réécrit l'état de session ; il n'exige pas le rôle hôte.

**Preuve :** 20 GET `/api/session/access-code` retournent 200 et déclenchent **20 appels de sauvegarde**, alors que le code existe déjà. Le comptage est instrumenté ; aucun remplissage de disque ou test de charge destructif n'a été réalisé.

**Impact :** amplification inutile d'une lecture en encodage et écriture de l'état complet, avec coût CPU/disque et travail synchrone sur la boucle réseau. L'absence de quota sur cette route facilite un abus par un participant.

**Source :** [lecture du code partagé](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:47).

**Correction attendue :** sauvegarder uniquement la création initiale du code, puis servir les lectures sans mutation ; ajouter une limite adaptée et traiter le coût de persistance sans bloquer les communications. **Critère de fermeture :** après initialisation, 20 lectures déclenchent zéro sauvegarde supplémentaire, sans modifier le code ou la reprise.

### S05 — Quota d'échecs périmé pendant la réception du corps

**Conditions :** plusieurs requêtes d'accès en cours ; le quota d'échecs se remplit pendant que l'une attend le corps HTTP. La vérification initiale a lieu avant un `await` et utilise ensuite l'ancien instant.

**Preuve :** le harnais remplit le limiteur pendant la lecture du corps. Une requête avec code valide reçoit ensuite **200**, bien que `join_limiter.blocked(...)` soit vrai. Les routes historiques de connexion possèdent déjà la seconde vérification.

**Impact :** les requêtes déjà engagées peuvent dépasser le quota d'échecs attendu. Le limiteur d'activité reste actif : il ne s'agit pas de tentatives illimitées ou d'un contournement de l'authentification.

**Source :** [route d'accès](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:101).

**Correction attendue :** recalculer l'instant et revérifier le quota après réception ; factoriser les protections communes des routes d'authentification. **Critère de fermeture :** test de corps retardé avec saturation concurrente : réponse 429, sans émission de cookie ou création de demande.

### B01 — Un MC devient participant lors d'un transfert approuvé

**Preuve :** un hôte en mode MC est non participant avant transfert ; après reprise approuvée sur un autre navigateur, la route lui attribue `Role.PLAYER`, conserve `host_mode=mc` et il devient participant. Reproduction effectuée dans le lobby.

**Impact :** la participation change sans choix explicite. La même affectation de rôle est accessible dans d'autres phases d'après le code, mais l'audit n'a pas reproduit son effet sur un score en partie. La perte automatique du privilège hôte peut être une protection voulue ; il faut la distinguer du changement de participation.

**Sources :** [transfert partagé](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/access_routes.py:207), [récupération historique](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/auth/routes.py:148).

**Correction attendue :** préserver explicitement le statut de participation/spectateur et expliquer la réauthentification hôte nécessaire. Ne pas résoudre le problème en accordant le rôle hôte sur la seule base du code commun. **Critère de fermeture :** matrice MC / hôte joueur / spectateur / joueur, dans chaque phase, sur les deux chemins de récupération.

### B02 — La pagination n'évite pas le parcours coûteux du catalogue

**Preuve :** recherche sans résultat, limite de page 20, données synthétiques en mémoire :

| Catalogue | Étiquettes par morceau | Durée HTTP locale |
| --- | --- | --- |
| 2 000 morceaux | 64 | 0,030 s |
| 20 000 morceaux | 64 | 0,267 s |
| 200 000 morceaux | 64 | 2,641 s |
| 200 000 morceaux | 0 | 0,800 s |

La fonction `async` parcourt et trie le catalogue, normalise les étiquettes et construit les résultats avant pagination, sans délégation de ce calcul. Les 64 étiquettes représentent 32 tags et 32 liens, dans les bornes par morceau. Ce jeu dense est un stress mémoire sans persistance ; il peut dépasser la taille maximale d'un snapshot. Le cas sans étiquettes reste significatif indépendamment de cette limite.

**Impact :** les grandes recherches risquent de retarder les WebSockets et minuteries partageant la boucle réseau. Le coût local et l'emplacement synchrone sont confirmés ; une dégradation acoustique de 2,641 s n'a pas été mesurée et ne doit pas être déduite directement de ce tableau.

**Source :** [recherche de bibliothèque](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/library/management.py:122).

**Correction attendue :** cache/index de recherche et de facettes par révision, pagination sans construction inutile de tous les objets, ou calcul délégué sur un état immuable cohérent. Éviter de faire lire un état mutable concurrent au hasard depuis un thread. Ajouter annulation et quotas adaptés.

**Critère de fermeture :** benchmark aux tailles supportées, avec et sans tags ; mesurer en parallèle `/healthz`, PING/PONG, changements de manche et préparation audio. Fixer un budget de latence documenté et vérifier qu'il tient en charge.

### B03 — Limite de 20 WebSockets malgré une capacité joueurs configurable jusqu'à 100

**Conditions :** plus de 20 connexions depuis une même IP publique, par exemple un lieu où tous les appareils passent par le même NAT, et capacité configurée au-delà du défaut de 20 joueurs.

**Preuve :** `max_players=32`, 21 joueurs inscrits en HTTP ; les 20 premiers ouvrent leur WebSocket et reçoivent STATE, le 21e est fermé avec **1008**. La configuration accepte 2 à 100 joueurs, mais `MAX_WS_PER_IP` reste fixé à 20.

**Impact :** un joueur admis ne peut pas utiliser la partie malgré la capacité annoncée. Un LAN à IP distinctes n'a pas nécessairement ce problème. À la capacité par défaut, plusieurs onglets ou connexions de reprise peuvent aussi consommer la marge ; ce cas n'a pas été reproduit ici.

**Sources :** [plafond WebSocket](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/main.py:43), [configuration joueurs](D:/Dev/PKG.OpenBlindySir/server/src/openblindysir_server/config.py:240).

**Correction attendue :** rendre les limites cohérentes et adaptées au NAT, préserver des plafonds globaux et par identité, prévoir le remplacement d'une connexion existante sans exiger une place supplémentaire. **Critère de fermeture :** tous les joueurs de la capacité déclarée se connectent derrière un NAT ; les connexions anonymes ou abusives restent bornées.

### B04 — Exemples et références de versions contradictoires

**Preuve :** le guide de métadonnées documente `disabled`, tandis que le modèle attend `enabled` et refuse les champs supplémentaires. L'import v2 contenant `disabled: true` retourne 200 pour le traitement du document, mais **zéro ligne acceptée** et une erreur `invalid`. L'exemple n'applique donc pas la désactivation promise.

Le guide de tests indique encore protocole 7 / snapshot 5 ; le guide de sécurité Bridge indique protocole 6. L'état courant est protocole 8 / snapshot 6. Ces mentions sont dans des références actuelles, à distinguer des notes historiques qui peuvent conserver leur version d'origine.

**Sources :** [exemple erroné](D:/Dev/PKG.OpenBlindySir/docs/media-and-metadata.md:58), [modèle réel](D:/Dev/PKG.OpenBlindySir/protocol/src/openblindysir_protocol/metadata.py:13), [recette](D:/Dev/PKG.OpenBlindySir/docs/testing.md:94), [sécurité Bridge](D:/Dev/PKG.OpenBlindySir/docs/bridge-security.md:3).

**Correction attendue :** documenter `enabled: false`, aligner les guides actuels FR/EN, tester les exemples JSON contre les modèles et vérifier les versions depuis une source unique. **Critère de fermeture :** import du document publié réussi, morceau exclu des tirages futurs, guides sans contradiction de compatibilité.

## 4. Protections observées et limites restantes

Les contrôles suivants constituent des points favorables, corroborés par le code et les tests existants. Ils n'annulent pas les constats précédents.

- Autorisations par rôle et protections contre la fuite des réponses avant révélation ; tests des transitions, archives, attributions concurrentes, arrêts et reconnexions.
- Contrôle d'Origin sur les mutations et les WebSockets ; cookies de production `__Host-`, HttpOnly, Secure et SameSite Strict ; variante de développement distincte.
- En-têtes CSP, protections d'encadrement et de contenu, réponses privées sans cache. Aucun usage dangereux évident de HTML brut ou d'évaluation de code trouvé dans les recherches ciblées du client.
- Neutralisation des cellules CSV commençant par un opérateur de formule, avec échappement des guillemets.
- Bridge : confinement des chemins, contrôles des liens/junctions, arguments FFmpeg construits sans shell, protocoles/formats autorisés, processus et transferts bornés, écoute intégrale soumise à opt-in.
- Snapshots avec permissions privées et écriture atomique ; tests de corruption et restauration. S02 concerne la transaction applicative autour de cette écriture, pas l'absence d'atomicité du fichier.
- App et Bridge en utilisateurs non-root, lecture seule, `cap_drop=ALL` et `no-new-privileges`. Caddy a une identité par défaut et la seule capacité ajoutée de liaison de port : possibilité de durcissement à étudier, sans vulnérabilité démontrée ici.
- Contrôleur d'hygiène sans signal de secret, musique privée ou artefact interdit dans les 337 fichiers ; contextes Docker limités et workflows avec actions épinglées et permissions restreintes.
- Publication distincte de la CI ordinaire, vérification de tag/commit/version et provenance des artefacts ; absence de publication automatique d'une branche de développement.

**Code partagé :** il sert volontairement d'invitation de session, accessible aux joueurs. Une personne le possédant peut rejoindre sous un nouveau pseudo ; une identité existante exige l'approbation hôte. Ce choix doit être expliqué aux organisateurs, avec rotation/fermeture des invitations si la session doit devenir privée. Il ne remplace pas l'authentification de l'hôte.

### Images Docker : inventaire obtenu, analyse CVE système non achevée

L'inventaire local recense **97 paquets Debian dans l'app**, **295 dans le Bridge**, les identifiants d'image et les paramètres d'isolation. Caddy annonce `v2.11.4`. Ces chiffres sont un inventaire, pas un verdict de sécurité.

Le contrôle automatique d'approbation a **refusé le scan Docker Scout de l'image applicative**, car il peut transmettre à un tiers un inventaire dérivé de l'image, destination et contenu non explicitement autorisés. Le scan du Bridge a également demandé une connexion à un compte Docker. Le mainteneur a ensuite choisi explicitement **de conserver l'audit local et de noter cette limite**. Aucun contournement ni nouveau transfert à Scout n'a été effectué.

Les vulnérabilités des paquets système, FFmpeg et bibliothèques embarquées, de Caddy et de ses composants restent donc **non évaluées par un scanner CVE complet**. OSV et npm ne couvrent pas cette lacune. Avant publication, prévoir un scanner local avec base d'avis à jour et inventaire hors volumes privés, ou une démarche externe explicitement autorisée. Réexaminer les images finales, pas seulement leurs tags ou les dépendances Python/JS.

## 5. Plan de correction et critères avant ouverture publique

1. **Fermer S02 en premier.** Définir le contrat de durabilité, mettre accès et transfert sous transaction, tester erreurs d'écriture et reprise après redémarrage. Aucune révocation ne doit être annoncée durable si elle ne l'est pas.
2. **Durcir les nouvelles routes d'accès : S01, S03, S04, S05.** Formats stricts, garde après lecture du corps, lecture sans sauvegarde, demandes bornées et confirmation identifiable. Ajouter des tests de régression distincts des seuls parcours heureux.
3. **Stabiliser B01 et B03.** Conserver la participation pendant la reprise et valider la capacité derrière un NAT, tout en conservant les protections anti-abus.
4. **Traiter B02 et aligner B04.** Mesurer la réactivité simultanée lors des recherches, optimiser les grands catalogues, publier des exemples conformes et des guides cohérents.
5. **Relancer la validation sur la candidate corrigée.** Suites Python/intégration/web/navigateur, nouveaux tests adverses, hygiène et avis de dépendances ; associer les résultats au commit exact. Les réussites actuelles ne valident pas des corrections futures.

Pour chacun des neuf constats, consigner commit de correction, preuve de non-régression et résultat de la reproduction correspondante. Tout report d'un constat doit avoir une justification documentée et un périmètre d'usage réellement restreint ; conserver un défaut tout en promettant sa capacité ou son comportement n'est pas une résolution.

| Porte de publication | État au 5 octobre | Preuve attendue |
| --- | --- | --- |
| Neuf constats de cet audit | **Ouverts** | Corrections et reproductions négatives sur la candidate |
| Suite automatisée existante | Verte sur le worktree audité | CI verte sur le commit propre final, avec nouveaux tests |
| CVE des images système/FFmpeg/Caddy | **Couverture incomplète** | Scan local complet, avis analysés, images finales identifiées |
| Version officielle et provenance | **Développement, dirty** | Version/changelog cohérents, commit propre, tag et hashes |
| Distribution Windows/Linux/macOS Intel/ARM | Non reconstruite dans cet audit | Builds et smokes natifs des quatre cibles sur la candidate |
| PyPI / GitHub Trusted Publishing | Comptes non vérifiés | Configuration mainteneur et environnements protégés vérifiés |
| Safari/iOS et Android physiques | Non exécutés dans cet audit | AAC, autoplay réel, verrouillage/retour arrière-plan, reprise cookie, QR et préécoute |
| Synchronisation acoustique G1 | Mesure utilisateur en attente | p90 ≤ 60 ms sur trois appareils, selon le protocole du projet |
| Préparation/upload VPS G2 | Mesure utilisateur en attente | p95 < 5 s et confinement, selon le protocole du projet |
| Responsive / accessibilité réelles | Chromium automatisé uniquement | Petit PC 13 pouces, zoom/clavier, nombreux joueurs, NVDA/VoiceOver |
| Hébergement public TLS et opérations | LAN seulement ; non qualifié ici | DNS/certificats publics, exposition des ports, limites, sauvegarde/restauration et retour arrière éprouvés |

La recette manuelle devra notamment couvrir : revue des dernières manches puis retour en arrière, arrêt puis menu de session, notation avec défilement selon la hauteur disponible, classement plafonné à cinq lignes visibles, préécoute privée de 15 secondes centrée, désactivation d'un morceau, édition sous sa carte, pagination et filtres combinés, transfert approuvé et rotation des invitations. Les tests Chromium en couvrent plusieurs parcours, mais ne remplacent pas cette recette sur les appareils et l'hébergement visés.

Les seuils G1/G2 sont les engagements déjà documentés du projet, pas des mesures obtenues ici. Les smokes multi-plateformes doivent également inclure antivirus/SmartScreen et Gatekeeper sur les machines visées avant d'annoncer leur compatibilité.

## 6. Pièces justificatives locales et reprise de l'audit

Ces pièces sont hors Git, destinées à la revue locale. Le rapport conservé dans `docs/audits` constitue le livrable versionnable ; joindre des preuves expurgées à la candidate si nécessaire.

- [Reproductions bornées](D:/Dev/PKG.OpenBlindySir/.local/audit_prepublic_repro.py) et [résultats JSON](D:/Dev/PKG.OpenBlindySir/.local/prepublic-reproductions-2026-10-05.json). Des enregistrements tels que `deep_finish_payload` correspondent à des contrôles réussis, pas à des constats supplémentaires.
- [Avis de dépendances et date de vérification](D:/Dev/PKG.OpenBlindySir/.local/dependency-security-prepublic-2026-10-05.json).
- [Inventaire Docker local](D:/Dev/PKG.OpenBlindySir/.local/prepublic-image-inventory-20261005.json) : versions de paquets et isolation, sans variables d'environnement, volumes ou musique.
- [Empreintes SHA-256 des 337 fichiers examinés](D:/Dev/PKG.OpenBlindySir/.local/prepublic-worktree-20261005.json). Cette capture précède l'ajout de ce rapport et de son lien dans les instructions de publication.
- [Procédure de publication](D:/Dev/PKG.OpenBlindySir/docs/releasing.md), [validation](D:/Dev/PKG.OpenBlindySir/docs/testing.md) et [mesures de synchronisation](D:/Dev/PKG.OpenBlindySir/docs/sync.md).

Reproduire les essais uniquement sur un état temporaire synthétique. Pour les suites, utiliser l'interpréteur du venv, FFmpeg/ffprobe dans le PATH, un répertoire temporaire neuf pour l'intégration et un port séparé pour Playwright. Les commandes de référence sont dans `docs/testing.md` ; les références de version signalées en B04 doivent être corrigées avant d'en faire la recette officielle.

**Avis final :** les bases sont solides et les parcours existants passent ; les changements récents d'accès et quelques cas de capacité introduisent néanmoins des défauts reproductibles. La candidate pourra être réévaluée après correction, couverture des images système et validation des conditions réelles de publication. Aucune release officielle n'est autorisée ou effectuée par ce rapport.
