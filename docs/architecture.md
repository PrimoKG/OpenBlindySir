# OpenBlindySir — Spécification canonique (architecture & produit)

> Destination : docs/architecture.md. Les sections 8 (protocole réseau), 9 (synchronisation audio) et 11 (Bridge) sont détaillées dans docs/protocol.md, docs/sync.md et docs/bridge-security.md, qui gardent la même numérotation.
>
> Statut : conception validée ; implémentation démarrée le 2026-10-01 (GO IMPLEMENTATION). L'avancement réel est consigné dans docs/DEVLOG.md.
>
> Règle documentaire : la **SPEC** décrit l'état actuel de la conception et se met à jour quand une décision change ; le **DEVLOG** raconte l'histoire réelle du développement et ne se réécrit jamais (§19).
>
> Licence : MIT.

État courant : **V0.5 développement**, logiciel `0.5.0.dev0`, protocole 13
(plage 13 à 13), snapshot 10, historique 3. Identités/secrets Bridge distincts,
archives privées bornées et passe clavier/focus sont implémentés. Les décisions
et limites opératoires sont détaillées en [V0.5](v0.5.md) / [English](v0.5.en.md)
et [ADR 0015](adr/0015-v05-private-bridges-history-compatibility.md).
Aucune publication, gel du protocole ou validation V1.0 n'est déclarée.

---

## 0. Conventions

### 0.1 Conventions de nommage

Cette sous-section est la seule source pour ces règles.

| Contexte | Forme | Exemples |
|---|---|---|
| Nom public : produit, UI, docs, titres de release | `OpenBlindySir` | OpenBlindySir, OpenBlindySir Server, OpenBlindySir Bridge |
| Dépôt GitHub | `OpenBlindySir` | `PrimoKG/OpenBlindySir` |
| Slug technique : Docker, CLI, distributions, chemins, cookies, loggers | `openblindysir` | `ghcr.io/primokg/openblindysir`, `openblindysir-server`, `openblindysir-bridge` |
| Paquets Python (distribution / import) | tiret pour la distribution, underscore pour l'import | `openblindysir-protocol` / `openblindysir_protocol`, `openblindysir-server` / `openblindysir_server`, `openblindysir-bridge` / `openblindysir_bridge` |
| Paquet web (`private`, non publié) | slug | `openblindysir-web` |
| Concepts métier, classes, messages | **aucune marque** | `Player`, `Round`, `Session`, `GameState`, `Answer`, `ScoreEvent`, `TrackRef`, `Bridge`, `AudioAsset` |
| Services Compose internes | noms fonctionnels | `app`, `caddy` |

- **Formes interdites** : `open-blindy-sir`, `OpenBlindySir` comme nom de module Python, l'ancien nom `Blind` ou `blind` comme marque.
- **Le terme générique « blind test »** (le type de jeu) reste utilisé tel quel.

---

## 1. Vision et périmètre

**OpenBlindySir** est une application web open source et auto-hébergée de **blind test** multijoueur, pensée pour **une seule partie privée à la fois** entre 2 et 15 amis qui jouent **à distance**. Chacun écoute dans son propre navigateur, souvent avec un chat vocal en parallèle.

Le système a trois composants :

1. **OpenBlindySir Server** tourne sur un petit VPS, dans Docker, derrière Caddy. Il sert l'interface web et maintient la partie en RAM, avec snapshots JSON privés pour restaurer joueurs, rounds, réponses et scores. Un seul processus anime la soirée.
2. **OpenBlindySir Bridge** tourne sur le PC qui contient la musique. Il scanne un seul dossier autorisé, envoie un catalogue léger au serveur et produit à la demande un **extrait** (20 à 30 s par défaut, 60 s au plus selon `CLIP_MAX_S`) avec FFmpeg. Il ouvre lui-même une connexion **sortante** vers le serveur. Les fichiers complets ne quittent jamais le PC.
3. **L'interface web OpenBlindySir**, dans le navigateur (joueur ou hôte). Elle télécharge l'extrait entier, le décode, se déclare prête, puis le joue à un instant `startAt` fixé par le serveur, grâce à une horloge synchronisée. La réponse est un texte libre.

**La notation est manuelle par défaut, automatique en option.** Le serveur peut comparer titre, artiste, album, année et featuring aux références figées de la manche. L’hôte garde la correction finale (+N, 0, −N) et reçoit les cas incertains à vérifier. Le serveur **mesure** aussi le moment de chaque validation. **La rapidité est mesurée et affichée, mais elle n'attribue jamais de points automatiquement.**

**Ce qu'OpenBlindySir n'est pas** : une plateforme SaaS, un clone de Kahoot, un système de rooms ou de comptes, un lecteur Spotify/YouTube/Deezer, ni un outil de téléchargement de musique.

**Glossaire**
| Terme | Sens |
|---|---|
| **Session** | Une soirée, restaurable après redémarrage. Elle porte les tokens des joueurs jusqu'à leur expiration ou la fin de session. |
| **Partie** | Une suite de rounds qui se termine par la vérification finale puis le classement. Une session peut enchaîner plusieurs parties. |
| **Round** | Un extrait et ses réponses conservées ; notation puis révélation à la fin de la partie. |
| **Asset** | Un extrait audio préparé et stocké temporairement en RAM sur le VPS. |
| **Reveal** | Publication finale du récapitulatif : morceaux, réponses, temps, rangs et points. |
| **Host Player Mode** | L'hôte joue sans métadonnées pendant les manches ; tous les morceaux sont visibles en revue globale privée. |
| **MC Mode** | L'hôte anime sans jouer et voit tout (fichier, prochain morceau). |

---

## 2. Principes de conception

1. **La solution la plus simple qui fonctionne**, pour 10 à 15 joueurs. Rien n'est conçu pour monter en charge.
2. **Un processus, une boucle d'événements.** Toutes les mutations d'état sont des fonctions **synchrones** (aucun `await` au milieu) et les entrées/sorties se font après. Il n'y a donc ni verrou ni course entre les mutations.
3. **Le serveur fait autorité** sur l'identité, les permissions, l'état, l'heure officielle, les réponses acceptées, l'ordre de validation et les scores. Le navigateur et le Bridge ne décident de rien.
4. **État en RAM avec snapshots privés, pas de base de données.** Les scores sont la projection d'un **journal d'événements**, jamais un nombre modifiable.
5. **Vue complète par destinataire.** À chaque changement, le serveur envoie à chaque client sa vue complète, filtrée selon son rôle. Une seule fonction, `view_for()`, décide de ce que voit qui : c'est le seul point de contrôle contre les fuites de spoilers.
6. **Le Bridge est une frontière de sécurité, et il considère le serveur comme non fiable**, ce qui prépare le cas de plusieurs Bridges appartenant à des personnes différentes.
7. **Remote-first.** La précision visée est celle qui reste perceptible avec un chat vocal en parallèle, soit quelques dizaines de millisecondes. Le vrai risque n'est pas l'horloge mais le cycle de vie audio sur mobile.
8. **Anti-spoiler sur tous les vecteurs** :
   - URL audio opaque ;
   - extrait **sans tags ni pochette** ;
   - aucune métadonnée dans la vue joueur avant les résultats ; revue globale privée pour l'hôte et vue dédiée pour l'animateur ;
   - console du Bridge et logs du serveur **sans noms de fichiers** par défaut.
9. **Les brouillons ne sont pas des faits.** Les brouillons de réponse, de notation et d'ajustement final vivent côté serveur et ne deviennent des faits (réponse validée, `ScoreEvent`) que par une action explicite.
10. **Mono-dev friendly** : peu de dépendances, peu de services, code lisible, tests là où le risque est réel.

---

## 3. Décisions d'architecture

