# Installer le Bridge — V0.5 — développement

[English](bridge-installation.en.md). Le Bridge tourne sur l'appareil musical.
Il ouvre une connexion sortante vers votre serveur ; aucun port entrant ni partage
réseau n'est nécessaire. Les sources complètes restent locales. Le serveur et le
build web se préparent avec [Docker](docker.md) ou le [lanceur PC](deployment.md).

**État de distribution :** le dépôt prépare les paquets et archives ; aucune
publication PyPI/GitHub n'est faite par cette modification. Les commandes PyPI
ci-dessous s'utilisent après publication. Depuis le dépôt, remplacez `uvx` par
`uv run` après `uv sync --locked`.

## Choisir une installation

| Parcours | Plateformes prévues | Prérequis |
|---|---|---|
| `uvx openblindysir-bridge` | Windows, Linux, macOS ; CPython **3.12, 3.13, 3.14** | uv, Python compatible (uv peut le fournir), FFmpeg/ffprobe |
| Archive `windows-x86_64` | Windows 10/11 x64 ; runner Windows 2025 | FFmpeg/ffprobe, aucun Python |
| Archive `linux-x86_64` | Linux glibc ≥2.35 (construction Ubuntu 22.04) | FFmpeg/ffprobe, aucun Python ; Alpine/musl exclu |
| Archives `macos-arm64`, `macos-x86_64` | macOS 15+ ; Apple Silicon et Intel séparément | FFmpeg/ffprobe, aucun Python |

La CI prévoit ces runners ; son succès et les artefacts doivent être contrôlés
**avant** release. Les archives ne sont ni signées ni notariées. Les builds locaux
ne valident pas à eux seuls macOS, SmartScreen, les antivirus ni les appareils mobiles.
Les autres architectures restent hors matrice binaire ; ne choisissez pas au hasard.

## Installer et vérifier FFmpeg

FFmpeg **n'est pas inclus** dans les paquets Python ou archives natives. Il est
inclus uniquement dans l'image Docker Bridge. Installez FFmpeg **et ffprobe**, puis
ouvrez un nouveau terminal :

```powershell
winget install --id Gyan.FFmpeg --exact
```

Sur macOS avec Homebrew :

```sh
brew install ffmpeg
```

Sur Debian/Ubuntu :

```sh
sudo apt update
sudo apt install ffmpeg
```

