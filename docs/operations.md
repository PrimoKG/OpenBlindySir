# Déployer, mettre à jour et restaurer — V0.5 — développement

[English](operations.en.md). [Installation Bridge](bridge-installation.md),
[Docker](docker.md), [hébergement natif](deployment.md), [dépannage](troubleshooting.md).

## Réseau et proxy

LAN : adresse stable du serveur, par exemple `https://192.168.1.42:8443`, pare-feu
TCP 8443 sur le réseau privé. VPN : adresse de l'interface VPN, participants sur
le même VPN et règle de pare-feu de cette interface. Internet : domaine contrôlé,
DNS A/AAAA cohérents, TCP 80/443 accessibles pour Caddy, redirection de la box si
nécessaire. CGNAT/double NAT peuvent empêcher l'entrée publique ; un VPN privé ou
un VPS est alors un chemin possible. `localhost` ne désigne jamais le PC d'un ami.

Le point d'entrée externe reste HTTPS/WSS. En privé, approuver uniquement la
racine Caddy de l'hôte dans les navigateurs ; pour Python Bridge, `SSL_CERT_FILE`
doit viser ce fichier. Le serveur interne 8000 reste non public. Ne pas faire de
proxy vers plusieurs workers : **une session, un processus serveur**.

Les profils fournis dans `deploy/` servent `/`, `/api/`, uploads et WebSocket
sur la même origine, sans préfixe. Un proxy existant doit préserver ces chemins,
autoriser l'upgrade WebSocket, ne pas mettre en cache les réponses privées,
et transmettre les en-têtes d'origine/hôte corrects. Autoriser uniquement l'IP
du proxy dans les paramètres d'en-têtes transférés, jamais un réseau arbitraire.
Pour limites d'upload/timeouts, garder au moins les bornes de l'application
(catalogue gzip et extraits bornés) ; une limite plus petite doit être diagnostiquée,
pas contournée en supprimant les protections applicatives. Les exemples Caddy et
les commandes exactes restent dans [deployment.md](deployment.md).

## Avant une mise à jour

Prévoir une interruption hors partie ; conserver un export CSV/JSON des résultats
validés. Noter révision/version/protocole et commandes Compose/options `-f` utilisées.
Arrêter proprement Bridge et serveur. Copier **privément** :

- natif : `.env`, dossier `STATE_DIR` (défaut `.local/state`), configuration et
  backups Bridge, configuration Caddy et son stockage privé ;
- Docker : `.local/docker/hosting.env`, overrides Compose, volumes `app_data`,
  `bridge_data`, `caddy_data`, `caddy_config` du projet réellement utilisé.

Voir les noms réels avec `docker compose --env-file .local/docker/hosting.env config --volumes`
et `docker volume ls`; les noms complets dépendent du projet `-p`. Inspecter les
montages du service si un doute subsiste. Sauvegarder à services arrêtés avec
l'outil de sauvegarde/volumes de votre installation Docker. Ne pas copier un
volume en cours d'écriture ni supposer un chemin hôte sous Docker Desktop.
Ne pas utiliser `down -v` : cette option supprime les volumes.

Les snapshots incluent réponses/catalogues et empreintes d'authentification ; ils
sont privés. Ne jamais les joindre à une issue publique. Les fichiers musicaux
complets ne sont pas dans le volume serveur.
Les snapshots et leur backup sont privés avant écriture (Unix `600`, ACL Windows
réservée au compte courant), puis remplacés atomiquement. Le dossier d'état et
les fichiers ne peuvent pas être des liens ou junctions. Les fichiers temporaires
portent un nom aléatoire créé exclusivement ; une sauvegarde refusée préserve le
snapshot précédent et signale l'échec à l'hôte.

## Mettre à jour

Conserver une copie de l'ancienne installation et du backup précédent. Utiliser
une version/révision vérifiée. Dans le checkout natif de cette version :

```sh
uv sync --locked
npm --prefix web ci
npm --prefix web run build
uv run python tools/host_pc.py run --check
```

