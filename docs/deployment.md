# Héberger OpenBlindySir sur son PC

**Choix d'installation** : le [parcours complet Docker](docker.md) inclut serveur,
interface, Caddy et Bridge/FFmpeg sans installer leurs runtimes sur le PC. Ce guide
décrit le parcours **manuel**, qui reste disponible avec les mêmes règles de jeu.

Un VPS n'est pas nécessaire. Le serveur, l'interface et le Bridge peuvent tourner
sur le même PC. Le serveur reste un seul processus, garde la partie en mémoire et
ne partage pas le dossier musical. Cette procédure utilise le code du dépôt,
avec installation native, sans Docker.

## Choisir le chemin d'accès

| Usage | Adresse envoyée aux amis | Préparation réseau |
|---|---|---|
| Même réseau local | `https://192.168.1.42:8443` (IP LAN du PC, exemple) | Même LAN ; autoriser TCP 8443 dans le pare-feu pour ce réseau. Aucun port de la box à rediriger. |
| Distant par VPN privé, par exemple Hamachi | `https://IP-VPN-DU-PC:8443` | Tous les appareils rejoignent le VPN ; autoriser TCP 8443 sur cette interface pour les participants. Pas de redirection du port de jeu sur la box. |
| Distant par Internet | `https://blind.example.com` (votre domaine) | Domaine vers l'IP publique et redirection TCP 80/443 vers le PC ; pare-feu correspondant. |

