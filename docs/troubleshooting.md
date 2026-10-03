# Dépannage — V0.3

[English](operations.en.md). Commencez avec `openblindysir-bridge --version`,
`check-config`, `check-ffmpeg`, puis `doctor`. Préfixez avec `uvx` pour le paquet,
`uv run` pour le dépôt, ou utilisez le chemin du binaire. Hors partie, ajoutez
`doctor --connect` : scan des noms, enregistrement et fermeture de la connexion.
Le Bridge connecté se lance avec `run`. [Installation](bridge-installation.md).

## Configuration et outils

| Symptôme/code | Action |
|---|---|
| Sortie 2, configuration refusée | Relancer `init` dans un terminal. URL de base HTTPS sans `/host`, secret Bridge ≥32 caractères, dossier réel accessible, nom ≤24 caractères. HTTP uniquement vers localhost. |
| Saisie masquée indisponible | Ouvrir PowerShell/Terminal ; un pipe ou terminal sans TTY ne convient pas à `init`. Automatiser avec les variables privées `OPENBLINDYSIR_BRIDGE_*`. |
| Accès local refusé | Vérifier droits du compte et fichier/dossier non lié. Pas de lancement administrateur pour contourner le confinement. Vérifier espace disque/ACL avant de réessayer. |
| FFmpeg absent, sortie 3 | Installer FFmpeg **et ffprobe** ; rouvrir le terminal, vérifier PATH ou passer `--ffmpeg`/`--ffprobe`. Voir le guide d'installation par système. |
| Outil incomplet ou ancien | Installer un build ≥4.4 avec AAC, M4A, démultiplexeurs configurés et filtres audio. Les chemins de build ne sont pas copiés dans les rapports. |
| Binaire ne démarre pas | Extraire tout `_internal`, vérifier OS/architecture et SHA256SUMS ; exécution permise sur le volume. Lire le message antivirus, vérifier la provenance. Ne pas désactiver la protection ; préférer uvx si le problème persiste. |

## Connexion sortante

| Diagnostic | Vérifier |
|---|---|
| `network` / reconnexion | URL accessible depuis **l'appareil Bridge** ; DNS, VPN, proxy réseau, port HTTPS, pare-feu sortant. `/host` ne fait pas partie de l'URL Bridge. |
| `certificate` | Adresse couverte par le certificat, date du système et bonne autorité. En privé, fournir la racine de l'hôte via `SSL_CERT_FILE` au Bridge ; ne jamais désactiver TLS. |
| `authentication` | Copier localement **BRIDGE_SECRET** du serveur, pas BLIND_PASSWORD/HOST_PASSWORD. Vérifier qu'aucune ancienne variable ne surcharge le fichier. |
| `protocol` | Mettre à jour ensemble serveur, Bridge et build web : protocole **4**. Un cache web ou ancien onglet doit être rechargé. |
| `catalogue` | Contrôler limites du proxy et logs privés du serveur ; taille gzip, propriétaire/jeton de catalogue, Bridge remplacé en cours d'upload. Relancer le Bridge hors partie. |
| Test réussi mais Bridge hors ligne | `doctor --connect` ferme volontairement le test ; démarrer `run` et garder terminal/PC ouverts. |
| Connexion remplacée | Deux processus utilisent le même fichier/UUID ; arrêter le doublon. Pour deux bibliothèques, utiliser des configurations distinctes. |

Le Bridge n'écoute sur aucun port. Le navigateur et le Bridge utilisent le même
point d'entrée HTTPS public. Le proxy doit relayer WebSocket et uploads sur la
même origine ; pas de préfixe d'URL ni réécriture du secret.
[Réseau et reverse proxy](deployment.md), [opérations](operations.md).

## Catalogue et fichiers

Trois niveaux : dossier **accessible/monté**, dossiers **scannés**, dossiers
**sélectionnés** pour la partie. Un catalogue vide peut provenir d'un mauvais
montage, de zéro extension autorisée ou d'une sélection scannée vide. Lancez
`scan` localement ; vérifiez les compteurs sans partager les noms de votre musique.