Pour Docker, reprendre les mêmes profils, environment et montages, puis le
lanceur `start` qui reconstruit les images (ou `up -d --build --wait` avec les
mêmes options `-f`). Ne relancer ni `init` serveur ni génération de secrets.
Installer le Bridge correspondant ou son archive complète ; son config/UUID
reste en dehors de l'archive. Vérifier `--version`, `doctor`, puis registration
hors partie. Démarrer le serveur et les Bridges, recharger les onglets joueurs,
tester le son et une manche synthétique avant d'inviter.

**Compatibilité :** V0.5 = logiciel `0.5.0.dev0`, protocole 14 et plage 14 à 14.
Le serveur publie `/api/compatibility` et renvoie ses formats lors d'un refus de
connexion. Recharger un ancien onglet puis mettre à jour les trois composants.
Le Bridge/protocole Python portent une version exacte commune. Pas de downgrade
automatique ou de protocole mixte. Cette V0.5 n'est pas publiée et ne fige pas le protocole.

## Sauvegardes et retour arrière

V0.5 écrit le **snapshot 11** et lit 1/2/3/4/5/6/7/8/9/10/11 ; l'historique **3** migre les records
anciens/versions 1 et 2. Un format futur inconnu arrête le démarrage : préserver les
fichiers et utiliser la version capable de les lire. Ce refus ne retombe pas sur un
backup plus ancien. Une corruption connue tente `session.previous.json` ; si les
deux copies sont invalides, restaurer le backup privé sans réinitialiser silencieusement.
Les champs anciens absents prennent des valeurs neutres. Une manche en cours
revient en revue interrompue ; aucun audio n'est persisté ou lancé automatiquement.

Sauvegarder **tout `STATE_DIR`**, dont `bridge-credentials.json`, pour conserver les
rotations/révocations. L'autorité est ce registre privé, pas un ancien secret de
`.env`. Les cookies dépendent des mots de passe partie/hôte : les changer les
invalide, mais tourner un secret Bridge ne déconnecte pas les joueurs.
Ne pas partager un UUID entre processus ni gérer simultanément le registre par
plusieurs opérateurs. Les fichiers d'identité délivrés contiennent le secret en
clair et doivent rester privés ou être effacés quand leur copie n'est plus nécessaire.

Le serveur conserve au plus 50 archives, 90 jours et 16 Mio sans audio. Elles sont
figées à la validation finale, servies à la demande aux hôtes et purgées des deux
snapshots lors d'une suppression confirmée. Les exports/backups externes et les
résultats courants ne sont pas effacés par cette action. Limite snapshot : 64 Mio
par fichier ; prévoir jusqu'à 256 Mio avec les copies et écritures temporaires.
Les catalogues cumulés sont bornés à 200 000 pistes. Voir [les opérations V0.5](v0.5.md).

V0.3 **ne lit pas** le snapshot 8. Pour revenir : arrêter les services, restaurer
**l'installation entière, build web/Bridges compris, et le backup pré-migration**
avec ses secrets. Conserver privément l'état récent pour analyse ; ses réponses ne
se fusionnent pas automatiquement dans l'ancien format. Un backup V0.5 nécessite
une installation compatible V0.5. Vérifier santé, accès hôte, registre, catalogues
et export après reprise ; la validation humaine des scores reste nécessaire.

## Distribution et release

Le [workflow de release](releasing.md) valide le commit, les paquets et les quatre
archives avant publication. Aucun token PyPI dans le dépôt ; identité OIDC et
environnement protégé configurés par le mainteneur. Une archive bloquée par une
protection système ou une régression ne doit pas être remplacée sous le même
numéro de version : retirer/yank si nécessaire et publier un correctif versionné.

## Certificat LAN et notation optionnelle

Pour approuver l’autorité HTTPS locale sur Windows/iOS/Android, voir
[certificat-local.md](certificat-local.md). Partager uniquement le certificat public
`root.crt`, jamais ses clés. Le mode LAN est conservé.
La [notation automatique](notation-automatique.md) nécessite de mettre à jour
serveur, Bridge et interface ensemble (protocole 14, snapshot 11), après sauvegarde privée.
