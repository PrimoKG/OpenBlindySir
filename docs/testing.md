# Validation des parcours V0.5 — développement

## Vérification automatisée

Depuis la racine, FFmpeg et ffprobe accessibles dans le PATH :

```powershell
uv sync --all-packages --dev
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python tools/gen_ts_types.py --check
uv run pytest -p no:cacheprovider
uv run pytest -m integration -p no:cacheprovider
cd web
npm ci
npm run lint
npm test
npm run build
npx playwright install chromium webkit
npm run e2e
npm run e2e:webkit
```

La sélection pytest par défaut exclut les tests d'intégration et garde les tests
FFmpeg réel si les outils sont installés. Playwright lance serveur + Bridge démo
avec sons synthétiques, sortie Opus et écoute intégrale autorisée pour cette
seule pile de test. La production conserve AAC et l'opt-in désactivé. Sans `uv`,
`E2E_PYTHON` peut désigner l'interpréteur du workspace ; `E2E_PORT` isole la pile.
Les builds WebKit sans `AudioContext` ignorent explicitement les tests audio ;
leur réussite graphique ne valide pas Safari/iOS. Comptes et limites de la
dernière exécution : [DEVLOG](DEVLOG.md).

Régressions : transitions automatiques côté serveur sans hôte connecté, pause de
l’intermission, mode manuel, consommation des annulations avant écoute et reset de
réserve, barèmes sémantiques/révisions concurrentes et motifs de corrections ; revue globale sans publication intermédiaire, notes signées/zéro,
arrêts dans toutes les phases, snapshots V1–V4 → V5, équipes/spectateurs/joueurs
retirés, exports, anti-fuite HTTP/WS ; identité multi-Bridge, upload propriétaire,
sources relatives/NFC/junctions, import JSON partiel, récupération et verrou ;
MP4/MOV/MKV/AVI audio seul, aucune piste audio, première piste audio même si une
autre est par défaut, vidéo >96 MiB, playlists déguisées, processus bornés ;
réécoute exacte, changement de source, cache plein, opt-in et segments courts.
Les tests navigateur contrôlent aussi enregistrement confirmé, recherche,
réécoute à la demande, erreurs, clavier et débordement aux largeurs 320/390/1280.
L'audit couvre les raccourcis/remises à zéro avant accusé serveur, les saisies
concurrentes avec un bouton de score, la reprise d'un seek privé en échec,
la fin d'un transfert à la perte du Bridge ou au rejet de l'upload, les scans
successifs avant réception du catalogue, l'annulation d'une requête bibliothèque
bloquée à l'échéance de confirmation, les scans/uploads lents sans blocage de
PONG/CANCEL et les anciens catalogues reçus après remplacement de connexion.

V0.3 ajoute les codes CLI, la saisie masquée/confirmation et les permissions de
configuration, FFmpeg obligatoire/facultatif, diagnostics sans chemins/secrets,
enregistrement réel et refus d'authentification. Le choix MC est testé avec
révisions concurrentes, manche numérotée, verrou de préparation, réservations,
répétitions, pertes de fichier/Bridge, snapshots et matrice anti-fuite par rôle.
Les tests UI vérifient confirmation avant lancement, clavier/mobile et délai
d'accusé fixe malgré des états répétés, en français et en anglais.

## Vérifier la distribution

```powershell
uv sync --locked --group distribution
uv run python tools/release.py verify
uv run --group distribution python -m build --no-isolation --outdir dist/python protocol
uv run --group distribution python -m build --no-isolation --outdir dist/python bridge
uv run --group distribution python -m twine check dist/python/*
uv run python tools/release.py python-manifest --directory dist/python
uv run python tools/smoke_bridge_distribution.py --wheels dist/python --version 0.3.0.dev0
uv run --group distribution python tools/build_bridge.py --output dist/binary
```

Le build Python par défaut reconstruit le wheel **depuis son sdist**, sans lire
VERSION/LICENSE dans un dossier parent. Le smoke utilise uvx isolé, un dossier
temporaire hors checkout et une configuration synthétique ; il contrôle aide,
version, absence d'écriture implicite, FFmpeg réel, configuration valide/invalide
et doctor JSON expurgé. Pour une archive, passer son chemin complet :

```powershell
uv run python tools/smoke_bridge_distribution.py --archive dist/binary/OpenBlindySir-Bridge-0.3.0.dev0-windows-x86_64.zip --version 0.3.0.dev0
```

