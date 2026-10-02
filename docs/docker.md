# Tout lancer avec Docker

Docker avec Compose est le seul environnement applicatif à installer sur le PC
hôte. Python, uv, Node.js, Caddy et FFmpeg sont dans les images. Les joueurs
utilisent simplement leur navigateur ; aucun programme OpenBlindySir à installer.
Le [lancement manuel](deployment.md) reste disponible.

## Préparer le PC et les fichiers

Installez [Docker Desktop](https://docs.docker.com/desktop/) sur Windows/macOS,
ou Docker Engine avec Compose sur Linux. Démarrez le moteur **Linux** et vérifiez
`docker version` et `docker compose version` dans un terminal. Compose 2.20 ou
plus récent est nécessaire. Docker Desktop peut demander l'activation de la
virtualisation et de WSL 2 sur Windows : cela relève de son installation.

Téléchargez et décompressez le code du dépôt, ou clonez-le si Git est déjà installé.
Ouvrez un terminal dans ce dossier. Git n'est pas nécessaire avec une archive ZIP.
Un accès Internet est nécessaire au premier build pour télécharger les bases,
les dépendances verrouillées et FFmpeg. La compilation se fait dans Docker.

Choisissez le dossier musical du PC. Il est monté **en lecture seule**, uniquement
dans le Bridge ; le serveur n'y accède pas. Docker Desktop doit autoriser son accès
à ce dossier. Sous Linux, le dossier et ses fichiers doivent être lisibles par
l'utilisateur 10001 du conteneur : adaptez les droits de lecture ou ACL du dossier,
sans donner au conteneur des droits d'écriture ni le lancer comme root.

## Première configuration sous Windows

Remplacez l'IP par celle du PC sur le LAN et le chemin par votre dossier :

```powershell
.\tools\docker-host.ps1 init -Address 192.168.1.42:8443 -MusicDir 'D:\Musique'
.\tools\docker-host.ps1 start
```

Si Windows bloque l'exécution de ce script, utilisez pour cette commande seulement :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\docker-host.ps1 init -Address 192.168.1.42:8443 -MusicDir 'D:\Musique'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\docker-host.ps1 start
```

Cela ne change pas la politique système. Lisez le script du dépôt avant de l'exécuter.
PowerShell est déjà fourni par Windows ; Python et Node.js ne sont pas requis.

`init` construit l'image serveur et utilise son Python pour créer
`.local/docker/hosting.env`, avec trois secrets distincts. Il refuse d'écraser
ce fichier. `start` construit les images nécessaires, démarre les trois services,
attend leur démarrage et ouvre **`/host` dans votre navigateur par défaut**.
Les services continuent à tourner après fermeture du terminal.

Sous Windows, le lanceur prépare un dossier temporaire contenant uniquement les
sources nécessaires aux images, puis le supprime après la construction. Cela
évite que Docker tente d'ouvrir des résultats de tests ou des dossiers locaux
inaccessibles, même lorsqu'ils sont exclus par `.dockerignore`. Aucun outil
supplémentaire ni changement de droits sur ces dossiers n'est nécessaire.
`start -NoBuild` réutilise les images déjà construites et refuse de construire
implicitement depuis le dossier du dépôt.

Pour un premier essai sans bibliothèque musicale :

```powershell
.\tools\docker-host.ps1 init -Address localhost:8443 -Demo
.\tools\docker-host.ps1 start
```

Le Bridge produit alors des sons synthétiques avec le FFmpeg du conteneur.
`localhost` permet seulement de jouer sur ce PC ; les amis utilisent l'IP LAN/VPN.

## Linux et macOS

```sh
sh tools/docker-host.sh init --address 192.168.1.42:8443 --music-dir '/chemin/Musique'
sh tools/docker-host.sh start
```

Pour la démo : `sh tools/docker-host.sh init --address localhost:8443 --demo`.
Le lanceur ouvre le navigateur avec `xdg-open` ou `open`, s'ils sont disponibles.
Sur une machine sans interface graphique, il imprime l'adresse à ouvrir ailleurs.

## Réseau local, VPN privé ou Internet

| Usage | Configuration initiale | Réseau |
|---|---|---|
| LAN | `-Address 192.168.1.42:8443` | Même réseau ; TCP 8443 autorisé dans le pare-feu. |
| VPN privé, par exemple Hamachi | `-Address IP-VPN-DU-PC:8443` | Participants sur le même VPN ; pare-feu de cette interface. |
| Internet | `-Mode public -Address blind.example.com` | Domaine vers l'IP publique, TCP 80/443 redirigés vers le PC et autorisés dans le pare-feu. |

Les options POSIX correspondantes sont `--mode` et `--address`. Le lanceur choisit
le profil privé ou public automatiquement. En privé, il publie seulement HTTPS
sur l'interface choisie. En public, il publie 80/443 ; Caddy obtient le certificat
public et redirige HTTP vers HTTPS. Le port interne **8000 n'est jamais publié**.
Pas de port entrant à ouvrir pour le Bridge.

Le [guide réseau](deployment.md#choisir-le-chemin-daccès) explique aussi CGNAT,
DNS, double NAT et VPN. Docker ne configure ni votre box ni le pare-feu.

## Certificat privé et accès au jeu

En LAN/VPN, le navigateur doit approuver l'autorité privée de Caddy. `start` exporte
uniquement son certificat racine public dans **`.local/docker/root.crt`**.
Les clés restent dans le volume Caddy ; ne partagez pas ce volume.

Faites approuver `root.crt` sur le PC hôte et les appareils des participants, selon
la [procédure du guide manuel](deployment.md#certificat-du-mode-privé). La première
ouverture automatique peut donc afficher une alerte : configurez la confiance et
rouvrez la page, sans désactiver la vérification TLS. Aucun certificat n'est installé
automatiquement. En public, cette préparation privée n'est pas nécessaire.

Consultez `hosting.env` dans un éditeur local. Envoyez aux joueurs uniquement
l'adresse de la partie et **BLIND_PASSWORD**. Gardez **HOST_PASSWORD** pour
l'hôte et **BRIDGE_SECRET** pour le Bridge. Le fichier entier est privé : ne le
partagez pas et ne le mettez pas dans Git.

Le Bridge est déjà lancé et connecté automatiquement. Sur `/host`, rejoignez,
élevez-vous avec le mot de passe hôte, sélectionnez vos dossiers, enregistrez les
réglages et lancez après le test audio des joueurs. Le
[guide utilisateur](guide-utilisateur.md) décrit toutes les étapes.

## Relancer, arrêter et modifier

| Action | Windows | Linux/macOS |
|---|---|---|
| Démarrer et ouvrir | `.\tools\docker-host.ps1 start` | `sh tools/docker-host.sh start` |
| Démarrer sans navigateur | `.\tools\docker-host.ps1 start -NoBrowser` | `sh tools/docker-host.sh start --no-browser` |
| Ouvrir seulement | `.\tools\docker-host.ps1 open` | `sh tools/docker-host.sh open` |
| État des services | `.\tools\docker-host.ps1 status` | `sh tools/docker-host.sh status` |
| Exporter la racine privée | `.\tools\docker-host.ps1 certificate` | `sh tools/docker-host.sh certificate` |
| Arrêter | `.\tools\docker-host.ps1 stop` | `sh tools/docker-host.sh stop` |

Arrêter ou recréer le serveur **efface la partie et les scores en RAM**. Gardez
le PC et Docker allumés, sans mise en veille. `stop` conserve les volumes :
certificats et identité du Bridge. Ne faites pas `docker compose down -v` si vous
voulez les conserver. Les services redémarrent avec Docker grâce à leur politique
`unless-stopped`, sauf si vous les avez arrêtés volontairement.

Pour changer de réseau, modifiez `DOMAIN`, `TLS_HOST`, `TLS_SERVER_NAME`, `HTTPS_PORT`, `BIND_IP`
et `CADDY_PROFILE` dans `hosting.env`, puis arrêtez et relancez. Exemple privé :
`DOMAIN=192.168.1.42:8443`, `TLS_HOST=192.168.1.42`, `HTTPS_PORT=8443`,
`TLS_SERVER_NAME=192.168.1.42`, `BIND_IP=192.168.1.42`, `CADDY_PROFILE=private`. En public : domaine sans port,
port 443, `BIND_IP=0.0.0.0`, `CADDY_PROFILE=public`. Gardez une URL unique pour tous.

Pour utiliser votre musique après une démo, renseignez `MUSIC_DIR` avec son chemin
absolu (`D:/Musique` sous Windows) et mettez `BRIDGE_DEMO=false`, puis arrêtez et
relancez. Le dossier doit déjà exister ; une faute de chemin ne crée pas un dossier
vide silencieusement. Après un ajout de pistes, redémarrez le Bridge pour rescanner :

```powershell
docker compose --env-file .local/docker/hosting.env restart bridge
```

## Utiliser directement Compose

Le lanceur est une commodité. Avec `hosting.env` déjà préparé :

```sh
docker compose --env-file .local/docker/hosting.env up -d --build --wait
docker compose --env-file .local/docker/hosting.env ps
docker compose --env-file .local/docker/hosting.env logs --tail 50 app bridge caddy
docker compose --env-file .local/docker/hosting.env down
```

En public, ajoutez `-f compose.yaml -f deploy/compose.public.yaml` **avant** l'action
`up`, `ps`, `logs` ou `down`. Les lanceurs le font automatiquement et isolent les
variables de configuration héritées du terminal. Les commandes directes Compose
peuvent être influencées par ces variables : utilisez un terminal propre.

## Partager le même environnement

Partagez la même révision du dépôt : les bases d'images sont fixées par digest,
et les dépendances Python/npm par les fichiers lock. FFmpeg est intégré à l'image
Bridge avec les paquets Debian du build, sans dépendre du FFmpeg des PC.
Pour distribuer **exactement vos deux images construites**, exportez-les :

```sh
docker image save -o openblindysir-images.tar openblindysir-server:local openblindysir-bridge:local
```

Sur l'autre PC de la même architecture (par exemple amd64), avec la même
révision du code et les fichiers Compose :

```sh
docker image load -i openblindysir-images.tar
```

Puis utilisez `init` et `start` avec `-NoBuild` sous Windows ou `--no-build` en
POSIX, et les paramètres personnels habituels. Caddy est téléchargé par son digest
fixe s'il manque. Chaque hôte génère ses propres secrets et configure son propre
dossier musical. Les images ne contiennent ni bibliothèque ni secrets.
Ce parcours n'exige pas une image GHCR publiée ; aucune release n'est créée ici.

## Bridge sur un autre PC

Le même Bridge Docker peut se connecter à un serveur situé ailleurs. Sur le PC
musical, créez un fichier privé `.local/bridge.env` avec `BRIDGE_SERVER` (URL HTTPS
du serveur), `BRIDGE_SECRET` et `MUSIC_DIR` (chemin absolu). Il ne doit contenir
ni mot de passe joueur ni mot de passe hôte. Puis :

```sh
docker compose --env-file .local/bridge.env -f deploy/compose.bridge.yaml up -d --build
```

Pour un serveur privé LAN/VPN, ajoutez `BRIDGE_CA_FILE` avec le chemin du `root.crt`
de l'hôte et ajoutez `-f deploy/compose.bridge.private.yaml` avant `up`. La racine
est montée en lecture seule et utilisée par Python pour vérifier HTTPS/WSS.
En public, l'autorité système de l'image suffit. Utilisez les mêmes options pour
`logs`, `restart` ou `down`. Si ce Bridge remplace celui de la pile complète,
arrêtez d'abord le Bridge de cette pile ; un seul Bridge actif doit servir la bibliothèque.

## Dépannage

| Symptôme | Vérification |
|---|---|
| API Docker absente ou démarrage bloqué | Démarrer/réparer Docker Desktop ; vérifier le moteur Linux, WSL/virtualisation et `docker version`. |
| Build échoué | Lire l'étape ; vérifier Internet, espace disque et accès aux registres. |
| Dossier absent ou refusé | Chemin absolu, partage Docker Desktop, droits de lecture Linux. |
| Page injoignable | État des trois services, interface IP réellement présente, pare-feu/VPN/DNS/NAT. |
| Page avec alerte TLS | Faire approuver la bonne racine privée ; vérifier que l'adresse correspond à `DOMAIN`. |
| Bibliothèque déconnectée | Logs Bridge, secret, droits du dossier ; en distant, URL et certificat. |
| Ports déjà utilisés | Changer le port privé et `DOMAIN` ensemble ou arrêter le service concurrent ; le profil public utilise 80/443. |

La CI exerce une partie Docker avec sons synthétiques et certificat vérifié.
Cela ne remplace pas les essais sur votre LAN/VPN, votre musique ou vos appareils.
G1/G2 restent à mesurer, WebKit reste non validé et aucune soirée/VPS n'est déployée
automatiquement. [Référence Docker Compose](https://docs.docker.com/compose/).
