# Construire et publier une release

Le checkout courant est **0.5.0.dev0**, protocole 5, en développement. La V0.5
n'est ni publiée ni stabilisée et ne fige pas le protocole. Les commandes de
publication ci-dessous décrivent une procédure future ; les numéros 0.3.0 sont
des exemples historiques, pas une release annoncée ou une version compatible V0.5.

Les workflows sont distincts : `ci.yml` appelle validation application et
distribution sur push main/PR, **sans publication**. `release.yml` est déclenché
uniquement par push d'un tag `v*`, puis refuse toute forme autre que **vX.Y.Z**
ou **vX.Y.Z-rc.N**, ou incohérente avec VERSION/HEAD/CHANGELOG. Ni branche ni
workflow_dispatch ne publie. Les tags `.dev` sont refusés.

## Dépendances à préparer par le mainteneur

1. Réserver/créer les projets PyPI `openblindysir-protocol` et
   `openblindysir-bridge` (ou leurs pending publishers si les noms sont disponibles).
2. Pour **chacun**, configurer un Trusted Publisher GitHub : owner `PrimoKG`,
   repository `OpenBlindySir`, workflow `release.yml`, environment `pypi`.
3. Créer les environnements GitHub **pypi** et **release**, protéger les tags et
   configurer reviewers/règles de branche/tag selon la politique du dépôt.
4. Autoriser les runners `windows-2025`, `ubuntu-22.04`, `macos-15` (arm64),
   `macos-15-intel` (x64) et vérifier les coûts/disponibilités.

La publication utilise `uv publish --trusted-publishing always` et une identité
OIDC courte : `id-token: write` seulement dans le job PyPI, `contents: write`
seulement dans celui de release GitHub. Aucun API token dans Git/env/examples.
Le mainteneur doit effectuer cette configuration sur ses comptes ; elle ne peut
pas être déduite d'un build local. Référence :
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Préparer le commit et le tag

Depuis un checkout propre de la révision à publier, par exemple pour 0.3.0 :

```sh
uv sync --locked --group distribution
uv run python tools/release.py set-version --version 0.3.0
uv lock
```

Le script met à jour VERSION, les trois modules `_version.py` et les dépendances
exactes Bridge/serveur → protocole. Ajouter `## [0.3.0]` au CHANGELOG avec les
changements de cette release, vérifier les guides/migrations et conserver le
DEVLOG historique. Pour une RC, VERSION devient `0.3.0rc1`, tag `v0.3.0-rc.1`.
Ne pas augmenter le protocole si son schéma n'a pas changé ; sinon générer types
et lock avec son bump explicite avant la validation.

Exécuter Ruff, Pyright, schéma, pytest/integration, web lint/typecheck/test/build
et Playwright, puis les checks distribution. Commiter la révision, attendre la
CI main/PR verte ; créer/pousser le tag validé selon le processus Git du dépôt.
Le workflow refait **tous** les checks, sans reprendre des artefacts d'une PR.
Il vérifie le tag et l'état propre avant toute publication.

## Construction locale

```sh
uv run --group distribution python -m build --no-isolation --outdir dist/python protocol
uv run --group distribution python -m build --no-isolation --outdir dist/python bridge
uv run --group distribution python -m twine check dist/python/*
uv run python tools/release.py python-manifest --directory dist/python
uv run --group distribution python tools/build_bridge.py --output dist/binary
```

Chaque wheel est construit **depuis son sdist**, lequel contient version et
licence propres. Le Bridge ne dépend pas d'un checkout à l'exécution. Le build
natif doit être exécuté sur chaque OS/architecture : PyInstaller onedir/console,
UPX désactivé, FFmpeg absent. Ne pas copier un `.exe` seul.

```sh
uv run python tools/smoke_bridge_distribution.py --wheels dist/python --version 0.3.0
uv run python tools/smoke_bridge_distribution.py --archive dist/binary/OpenBlindySir-Bridge-0.3.0-linux-x86_64.zip --version 0.3.0
```

Adapter version/archive à la construction réelle. Les smokes utilisent un dossier
temporaire extérieur au checkout, uvx isolé et des valeurs synthétiques : aide,
version, FFmpeg, configuration et JSON expurgé, configuration invalide. Les tests
Bridge incluent scan/confinement/extraction avec FFmpeg et assistant masqué.
La CI les exécute sur CPython 3.12/3.13/3.14 et les quatre runners. Les fichiers
ZIP gardent les permissions Unix ; extraction/CLI sont vérifiés. Les vérifications
SmartScreen/antivirus/Gatekeeper et une vraie saisie terminal restent à effectuer
sur machines utilisatrices avant de promettre cette compatibilité.

## Provenance et publication

Chaque artefact comporte version/protocole/commit, état dirty et hashes. Un
build local dirty est autorisé pour essai, **refusé pour publication**. Les ZIP
ont un ordre et timestamps fixés au commit ; compilateurs, patches CPython et
runners empêchent de promettre une reproductibilité binaire octet pour octet.
PyInstaller/hooks/outils Python sont fixés dans uv.lock, npm dans package-lock.
FFmpeg de smoke vient du gestionnaire du runner et n'entre jamais dans l'archive.

La collecte reprend uniquement les artefacts du même run, vérifie métadonnées
des wheels/sdists, commit/version et hashes internes de chaque archive, absence
de config/FFmpeg et présence des **quatre targets**. `release-manifest.json` et
`SHA256SUMS` couvrent les fichiers téléchargeables. PyPI publie protocole puis
Bridge par OIDC ; la release GitHub n'arrive qu'après son succès, RC marquée
prerelease. Aucun serveur, image Docker ni site n'est publié par ce workflow.

## Corriger une release défectueuse

Arrêter le rollout, préserver logs expurgés et artefacts/hash du run. Proposer
le [retour arrière](operations.md) avec son backup antérieur. Sur PyPI, utiliser
le **yank** de la version défectueuse avec motif ; ne pas supprimer arbitrairement
un historique. Marquer la release GitHub avec un avis visible, puis préparer
une nouvelle version corrigée et son nouveau tag après tous les checks.
Ne pas déplacer un tag public ou remplacer ses fichiers sous le même nom.

Si PyPI a accepté le protocole mais pas le Bridge, résoudre la cause et relancer
le job **avec les mêmes fichiers vérifiés**, en vérifiant d'abord ce qui est déjà
publié. Ne pas rebâtir silencieusement sous la même version : les hashes doivent
rester ceux du run. `uv publish` refuse normalement un fichier déjà existant ;
le mainteneur vérifie sa somme et peut reprendre manuellement uniquement les
fichiers manquants via le même environnement/identité. Aucun contournement
automatique de doublon n'est prévu.