| Sujet | Décision | Justification | Alternative écartée | ADR |
|---|---|---|---|---|
| Backend | Python ≥ 3.12, FastAPI, Uvicorn **1 worker**, Pydantic v2, outillage `uv` (workspace + lockfile) | Pydantic valide chaque message ; asyncio sérialise l'état ; 3.12 apporte `os.path.isjunction` pour le Bridge. | Node/TS : gain modeste, et FFmpeg est plus simple à piloter en Python. Go : idéal pour un binaire de Bridge, mais deux paradigmes à maintenir. | 0001 |
| Frontend | React + TS + Vite. Pas de Redux, pas de routeur (deux vues `/` et `/host`), pas de bibliothèque i18n, pas de framework CSS. Biome pour le lint et le formatage. | Peu de dépendances. L'état vient du serveur, donc `useSyncExternalStore` suffit. | Svelte, Preact : gain marginal, React est plus familier aux contributeurs. | — |
| Temps réel | Un WebSocket par joueur (cookie) et un par Bridge (secret). **Le volumineux passe en HTTP** : catalogue, extraits, téléchargements. | Faible gigue pour la synchro et le push d'état ; HTTP gère bien les tailles et les timeouts. | SSE + POST (synchro plus bruitée) ; WebRTC (surdimensionné). | — |
| Protocole | **Vue complète par destinataire**, regroupée sur 50 à 100 ms, plus quelques messages critiques (`PLAY`, `PONG`, acks). | Reconnexion triviale, un seul point anti-spoiler. | Événements incrémentaux : risque élevé de désynchronisation. | 0006 |
| Bridge | CLI Python, jusqu'à la V1 au moins. WSS sortant et HTTPS PUT. Catalogue indexé par Track ID. FFmpeg en sous-processus avec un gabarit fixe. | Aucun port entrant ; le serveur ne peut jamais désigner un chemin. | Montage réseau (SSHFS/SMB) : expose le système de fichiers. | 0002 |
| FFmpeg | **Côté Bridge uniquement**. L'image serveur ne contient pas FFmpeg. | Image légère, aucun transcodage sur le VPS. | Transcoder sur le VPS : obligerait à y envoyer les fichiers complets. | — |
| Format audio | **Par défaut AAC-LC 128 kbps, 48 kHz stéréo, MP4/.m4a faststart.** Opus/WebM 96 kbps reste candidat. Un seul format, réglé par configuration serveur. Le choix final est fait au spike S0. | AAC se décode partout via `decodeAudioData`. Le support d'Opus sur iOS dépend des versions et doit être mesuré. | MP3 : moins efficace, gestion du délai d'encodeur hétérogène. | 0004 |
| Cache audio | **RAM**, plafond dur (32 Mo au total, 2 Mo par extrait). Éviction selon le rôle (précédent, courant, suivant). | Il n'y a que 2 à 4 Mo utiles, et rien à nettoyer. | tmpfs ou disque : fichiers partiels et nettoyage à gérer, sans bénéfice. | 0005 |
| Persistance | **Snapshots JSON atomiques privés**, sans audio ni base de données. Voir ADR 0009. | La soirée est l'unité de vie. | SQLite : aucune requête ni relation, donc de la cérémonie. | 0009 |
| Scores | **Journal `ScoreEvent` comme source de vérité.** `score = Σ` des événements actifs. | Annulable, testable, traçable. | Compteur modifiable : corrections silencieuses, invariants impossibles à vérifier. | 0007 |
| Temps de réponse | **Horodatage serveur brut** (horloge monotone), sans compensation RTT, affiché au dixième. | Impossible à falsifier pour le client, simple, explicable. | Compensation RTT : gain marginal et nouvelle surface de triche. | 0003 |
| Auth | Mot de passe de partie → cookie `__Host-` HttpOnly. Élévation hôte par un second mot de passe. Bridge par bearer. | Simple, résistant au vol par XSS, reconnexion transparente. | JWT, ou bearer en `localStorage` (lisible en cas de XSS). | — |
| Docker | **Une image applicative** (multi-stage : build web puis Python slim) qui sert aussi la SPA, plus Caddy officiel dans Compose. | Deux conteneurs, TLS automatique. | nginx + certbot, Traefik : plus de configuration. | — |
| Reverse proxy | Caddy inclus par défaut, **optionnel** (variante documentée « j'ai déjà un proxy »). | Rien à configurer pour un débutant. | Caddy obligatoire : gêne qui a déjà Traefik ou nginx. | — |

---

## 4. Architecture globale

```
                     JOUEURS (villes/pays différents, 4G/fibre/wifi, mobile/desktop)
   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────────────────────┐
   │ Joueur A   │ │ Joueur B   │ │ Joueur C   │ │ Hôte (navigateur)           │
   │ SPA React  │ │ SPA React  │ │ SPA React  │ │ vue joueur + tiroir hôte    │
   │ AudioEngine│ │ AudioEngine│ │ AudioEngine│ │ (Player Mode) ou dashboard  │
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └──────────────┬──────────────┘
         │ ① HTTPS GET /                   (SPA statique)       │
         │ ② HTTPS POST /api/session/join                       │
         │      → cookie __Host-openblindysir                   │
         │ ③ WSS /api/ws  ⇄ STATE / PING-PONG / PLAY / réponses │
         │ ④ HTTPS GET /api/audio/{asset_id opaque} (cookie)    │
         └───────────────┬──────────────────────────────────────┘
                         ▼
 ╔═══════════════════════ VPS (Docker Compose) ══════════════════════════════════╗
 ║  ┌──────────────────┐        ┌──────────────────────────────────────────────┐ ║
 ║  │ Caddy :80/:443   │──HTTP──▶ app  (uvicorn, 1 process, 1 event loop)      │ ║
 ║  │ TLS Let's Encrypt│   +WS  │  ├─ Static: SPA buildée                      │ ║
 ║  │ volume caddy_data│        │  ├─ Auth: sessions/tokens hachés (RAM)       │ ║
 ║  └──────────────────┘        │  ├─ Game core: partie/round/réponses/scores  │ ║
 ║                              │  │   (pur, synchrone, horloge injectable)    │ ║
 ║                              │  ├─ Views: view_for(destinataire)            │ ║
 ║                              │  ├─ WS hub joueurs (broadcast regroupé)      │ ║
 ║                              │  ├─ Library: catalogues des Bridges (RAM)    │ ║
 ║                              │  ├─ Bridge link: jobs PREPARE, upload tokens │ ║
 ║                              │  └─ Audio cache: dict RAM ≤ 32 Mo            │ ║
 ║                              └──────────────────────▲───────────────────────┘ ║
 ╚═════════════════════════════════════════════════════│═════════════════════════╝
                                                       │ ⑤ WSS /api/bridge/ws (contrôle)
                                                       │ ⑥ HTTPS PUT /api/bridge/catalog
                                                       │ ⑦ HTTPS PUT /api/bridge/assets/{id}
                          ─────────────── Box / NAT (connexions SORTANTES uniquement) ───
                                                       │
                                     ┌─────────────────┴───────────────────┐
                                     │ OpenBlindySir Bridge (PC)           │
                                     │  ├─ Scanner (racine unique)         │
                                     │  ├─ Catalogue: track_id → relpath   │
                                     │  ├─ Sandbox: lookup + realpath check│
                                     │  ├─ Job runner (1 job, timeouts)    │
                                     │  └─ ffprobe / ffmpeg (gabarit fixe) │
                                     └─────────────────┬───────────────────┘
                                                       │ lecture seule
                                              D:\Music  (racine autorisée)
```

**Déroulé d'un round**
1. Le serveur tire un morceau et envoie `PREPARE` au Bridge (⑤).
2. Le Bridge lance ffprobe puis ffmpeg, téléverse l'extrait (⑦) et répond `JOB_DONE` (⑤). L'asset passe `STORED` en RAM.
3. L'URL opaque apparaît dans la vue. Les clients téléchargent (④), décodent et répondent `READY` (③).
4. Le serveur fixe `official_start_at` et envoie `PLAY` (③). Chaque client planifie la lecture localement.
5. Les validations de réponse sont horodatées par le serveur dès leur réception.
6. Pendant ce temps, le Bridge prépare déjà l'asset N+1.

---

## 5. Composants

### 5.1 Frontend web (SPA)
**Rôle** : afficher la vue envoyée par le serveur, transmettre les intentions (réponse, commandes hôte), gérer l'audio et l'horloge. **Aucune règle de jeu côté client.**

**Modules**
| Module | Contenu |
|---|---|
| `net/socket` | WebSocket, reconnexion avec backoff, store de la vue |
| `audio/clock` | Estimation de l'offset d'horloge (fonctions pures) |
| `audio/engine` | `AudioContext` unique, déverrouillage, téléchargement, décodage, planification, `GainNode` pour le volume local, rapports |
| `audio/unlock` | Recettes de déverrouillage par plateforme |
| `i18n` | `fr.ts` et `en.ts` typés, fonction `t(key, params)` d'environ 30 lignes ; TypeScript impose la parité des clés |
| `player/`, `host/`, `ui/` | Les vues |

**Interface joueur (mobile d'abord)**
- **Lobby** : en-tête « OpenBlindySir », liste des joueurs, bouton « Tester mon audio » puis « Je l'entends ✓ », état audio, « En attente de l'hôte… ».
- **Round** :
  - « ROUND 4 / 20 », compte à rebours, puis barre de progression de l'extrait ;
  - champ « Ta réponse » et bouton **VALIDER** ;
  - une fois validé : **« ✓ Réponse enregistrée »**, sans temps ni rang pendant le round ;
  - pendant OPEN, un **compteur anonyme** « 5/8 ont validé » s'affiche selon la règle du §6.8. Il ne montre ni noms, ni ordre, ni temps.
- **Manche fermée** : sa propre réponse conservée, aucun morceau, réponse d'autrui ou point.
- **Vérification finale** : « L'hôte vérifie les scores… », attente sans classement.
- **Résultats finaux** : podium, classement complet, ajustements finaux affichés.
- **Réglages** : volume local, correction audio manuelle ±500 ms au prochain PLAY.

Les préférences locales (volume, latence, langue) sont stockées dans `localStorage` sous des clés préfixées `openblindysir:`.

**Interface hôte**
- **Host Player Mode** : la vue joueur plus un **tiroir de contrôle** repliable (lancer, forcer, rejouer, stop, passer, fermer, +temps, terminer). Aucune métadonnée pendant les manches. Notation et réécoute privées de toutes les manches à la fin.
- **MC Mode** : tableau de bord complet (joueurs, connexions, états audio, RTT, prochain morceau, nom de fichier) et mêmes commandes.
- **REVIEW** : manche fermée conservée ; manche suivante ou arrêt.
- **FINAL_SCORE_REVIEW** : navigation, notation et réécoute globales, voir §6.4–6.6.
- **Panneau Diagnostic** : voir §21.

Les deux modes sont utilisables sur mobile.

**Accessibilité de base**
- vrais `<button>`, ordre de focus logique, Entrée pour valider ;
- `aria-live` pour le compte à rebours et les statuts ;
- les statuts sont toujours **texte + icône**, jamais la couleur seule (« ✓ Prêt », « ⏳ Téléchargement », « ✕ Déconnecté ») ;
- contraste AA, cibles tactiles d'au moins 44 px, respect de `prefers-reduced-motion`.

### 5.2 Serveur de jeu
**Rôle** : identité, permissions, état de la partie, horloge de référence, sélection des morceaux, horodatage et ordre des réponses, journal des scores, vues filtrées.

- Le cœur du jeu (`game/`) n'importe ni FastAPI ni WebSocket. Il reçoit des commandes et une horloge injectée, et produit un nouvel état.
- `views.view_for(destinataire)` est la seule fonction qui projette l'état vers un client.
- **Frontière** : le serveur ne lit jamais de fichier audio et ne lance jamais FFmpeg.

### 5.3 Service et cache audio (dans le serveur)
- Dictionnaire `asset_id → {bytes, mime, state, round_id, role}`, avec un plafond global et un plafond par extrait.
- Rétention : précédent (pour réécouter après le reveal), courant, suivant (profondeur 1, réglable à 2). Tout le reste est évincé.
- **Upload accepté uniquement pour un job en attente**, avec un upload token à usage unique valable 2 minutes. Le corps est lu en flux et coupé dès qu'il dépasse la limite. Vérification des magic bytes (`ftyp`, `OggS`, en-tête EBML) et du sha256.
- Seul un asset `STORED` peut être servi. Un upload partiel n'est donc jamais visible.

### 5.4 Bridge
**OpenBlindySir Bridge** (appelé « Bridge » dans la suite) : scanner, catalogue, sandbox, exécution des jobs FFmpeg, client WSS/HTTPS, statut console, mode `--demo`. **Il ne connaît pas les règles du jeu.** Détails au §11 et dans [docs/bridge-security.md](bridge-security.md).

### 5.5 Reverse proxy (Caddy)
- Rôle limité : TLS automatique, HSTS, redirection HTTP vers HTTPS, proxy HTTP/WS vers `app:8000`.
- Les en-têtes de sécurité et les limites sont posés **par l'application**, pour qu'elle fonctionne derrière n'importe quel proxy.
- Configuration : la commande `caddy reverse-proxy --from $DOMAIN --to app:8000` suffit, sans Caddyfile.
- Le volume `caddy_data` doit être **persistant**, sinon on se heurte aux limites de Let's Encrypt.

### 5.6 Persistance
Snapshots JSON atomiques privés, sans base de données ni audio sur disque. Voir §14 et
[ADR 0009](adr/0009-session-snapshots.md).

---

## 6. Règles de jeu (V0.2)

### 6.1 Déroulé
File mélangée sans répétition de session → préparation/chargement → compte à
rebours → OPEN. On répond dès la première note. Fermeture par deadline, tous
les joueurs en ligne validés ou l'hôte. REVIEW conserve les réponses, sans
notation ni reveal ; `next` lance la manche suivante. La dernière fermeture
ouvre automatiquement FINAL_SCORE_REVIEW. Pause/reprise, replay et délai restent disponibles.

### 6.2 Réponses
Texte libre ≤1 000 caractères par défaut (limite configurable, plafond 1 500), brouillon synchronisé et validation définitive.
Après fermeture, le dernier brouillon non vide devient CAPTURED. Il garde son
heure de réception serveur, sans rang ni temps de validation. Absence : NONE.
Une soumission tardive est refusée, une seconde validation est ignorée.

### 6.3 Temps et rapidité
`elapsed_ms = réception monotone serveur − premier official_start_at − pauses`.
Le départ officiel ne change ni au replay ni au stop. Aucun timestamp client
ou compensation RTT. Rang strict par ordre de traitement, near_tie sous 300 ms
par défaut, late_start_ms comme aide au jugement. Horodatage mural de réception
conservé dans la revue et les exports, stable après redémarrage. CAPTURED montre
l'heure du dernier brouillon reçu, précision limitée par le debounce de 500 ms.
Aucun point automatique, bonus de vitesse ou barème appliqué par le logiciel.

### 6.4 Revue globale privée
Seulement FINAL_SCORE_REVIEW : toutes les manches entendues, entrée de catalogue
et nom de Bridge d'origine, participants historiques même retirés, titre/artiste/
featuring/album/année, réponses et timing. Dossiers et morceaux à venir restent
masqués à l'hôte joueur pendant IN_GAME. Le MC peut lire les réponses en direct.
Points ±1000 par réponse, zéro explicite (`reviewed=true`), brouillons côté serveur.
Politique CAPTURED `manual` ou `zero` annoncée au lobby. Corrections de métadonnées
et notes survivent aux vues, reconnexions et snapshots. Réécoute exacte et complète
privées : [ADR 0011](adr/0011-global-review-and-private-replay.md).

### 6.5 Corrections
Toutes les notes restent modifiables avant la validation finale. Pas d'événement
de score pendant IN_GAME ou la revue. Les commandes historiques publish,
undo_publish et adjust sont refusées ; l'audit historique reste compatible.
final_set fixe une correction globale par joueur ; final_reset efface seulement
ces corrections. Totaux provisoires = journal actif + drafts des manches incluses
+ correction finale. Totaux d'équipe = somme des joueurs.
Saisie numérique, raccourcis et remise à zéro attendent tous la valeur confirmée
par le serveur ; les contrôles de la ligne et la publication sont bloqués pendant
la sauvegarde. Une vue sans la valeur demandée ne constitue pas un accusé.

### 6.6 Validation obligatoire
final_validate exige la phase attendue et une confirmation explicite. Des lignes
non vérifiées provoquent unreviewed_scores sauf confirm_unreviewed=true.
Publication atomique : événements round non nuls pour chaque manche incluse,
événements final_adjustment non nuls, reveal des manches incluses, gel du journal
et archivage, puis FINAL_RESULTS. Double clic refusé/sans nouvel événement.
Les joueurs attendent avec classements vides ; aucun brouillon privé n'est transmis.

### 6.7 Résultats
Classement figé, égalités partagées, podium, équipes, récapitulatif par joueur
avec métadonnées, réponses, temps/rang, réception et points. Une manche entendue
annulée reste présente avec included=false et zéro point. CSV UTF-8 protégé des
formules/JSON à partir des résultats publiés. Historique privé : 50 dernières
parties. Nouvelle partie garde les joueurs encore inscrits, le catalogue et les pistes entendues ; fin de
session réinitialise joueurs/partie et révoque tokens/codes, tout en conservant
catalogues, métadonnées et archives. Spectateurs sans score/réponse.

### 6.8 Visibilité
| Phase | Joueur et hôte joueur | MC | Panneau hôte |
|---|---|---|---|
| OPEN | Sa réponse ; progression anonyme si ≥3 attendus. | Morceaux et réponses en direct. | Aucune revue/points publiés. |
| REVIEW en IN_GAME | Sa réponse fermée. | Morceau autorisé. | Suivant/arrêt, pas de tableau de notation. |
| FINAL_SCORE_REVIEW | Attente, classements vides. | Attente avec rôle hôte. | Toutes les manches, métadonnées, réponses et totaux provisoires. |
| FINAL_RESULTS | Résultats complets figés. | Idem. | Résultats, bibliothèque et historique. |

players[] ne porte aucun statut de réponse. Vues complètes filtrées par destinataire,
compteur de version propre à chaque connexion ; ni nom de fichier, track_id ou
réponse d'autrui dans une vue joueur avant publication finale.

### 6.9 Sélection et bibliothèque
Sélection multi-dossiers/multi-Bridges, union sans doublons, identités stables.
Équilibrage facultatif : groupes par Bridge et dossier sélectionné le plus profond,
ou dossier contenant le fichier pour une sélection racine ; alternance de groupes
internes mélangés jusqu'à épuisement. Les pistes neuves précèdent les répétitions.
Sources scannées et sélection de partie sont distinctes. Une mise à jour conserve
la fiche d'origine des manches déjà jouées. Recherche/import/édition privée :
[ADR 0012](adr/0012-dynamic-sources-and-metadata.md). V0.3 ajoute le choix manuel
MC pour une manche non préparée, avec révision, réservation et lancement explicite
([ADR 0014](adr/0014-manual-mc-selection.md)).

---

## 7. Machines à états

### 7.1 Partie
```text
LOBBY ──start_game──> IN_GAME ──dernière fermeture / end_game──> FINAL_SCORE_REVIEW
  ▲                                                                  │
  └──────────────────new_game── FINAL_RESULTS <──final_validate────────┘
```
Pas de chemin IN_GAME → FINAL_RESULTS. end_game disponible aussi en LOBBY et
revue globale, idempotent en revue/résultats ; end_session partout révoque la soirée.

| Fin anticipée | Effet |
|---|---|
| LOBBY | Revue vide. |
| QUEUED/PREPARING/LOADING/COUNTDOWN | CANCELLED, sans départ officiel, hors revue des morceaux entendus. |
| OPEN, y compris pause | score : fermeture/capture et manche incluse ; abandon : conservation des réponses, CANCELLED et included=false. |
| REVIEW | Conservation de toutes les manches fermées. |
| FINAL_SCORE_REVIEW/FINAL_RESULTS | Répétition sans effet, aucun draft perdu. |

Son et préchargement arrêtés ; jobs inutiles CANCEL, cache libéré.

### 7.2 Round
```text
QUEUED → PREPARING → LOADING → COUNTDOWN → OPEN → REVIEW
             │              échec/saut │          │
             └─FAILED/remplacement     └─CANCELLED │
                                      next → prochaine manche
                         final_validate → REVEALED (manches incluses)
```
REVIEW est une manche fermée, conservée, permettant next et libérant son slot.
REVEALED n'arrive qu'à la publication finale. Les manches entendues annulées restent
CANCELLED. official_start_at ne bouge pas pour une manche entendue ; annuler un
COUNTDOWN futur retire le départ mais conserve le morceau dans la réserve consommée.
Une allocation annulée avant lecture consomme également le morceau ; un simple
préchargement ne le consomme pas. L’enchaînement REVIEW → prochaine manche est
automatique par défaut après 2 s (minuterie serveur), configurable de 0 à 10 s,
avec pause/reprise et mode manuel. Les critères titre/artiste/personnalisé sont
persistés séparément ; une révision par réponse protège les corrections concurrentes.

### 7.3 Asset
REQUESTED → ENCODING → UPLOADING → STORED → EVICTED, ou FAILED.
Erreurs : NO_AUDIO, DECODE_ERROR, TOO_SHORT, silent_audio, TIMEOUT, BRIDGE_OFFLINE,
INVALID_UPLOAD, CANCELLED. N+1 préparé quand N charge ; clients préchargent hors
lecture. Réécoute privée séparée, sans états/slots/assets du cœur.

### 7.4 Joueur
Connexion ONLINE/OFFLINE/REMOVED ; audio LOCKED/IDLE/LOADING/READY/PLAYING/ERROR ;
réponse NONE/DRAFT/LOCKED/CAPTURED. Cookie existant : identité/brouillon retrouvés,
dernier onglet gagne (4001). Nouveau join soumis au verrou ; reconnexion autorisée.
Code privé six caractères + mot de passe : usage unique, révocation des anciens
tokens, rôle player (nouvelle élévation requise), hachage persistant, cinq essais/min.
Code valable jusqu'à usage, rotation ou fin de session. Retiré : récupération refusée.

### 7.5 Bridge
États OFFLINE/CONNECTED/SYNCING/ONLINE/REJECTED par UUID. Huit liens maximum,
reconnexion d'un même UUID remplace seulement ce lien. Jets/jobs liés au propriétaire.
Racine locale autorisée, dossiers scannés persistés, rescan sérialisé hors boucle
événementielle. Catalogue précédent conservé avec erreur si scan inaccessible.

### 7.6 Pannes et reprise
Bridge perdu : assets RAM jouables, préparation reprend à sa reconnexion. Fichier
indisponible/sans audio/silencieux : remplacement borné. Upload invalide jamais
servable. Snapshot : OPEN interrompu fermé/capturé avec avertissement, départ futur
remis en préparation ; notes, métadonnées, participants et archives conservés,
audio RAM perdu. Hôte absent : réponses ferment à l'échéance, revue attend l'hôte.
Erreur de notation corrigée en brouillon avant publication ; après, journal figé.
Réécoute indisponible : erreur récupérable sans perturber la notation.

---

## 8. Protocole réseau

Règles clés :
- **Enveloppe** `{ "t": "TYPE", ...champs }` : union discriminée Pydantic avec `extra="forbid"` sur tous les messages entrants. Un entier `protocol` est échangé à la connexion ; en cas d'incompatibilité, le serveur force le rechargement de la SPA.
- **HTTP (§8.1)** : `POST /api/session/join {password, nickname}` pose le cookie `__Host-openblindysir` ; élévation hôte par `POST /api/session/host` ; audio servi par `GET /api/audio/{asset_id}` (URL opaque, `no-store`) ; le Bridge envoie son catalogue et ses extraits par `PUT` (secret Bridge, puis upload token à usage unique).
- **WebSocket joueur `/api/ws` (§8.2)** : cookie + vérification de l'`Origin`. Le serveur envoie `STATE {v, view}`, la vue complète filtrée par `view_for()` selon la matrice du §6.8. Pendant OPEN, la vue joueur et celle de l'hôte en Host Player Mode ne donnent sur les réponses que `progress {validated, expected} | null` (à `null` si `expected < 3`) ; `players[]` ne contient aucun champ lié à la réponse du round en cours.
- `ANSWER_SUBMIT` est horodaté par le serveur et tout champ supplémentaire est rejeté ; `ANSWER_ACK` ne contient aucune donnée temporelle ; les commandes `HOST` sont refusées hors session hôte et idempotentes (`round_id` / `expected_phase`).
- **WebSocket Bridge `/api/bridge/ws` (§8.3)** : `Authorization: Bearer <secret propre à l'UUID>`. `PREPARE` encode une piste du catalogue ; `SCAN_SOURCES` modifie seulement les sous-dossiers autorisés sous la racine locale. Aucun argument FFmpeg ; `JOB_FAILED` ne contient pas de chemin absolu. Les tags de `JOB_DONE` servent à la revue globale privée puis au récapitulatif final.

Détail complet : [docs/protocol.md](protocol.md)

---

## 9. Synchronisation audio

Règles clés :
- **Objectifs (§9.1)** : écart p90 entre joueurs ≤ 60 ms sur appareils filaires ou haut-parleur, ≤ 150 ms avec 4G et mobiles ; plus de 250 ms hors Bluetooth est un bug. Le Bluetooth est documenté, avec un curseur manuel en V0.2.
- **Horloge (§9.2)** : `PING`/`PONG` sur l'horloge monotone du serveur ; offset = médiane des θ des 3 échantillons de plus petit RTT parmi les 30 derniers ; rafale de 8 pings à la connexion, à la reconnexion, au retour au premier plan et à chaque LOADING.
- **READY et ready check (§9.3, §9.4)** : l'extrait est téléchargé et décodé en entier avant `READY` ; départ automatique quand les joueurs en ligne déverrouillés sont prêts, `READY_TIMEOUT` de 10 s, « Lancer quand même » pour l'hôte.
- **Départ (§9.5)** : `start_at = now_server + LEAD` (3 000 ms) ; le premier `start_at` du round devient `official_start_at`. Le client planifie via `getOutputTimestamp` (latence de sortie incluse), avec repli sur `outputLatency`/`baseLatency` ; un client en retard démarre à la bonne position.
- **Aucune resynchronisation pendant la lecture (§9.6)** ; une reconnexion repasse par la rafale de synchro et la règle « `T` passé ».
- **Déverrouillage (§9.7)** : un seul `AudioContext` par page, déverrouillé par un geste explicite ; l'état `LOCKED` est signalé au serveur et visible par l'hôte ; recettes spécifiques à iOS (bouton silencieux, `navigator.audioSession`).

Détail complet : [docs/sync.md](sync.md)

---

## 10. Pipeline audio

Source locale → sandbox → ffprobe première piste audio → départ/durée bornés →
FFmpeg audio seulement → mesure de durée/hash → upload unique → cache RAM →
lecture Web Audio synchronisée. Sortie par défaut inchangée : AAC/M4A 128 kbit/s,
48 kHz stéréo, environ 400 ko pour 25 s. Opus/WebM configurable. Formats et limites :
[media-and-metadata](media-and-metadata.md).

Politique partagée protocol/media.py : mp3,flac,wav,mov,ogg,aiff,asf,aac,matroska,avi.
Extension → démultiplexeur forcé (-f), -protocol_whitelist file, -format_whitelist,
entrée file: + chemin résolu ; MOV enable_drefs=0/use_absolute_path=0. Playlists,
flux réseau et fichiers externes refusés. Arguments en liste, jamais shell.
-map 0:a:0 -vn -sn -dn -map_metadata -1 -map_chapters -1 ; première piste audio
même si une autre est « default ». Aucune vidéo/pochette/métadonnée musicale dans le clip.

Départ : fenêtre max(10 s, 8 %) → durée − extrait − max(20 s, 10 %), repli au tiers
si vide ; morceau <8 s refusé. Trois recherches de silence maximum, timeout 10 s
chacune ; normalisation fixe loudnorm=I=-16:TP=-1.5:LRA=11 et fondus facultatifs.
Encode timeout 30 s, ffprobe 10 s ; stdout ≤128 Kio et stderr roulant ≤8 Kio,
processus tué/récolté sur timeout ou annulation. Sortie trop courte/illisible refusée.

Réécoute exacte : cache temporaire Bridge ≤64 Mio ou régénération identique
vérifiée par SHA-256 et révision de source. Écoute complète : opt-in local, offsets
bornés et segments ≤30 s, sans normalisation/fondus. Transfert serveur séparé
≤2 Mio par défaut, deux jobs/un par hôte, aucune conservation durable. Le lecteur
indépendant n'émet pas PLAY/STOP et garde un Blob court. Aucun fichier entier transféré.

---

## 11. Bridge

CLI Python, connexions sortantes HTTPS/WSS, TLS actif sauf démo locale autorisée.
Configuration persistante privée, UUID stable ; priorité CLI > environnement >
fichier pour les choix locaux. Le fichier privé `--credentials` remplace UUID/nom/secret.
Jusqu'à huit Bridges connectés avec secrets distincts ; bootstrap ancien lié à un seul UUID.
Registre privé de hashes/révocations, au plus 64 identités et 200 000 pistes cumulées.
Racine autorisée localement ; sous-dossiers dynamiques relatifs NFC ≤64, parcours
borné à 200 000 fichiers/profondeur 32, aucun lien/junction ni dans la racine ou
ses parents. Nouvelle vérification de chemin/confinement/taille/mtime à l'ouverture.
Collisions NFC/ID exclues ; track_id = hash du chemin relatif à la racine.
Protocoles fermés WELCOME/PREPARE/CANCEL/PING/SCAN_SOURCES ; aucun argument FFmpeg.
Un job actif, file de quatre, timeouts et sorties de processus bornées. Cache privé
des seuls extraits pour réécoute, aucune source complète. Full review désactivée
par défaut, accord du propriétaire du Bridge requis localement.
Console sans noms par défaut, mode démo synthétique ; FFmpeg installé localement
ou fourni dans l'image Docker. V0.3 fournit les wheels/sdists autonomes, assistant
masqué, diagnostics et archives PyInstaller onedir sans FFmpeg
([ADR 0013](adr/0013-bridge-distribution.md)).
Voir [bridge-security](bridge-security.md) et [ADR 0012](adr/0012-dynamic-sources-and-metadata.md).

---

## 12. Sécurité et modèle de menaces

| Menace | Impact | Mitigation | Quand |
|---|---|---|---|
| Joueur qui envoie des commandes hôte | Triche, sabotage | Rôle stocké côté serveur et vérifié à chaque commande `HOST`. Test paramétré sur toutes les commandes. | V0.1 |
| Joueur qui falsifie son temps de réponse | Avantage indu si l'hôte tient compte de la vitesse | Horodatage serveur uniquement, `extra="forbid"`, aucune compensation calculée à partir de données client. `late_start_ms` mesuré côté serveur. | V0.1 |
| Joueur qui découvre le morceau à l'avance (DevTools) | Spoiler | URL aléatoire de 128 bits sans lien avec `track_id`, extrait **sans métadonnées**, `no-store`, préchargement client seulement pendant REVIEW, `view_for()` sans métadonnées pour les joueurs avant le reveal et pour l'hôte joueur pendant OPEN. Écouter le morceau suivant quelques secondes plus tôt reste possible : risque accepté. | V0.1 |
| Token de session volé | Usurpation d'identité | Cookie `__Host-openblindysir`, HttpOnly, Secure, SameSite=Strict ; token de 256 bits **stocké haché** ; expiration avec la session (fin, kick, 24 h d'inactivité). La reconnexion du vrai joueur expulse l'autre. Kick possible. | V0.1 |
| Force brute sur les mots de passe | Accès au jeu, puis aux droits hôte | Limitation par IP des tentatives **échouées** (join 5/min, host 3/min), plafond global, `hmac.compare_digest` ; les connexions réussies ne sont pas comptées, pour ne pas bloquer des amis derrière la même box. **Démarrage refusé** si un secret manque, est faible (< 12 caractères, `BRIDGE_SECRET` < 32), vaut « changeme », ou si `HOST_PASSWORD == BLIND_PASSWORD`. IP réelle via `--proxy-headers`, uniquement depuis le proxy de confiance. | V0.1 |
| XSS par pseudo ou réponse | Vol de session | Échappement React, `dangerouslySetInnerHTML` interdit par le lint, CSP stricte (`default-src 'self'`, pas d'inline, `media-src 'self' blob:`, `frame-ancestors 'none'`). Pseudo : NFKC, 1 à 24 caractères, sans caractères de contrôle, zero-width ni **bidi override**. Réponse ≤ 1 000 caractères par défaut, plafond protocole 1 500. | V0.1 |
| CSRF / détournement de WebSocket inter-site | Actions faites au nom d'un joueur | SameSite=Strict, **vérification de l'`Origin`** sur les POST et le WebSocket, corps JSON obligatoire, aucun CORS. | V0.1 |
| Path traversal depuis le serveur | Lecture de fichiers hors du dossier | `track_id` sert de **clé de dictionnaire, jamais de chemin**. ID inconnu : erreur. | V0.1 |
| Évasion par symlink ou junction | Idem | Liens ignorés au scan, `realpath` et confinement vérifiés au scan **et** à l'ouverture, tests sur un runner Windows. | V0.1 |
| Serveur malveillant vu du Bridge | Lecture de fichiers, exécution, saturation du PC | Protocole fermé de 5 messages, aucun argument FFmpeg libre, bornes fixées par le Bridge, file limitée, timeouts, préfixe `file:`, `protocol_whitelist` et `format_whitelist`, contrôle de la durée produite. Fuite résiduelle (documentée) : arborescence et noms de fichiers. | V0.1 |
| Faux Bridge (secret volé) | Diffusion d'audio choisi par l'attaquant, saturation | Secret fort, upload uniquement pour un job en attente (token à usage unique), ≤ 2 Mo, magic bytes, huit Bridges au maximum, token lié au propriétaire. Secret propre à chaque UUID, hashes privés, rotation/révocation ciblée et contrôle après réception ; bootstrap limité au premier UUID. | V0.5 |
| Rotation CLI simultanée à une révocation hôte | Réactivation d'un secret révoqué | Verrou système non bloquant sur le registre, relecture sous verrou, commit atomique, rollback/cache invalidé si échec ; émission de credentials exclusive et nettoyage d'une émission échouée. | V0.5 |
| Joindre/quitter de façon répétée | Accumulation d'identités, mémoire/disque saturés | Toutes les inscriptions limitées à 60/IP/minute et 600/serveur/minute ; 1 000 identités retirées/actives au plus, puis `game_full`. Nouvelle partie libère les identités retirées après archivage ; `MAX_PLAYERS` reste le plafond simultané. | V0.5 |
| Audio malformé | Plantage du décodeur | Décodage dans le bac à sable du navigateur ; en cas d'échec, `ERROR`. Si la majorité des clients échoue, l'asset passe FAILED. | V0.1 |
| Fichier piégé visant FFmpeg | Exécution de code sur le PC | Fichiers fournis par l'utilisateur (risque faible), vérification de la version de FFmpeg, timeouts, et consigne de ne pas lancer le Bridge en administrateur. | V0.1 (doc) |
| DoS trivial | Soirée gâchée | Messages WS limités à 16 Ko (joueur) et 64 Ko (Bridge), débit plafonné par connexion, 20 connexions par IP au plus (NAT partagé entre amis), `MAX_PLAYERS`, taille des requêtes HTTP bornée. Un DDoS réel est hors périmètre. | V0.1 |
| MITM / absence de TLS | Vol des secrets | HTTPS obligatoire (Caddy + HSTS), cookie Secure, le Bridge refuse toute connexion non TLS hors localhost. | V0.1 |
| Secrets dans les logs ou le dépôt | Fuite | Filtre de masquage dans les logs, aucun secret dans une URL. Hygiène Git au §19.7, secret scanning et push protection GitHub. | V0.1 |
| Chaîne d'approvisionnement | Code malveillant | Lockfiles, Dependabot groupé, actions épinglées par SHA, image de base slim. | V0.1 |
| Évasion du conteneur | Accès au VPS | Utilisateur non root, `read_only`, `no-new-privileges`, seul volume privé `app_data` monté sur l'app ; bibliothèque réservée au Bridge. | V0.1 |
| Mot de passe de partie diffusé à des inconnus | Intrusion | Kick, `MAX_PLAYERS`, verrouillage des inscriptions. | V0.2 |

---

## 13. Modèle de données (conceptuel)

**Session** : `epoch` aléatoire, `started_at`, `bounds` (issues de l'environnement), `joins_locked`.

**Player**
| Champ | Contenu |
|---|---|
| `id` | `p_…` |
| `nickname` | |
| `token_hash` | |
| `role` | player / host |
| `host_mode` | player / mc |
| `connection` | |
| `audio_state` | |
| `clock` | `{offset, rtt_min}` |
| `latency_ms` | Préférence locale ±500 ms, prochain PLAY/STOP seulement |
| `joined_at`, `last_seen` | |
| connexion | Non sérialisée |

**GameSettings** : `rounds`, `clip_seconds`, `answer_grace_s`, `sources[] (bridge_id, folder_prefix)`, `auto_start`, `prefetch_depth`, `allow_repeats`, `balance_folders`, règles de réponse/barème, normalisation et silence.

**GameState**
- `phase` : LOBBY / IN_GAME / FINAL_SCORE_REVIEW / FINAL_RESULTS
- `settings`, `queue[] TrackRef`, `played set<TrackRef>` (à l'échelle de la session), `rounds[]`, `current_index`
- `final_draft {player_id → delta}`, `finalized_at?`

**Round**
- `id` aléatoire, `number`, `track_ref`, `asset_id`, `state`
- **`official_start_at`** : fixé au premier `PLAY`, jamais modifié
- `plays[] {play_id, start_at, clip_offset}`, `deadline`
- `answers {player_id → Answer}`, `ready_received_at {player_id → t}`
- `score_draft {player_id → int}`, `score_reviewed set<player_id>`, `included`, `participant_ids`
- `track_entry`/nom du Bridge capturés au départ, `metadata_revision`, `published_at?`, `reveal` privé avant résultats

**Answer**
| Champ | Contenu |
|---|---|
| `player_id` | |
| `status` | NONE / DRAFT / LOCKED / CAPTURED |
| `text` | Validé ou capturé |
| `draft_text` | |
| `draft_last_changed_at` | Monotone serveur. Diagnostic uniquement, jamais utilisé pour classer. |
| `received_at` | Monotone serveur, renseigné si LOCKED |
| `received_at_wall_ms` | Millisecondes UNIX de réception/capture ; export et revue |
| `elapsed_ms` | Si LOCKED |
| `order` | Si LOCKED, sinon null |
| `near_tie` | |
| `late_start_ms` | |

**ScoreEvent** : journal en ajout seul.
- Champs : `id`, `game_id`, `player_id`, `round_id?`, `delta` (entier signé, borné à ±1000), `kind`, `by` (joueur hôte), `at`, `note?`, `revokes?` (liste d'ids).
- Valeurs de `kind` :

| `kind` | Créé par | `round_id` |
|---|---|---|
| `round` | `final_validate` : note finale de chaque manche incluse, un événement par delta non nul | oui |
| `adjustment` | Héritage V0.1 ; aucune nouvelle commande en V0.2 | optionnel |
| `final_adjustment` | `final_validate`, un événement par joueur dont le delta est non nul | non |
| `revoke` | Migration d'une partie V0.1 non terminée : publications reportées en brouillons ; `undo_publish` désactivé | oui |

- **Invariants** :
  - `score(joueur) = Σ delta des événements actifs`, c'est-à-dire non révoqués ; un `revoke` porte lui-même un delta de 0 ;
  - **aucun champ `score` n'est stocké** ;
  - les brouillons (`score_draft`, `final_draft`) ne sont jamais des événements ;
  - après `FINAL_RESULTS`, aucun événement ne peut s'ajouter pour ce `game_id`.

**TrackRef** : `bridge_id`, `track_id`, `relpath` (**côté serveur uniquement**), `folder`, `ext`, `available`.

**Bridge** : `bridge_id`, `name`, `version`, `state`, `catalog_hash`, `track_count`, `jobs_in_flight`, `last_seen`.

**AudioAsset** : `asset_id` (128 bits aléatoires), `track_ref`, `job_id`, `upload_token_hash`, `state`, `bytes`, `mime`, `actual_start`, `clip_duration`, `tags?`, `role`, `error?`.

La recette de réécoute mémorise aussi durée d'entrée, durée source, SHA-256,
révision taille/mtime et normalisation ; elle survit au snapshot sans octets audio.
Métadonnées importées/corrections : clé `(bridge_id, track_id)` et cinq champs
facultatifs, priorité manuelle non vide puis import puis tags/nom du fichier.

---

## 14. Persistance

| Donnée | Emplacement | Après un redémarrage |
|---|---|---|
| Joueurs, rôles, hashes des cookies | RAM + snapshot privé | Restaurés ; TTL de session incluant l'interruption |
| Partie, réponses, brouillons, journal des scores, réglages | RAM + snapshot privé | Restaurés ; OPEN interrompu ferme les réponses pour correction |
| Catalogues, morceaux déjà entendus, corrections de métadonnées | RAM + snapshot privé | Conservés ; Bridges attendus hors ligne jusqu'à reconnexion |
| Archives figées : 50 parties, 90 jours, 16 Mio | RAM + snapshot privé | HTTP hôte à la demande, suppression/purge confirmée des deux copies, sans audio |
| Assets audio | RAM uniquement | Perdus, jamais écrits dans le snapshot |
| Mots de passe partie/hôte, limites | `.env` | Changer ces mots de passe invalide les cookies ; rotation Bridge indépendante |
| Identités Bridge | `STATE_DIR/bridge-credentials.json` privé | Hashes/révocations font autorité ; sauvegarder avec tout l'état |

`STATE_DIR=.local/state` en natif, `/data/state` dans Compose avec volume `app_data`.
`session.json` est écrit atomiquement avec fsync ; `session.previous.json` fournit un
repli si le dernier fichier est corrompu. Deux fichiers illisibles empêchent un démarrage
silencieux avec perte de session. Format JSON versionné, classes autorisées, taille ≤64 MiB,
sans pickle, audio ni secrets en clair. Format 10 lit 1–10, historique 3 migre 1/2 ;
un format inconnu bloque le démarrage, sans repli sur une copie plus ancienne.
Deux copies et leurs écritures temporaires exigent jusqu'à 256 Mio.
Les réponses et chemins relatifs du catalogue sont
privés dans ce dossier : protéger son accès et le sauvegarder. Une erreur d'écriture laisse
la partie fonctionner et affiche un avertissement à l'hôte. Voir [ADR 0009](adr/0009-session-snapshots.md).

La lecture est bornée pendant le transfert disque, et les JSON du registre et des
snapshots refusent les clés dupliquées. Types, index de manche, séquence du journal et données de récupération
sont validés avant application. Une corruption de format connu utilise un secours
validé ; sans secours, la reprise refuse de modifier la partie. Les versions inconnues
restent un motif de refus explicite. Le registre de secrets se coordonne avec les
commandes CLI via `bridge-credentials.lock` ; son verrou système est libéré même à
l'arrêt brutal et une contention exige de relancer l'action.

**Pas de SQLite.** Fin de session révoque les cookies et vide la partie et la liste des
morceaux entendus ; les archives et corrections de métadonnées restent disponibles à l'hôte.

---

## 15. Configuration

| Niveau | Où | Contenu |
|---|---|---|
| Secrets | `.env` | `BLIND_PASSWORD`, `HOST_PASSWORD`, `BRIDGE_SECRETS` facultatif (UUID → secret), `BRIDGE_SECRET` bootstrap facultatif si map fournie |
| Déploiement | `.env` | `DOMAIN` (ex. `openblindysir.example.com`), `TRUSTED_PROXIES`, `LOG_LEVEL`, `LOG_FORMAT=text\|json`, `LOG_TRACK_NAMES=false` |
| Sauvegarde de soirée | `.env` / Compose | `STATE_DIR=.local/state` en natif, `/data/state` sur le volume `app_data` dans Compose. Fichiers privés, sans audio ni secrets en clair ; voir ADR 0009. |
| Limites serveur (valeurs par défaut raisonnables) | `.env` | `MAX_PLAYERS=20`, `CLIP_MIN_S=5`, `CLIP_MAX_S=60`, `CLIP_FORMAT=aac`, `CLIP_BITRATE=128`, `AUDIO_CACHE_MB=32`, `MAX_CLIP_MB=2`, `READY_TIMEOUT_S=10`, `ANSWER_MAX_CHARS=1000`, `NEAR_TIE_MS=300`, `SESSION_IDLE_TTL_H=24` |
| Développement | `.env` | `DEV_MODE=1` : cookie non Secure, mots de passe faibles tolérés, logs verbeux. **Jamais en production.** |
| Réglages de partie | Interface hôte, dans les bornes de l'environnement | Manches, extrait, délai après extrait, sources, rôle, départ automatique, répétitions, consigne/barème, brouillons capturés, loudnorm et silence |
| Bridge | CLI > env > `config.toml` pour choix locaux ; `--credentials` prioritaire pour identité | URL, racine et outils locaux ; fichier privé UUID/nom/secret |

> **Note de nommage.** Dans `BLIND_PASSWORD`, « BLIND » désigne le concept fonctionnel (le mot de passe pour rejoindre le blind test), pas une marque. Ce nom est retenu parce qu'il est court et parlant. Les variables ne portent pas de préfixe de marque : elles vivent dans le `.env` propre au déploiement, donc il n'y a pas de collision possible. C'est pour cette raison que le mode développement s'appelle simplement `DEV_MODE`.

Il n'y a **pas d'identifiant partagé** (aucune variable `BLIND_USERNAME`) : chaque joueur entre `BLIND_PASSWORD` et choisit un pseudo, qui devient son identité pour la session (§7.4).

Il n'y a **pas de fichier de configuration serveur** en V1 : un concept de moins à apprendre.

---

## 16. Structure du dépôt

Les commentaires `# EN` et `# FR` indiquent la langue de rédaction des documents (§18).

```
OpenBlindySir/
├── README.md                 # EN — « # OpenBlindySir » + bandeau de statut ; pitch, Bridge, archi, quickstart, sécurité, droits musique
├── LICENSE                   # MIT
├── CHANGELOG.md              # EN — orienté utilisateurs/releases (Keep a Changelog)
├── CONTRIBUTING.md           # EN
├── SECURITY.md               # EN
├── CODE_OF_CONDUCT.md        # EN — Contributor Covenant
├── VERSION                   # numéro de version unique du monorepo
├── .gitignore
├── .gitattributes            # normalisation des fins de ligne (LF) — dev sous Windows
├── .env.example              # valeurs fictives uniquement
├── pyproject.toml            # workspace uv (members: protocol, server, bridge)
├── uv.lock
├── Dockerfile                # multi-stage: web build → python slim runtime
├── compose.yaml              # name: openblindysir — app + caddy (image GHCR)
├── .github/
│   ├── workflows/{ci,validation,distribution,release,nightly}.yml
│   ├── ISSUE_TEMPLATE/bug.yml, feature.yml, config.yml       # EN
│   ├── PULL_REQUEST_TEMPLATE.md                               # EN
│   └── dependabot.yml
├── protocol/                 # paquet Python partagé : modèles Pydantic des messages
│   ├── pyproject.toml        # distribution « openblindysir-protocol », license = "MIT"
│   └── src/openblindysir_protocol/
├── server/
│   ├── pyproject.toml        # « openblindysir-server », script CLI openblindysir-server
│   ├── src/openblindysir_server/
│   │   ├── main.py  config.py  logging.py  security.py
│   │   ├── auth/             # sessions, cookies, rate limit
│   │   ├── game/             # PUR : state, rounds, answers (timing), scoring (journal),
│   │   │                     #       final_review, selection, views (view_for)
│   │   ├── ws/               # hub joueurs, endpoint bridge
│   │   ├── library/          # catalogues, arborescence
│   │   └── audio/            # cache RAM, jobs, uploads
│   └── tests/
├── bridge/
│   ├── pyproject.toml        # « openblindysir-bridge », script CLI openblindysir-bridge
│   ├── src/openblindysir_bridge/
│   │   ├── cli.py  config.py  scanner.py  catalog.py
│   │   ├── sandbox.py  ffmpeg.py  jobs.py  client.py  demo.py
│   └── tests/                # fixtures générées à l'exécution (lavfi), jamais commitées
├── web/
│   ├── package.json          # "name": "openblindysir-web", "private": true, "license": "MIT"
│   ├── package-lock.json  vite.config.ts  biome.json
│   ├── src/
│   │   ├── main.tsx  app/  player/  host/  ui/
│   │   ├── net/  audio/  i18n/
│   │   └── protocol/         # types TS générés depuis protocol/
│   └── tests/  e2e/
├── deploy/
│   ├── compose.no-proxy.yaml
│   ├── compose.dev.yaml
│   └── examples/nginx.conf, traefik.md
├── tools/
│   ├── gen_ts_types.py       # Pydantic → JSON Schema → TS (vérifié en CI)
│   ├── bots.py               # N faux joueurs (intégration + charge)
│   ├── sync_analyze.py       # analyse d'un enregistrement micro (clics)
│   └── check_repo_hygiene.py # aucun fichier audio / .env / secret tracké
└── docs/
    ├── architecture.md       # FR — CETTE spec (état actuel de la conception)
    ├── protocol.md           # FR — §8 complet : protocole réseau
    ├── sync.md               # FR — §9 complet : synchronisation audio
    ├── bridge-security.md    # FR — §11 complet : Bridge, sandbox, packaging
    ├── deployment.md         # EN — déploiement (utilisateurs externes)
    ├── testing.md            # FR — stratégie + checklist manuelle appareils réels
    ├── DEVLOG.md             # FR — histoire réelle du développement
    └── adr/                  # FR
        ├── 0000-template.md
        ├── 0001-single-process-in-memory-server.md
        ├── 0002-bridge-outbound-connection-and-sandbox.md
        ├── 0003-server-side-answer-timing.md
        ├── 0004-audio-format.md                 # « Proposé » jusqu'au spike S0
        ├── 0005-no-database-v01.md
        ├── 0006-full-state-snapshots-over-websocket.md
        └── 0007-score-event-journal.md
```

Les trois paquets Python restent distincts (`openblindysir_protocol`, `openblindysir_server`, `openblindysir_bridge`) et forment un workspace uv ; le nom `OpenBlindySir` n'est jamais un nom de module Python (§0.1).

---

## 17. Docker et déploiement

**Environnement complet Docker (2026-10-02, GO du mainteneur)**
- `Dockerfile` multi-stage, cibles `app` et `bridge` ; bases Node 24, Python 3.13
  et uv fixées par digest multi-architecture, dépendances Python/npm verrouillées.
- `openblindysir-server:local` : serveur mono-processus et SPA construite,
  **sans FFmpeg**, utilisateur 10001, `/healthz`, `openblindysir-server serve`.
- `openblindysir-bridge:local` : Bridge existant et FFmpeg/ffprobe Debian,
  utilisateur 10001, identité persistée dans `/data`, extraits temporaires en tmpfs.
- Le contexte de build est une allowlist : aucun secret, musique, cache ou Git.
- Les bases proposent amd64/arm64 ; le parcours CI est réellement testé sur amd64.
  Ne pas confondre cette disponibilité des bases avec une validation arm64 complète.
- Images construites localement et partageables avec `docker image save/load` ;
  publication GHCR et tags de release ci-dessous **restent prévus**, sans image publiée
  ou release affirmée avant leur création effective.

**Tags de l'image**
| Tag | Exemple | Quand |
|---|---|---|
| `edge` | `edge` | Chaque merge sur `main` |
| `X.Y.Z-rc.N` | `0.1.0-rc.1` | Pré-release, sans `latest` |
| `X.Y.Z`, `X.Y`, `latest` | `0.1.0`, `0.1`, `latest` | Releases uniquement. **Aucun `latest` avant une v0.1.0 réellement jouable.** |

**`compose.yaml` (présent)**
- **`name: openblindysir`** : préfixe stable ; services `app`, `caddy`, `bridge`.
- Tous sont en filesystem read-only, capacités réduites, no-new-privileges,
  tmpfs temporaire et restart unless-stopped. L'app garde un seul processus.
- Caddy et Bridge partagent l'espace réseau de l'app. Le backend 8000 écoute
  uniquement en loopback ; HTTP localhost du Bridge reste conforme à ses règles.
  Les proxies approuvés sont seulement 127.0.0.1 et ::1 ; aucun réseau Docker
  arbitraire n'est approuvé. Aucun port backend n'est publié.
- Les ports publiés sur cet espace réseau servent Caddy : HTTPS uniquement sur
  l'interface privée choisie ; HTTP 80 ajouté par `deploy/compose.public.yaml`
  pour le mode public sur 80/443. Image Caddy officielle fixée par digest.
- Profils `deploy/Caddyfile.docker.private/public` ; autorité locale en privé,
  ACME en public, administration désactivée. Racine exportable, clés en volume.
- Bibliothèque montée uniquement dans le Bridge, en lecture seule ; le montage
  refuse de créer un dossier hôte absent. Volumes Caddy, identité Bridge et snapshots
  applicatifs `app_data:/data` persistants.

**Parcours utilisateur**
- **Docker sur PC, sans autres runtimes applicatifs** :
  1. Docker avec Compose et moteur Linux, archive du dépôt ou clone ;
  2. `tools/docker-host.ps1 init` ou `sh tools/docker-host.sh init` avec adresse
     LAN/VPN ou domaine public et dossier musical ; configuration privée générée
     dans un conteneur, dans `.local/docker/hosting.env` ;
  3. `start` construit/démarre tous les services et ouvre `/host` dans le navigateur ;
  4. en privé, faire approuver le certificat racine exporté ; préparer pare-feu,
     VPN ou DNS/redirection selon le réseau. Rien de cela n'est modifié automatiquement ;
  5. partager seulement URL et mot de passe de partie. [Guide Docker](docker.md).
- **Bridge Docker distant** : `deploy/compose.bridge.yaml` et son override privé
  pour la racine TLS ; même image, connexion sortante HTTPS, aucun port publié.
- **Proxy Docker personnalisé et images GHCR** : parcours de distribution encore
  prévu. Le proxy natif existant reste documenté dans le guide manuel.
- **Développement** :
  - sans Docker : `DEV_MODE=1 uv run openblindysir-server` pour le serveur, `npm run dev` (proxy Vite vers `/api` et le WebSocket), `uv run openblindysir-bridge --demo` ou le Bridge sur un vrai dossier ;
  - le job Docker CI construit les images et joue en HTTPS/WSS avec Bridge démo.

**Hébergement natif sur PC (2026-10-02, demandé par le mainteneur)**
- Le VPS est une option ; le même serveur mono-processus peut tourner sur le PC
  de l'hôte, avec le Bridge sur ce PC ou sur un autre ordinateur.
- `tools/host_pc.py init` prépare une configuration privée et des secrets ; `run`
  lance le serveur sur la boucle locale et Caddy devant lui, sans Docker.
- Profil privé : HTTPS sur l'IP LAN ou VPN choisie, certificat local approuvé par
  les appareils, aucun port entrant de la box à ouvrir pour le jeu. Profil public :
  domaine vers le PC, HTTPS public et TCP 80/443 redirigés vers Caddy.
- Les cookies Secure, l'origine exacte, les secrets et les permissions restent
  inchangés. Le lanceur ne modifie pas le pare-feu, la box ou la confiance système.
- [Guide d'hébergement](deployment.md) et [guide utilisateur](guide-utilisateur.md)
  en français pour l'interface v0.1. Cela ne valide ni G1/G2 ni le déploiement VPS
  ou une release. Le parcours Docker ci-dessus est disponible en complément ;
  la distribution GHCR, le VPS et la soirée réelle restent à réaliser.

---

## 18. Open source et documentation

- **License: MIT.** Fichier `LICENSE` contenant le texte MIT standard :
  ```
  MIT License
  Copyright (c) 2026 PrimoKG
  ```
  Le titulaire est le propriétaire du dépôt GitHub tel qu'il apparaît au moment du GO. Aucun autre nom légal n'est deviné.
- **MIT figure aussi dans** :
  - le README (badge et section License) ;
  - CONTRIBUTING (« inbound = outbound » : les contributions sont acceptées sous MIT) ;
  - les métadonnées des paquets (`license = "MIT"` et `license-files = ["LICENSE"]` dans chaque `pyproject.toml`, `"license": "MIT"` dans `package.json`) ;
  - les labels OCI de l'image ;
  - les notes de release.
- **README** : il commence par
  ```
  # OpenBlindySir
  ⚠️ Early development — API/protocol may change.

  OpenBlindySir is an open-source, self-hosted, remote-first multiplayer blind-test
  application. Your music library stays on your own computer and is exposed to the
  game only through the OpenBlindySir Bridge.
  ```
  Le bandeau **« ⚠️ Early development — API/protocol may change. »** reste en place jusqu'à la v1.0. Le README contient ensuite :
  - ce que le projet n'est pas ;
  - le principe du Bridge, illustré par un schéma ;
  - un aperçu de l'architecture ;
  - le quickstart, dès qu'il existe (avant cela, la mention « not usable yet ») ;
  - le statut, License: MIT, la sécurité (lien vers SECURITY.md) ;
  - **« Music & rights »** :
    - chacun fournit ses propres fichiers ;
    - les fichiers restent sur sa machine, à part les extraits temporaires en RAM sur son propre serveur ;
    - l'utilisateur est responsable de ce qu'il utilise ;
    - aucune musique n'est fournie ;
    - aucun téléchargement depuis des plateformes commerciales.
- **CONTRIBUTING** :
  - installation de l'environnement de dev, commandes de test, style (ruff, Biome) ;
  - Conventional Commits ;
  - ouvrir une issue avant une PR importante ;
  - **périmètre explicite** (pas de comptes, pas de rooms, pas de streaming depuis des plateformes) ;
  - règle « aucun fichier audio réel dans le dépôt ».
- **SECURITY.md** : signalement via GitHub Private Vulnerability Reporting, seule la dernière version mineure est supportée, réponse dans la mesure du possible.
- **CODE_OF_CONDUCT** : Contributor Covenant.
- **Issues** : formulaires YAML (bug : navigateur, OS, versions du serveur et du Bridge, logs ; demande de fonctionnalité). Les questions vont dans Discussions.
- **ADR** : elles nomment le produit « OpenBlindySir ». Leurs noms de fichiers sont des noms techniques sans marque (`0001-single-process-in-memory-server.md`…).

**Langue des documents**

| Langue | Éléments |
|---|---|
| **Anglais** (public open source) | `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, modèles d'issues et de PR, description du dépôt GitHub et topics, GitHub Releases et notes de release, documentation utilisateur et de déploiement (`docs/deployment.md`, et plus tard le dépannage) |
| **Anglais** (convention technique) | Messages de commit (Conventional Commits), identifiants et commentaires de code, noms d'événements de log, codes d'erreur du protocole |
| **Français** (conception interne) | `docs/architecture.md`, `docs/protocol.md`, `docs/sync.md`, `docs/bridge-security.md`, `docs/testing.md`, `docs/DEVLOG.md`, `docs/adr/*`, notes techniques internes |
| **Français** (produit V0.1) | Textes de l'interface web via `i18n/fr.ts` ; messages console du Bridge |

> L'interface dispose des dictionnaires complets FR/EN. Les messages console du Bridge restent en français. `SECURITY.md`, en anglais, résume le modèle de menaces et renvoie à `docs/bridge-security.md`, en français.

**Trois traces aux rôles distincts**

| Fichier | Public | Contenu | Règle |
|---|---|---|---|
| `docs/architecture.md` (SPEC) | Contributeurs | État **actuel** de la conception | Mise à jour quand une décision change |
| `docs/DEVLOG.md` | Mainteneur | **Histoire réelle** : objectifs, décisions, échecs, tests réellement exécutés, dette technique | **Jamais réécrit après coup**, on ajoute seulement |
| `CHANGELOG.md` | Utilisateurs | Added / Changed / Fixed / Security, par release | Aucun détail interne |
| `docs/adr/NNNN-*.md` | Contributeurs | Décisions **structurantes** uniquement | Format court, voir ci-dessous |

**Format d'une ADR**
```
# NNNN — Titre de la décision
Statut : Proposé | Accepté | Remplacé par NNNN   ·   Date : YYYY-MM-DD
## Contexte
## Options considérées
## Décision
## Conséquences
```
Une ADR remplacée n'est pas supprimée : on change son statut et on la relie à la nouvelle.

---

## 19. Processus de développement

### 19.1 Principe
**Comprendre, puis modifier, tester, documenter, commiter, pousser**, par petites unités logiques. Jamais un gros lot de code suivi d'un unique commit.

### 19.2 Démarrage du dépôt (au « GO IMPLEMENTATION »)
1. Vérifier si le dossier est déjà un dépôt Git ; sinon `git init`, branche `main`.
2. Créer **`.gitignore` et `.gitattributes` avant tout commit**. Le `.gitignore` couvre :
   - `.env` et `.env.*` (sauf `.env.example`) ;
   - `node_modules/`, `dist/`, `build/`, `.venv/`, `__pycache__/`, caches (pytest, ruff, pyright), `coverage/`, `playwright-report/`, `test-results/`, `*.log` ;
   - **toutes les extensions audio** (`*.mp3 *.flac *.wav *.m4a *.aac *.ogg *.opus *.oga *.wma *.aiff`) ;
   - certificats et clés (`*.pem *.key *.crt`) ;
   - données Caddy ;
   - fichiers d'OS et d'IDE ;
   - enregistrements de tests de synchro.
3. Contenu du bootstrap :
   - `LICENSE` : texte MIT standard, `Copyright (c) 2026 PrimoKG`. Le titulaire est le propriétaire du dépôt GitHub (`PrimoKG`), confirmé par le mainteneur au GO ;
   - `README.md` : commence par `# OpenBlindySir` suivi du bandeau de statut ;
   - `.env.example` avec des valeurs fictives ;
   - `docs/architecture.md` (cette spec), avec `docs/protocol.md`, `docs/sync.md` et `docs/bridge-security.md` ;
   - `docs/DEVLOG.md` avec sa première entrée ;
   - `CHANGELOG.md` avec une section `Unreleased` ;
   - ADR 0001 à 0003 et 0005 à 0007 au statut « Accepté », ADR 0004 au statut « Proposé » ;
   - CONTRIBUTING, SECURITY, CODE_OF_CONDUCT ;
   - `tools/check_repo_hygiene.py`.
4. **Contrôle d'hygiène explicite** : relire `git status` et la liste des fichiers suivis, lancer le script d'hygiène, vérifier qu'aucun `.env`, secret, fichier audio ou build n'est présent.
5. Commit **`chore: bootstrap repository`**.
6. Création du dépôt GitHub (§19.6), puis push.

### 19.3 Commits
- **Conventional Commits**, avec les scopes `protocol`, `server`, `web`, `bridge`, `docker`, `ci`, `docs`, `deps`, `tools`. Types : `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`.
- Les messages de commit sont rédigés en anglais.
- Exemples :
  - `feat(protocol): define player and bridge messages`
  - `feat(server): implement game state machine`
  - `feat(server): record server-side answer timing`
  - `feat(server): add final score review phase`
  - `feat(bridge): add sandboxed library scanner`
  - `feat(web): add synchronized audio engine`
  - `test(server): cover reconnect and scoring transitions`
  - `docs: document bridge threat model`
- Un commit correspond à une unité logique : ni « update » ou « wip », ni un commit par ligne modifiée.
- Le message se termine par la ligne d'attribution prévue pour les commits générés avec l'assistant.

### 19.4 Tester avant de commiter
| Zone modifiée | Vérification avant un commit significatif |
|---|---|
| Serveur | `pytest` (server + protocol), ruff, pyright |
| Frontend | Biome, `tsc --noEmit`, Vitest |
| Bridge | Tests du Bridge (et tests Windows en CI) |
| Protocole | Tests Python + régénération des types TS sans écart |
| Docker | `docker build` |

**`main` ne doit jamais être cassé volontairement.** Un travail expérimental qui échoue vit sur une branche dédiée, et le DEVLOG dit pourquoi.

### 19.5 Branches
| Situation | Pratique |
|---|---|
| Avant la CI (bootstrap) | Commits directs sur `main`, après tests locaux |
| Spikes | Branches `spike/audio-sync` et `spike/bridge`, **poussées mais pas fusionnées**. Le code jetable n'arrive pas sur `main`. Les résultats vont dans le DEVLOG et les ADR, et les outils réutilisables (`sync_analyze.py`, clip de calibration) sont réintégrés proprement. |
| Une fois la CI en place | Une branche par jalon (`feat/game-core`…), une PR, fusion **quand la CI est verte** (rebase-merge pour garder les commits granulaires et un historique linéaire). Pas de PR pour une correction triviale de documentation. |

### 19.6 GitHub
- Si **`gh auth status`** est authentifié, **et seulement une fois le bootstrap local propre et commité** :
  ```
  gh repo create OpenBlindySir --public --source=. --remote=origin --push \
    --description "Self-hosted remote-first multiplayer blind test — your music stays on your PC."
  ```
  Branche par défaut `main`.
- Puis, si l'API le permet :
  - activer **secret scanning + push protection**, alertes Dependabot, **private vulnerability reporting** ;
  - ajouter les topics : `blind-test`, `self-hosted`, `multiplayer`, `fastapi`, `react`, `web-audio` ;
  - créer les milestones `v0.1`, `v0.2`.
- **Si `gh` n'est pas authentifié** :
  - aucun identifiant n'est inventé et rien n'est publié ailleurs ;
  - le dépôt local reste propre et le développement continue ;
  - le rapport indique précisément que **seules la création et le push distants sont bloqués**.
- **Push à chaque jalon validé** : bootstrap, spike audio, spike Bridge, socle, cœur du jeu, vertical slice, intégration du Bridge réel, robustesse, Docker, release candidate. On évite que plusieurs jours de travail n'existent qu'en local.

### 19.7 Ce qui n'entre jamais dans le dépôt
- `.env` ;
- tokens, cookies, `BRIDGE_SECRET`, `HOST_PASSWORD`, `BLIND_PASSWORD` ;
- certificats ;
- identifiants GitHub ;
- logs contenant des secrets ;
- configuration personnelle du Bridge ;
- **toute musique, tout extrait réel, toute pochette commerciale**.

Les tests utilisent **uniquement** des sons générés à l'exécution (sinusoïdes, clics, silence, via `lavfi`), ou plus tard des fixtures explicitement sous licence libre, avec leur licence documentée.

Garde-fous :
- `.gitignore` ;
- script d'hygiène, exécuté localement et en CI ;
- push protection de GitHub ;
- **vérification manuelle explicite avant le premier push public**.

### 19.8 Intégration continue
Elle est ajoutée **au fur et à mesure que le code à vérifier existe**, jamais de job vide. Chaque job vérifie quelque chose de réel.

| Job | Vérifie | Déclencheur |
|---|---|---|
| `hygiene` | Aucun fichier audio, `.env` ou secret évident suivi | Chaque PR et push |
| `python` | ruff check et format, pyright (mode basic), pytest sur protocol et server | PR et push |
| `bridge-linux` | pytest Bridge, avec FFmpeg installé | PR et push |
| `bridge-windows` | pytest Bridge sur `windows-latest` : **junctions, chemins, sandbox** | PR et push |
| `web` | Biome, `tsc`, Vitest, build Vite | PR et push |
| `protocol-drift` | Régénération des types TS, échec en cas d'écart | PR et push |
| `integration` | Serveur, Bridge démo et 10 bots, partie complète jusqu'à `FINAL_RESULTS` | PR et push |
| `e2e` | Playwright Chromium, jeu réel et parcours UI | PR, `main` et validation de tag |
| `fuzz-core` / `e2e-webkit` | Profil Hypothesis long et WebKit informatif (`continue-on-error`) | `nightly.yml`, schedule et lancement manuel ; distinct des portes de release |
| `docker` | Build app/Bridge et partie synthétique HTTPS/WSS ; aucune publication d'image | PR, `main` et validation de tag |
| `distribution` | Wheels issus des sdists ; uvx Python 3.12/3.13/3.14 sur quatre OS/architectures ; archives onedir et smoke hors checkout sur quatre runners natifs | PR, `main` et validation de tag |
| `release` | Wheels/sdists protocole et Bridge par OIDC PyPI, archives Bridge natives/manifest/SHA256SUMS sur GitHub après validation complète | Tag vX.Y.Z ou vX.Y.Z-rc.N validé ; aucune image publiée par ce workflow |

`ci.yml` appelle `validation.yml` et `distribution.yml` avec permissions de lecture.
`release.yml` rappelle ces validations avant collecte/publication ; seuls ses jobs
de publication obtiennent OIDC PyPI ou écriture GitHub. Les artefacts proviennent
du même run et leurs version/protocole/commit/hashes sont vérifiés.

**Dependabot** : écosystèmes uv/pip, npm, github-actions et docker, avec des **mises à jour groupées et mensuelles**.

### 19.9 Versions et releases
- **SemVer**, une version unique pour tout le monorepo (`VERSION`), et un entier `protocol` distinct. On reste en `0.x` tant que le protocole bouge.
- **Procédure de release** :
  1. configuration préalable des Trusted Publishers PyPI et environnements protégés ;
  2. tests complets et recette des appareils/binaires réellement ciblés ;
  3. `tools/release.py set-version`, lock uv et entrée numérotée du changelog ;
  4. commit propre, tag Git `vX.Y.Z` (ou `vX.Y.Z-rc.N`) correspondant à VERSION ;
  5. push du tag : validation application et distribution avant publication ;
  6. collecte des deux wheels/sdists et des quatre archives natives du même run,
     avec contrôle de provenance et sommes SHA-256 ;
  7. publication protocole puis Bridge sur PyPI par OIDC ;
  8. GitHub Release avec archives, notices, manifest et `SHA256SUMS`.
  La [procédure exacte](releasing.md) et [ADR 0013](adr/0013-bridge-distribution.md)
  remplacent ici le projet de publication GHCR ; aucune image n'est publiée par
  les workflows actuels. Les versions `.dev` sont des builds de développement.
- Pas de release par commit. Une pré-release `vX.Y.Z-rc.N` est possible avant chaque version mineure.

### 19.10 Issues et suivi
- Créer des issues uniquement pour les **vrais** sujets non traités sur le moment : bugs, améliorations reportées, limitations, éléments de la feuille de route.
- Labels réduits : `bug`, `enhancement`, `limitation`, `roadmap`, `good first issue`.
- **Milestones `v0.1`, `v0.2`** plutôt qu'un GitHub Project. Un tableau Kanban (Backlog / Next / In progress / Done) seulement si les issues ouvertes dépassent une vingtaine.
- **Le DEVLOG reste la trace principale.**

### 19.11 Entrées du DEVLOG
```
## YYYY-MM-DD — Nom du jalon / intervention
**Objectif** — ce qu'on cherchait à construire ou corriger.
**Décisions** — décisions réellement prises (lien ADR si structurante).
**Implémentation** — ce qui a effectivement été réalisé.
**Zones touchées** — server/game, web/audio, bridge/sandbox, protocol, Docker…
**Tests** — commandes réellement exécutées et résultats (pytest X/X, Vitest X/X,
            Playwright X/X, docker build PASS, test manuel : appareil + résultat).
**État** — DONE | PARTIAL | BLOCKED | EXPERIMENTAL
**Problèmes connus** — régressions, limitations, TODO importants.
**Prochaine étape** — une seule étape principale.
```
**Règles**
- On n'invente jamais un test non exécuté.
- On écrit les échecs tels qu'ils se sont produits, par exemple : « Opus/Ogg sur iOS 17 : `decodeAudioData` échoue sur l'appareil X ; AAC retenu ».
- On ne réécrit pas les entrées passées. La SPEC peut évoluer ; le DEVLOG ne fait que s'allonger.

### 19.12 Compte rendu de chaque intervention de l'IA
À la fin de chaque intervention importante, un résumé est donné dans la conversation. Il correspond à l'entrée DEVLOG du même travail.
```
Réalisé — résumé court.
Principales modifications — liste concise.
Tests — commandes réellement exécutées + résultats.
Git — branche · commits (hash court + message) · push effectué ou non (et pourquoi).
État — DONE / PARTIAL / BLOCKED.
Restant — ce qui reste à faire.
Prochaine étape recommandée — une seule.
```

---

## 20. Tests

### 20.1 Priorité 1 : tests unitaires rapides, à chaque PR
**1. Machine à états de la partie et du round** (logique pure, horloge injectée)
- Toutes les transitions valides, et le rejet des transitions invalides.
- **Aucun chemin `IN_GAME → FINAL_RESULTS`.**
- Toutes les fins anticipées (`end_game` dans chaque phase du round, avec `score` et `abandon`) aboutissent à `FINAL_SCORE_REVIEW`.
- Deadline, `add_time`, fermeture automatique quand tous les joueurs en ligne ont validé, replay, échecs d'asset avec remplacement, idempotence des commandes hôte.

**2. Réponses**
- Brouillon puis validation.
- Seconde validation ignorée.
- Validation reçue après la fermeture : rejetée, le brouillon est capturé.
- Le brouillon est restauré à la reconnexion.
- `CAPTURED` n'a ni rang ni temps de validation ; son heure de réception du dernier brouillon reste disponible.

**3. Mesure du temps**
- `elapsed` est calculé à partir d'`official_start_at`.
- **Il ne change pas après un replay ou un stop.**
- Un `ANSWER_SUBMIT` contenant un champ de timestamp est rejeté par le schéma.
- L'ordre est strict pour 10 validations traitées dans la même itération de la boucle.
- `near_tie` est vrai sous le seuil et faux au-dessus.
- `late_start_ms` est calculé à partir de `ready_received_at`.
- `draft_last_changed_at` est mis à jour mais n'influence jamais `order` ni les points.
- L'arrondi d'affichage (4,237 s donne « 4,2 s ») est testé côté web.

**4. Journal des scores**
- L'invariant `score = Σ événements actifs` tient après chaque opération.
- `final_validate` crée un événement `round` par delta non nul de chaque manche incluse.
- Les anciennes commandes publish/undo_publish/adjust sont refusées ; la migration de snapshot conserve l'audit via revoke.
- Les corrections finales fonctionnent, y compris sur l'hôte.
- Les deltas négatifs et les bornes sont respectés.
- Les brouillons ne créent jamais d'événement.

**5. Vérification finale**
- `final_set` ne crée pas d'événement.
- `final_validate` crée exactement un `final_adjustment` par delta non nul.
- L'hôte peut s'ajuster lui-même.
- `final_validate` est idempotent.
- Le brouillon est conservé après la reconnexion de l'hôte.
- Après `FINAL_RESULTS`, tout ajout d'événement est refusé.

**6. Permissions** : test paramétré qui envoie **chaque** commande `HOST`, y compris `final_set` et `final_validate`, depuis un joueur ordinaire, et vérifie le refus. L'élévation avec un mauvais mot de passe est refusée et soumise à la limitation de débit.

**7. Fuites d'information, `view_for()` par rôle et par phase.** On vérifie l'objet sérialisé **en entier**, pour détecter aussi un champ ajouté plus tard.

La matrice anti-fuite teste OPEN/REVIEW sans reveal ou points, les réponses en direct uniquement MC, la revue globale réservée aux hôtes et les résultats publics figés (§6.8). Elle teste aussi les routes HTTP de bibliothèque et réécoute.

Assertions supplémentaires sur le compteur de progression :
- `progress` vaut `null` quand `expected < 3` ;
- `progress` est mis à jour à chaque validation sans exposer d'identifiant ;
- l'hôte en MC Mode est exclu de `expected` ;
- `players[]` en OPEN ne contient aucun champ de réponse.

**8. Reconnexion** : reprise par cookie, éviction de l'ancienne connexion, kick (token révoqué), fin de session, règles sur les pseudos (casse, NFKC, bidi).

**9. Sandbox du Bridge**
- `..`, chemins absolus, ID inconnu.
- Lien symbolique vers l'extérieur ; **junction Windows** (runner Windows).
- Fichier remplacé par un lien après le scan.
- NFC/NFD, noms commençant par `-` ou contenant `:`.

**10. Commande FFmpeg** : tests golden sur la liste d'arguments exacte (préfixe `file:`, `-map_metadata -1`, bornes appliquées même si le serveur demande 3 600 s).

**11. Horloge (Vitest)**
- Réseau simulé avec gigue, asymétrie et valeurs aberrantes : l'erreur reste ≤ asymétrie/2.
- Conversion `start_at` vers le temps `AudioContext`.
- Cas « `T` déjà passé ».

### 20.2 Priorité 2 : intégration en CI
Serveur réel en processus, **Bridge démo** et **10 bots** jouent une partie complète :
- join, ready, lecture ;
- validations avec ordre et temps ;
- conservation des réponses puis notation globale ;
- vérification finale avec une correction, y compris sur l'hôte ;
- `FINAL_RESULTS`.

Variantes :
- un bot se reconnecte pendant OPEN ;
- le Bridge est tué puis relancé entre deux rounds ;
- upload corrompu ;
- fichier supprimé après le scan ;
- `end_game` anticipé pendant OPEN.

Les bots servent aussi au test de charge manuel (50 bots : RAM, latence des `PONG`).

### 20.3 Priorité 3 : E2E Playwright
- Chromium, un hôte et deux joueurs, Bridge démo, partie de deux rounds jusqu'à `FINAL_RESULTS`. Vérifie le parcours UI, l'affichage « ✓ Réponse enregistrée » **sans temps**, puis les temps et rangs au reveal.
- WebKit peut être exécuté localement avec `npm run e2e:webkit` ; `nightly.yml`
  l'exécute de façon informative. Les builds sans AudioContext ignorent les
  scénarios audio. **Ne remplace pas** un vrai iPhone.

### 20.4 Tests manuels avant chaque release (`docs/testing.md`)
iPhone (bouton silencieux, verrouillage de l'écran), Android, Firefox, Safari macOS, Bluetooth, 4G, test acoustique de synchronisation.

**Ce qu'on n'automatise pas** : la mesure acoustique réelle, les particularités de chaque appareil, le rendu visuel.

### 20.5 Validation de la synchronisation
1. **Mesure déclarée par les clients**, en continu : le panneau hôte affiche l'erreur estimée, `rtt_min`, ε et `late_ms` par joueur, par exemple « A +12 ms ±8, B −25 ms ±30 ». Cela détecte les bugs de logique et les clients lents, mais pas les biais matériels.
2. **Mesure acoustique**, pendant le spike puis avant chaque release :
   - un **clip de calibration** généré (clics toutes les 500 ms) ;
   - 3 ou 4 appareils sur des réseaux différents (fibre, 4G, Wi-Fi dégradé avec `tc netem` ou Clumsy) ;
   - un micro enregistre l'ensemble ;
   - `tools/sync_analyze.py` calcule les écarts.

   **Critère : p90 ≤ 60 ms.**
3. **Bouton hôte « Test de synchro »** : joue le clip de calibration chez tout le monde.

---

## 21. Observabilité et débogage

**Logs**
- Une ligne par événement sur stdout, `event=` puis des paires clé=valeur.
- `LOG_FORMAT=text` par défaut, ou `json`.
- Module `logging` standard avec un formatter maison.
- Logger racine : `openblindysir`, avec les sous-loggers `openblindysir.game`, `.ws`, `.bridge`, `.audio`.

**Événements** : `session_started`, `player_joined`, `player_reconnected`, `player_superseded`, `player_offline`, `player_kicked`, `host_elevated`, `login_failed` (IP tronquée), `bridge_connected`, `bridge_rejected`, `bridge_lost`, `catalog_received`, `job_requested(track_id)`, `job_done(ms, bytes)`, `job_failed(code)`, `asset_stored`, `asset_evicted`, `round_loading`, `round_started(ready=n/m)`, `answer_locked(player_id, order, elapsed_ms)`, `round_closed(locked=n, captured=k)`, `round_published`, `publish_undone`, `score_adjusted`, `final_review_started`, `final_validated(corrections=n)`, `playback_report_summary(p50, p90, max)`, `ws_rate_limited`, `upload_rejected`.

**Ne jamais logger**
- secrets, tokens, cookies, en-têtes `Authorization` ;
- chemins ou noms de morceaux (seulement `track_id` ; `LOG_TRACK_NAMES=false` par défaut) ;
- **le contenu des réponses** (on logge leur longueur).

**Interfaces de débogage**
- **Panneau Diagnostic** de l'hôte :
  - par joueur : connexion, état audio, RTT, offset, ε, erreur de départ, famille de navigateur, état de l'`AudioContext` ;
  - Bridge : état, jobs, latences ;
  - cache ;
  - par round : `draft_last_changed_at` des réponses non validées.
- `?debug=1` côté joueur : petit overlay (θ, RTT, `outputLatency`, état du contexte, `late_ms`).
- Bouton « Copier le diagnostic » (JSON) pour joindre à une issue.

---

## 22. Performances et bande passante

**Taille d'un extrait** (AAC, environ 2 % d'en-tête de conteneur)
| Durée | 96 kbps | 128 kbps |
|---|---|---|
| 20 s | ~240 Ko | ~320 Ko |
| 30 s | ~360 Ko | ~480 Ko |

**Trafic du VPS vers les joueurs (128 kbps)**
| Joueurs | 20 s par round | 20 s × 50 | 30 s par round | 30 s × 50 | 30 s × 100 |
|---|---|---|---|---|---|
| 5 | 1,6 Mo | 80 Mo | 2,4 Mo | 120 Mo | 240 Mo |
| 10 | 3,2 Mo | 160 Mo | 4,8 Mo | 240 Mo | 480 Mo |
| 15 | 4,8 Mo | 240 Mo | 7,2 Mo | 360 Mo | 720 Mo |

Prévoir environ 10 % de plus pour les replays et les retéléchargements. Le WebSocket représente moins de 5 Mo par soirée.

**Bridge vers le VPS**
- Volume : 50 rounds × 480 Ko ≈ **24 Mo** (100 rounds ≈ 48 Mo).
- Durée d'envoi par extrait : environ 3,8 s à 1 Mbps montant, 0,4 s à 10 Mbps. **Le préchargement masque ce délai.**

**Pic de distribution** : 7,2 Mo pour 15 joueurs, moins d'une seconde à 100 Mbps, et étalé par le préchargement.

**CPU du Bridge** : environ 50 ms pour ffprobe, 0,2 à 1 s pour l'encodage d'un extrait de 30 s, sur un seul thread.

**VPS** : application 80 à 120 Mo, Caddy 30 à 50 Mo, cache audio 4 Mo au plus, CPU quasi nul. **Configuration minimale : 1 vCPU / 512 Mo ; 1 Go est confortable.** Une soirée consomme moins de 0,1 % d'un quota de trafic typique.

**Client** : un AudioBuffer décodé occupe environ 384 Ko/s, soit **11,5 Mo pour 30 s** ; extrait courant et suivant ≈ 23 Mo. Le décodage prend 50 à 200 ms sur un mobile moyen.

---

## 23. MVP V0.1 (réellement jouable)

Ce périmètre décrit le MVP V0.1 historique. Les §§6–14 et la roadmap §25
font autorité pour V0.2 : aucune publication de points ou de morceau entre les manches.

1. Entrée par mot de passe de partie et pseudo, cookie de session, reconnexion automatique, éviction de l'ancien onglet.
2. Élévation en hôte, **Host Player Mode** et **MC Mode**.
3. Lobby : liste des joueurs, **« Tester mon audio »**, états audio visibles par l'hôte.
4. Bridge en CLI (`uv run openblindysir-bridge`) : scan d'une racine, catalogue, sandbox, PREPARE → FFmpeg → upload, reconnexion, **mode `--demo`**.
5. Configuration de la partie : nombre de rounds, durée des extraits, sélection de dossiers, tirage aléatoire sans répétition dans la session.
6. Round : préchargement de N+1, ready check (départ automatique, timeout, départ forcé), compte à rebours, **lecture synchronisée**, rattrapage en cas d'arrivée tardive, replay, stop, skip, +temps, fermeture.
7. Réponse libre avec brouillon synchronisé et **VALIDER définitif** ; le joueur voit **« ✓ Réponse enregistrée »**, sans temps. Fermeture par deadline, par l'hôte, ou quand tous ont validé. Compteur anonyme `n/m ont validé`, masqué si `m < 3` (§6.8).
8. **Mesure côté serveur de la rapidité** : `elapsed` (horloge monotone, lue à l'entrée du handler, aucun timestamp client, pas de compensation), ordre de validation, quasi-égalité, retard audio mesuré par le serveur ; `draft_last_changed_at` conservé pour le diagnostic.
9. **REVIEW** : réponses triées par ordre avec temps au dixième, rang, `≈` et ⚠ retard audio. Notation manuelle en brouillon (0 / +1 / +2 / +3 / ±N libre, hôte compris), **sans aucun barème appliqué automatiquement**, puis publication.
10. **Reveal** : morceau, réponses, temps, rangs, points de tous, classement. Annulation de la dernière publication. Ajustement ponctuel en cours de partie.
11. **Journal `ScoreEvent`** (`round`, `adjustment`, `final_adjustment`, `revoke`) comme unique source des scores.
12. **FINAL_SCORE_REVIEW obligatoire** :
    - affichage score actuel → ajustement → score résultant ;
    - détail round par round ;
    - ±N sur n'importe quel joueur, hôte compris ;
    - brouillon conservé côté serveur ;
    - **confirmation explicite** « Valider les scores et afficher les résultats ».
13. **FINAL_RESULTS** : classement, podium, ajustements finaux affichés, scores figés. Fin anticipée qui passe par la vérification finale. Nouvelle partie, fin de session, kick.
14. Remplacement automatique des morceaux en échec, gestion de « Bridge déconnecté ».
15. Sécurité de base (toutes les lignes V0.1 du §12).
16. Overlay de réactivation audio sur iOS et Android, rapports de synchro, panneau Diagnostic.
17. Image Docker `ghcr.io/primokg/openblindysir` (tag `edge`), Compose avec Caddy, `.env.example`, README `# OpenBlindySir` avec bandeau de statut, License: MIT et section « Music & rights ».
18. Textes en français via le dictionnaire i18n.
19. Dépôt public propre : DEVLOG, CHANGELOG, ADR, CI conforme au §19.8.

---

## 24. Exclusions et reports après V0.2

- **Bonus automatiques de vitesse**, y compris « appliquer 3/2/1 », restent exclus. La notation textuelle optionnelle demandée pour V0.5 est décrite dans [notation-automatique](notation-automatique.md) ; le mode manuel reste disponible et l’hôte garde la correction finale.
- Compensation de latence sur les temps de réponse.
- Affichage du temps au joueur pendant le round (il est montré au reveal).
- Affichage de `draft_last_changed_at` dans l'interface principale.
- Réouverture de la vérification finale après `FINAL_RESULTS`.
- Secrets distincts et révocation ciblée : V0.5. Déduplication entre bibliothèques : évolution future.
- Exécutables du Bridge, paquet PyPI, FFmpeg embarqué.
- Choix manuel MC implémenté en V0.3 avant préparation ; playlists externes exclues.
- Chat, avatars, thèmes, effets sonores, waveform, PWA.
- Import Spotify, Deezer, YouTube ou CSV.
- Comptes, rooms, multi-session (exclus définitivement).

---

## 25. Feuille de route

| Version | Nom | Contenu |
|---|---|---|
| **V0.1** | « Une vraie soirée » | §23, validée par **une vraie soirée test** entre amis |
| **V0.2** | « Confort et robustesse » | Implémenté : revue globale/réécoute privée, audio des vidéos, sources dynamiques multi-Bridge, recherche/métadonnées, pause/reprise, silence/loudnorm, snapshots, exports, équipes/spectateurs, FR/EN, latence manuelle, récupération par code, verrou d'inscription, réponses MC en direct et équilibrage par dossier. Validation acoustique/appareils à terminer avant release. |
| **V0.3** | « Distribution » | Implémenté : paquets autonomes uvx, onedir/manifest/checksums, assistant privé/diagnostics, choix MC et guides FR/EN. Publication en attente de configuration PyPI/environnements et validation des quatre runners ; binaires non signés. |
| **V0.5** | « Préparer la stabilisation » | Implémenté : identités/secrets Bridge distincts, révocation/rotation, historique durable privé, clavier/focus, compatibilité explicite, migrations et contrôles sécurité ; aucune publication ni gel. |
| **V1.0** | « Stable » | Étape future : recette plateformes/appareils/lecteurs d'écran, validation opérationnelle et décision explicite de stabilisation avant gel et retrait du bandeau. |

**Après la V1, si c'est utile** :
- Import d'une liste « artiste – titre » (CSV, export Exportify) mise en correspondance avec la bibliothèque locale. Une URL Spotify ne serait qu'un raccourci vers cette liste, via l'API officielle, **sans jamais télécharger d'audio**.
- Nouveaux types de rounds.

---

## 26. Ordre d'implémentation

Chaque étape suit le même enchaînement : tests, DEVLOG, commits, puis push au jalon.

La table ci-dessous conserve le plan initial : sa colonne « Push » décrit la
cible prévue, pas une preuve d'exécution. Les validations réelles et les portes
G1/G2 encore ouvertes sont consignées dans DEVLOG et testing ; ni une soirée,
ni un VPS, ni un tag/release ne sont déduits de cette table.

| # | Étape | Contenu | Porte de validation | Push |
|---|---|---|---|---|
| 0 | **Bootstrap** | Dépôt local `OpenBlindySir` selon §19.2 : Git, `.gitignore` et `.gitattributes`, LICENSE MIT, README OpenBlindySir, documentation canonique, ADR. Puis `gh repo create OpenBlindySir`. | Script d'hygiène OK, vérification manuelle avant le push public | ✅ `main` |
| 1 | **Spike S0 : synchro et formats** (`spike/audio-sync`, code jetable) | Page HTML et FastAPI minimal. `decodeAudioData` testé en AAC/M4A, Opus/WebM et Opus/Ogg sur **un vrai iPhone**, Android, Safari, Firefox, Chrome. Déverrouillage, bouton silencieux, `getOutputTimestamp`. Mesure acoustique. | **G1** : format choisi (ADR 0004 « Accepté »), p90 ≤ 60 ms sur 3 appareils hétérogènes, recette iOS validée | ✅ branche spike |
| 2 | **Spike S1 : Bridge** (`spike/bridge`) | Scan d'une vraie bibliothèque (celle du mainteneur), junction Windows, FFmpeg sur FLAC, MP3, M4A (moov en fin de fichier) et MP3 VBR, WSS sortant à travers une box domestique, PUT vers un vrai VPS | **G2** : préparation + upload < 5 s au p95, aucun fichier hors de la racine accessible | ✅ branche spike |
| 3 | **Socle** | Workspace uv, paquet `protocol` (messages, y compris commandes finales et `ANSWER_SUBMIT` strict), génération des types TS, squelette web, CI (`hygiene`, `python`, `web`, `protocol-drift`) | CI verte | ✅ |
| 4 | **Cœur du jeu pur** | Machines à états (dont `FINAL_SCORE_REVIEW` et `FINAL_RESULTS`), réponses et timing, journal `ScoreEvent`, `view_for` par rôle, sélection. **Tests de priorité 1, sans réseau.** | Tests §20.1 points 1 à 7 verts | ✅ |
| 5 | **Vertical slice n°1** | Auth, cookies, WebSocket, `STATE`, hub, **Bridge démo**, interfaces joueur et hôte minimales, moteur audio repris du spike. **Partie complète jusqu'à `FINAL_RESULTS` avec des sons synthétiques.** Job CI `integration`. | Bots : partie complète verte | ✅ |
| 6 | **Vertical slice n°2 : Bridge réel** | Scanner et sandbox, catalogue, sélection des dossiers, préchargement, remplacement des morceaux en échec. Jobs CI `bridge-linux` et `bridge-windows`. | Tests sandbox verts sous Windows | ✅ |
| 7 | **Robustesse** | Reconnexion, éviction, arrivée tardive, overlays mobiles, timeouts du ready check, panneau Diagnostic, E2E Playwright | Variantes d'intégration et E2E vertes | ✅ |
| 8 | **Déploiement réel** | Compose, Caddy, GHCR `edge`, déploiement sur le VPS du mainteneur, **soirée alpha** avec 5 à 10 amis, retours consignés tels quels dans le DEVLOG | Une soirée réellement jouée | ✅ |
| 9 | **Durcissement et release** | Passe de sécurité (§12), en-têtes, limites, documentation, checklist manuelle, `v0.1.0-rc.1`, puis **`v0.1.0`** selon §19.9 | Checklist manuelle OK | ✅ tag + Release |

Le format audio n'est pas fixé à l'avance : il est choisi à partir des mesures du spike S0 (porte G1, ADR 0004).

---

## 27. Risques techniques

**CRITICAL**
- **Cycle de vie audio sur iOS** (déverrouillage, bouton silencieux, verrouillage de l'écran, WebSocket tué en arrière-plan). *Mitigation : spike S0 sur un vrai appareil, overlay de réactivation, rattrapage.*

**HIGH**
- **Format décodable par tous les navigateurs** (Opus sur Safari et iOS). *Mitigation : AAC par défaut, spike S0.*
- **Faille de sandbox du Bridge** dans un projet public (junctions Windows). *Mitigation : accès par table de correspondance, double vérification, CI Windows.*
- **Latence Bluetooth** non compensée ou mal signalée. *Mitigation : `getOutputTimestamp`, curseur en V0.2, documentation.*
- **Désynchronisation de l'état client** après une reconnexion. *Mitigation : vue complète à chaque changement.*

**MEDIUM**
- Distribution du Bridge : faux positifs antivirus PyInstaller, SmartScreen, Gatekeeper.
- Variabilité de FFmpeg : builds sans `libopus`, seek imprécis sur MP3 VBR, `moov` en fin de fichier.
- Boucle d'événements bloquée, qui fausse à la fois les `PONG` et les horodatages des réponses. *Mitigation : tout en asynchrone, horloge lue à l'entrée des handlers, surveillance de la latence de boucle dans les logs.*
- Mauvaise configuration WebSocket des proxys tiers.
- Upload montant lent combiné à des rounds rapides. *Mitigation : profondeur de préchargement de 2.*

**LOW**
- Ressources du VPS et bande passante.
- Très gros catalogues.
- Normalisation Unicode NFC/NFD sur macOS.
- Dérive d'horloge pendant un extrait.
- Collisions de `track_id`.

## Notation textuelle optionnelle — protocole 10

`auto_scoring.py` utilise RapidFuzz localement avec des entrées bornées et des
références/configurations figées par manche. Le snapshot 8 persiste preuves privées,
priorité des corrections manuelles et progression des vagues. Les vues publiques
masquent points/critères jusqu’à la révélation effective ; les acquittements de
réponse n’exposent aucune décision. Voir [le guide](notation-automatique.md).

## Sélections thématiques — protocole 12

Les sources et filtres genre/langue/année/tags/univers déterminent ensemble le pool et les manches. Un aperçu privé utilise le même moteur, compte les pistes jouables et inédites sans doublonner les dossiers, et propose des exemples. Les presets locaux incluent ces critères. Métadonnées version 3, snapshots 9 migrés depuis 1–8. Voir [soirées à thème](themed-nights.md) et [protocole](protocol.md).