Hamachi fournit un réseau virtuel reliant les machines : utilisez l'adresse VPN
affichée pour le PC hôte, pas son adresse LAN, et vérifiez que le VPN choisi prend
en charge les appareils de vos amis. [Documentation du fournisseur](https://vpn.net/).

Le mode privé garde HTTPS avec un certificat local à approuver sur chaque appareil.
Le mode public utilise un certificat public. Le VPN ne remplace pas la configuration
du navigateur, les mots de passe ou les contrôles d'origine d'OpenBlindySir.

## Installer les prérequis

Sur le PC hôte : Git, Python 3.12 ou plus récent, [uv](https://docs.astral.sh/uv/),
Node.js 22 ou plus récent et [Caddy](https://caddyserver.com/docs/install).
Le binaire Caddy standard suffit ; aucun module supplémentaire requis. Placez-le
dans le PATH, ou passez son chemin avec `--caddy` dans les commandes ci-dessous.
Si un autre Caddy tourne déjà, utilisez ce proxy existant avec les réglages de la
dernière section, ou arrêtez son service avant d'utiliser le lanceur.

Installez FFmpeg et ffprobe sur le PC qui contient la musique. Le serveur seul
n'utilise pas FFmpeg. Après avoir cloné le dépôt, depuis sa racine :

```powershell
uv sync --locked
npm --prefix web ci
npm --prefix web run build
```

Ces commandes s'utilisent aussi dans un terminal Linux/macOS. Sous Windows,
si le dossier `bin` de FFmpeg n'est pas dans le PATH, ajoutez-le au terminal du
Bridge avant de démarrer ce dernier :

```powershell
$env:Path = 'C:\Tools\ffmpeg\bin;' + $env:Path
uv run openblindysir-bridge check-ffmpeg
```

Le chemin est un exemple à remplacer par celui de votre installation. Le contrôle
doit afficher FFmpeg et les encodeurs disponibles, dont AAC pour le format normal.

## Créer la configuration

### Réseau local ou VPN privé

Repérez l'IP du PC sur l'interface choisie (`ipconfig` sous Windows, ou l'application
VPN). Utilisez une adresse stable pendant la soirée. Remplacez l'IP exemple :

```powershell
uv run python tools/host_pc.py init --address 192.168.1.42:8443
```

Pour un VPN, la commande est identique avec l'IP VPN du PC. Le mode `private` est
le défaut. Pour tester uniquement sur le PC hôte, utilisez `localhost:8443` ; les
amis ne peuvent pas accéder au serveur avec leur propre `localhost`.

### Accès Internet

Préparez un domaine ou un nom DNS dynamique pointant sur votre IP publique. Sur la
box, réservez l'IP LAN du PC et redirigez **TCP 80 et TCP 443** vers ce PC. Autorisez
ces mêmes ports dans son pare-feu. Ne redirigez pas le port interne 8000. Puis :

```powershell
uv run python tools/host_pc.py init --mode public --address blind.example.com
```

Remplacez ce domaine par le vôtre. Le profil public conserve le port HTTPS standard
443. Caddy obtient et renouvelle le certificat quand le DNS et les ports atteignent
ce PC. [Démarrage du reverse proxy Caddy](https://caddyserver.com/docs/quick-starts/reverse-proxy).

Si l'opérateur utilise un CGNAT, ou si une autre box crée un double NAT, une simple
redirection peut ne pas suffire : utilisez un VPN privé joignable par vos amis ou
faites configurer une vraie entrée publique. Testez l'URL depuis un autre réseau,
par exemple une connexion mobile ; certaines box ne bouclent pas l'IP publique
depuis le LAN. Un enregistrement IPv6 doit aussi pointer vers une interface
accessible et avoir les règles de pare-feu correspondantes.

### Ce que le lanceur prépare

`init` crée `.env` avec trois secrets distincts, le mode choisi et l'adresse. Il
refuse d'écraser un fichier existant. Ce fichier est privé et ignoré par Git.
Consultez-le localement : partagez seulement **BLIND_PASSWORD** avec les joueurs.
Gardez **HOST_PASSWORD** pour l'hôte et **BRIDGE_SECRET** pour le Bridge.

Pour changer d'adresse, modifiez `DOMAIN` dans `.env` puis redémarrez ; écrivez
l'IP/domaine avec son port éventuel, **sans `https://` ni chemin**. Pour changer
de type d'accès, modifiez aussi `PC_HOSTING_MODE=private` ou `public`. Ne changez
pas ces réglages pendant une partie en cours.

Vous pouvez choisir un autre fichier privé avec `--env-file`, à fournir à `init`
et à `run`. Gardez ce fichier hors de Git. Les variables du terminal ont priorité
sur le fichier, comme pour le serveur habituel ; retirez un ancien `DEV_MODE=1`
ou d'anciens secrets de ce terminal si le lancement refuse la configuration.

## Démarrer et arrêter

```powershell
uv run python tools/host_pc.py run --check
uv run python tools/host_pc.py run
```

Si Caddy n'est pas dans le PATH :

```powershell
uv run python tools/host_pc.py run --caddy 'C:\Tools\caddy.exe'
```

Avec un environnement déjà installé mais sans `uv` dans le PATH, vous pouvez aussi
exécuter le lanceur avec `.\.venv\Scripts\python.exe tools\host_pc.py run` sous
Windows, ou `.venv/bin/python tools/host_pc.py run` sous Linux/macOS.

Le lanceur valide les secrets, la configuration et la présence du build Web, puis
démarre le serveur et Caddy. Il affiche les URL joueur et hôte. Le serveur interne
écoute **uniquement sur 127.0.0.1** ; seuls les en-têtes provenant de la boucle
locale sont approuvés. Le profil privé écoute sur l'IP choisie, sans ouvrir
d'autres interfaces. Le profil public sert le domaine en HTTPS. L'API
d'administration Caddy est désactivée dans ces profils.

Gardez ce terminal ouvert et le PC allumé, relié au réseau, sans mise en veille.
**Ctrl+C arrête les deux services. La partie et ses scores sont alors perdus**,
car ils ne sont pas persistés. Si un des services s'arrête, le lanceur arrête l'autre.
Il ne modifie ni le pare-feu, ni la box, ni les certificats approuvés du système.

## Certificat du mode privé

Au premier contrôle/démarrage, Caddy crée sa propre autorité locale. Son certificat
racine public est dans `.local/caddy/pki/authorities/local/root.crt`. Le lanceur
affiche le chemin exact. Conservez le dossier `.local/caddy` entre les soirées.
**Ne partagez jamais les clés ni le reste de ce dossier** ; seul `root.crt` est
destiné aux participants.

Faites vérifier et approuver ce certificat sur chaque appareil qui ouvre la
partie, y compris le PC hôte. Sous Windows, importez-le pour l'utilisateur dans
« Autorités de certification racines de confiance ». Firefox et les appareils
mobiles peuvent avoir leur propre procédure de confiance. Vérifiez l'origine du
fichier avec l'hôte et retirez cette confiance quand vous n'en avez plus besoin.
Ne contournez pas une alerte de certificat et ne désactivez pas TLS : si une alerte
reste affichée, corrigez le certificat ou l'adresse avant de jouer.
[Principe HTTPS local de Caddy](https://caddyserver.com/docs/automatic-https#local-https).

## Connecter le Bridge

Dans un deuxième terminal, sur le PC avec la musique :

```powershell
uv run openblindysir-bridge init
```

Répondez aux questions : URL du serveur, dossier musical, secret **BRIDGE_SECRET**
copié depuis `.env`, nom affiché. Le secret est saisi sans affichage. La
configuration du Bridge est conservée dans le profil utilisateur ; ne la partagez
pas. Pour jouer avec la vraie bibliothèque, vérifiez le dossier puis lancez :

```powershell
uv run openblindysir-bridge scan
uv run openblindysir-bridge run
```

Si le Bridge est **sur le même PC que le serveur**, utilisez
`http://127.0.0.1:8000` comme URL Bridge : ce trafic reste sur le PC. Les joueurs
utilisent toujours l'URL HTTPS imprimée. Si vous avez changé le `PORT` interne,
adaptez cette URL.

Si le Bridge est **sur un autre PC**, utilisez l'URL HTTPS joueur. Pour le mode
privé, configurez aussi la confiance Python dans le terminal du Bridge :

```powershell
$env:SSL_CERT_FILE = 'C:\Partie\root.crt'
uv run openblindysir-bridge run
```

Sous Linux/macOS : `SSL_CERT_FILE=/chemin/root.crt uv run openblindysir-bridge run`.
Le fichier doit être le certificat racine de l'hôte. La vérification TLS reste
active pour le contrôle WebSocket et les uploads.
[Confiance TLS par SSL_CERT_FILE dans HTTPX](https://www.python-httpx.org/environment_variables/#ssl_cert_file).

Pour un premier essai sans musique réelle, après `init` du Bridge, vous pouvez
utiliser `uv run openblindysir-bridge --demo` : il génère des sons synthétiques.
Dans la console Bridge, `r` rescane le dossier et `q` quitte. Le Bridge n'exige
aucune ouverture de port entrant, même lorsqu'il tourne sur un autre PC.

## Ouvrir la partie

Ouvrez l'URL HTTPS imprimée, rejoignez avec le mot de passe de partie, puis allez
sur `/host` avec le mot de passe hôte. Vérifiez « Bibliothèque connectée »,
choisissez les dossiers, enregistrez les réglages et faites tester l'audio par
les joueurs. Le [guide utilisateur](guide-utilisateur.md) décrit ensuite toutes
les étapes du jeu, la notation et la vérification finale.

## Dépannage de l'hébergement

| Symptôme | Vérification |
|---|---|
| `Caddy introuvable` | Installer le binaire officiel et utiliser PATH ou `--caddy`. |
| `Interface absente` | Refaire `npm --prefix web run build` depuis le dépôt. |
| Configuration refusée | Lire le nom de variable et la raison affichée ; garder les secrets forts/distincts et `DEV_MODE=0`. |
| Port déjà utilisé | Vérifier qu'aucun autre proxy/serveur n'utilise ces ports ; changer l'adresse privée ou le `PORT` interne, puis redémarrer. |
| Fonctionne sur le PC, pas chez les amis | Vérifier IP de la bonne interface, VPN commun, pare-feu et isolation Wi-Fi. En public, DNS, NAT/CGNAT et redirection 80/443. |
| Page visible, entrée refusée | Tous doivent utiliser exactement la même URL HTTPS que `DOMAIN`, avec le bon port ; les autres origines sont refusées. |
| Bridge ne se connecte pas | Vérifier URL, secret, FFmpeg ; s'il est ailleurs, confiance TLS et route réseau. |
| Pièces musicales ajoutées non visibles | `r` dans le Bridge pour rescanner, puis recharger la bibliothèque dans le lobby. |

Si vous utilisez déjà un proxy, vous pouvez démarrer uniquement le serveur avec
`uv run openblindysir-server serve`, `.env` contenant `DOMAIN`, `DEV_MODE=0`,
`BIND_HOST=127.0.0.1`, `PORT=8000`, `STATIC_DIR=web/dist` et les secrets. Faites
relayer HTTP et WebSocket vers la boucle locale ; `TRUSTED_PROXIES` doit contenir
uniquement les adresses réelles de ce proxy. Les templates `deploy/Caddyfile.pc.*`
documentent les profils du lanceur ; ils reçoivent leurs variables de celui-ci.

La validation locale ne garantit pas la configuration de votre box, de votre VPN
ou de vos appareils. Le mode public n'a pas été déployé sur Internet pendant cette
intervention. G1/G2, la vraie bibliothèque et les appareils mobiles restent à
mesurer avant une release ; un déploiement VPS et une soirée réelle restent à faire.