Sous Docker, l'interface ne peut pas ouvrir un dossier du PC qui n'est pas monté.
Ajoutez un bind mount en lecture seule sous `/music`, recréez **le Bridge**, puis
ajoutez ce sous-dossier au scan et à la sélection. Le serveur n'a pas à être
redémarré. [Exemple Compose exact](docker.md#sources-dynamiques-et-réécoute).

Liens symboliques/junctions et chemins liés dans leurs parents sont refusés.
Fichiers cachés, extensions hors liste, arborescences trop profondes et collisions
NFC/ID sont ignorés ou diagnostiqués. Limites : profondeur 32, 200 000 fichiers,
64 sous-dossiers scannés, 8 Bridges. Des sélections parentes/enfants ne doublonnent
pas les pistes. Un nouveau fichier sous le montage existant demande un rescan.
Un chemin inaccessible conserve le dernier catalogue valide.

Un catalogue décrit des fichiers ; il ne décode pas toute la bibliothèque.
Durée/tags sont mesurés lors d'une préparation ou écoute privée. L'absence de
durée signifie « non mesurée », pas fichier invalide.
[Formats et métadonnées](media-and-metadata.md).

## Extraction et choix MC

| Échec privé | Action possible |
|---|---|
| `NOT_FOUND` | Fichier déplacé/supprimé : rescan, puis choisir un remplacement. |
| `DECODE_ERROR`, `NO_AUDIO` | Vérifier localement le fichier et son codec ; choisir un autre morceau. Les vidéos fournissent seulement la première piste audio. |
| `TOO_LARGE`, timeout / upload rejeté | Vérifier taille/charge, proxy et réseau ; les limites locales restent actives. Réduire la durée via les réglages permis ou choisir une autre source. |
| `BRIDGE_OFFLINE` | Relancer le Bridge avec son identité ; après retour, remplacer/reconfirmer le choix ou revenir au tirage. |
| Pas de piste disponible | Revoir dossiers sélectionnés, Bridges en ligne, réservations futures et répétitions ; libérer un choix futur ou ajouter des sources. |
| Choix verrouillé | L'extrait a déjà été demandé/préparé ; modifier une manche future non préparée. Pour changer la manche actuelle, utiliser les commandes de remplacement/annulation proposées. |
| Sélection non confirmée | Attendre « Choix enregistré ». Une édition concurrente est refusée ; recharger la vue et réessayer. Le lancement est désactivé pendant l'attente d'accusé. |

Un choix manuel en panne **n'est pas remplacé silencieusement** : message MC,
remplacement, retour au tirage, passer ou arrêter. Une manche manuelle prête
attend **Lancer maintenant**, même avec auto-start. Ni morceau sélectionné, ni
erreur privée de bibliothèque ne sont envoyés aux joueurs.

La normalisation `loudnorm` ajoute du travail ; l'évitement du silence est borné
et ne garantit pas un passage sonore dans tout fichier. Essayez un morceau connu,
vérifiez sa première piste audio, puis désactivez l'option concernée pour comparer.
Ne convertissez pas automatiquement toute la bibliothèque.

## Audio navigateur et reprise

Tester le bip, confirmer « Je l'entends », vérifier volume navigateur/système et
sortie casque. Une interaction débloque l'audio ; garder l'onglet actif. Bluetooth,
mise en veille et onglets suspendus ajoutent du retard : la correction audio
locale agit sur les lectures suivantes, pas sur les points. AAC est la sortie
par défaut. Un navigateur sans décodeur adapté doit essayer un navigateur pris
en charge ; les essais WebKit automatisés ne valent pas une mesure Safari/iOS.

Un redémarrage garde identités/réponses/scores si le volume d'état est conservé et
les secrets inchangés. L'audio en RAM est perdu ; une manche interrompue revient
en revue. Les points restent humains et la publication finale reste explicite.
[Sauvegarde/restauration](operations.md).

## Informations à transmettre

Utilisez `doctor --json` (ou `doctor --connect --json` hors partie ; l'annonce
reste sur stderr), version du serveur, système/architecture, code d'erreur,
étapes et heure approximative. Les hôtes disposent de diagnostics privés dans
le panneau ; relisez-les avant partage. Ne joignez jamais config.toml, ses backups,
`.env`, headers/cookies, secrets, racine musicale, catalogue complet, snapshot ou
clés TLS. `--verbose-paths` est un mode local volontaire, à garder privé.
Les traces navigateur et captures peuvent contenir réponses/noms : expurger.
Les problèmes de sécurité suivent [SECURITY.md](../SECURITY.md).

## V0.5 : identité, historique et formats

Un secret valide pour un UUID ne sert pas à un second Bridge. Vérifier le fichier
privé `--credentials` (prioritaire pour UUID/nom/secret), la révocation et l'absence
de copie de l'identité d'une autre instance. Le bootstrap historique ne s'utilise
que pour son premier UUID. Rotation : conserver UUID, délivrer un nouveau fichier,
reconnecter uniquement ce Bridge. Voir [FR](v0.5.md) / [EN](v0.5.en.md).

Incompatibilité : contrôler `/api/compatibility`, mettre à jour les trois composants
au protocole 5 et recharger l'onglet. Un format snapshot/historique inconnu n'est
pas une invitation à effacer l'état : conserver les deux copies et le registre,
utiliser la version compatible ou le backup pré-migration. Historique vide après
90 jours/50 parties/16 Mio : consulter la politique de rétention ; une sauvegarde
indisponible est signalée à l'hôte. Archive supprimée mais résultats courants
visibles : Nouvelle partie/Fin de session libère la partie courante ; les exports
et backups externes demandent un nettoyage séparé.
