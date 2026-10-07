# Pack Docker précompilé

Le pack est un candidat de validation local, pas une release publique signée. Il contient les images serveur, Bridge et Caddy, un manifeste de leurs identités et plateformes, les lanceurs et les guides FR/EN. Il évite d’installer Python, Node ou FFmpeg, et évite de compiler sur la machine de l’hôte. Docker avec Compose reste nécessaire. Le pack créé sur cette installation cible Linux/amd64 ; les autres architectures doivent avoir leur propre pack testé.

## Première installation sur Windows

1. Installer Docker Desktop depuis sa source officielle et démarrer le moteur Linux.
2. Vérifier l’origine du pack et son empreinte obtenue indépendamment du téléchargement. `SHA256SUMS` détecte les fichiers modifiés ; un manifeste fourni dans le même téléchargement ne prouve pas à lui seul l’identité de son auteur. Le pack n’est pas signé.
3. Décompresser dans un dossier appartenant à l’utilisateur, puis exécuter `powershell -File .\tools\load-pack.ps1`. Le lanceur vérifie tous les fichiers avant de charger les images et contrôle ensuite leur identité.
4. Exécuter `powershell -File .\tools\party-assistant.ps1`. **Configurer / Setup** demande le dossier musical et l’adresse LAN/VPN, prépare les secrets, puis **Démarrer / Start** lance la partie sans build. **État**, **Ouvrir**, **Arrêter** et **Certificat** sont accessibles dans la même fenêtre. Les mots de passe de configuration appartiennent à l’hôte : ne pas partager une capture de cette fenêtre.
5. Approuver explicitement l’autorité locale sur les appareils de confiance en suivant [le guide du certificat](certificat-local.md). Rien n’installe silencieusement une autorité. La bibliothèque est montée en lecture seule ; ne sélectionner qu’un dossier musical.

Linux/macOS : `sh tools/load-pack.sh`, puis `sh tools/docker-host.sh init --address ADRESSE:8443 --music-dir /chemin/musique --no-build` et `sh tools/docker-host.sh start --no-build`. Le shell vérifie les fichiers et les identités Docker. L’assistant graphique est Windows ; les lanceurs shell restent disponibles. Docker Desktop peut exiger une licence selon l’organisation.

## Mettre à jour et revenir en arrière

Les boutons **Sauvegarder**, **Mettre à jour** et **Restaurer** exécutent `tools/pack-maintenance.ps1`. La sauvegarde privée conserve l’état, la configuration, les montages et les identités d’images avec leurs empreintes. Une mise à jour choisit un nouveau dossier de pack vérifié. Une restauration demande une confirmation explicite, vérifie les empreintes et le volume cible, et sauvegarde l’état actuel avant de remplacer les données. Les images précédentes doivent encore être présentes dans Docker. Ces sauvegardes ne remplacent pas une copie externe des volumes et de l’autorité HTTPS.

Le compose du pack utilise des tags propres à ce pack, pas une image flottante. Conserver le pack précédent et la configuration privée `.local/docker/hosting.env` ainsi que `sources.override.yaml` si présent.

Avant une mise à jour, arrêter les services avec le lanceur, sauvegarder les volumes Docker, notamment `app_data`, ainsi que les deux fichiers privés de configuration et l’autorité Caddy. Ne jamais utiliser `down -v`. Pour une sauvegarde locale de l’état avant l’arrêt : `docker cp openblindysir-app-1:/data/state ./sauvegarde-privee-state` ; les données de cette copie ne doivent pas être publiées.

Charger le nouveau pack après vérification, copier la configuration privée dans son `.local/docker/`, puis lancer **Démarrer**. Les volumes existants sont réutilisés si le nom de projet Compose reste `openblindysir`. Le pack utilise ce projet via `name: openblindysir` dans compose.

Pour un retour arrière, arrêter les services, restaurer la sauvegarde de l’état compatible avec l’ancien pack dans son volume, puis relancer l’ancien pack et son ancienne configuration. **Le protocole 10 écrit des snapshots 8 et lit les formats 1 à 8. Une image de protocole 9 ne doit pas recevoir un snapshot 8 : restaurer sa sauvegarde de format 7.** Le retour arrière restaure aussi les scores et réponses à la date de la sauvegarde.

La signature d’un installateur natif et la publication automatisée de packs multiarchitectures restent des étapes de release. Aucune publication externe n’est réalisée par `tools/distribution_pack.py`.