Sources : [manifestes WinGet](https://github.com/microsoft/winget-pkgs/tree/master/manifests/g/Gyan/FFmpeg),
[formule Homebrew](https://formulae.brew.sh/formula/ffmpeg),
[téléchargements FFmpeg](https://ffmpeg.org/download.html).
Pour les autres distributions, utilisez leur gestionnaire de paquets officiel.
Les licences de votre build FFmpeg sont distinctes de celles du Bridge.

```sh
uvx openblindysir-bridge check-ffmpeg
```

Le contrôle vérifie les deux outils (≥4.4), les démultiplexeurs autorisés pour les
extensions configurées, AAC, sortie M4A et filtres `loudnorm`, `afade`, `silencedetect`.
Opus/WebM est facultatif. La découverte utilise le PATH, puis le ffprobe voisin de
FFmpeg. Indiquez les chemins localement s'ils sont absents du PATH :

```powershell
uvx openblindysir-bridge check-ffmpeg --ffmpeg 'C:\Tools\ffmpeg\bin\ffmpeg.exe' --ffprobe 'C:\Tools\ffmpeg\bin\ffprobe.exe'
```

Conservez ces chemins via `OPENBLINDYSIR_BRIDGE_FFMPEG` et
`OPENBLINDYSIR_BRIDGE_FFPROBE` dans votre environnement local, ou comme champs
`ffmpeg`/`ffprobe` dans votre configuration privée. N'ajoutez aucun contournement TLS.

## Première configuration

Installez [uv](https://docs.astral.sh/uv/getting-started/installation/), puis :

Demandez d'abord à l'hôte un **fichier d'identité privé propre à ce Bridge**
([émission côté serveur](#identité-distincte-v05)). Placez-le hors du dépôt partagé
et du dossier de l'archive, avec accès limité à votre compte. Dans les exemples,
remplacez `CHEMIN_IDENTITE.toml` par son chemin réel. Depuis le checkout non publié,
utilisez `uv run` à la place de `uvx`.

```sh
uvx openblindysir-bridge --help
uvx openblindysir-bridge --version
uvx openblindysir-bridge init --credentials CHEMIN_IDENTITE.toml
uvx openblindysir-bridge run --credentials CHEMIN_IDENTITE.toml
```

Sans argument, une première exécution ouvre aussi l'assistant si des réglages
manquent. Utilisez un vrai terminal : les entrées sont au clavier, le secret est
masqué, les messages s'adaptent à la largeur. Un terminal sans saisie masquée est
refusé. `configure` est un alias de `init`.

1. Adresse **de base**, par exemple `https://blind.example.com`, sans `/host`,
   identifiant, paramètres ni fragment. HTTP n'est permis que vers localhost.
2. Dossier musical local existant ; pas de lien symbolique ni junction.
3. À la demande du secret, appuyez sur **Entrée** pour conserver celui du fichier
   d'identité ; ne saisissez pas le mot de passe de partie ou hôte.
4. Conservez le nom du fichier d'identité avec Entrée (1 à 24 caractères, visible
   aux hôtes). Avec `--credentials`, ce fichier détermine UUID, nom et secret au lancement.
5. Confirmez l'enregistrement : toute configuration remplacée a une sauvegarde
   privée `config.toml.bak-…`. Annuler conserve l'original.
6. Confirmez les contrôles : FFmpeg, scan des noms et enregistrement au serveur.
   Aucun fichier entier ni conversion globale. Le résumé indique fichiers,
   configuration, outils et connexion. Le test se déconnecte ; `run` reste connecté.

Un diagnostic portant le même UUID remplace une connexion existante : faites
`init` et `doctor --connect` **hors partie**. Une bibliothèque vide est signalée
par zéro fichier ; le scan ne garantit pas que chaque fichier pourra être décodé.

Le parcours historique sans `--credentials` accepte le **BRIDGE_SECRET** de
bootstrap de l'hôte pour un seul UUID. Pour plusieurs appareils, utilisez un fichier
d'identité et un UUID distincts par Bridge ; partager ce bootstrap ne les autorise pas.

## Configuration durable et diagnostics

| Système | Emplacement par défaut |
|---|---|
| Windows | `%APPDATA%\OpenBlindySir\bridge\config.toml` |
| macOS | `~/Library/Application Support/OpenBlindySir/bridge/config.toml` ; ancienne configuration `~/.config/openblindysir/bridge/config.toml` conservée si présente |
| Linux | `$XDG_CONFIG_HOME/openblindysir/bridge/config.toml`, sinon `~/.config/openblindysir/bridge/config.toml` |

Les fichiers nouveaux et sauvegardes sont privés : mode 600 en Unix, ACL limitée
au compte courant sous Windows. Une erreur de permissions empêche le remplacement.
Gardez ce dossier pour conserver l'UUID et les sous-dossiers scannés. Deux Bridges
doivent avoir des fichiers/UUID distincts ; ne copiez pas leur identité.

```sh
uvx openblindysir-bridge check-config --credentials CHEMIN_IDENTITE.toml
uvx openblindysir-bridge doctor --credentials CHEMIN_IDENTITE.toml
uvx openblindysir-bridge doctor --connect --credentials CHEMIN_IDENTITE.toml
uvx openblindysir-bridge doctor --json --credentials CHEMIN_IDENTITE.toml
```

`check-config` ne scanne pas, n'écrit pas et ne se connecte pas. `doctor` vérifie
aussi les outils ; seul `--connect` annonce puis effectue scan/enregistrement.
Le JSON exclut secret, URL, UUID, nom et chemins personnels. Pour les réglages
locaux, les paramètres ont priorité sur `OPENBLINDYSIR_BRIDGE_*`, puis le fichier.
**Exception :** `--credentials` ou `OPENBLINDYSIR_BRIDGE_CREDENTIALS_FILE` fournit
UUID, nom et secret, avec priorité sur tous les autres réglages d'identité.
`--config` choisit un fichier privé distinct. Pour automatiser, fournissez le chemin
d'identité via `CREDENTIALS_FILE`, l'URL via `SERVER` et la racine via `DIR`, avec
le préfixe `OPENBLINDYSIR_BRIDGE_`. Gardez `--credentials` lors des diagnostics et
de chaque lancement, ou configurez cette variable durablement. Évitez `--secret`
dans l'historique ou la liste de processus.

Codes : **0** réussite, **2** arguments/configuration/accès, **3** FFmpeg,
**4** diagnostic de connexion, **130** annulation. `run` se reconnecte aux pannes
transitoires ; un rejet définitif se termine avec erreur. Ctrl+C arrête le Bridge.

## Lancer une archive native

Téléchargez depuis la release officielle et vérifiez `SHA256SUMS` et le commit.
Sous Windows : `Get-FileHash .\OpenBlindySir-Bridge-…zip -Algorithm SHA256`.
Sur Linux : `sha256sum -c SHA256SUMS` ; sur macOS : `shasum -a 256 -c SHA256SUMS`
(placez les fichiers de la release ensemble). Une somme protège l'intégrité,
pas l'identité d'un téléchargement provenant d'une source inconnue.

Décompressez **tout** le dossier, y compris `_internal` ; le `.exe` seul ne suffit
pas. Dans PowerShell ouvert dans ce dossier :

```powershell
.\openblindysir-bridge.exe --version
.\openblindysir-bridge.exe init --credentials CHEMIN_IDENTITE.toml
.\openblindysir-bridge.exe run --credentials CHEMIN_IDENTITE.toml
```

Sur Linux/macOS, dans le dossier extrait :

```sh
chmod u+x ./openblindysir-bridge
./openblindysir-bridge --version
./openblindysir-bridge init --credentials CHEMIN_IDENTITE.toml
./openblindysir-bridge run --credentials CHEMIN_IDENTITE.toml
```

Les mêmes commandes et fichier de configuration servent pour le binaire et uvx.
Lisez `README.txt`, `LICENSE`, `THIRD_PARTY_NOTICES.txt`, `notices/`, `VERSION` et
`release.json` inclus. Sur un volume `noexec`, déplacez le dossier vers un emplacement
autorisé. SmartScreen/Gatekeeper/antivirus peuvent bloquer un programme non signé :
vérifiez l'origine, la release et le hash, transmettez le diagnostic sans secrets au
mainteneur. Ne désactivez pas ces protections ; le parcours uvx est une alternative.

## Versions et mises à jour

V0.5 utilise le **protocole 6**, plage admise 6 à 6. Bridge, serveur et build web doivent annoncer
exactement ce protocole ; les protocoles 2/3/4/5 sont refusés. Le paquet Bridge dépend
de la **même version exacte** du paquet protocole. Les versions `.dev` du dépôt ne
sont pas des releases. Pour garder une release précise, après publication,
remplacez `VERSION` ci-dessous par la version publiée correspondant au serveur :

```sh
uvx --from openblindysir-bridge==VERSION openblindysir-bridge --version
uvx --from openblindysir-bridge==VERSION openblindysir-bridge run --credentials CHEMIN_IDENTITE.toml
```

Après une mise à jour, vérifiez `--version`, `doctor`, puis hors partie
`doctor --connect`. La configuration ne dépend pas du cache uvx ni du dossier de
l'archive. Sauvegardez-la et le serveur avant migration ; procédure dans
[mise à jour/restauration](operations.md). [Dépannage](troubleshooting.md).

## Identité distincte V0.5

Depuis le checkout non publié, l'hôte délivre un fichier TOML privé via
`uv run openblindysir-server bridge-credential --bridge-id UUID --name 'PC musique' --output .local/private/pc.toml`.
Le dossier parent doit être privé et le fichier de sortie ne doit pas déjà exister.
L'émission ne remplace jamais un fichier existant. Pour une rotation, réutilisez
le même UUID avec un nouveau nom de fichier, puis transmettez la nouvelle identité
et relancez ce Bridge avec son chemin. Les autres Bridges gardent leurs identités.
Les modifications du registre sont verrouillées ; si une autre commande le modifie,
réessayez après sa fin. Utilisez un stockage local acceptant verrous et liens
physiques ; ne supprimez pas `bridge-credentials.lock` pendant le fonctionnement.
Transmettez-le privément au seul propriétaire. Sur son appareil :
`uv run openblindysir-bridge run --config .local/bridge/config.toml --credentials .local/private/pc.toml`.
L'URL et la racine sont configurées localement avec `configure`. Le fichier d'identité
remplace UUID, nom et secret issus de CLI/environnement/configuration, mais pas ces
choix locaux. Gardez le même UUID lors d'une rotation et un UUID différent par instance.
Le secret bootstrap historique ne peut authentifier qu'un seul UUID.
Les commandes Docker, révocation et permissions sont dans [V0.5](v0.5.md).
Le diagnostic de protocole donne la plage requise sans recopier le texte distant.
Cette version est de développement : aucune release, signature ou gel de protocole.