Remplacer la version et la plateforme par celles réellement construites. Ne pas
construire pour un autre OS : chaque archive vient d'un runner natif. La matrice
distribution prévoit CPython 3.12/3.13/3.14 sur Linux x64 Ubuntu 22.04, Windows x64,
macOS 15 Intel et arm64 ; chaque cible a son smoke onedir sous Python 3.13.
Les validations locales et leur environnement exact sont dans DEVLOG. Elles ne
prouvent pas le succès futur des runners macOS, SmartScreen/antivirus ou Gatekeeper.
La publication exige une révision propre, les quatre cibles et la configuration
mainteneur décrite dans [releasing](releasing.md) ; aucun smoke ne publie.

## Recette sur les appareils et la bibliothèque réels

Mettre à jour serveur, web et tous les Bridges ensemble : protocole **6** (plage 6 à 6),
snapshot **5** (lecture 1/2/3/4/5), historique **2** (migration ancien/1). Sauvegarder `STATE_DIR` avant mise à
jour et utiliser une soirée de test avec sauvegarde distincte.

1. **Sources** : sélectionner racine et sous-dossier sans doublon. Ajouter/enlever
   un dossier scanné sous la racine ; vérifier le nouveau catalogue et les
   morceaux déjà joués. Tester deux Bridges avec fichiers de même nom et un
   dossier Docker non monté, selon [la procédure](docker.md#sources-dynamiques-et-réécoute).
2. **Recherche/métadonnées** : filtrer par Bridge, dossier, extension et
   disponibilité, rechercher fichier/titre/artiste. Importer des lignes valides,
   absentes, dupliquées, inconnues/ambiguës et incorrectes ; vérifier le rapport
   partiel. Corriger les cinq champs, vider une correction pour revenir à l'import,
   exporter, reconnecter et vérifier leur persistance.
3. **Invitation** : scanner le QR sur le même réseau ; aucun secret dans l'URL.
   Créer un code de récupération, verrouiller les inscriptions, restaurer le même
   joueur sur un autre appareil avec code + mot de passe. Ancien cookie invalidé,
   code à usage unique ; rôle hôte non transmis.
4. **Participation** : former deux équipes, ajouter un spectateur. Il entend le
   son, ne répond/ne marque pas et ne bloque pas le départ. L'animateur voit les
   réponses en direct ; le mode hôte joueur reste confidentiel pendant les manches.
5. **Réponse/audio** : son/délai, réponse validée et brouillon chez un autre joueur,
   pause/reprise, nouvel extrait. Tester le curseur local ±500 ms au prochain PLAY,
   sans effet sur les timestamps serveur. Essayer Bluetooth, arrière-plan et réseau
   lent ; aucun engagement de compensation des temps de réponse.
6. **Avant la fin** : fermer et passer à la manche suivante. Aucun morceau, réponse
   d'autrui ou score publié aux joueurs. Arrêter avant départ, en chargement,
   pendant lecture/saisie et pendant revue ; vérifier la confirmation et les règles
   conserver/annuler. Répéter l'arrêt sans perdre de brouillons ni doubler les scores.
7. **Revue globale** : naviguer/rechercher toutes les manches jouées, réponses,
   statut, réception, temps/rang. Corriger métadonnées, notes négatives, zéro et
   nombres à plusieurs chiffres ; attendre l'accusé avant navigation/validation.
   Rafraîchir ou reconnecter, vérifier conservation et totaux joueurs/équipes.
8. **Réécoute** : aucun transfert avant action. Lire/pause/chercher dans l'extrait
   exact, régler le volume ; les autres joueurs restent en attente. Activer l'opt-in
   local, écouter le morceau complet, chercher plus loin puis revenir à l'extrait.
   Tester Bridge hors ligne, source supprimée/modifiée et erreurs de décodage.
9. **Résultats** : validation finale explicite et confirmation des réponses non
   vérifiées. Comparer journal, recap, classements d'équipes, CSV/JSON à une feuille
   de score connue ; les manches annulées apportent zéro. Nouvelle partie et fin
   de session doivent respecter la conservation d'archives/métadonnées.
10. **Reprise** : crash en saisie et en correction, redémarrage conservant le
    snapshot ; réponses/drafts récupérés, manche interrompue signalée. Les recettes
    de réécoute restent connues, aucun audio n'est dans le snapshot. Pour Docker,
    recréer le conteneur en conservant `app_data`.
11. **Formats** : vraie vidéo avec/sans audio, plusieurs pistes, source volumineuse,
    fichier silencieux/faible/corrompu et codec absent. Diagnostic hôte exploitable,
    erreurs joueur génériques. Aucun audit de la bibliothèque entière n'est annoncé.
12. **Installation** : extraire l'archive entière sur chaque OS/architecture,
    contrôler hash/origine et lancement avec un compte ordinaire, saisie masquée,
    sauvegarde privée, FFmpeg absent/incomplet, certificat privé et secret erroné.
    Consigner les alertes réelles SmartScreen/antivirus/Gatekeeper sans désactiver
    les protections. Répéter uvx hors clone avec les trois versions Python supportées.
13. **Choix MC** : planifier avant préchargement, voir la confirmation, lancer
    explicitement, tester clavier/mobile, concurrence, morceau réservé/déjà joué,
    disparition et déconnexion. Remplacer, revenir au hasard, passer ou arrêter ;
    vérifier l'absence de détails de bibliothèque dans la vue joueur/hôte joueur.

## Mesures avant release

| Validation | Attendu | Statut |
|---|---|---|
| Safari réel iPhone/iPad | Déverrouillage, revue, arrière-plan, reprise, clavier | À faire |
| Chrome réel Android | Audio, revue mobile, QR, récupération | À faire |
| AAC de production | Décodage avec les réglages Docker/natifs | À faire |
| LAN/VPN et Bridge distant | Délais, reconnexions, préparation et segments | À faire |
| Vraie bibliothèque | Volume, silence, RAM, snapshots, import et rescans | À faire |
| Distribution native macOS Intel/arm64 | Build et smoke sur les runners de distribution, permissions, TLS | À exécuter sur ces machines |
| SmartScreen/antivirus/Gatekeeper | Lancement utilisateur et provenance, sans désactivation des protections | À mesurer sur machines représentatives |
| G1 | Audio réel, iOS, écart acoustique p90 ≤60 ms sur trois appareils ; [sync](sync.md) | `PENDING USER MEASUREMENT` |
| G2 | Préparation/upload p95 <5 s vers VPS et confinement ; [architecture §26](architecture.md) | `PENDING USER MEASUREMENT` |

Les navigateurs headless et tests Python ne remplacent pas ces mesures.
English guide and technical reference: [user guide](user-guide.en.md),
[V0.2 technical notes](v0.2.en.md).

## Contrôles V0.5

Les tests ajoutés couvrent secrets/UUID distincts, bootstrap mono-identité,
révocation/rotation durable, usurpation, contrôles après corps streamés, collisions
d'identifiants locaux, propriétaires de jobs, quota catalogue cumulé, disconnexion
et retour d'un Bridge, attente bornée/remplacement explicite et absence de noms de
sources dans la vue/API/diagnostic de l'hôte joueur en jeu.

L'historique est vérifié après changement de noms/catalogues et nouvelle partie,
avec réponses/temps/corrections immuables, accès privé, confirmations strictes,
limites nombre/âge/taille, suppression des deux copies, échec disque et redémarrage.
La machine à états garde l'ajout seul du journal dans chaque partie et contrôle
l'immuabilité de toute archive conservée. Formats futurs refusés, corruption avec
backup valide et reprise des anciennes versions ont leurs tests dédiés.

L'intégration réelle démarre deux Bridges (mêmes IDs de morceaux locaux, secrets
distincts), prépare une manche de chaque source, note et archive, tue le serveur,
reprend cookies/scores/archive, reconnecte les Bridges puis supprime l'archive.
Playwright ajoute historique/purge/réessai, clavier/Échap/focus, Bridges/révocation,
320 px, texte à 200 % et incompatibilité sans boucle de rechargement.
La CI de validation installe Chromium **et WebKit** ; les skips audio WebKit sont
explicites. Consulter le [DEVLOG](DEVLOG.md) pour les résultats réellement exécutés.
Les quatre runners natifs, NVDA/VoiceOver, Safari/iOS/Android physiques, vrais fichiers
et mesures acoustiques restent une recette distincte. Aucun test ne publie V0.5.

L'audit complémentaire V0.5 teste les mutations de credentials refusées par le
disque (rotation, révocation et bootstrap), les écritures concurrentes dans un autre
processus, la libération du verrou après kill, le remplacement à taille/mtime identiques,
les identités/noms/JSON malformés, l'émission privée concurrente et ses chemins réservés.
Le churn joindre/quitter est testé dans le noyau et par HTTP, ainsi que la libération
des identités retirées après archivage. Les snapshots corrompus (types, index, cookies,
récupération, séquence du journal, Unicode, clés dupliquées) doivent reprendre le
secours avec le score et le cookie ; sans secours, aucun état partiel n'est appliqué.
