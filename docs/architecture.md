# OpenBlindySir — Spécification canonique (architecture & produit)

> Destination : docs/architecture.md. Les sections 8 (protocole réseau), 9 (synchronisation audio) et 11 (Bridge) sont détaillées dans docs/protocol.md, docs/sync.md et docs/bridge-security.md, qui gardent la même numérotation.
>
> Statut : conception validée ; implémentation démarrée le 2026-10-01 (GO IMPLEMENTATION). L'avancement réel est consigné dans docs/DEVLOG.md.
>
> Règle documentaire : la **SPEC** décrit l'état actuel de la conception et se met à jour quand une décision change ; le **DEVLOG** raconte l'histoire réelle du développement et ne se réécrit jamais (§19).
>
> Licence : MIT.

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

1. **OpenBlindySir Server** tourne sur un petit VPS, dans Docker, derrière Caddy. Il sert l'interface web et garde tout l'état de la partie en RAM : joueurs, rounds, réponses, scores. Le processus *est* la room.
2. **OpenBlindySir Bridge** tourne sur le PC qui contient la musique. Il scanne un seul dossier autorisé, envoie un catalogue léger au serveur et produit à la demande un **extrait** (20 à 30 s par défaut, 60 s au plus selon `CLIP_MAX_S`) avec FFmpeg. Il ouvre lui-même une connexion **sortante** vers le serveur. Les fichiers complets ne quittent jamais le PC.
3. **L'interface web OpenBlindySir**, dans le navigateur (joueur ou hôte). Elle télécharge l'extrait entier, le décode, se déclare prête, puis le joue à un instant `startAt` fixé par le serveur, grâce à une horloge synchronisée. La réponse est un texte libre.

**La notation est entièrement humaine.** Le serveur ne sait pas quelle est la bonne réponse et n'évalue jamais le contenu d'une réponse. Il **mesure** le moment de chaque validation et le transmet à l'hôte, qui attribue lui-même les points (+N, 0, −N) avec le barème qu'il veut. **La rapidité est mesurée et affichée, mais elle n'attribue jamais de points automatiquement.**

**Ce qu'OpenBlindySir n'est pas** : une plateforme SaaS, un clone de Kahoot, un système de rooms ou de comptes, un lecteur Spotify/YouTube/Deezer, ni un outil de téléchargement de musique.

**Glossaire**
| Terme | Sens |
|---|---|
| **Session** | Durée de vie du processus serveur, en pratique une soirée. Elle porte les tokens des joueurs. |
| **Partie** | Une suite de rounds qui se termine par la vérification finale puis le classement. Une session peut enchaîner plusieurs parties. |
| **Round** | Un extrait, les réponses, la notation, le reveal. |
| **Asset** | Un extrait audio préparé et stocké temporairement en RAM sur le VPS. |
| **Reveal** | Publication aux joueurs du résultat d'un round : morceau, réponses, temps, rangs, points. |
| **Host Player Mode** | L'hôte joue et ne voit jamais d'information sur le morceau avant le reveal. |
| **MC Mode** | L'hôte anime sans jouer et voit tout (fichier, prochain morceau). |

---

## 2. Principes de conception

1. **La solution la plus simple qui fonctionne**, pour 10 à 15 joueurs. Rien n'est conçu pour monter en charge.
2. **Un processus, une boucle d'événements.** Toutes les mutations d'état sont des fonctions **synchrones** (aucun `await` au milieu) et les entrées/sorties se font après. Il n'y a donc ni verrou ni course entre les mutations.
3. **Le serveur fait autorité** sur l'identité, les permissions, l'état, l'heure officielle, les réponses acceptées, l'ordre de validation et les scores. Le navigateur et le Bridge ne décident de rien.
4. **État en RAM, pas de base de données.** Les scores sont la projection d'un **journal d'événements**, jamais un nombre modifiable.
5. **Vue complète par destinataire.** À chaque changement, le serveur envoie à chaque client sa vue complète, filtrée selon son rôle. Une seule fonction, `view_for()`, décide de ce que voit qui : c'est le seul point de contrôle contre les fuites de spoilers.
6. **Le Bridge est une frontière de sécurité, et il considère le serveur comme non fiable**, ce qui prépare le cas de plusieurs Bridges appartenant à des personnes différentes.
7. **Remote-first.** La précision visée est celle qui reste perceptible avec un chat vocal en parallèle, soit quelques dizaines de millisecondes. Le vrai risque n'est pas l'horloge mais le cycle de vie audio sur mobile.
8. **Anti-spoiler sur tous les vecteurs** :
   - URL audio opaque ;
   - extrait **sans tags ni pochette** ;
   - aucune métadonnée dans la vue avant le reveal ;
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
| Persistance | **Aucune en V0.1.** Un snapshot JSON est candidat pour la V0.2. | La soirée est l'unité de vie. | SQLite : aucune requête ni relation, donc de la cérémonie. | 0005 |
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
- **Reveal** : morceau, réponses de tous, **temps, rangs, marqueurs de quasi-égalité**, points du round, classement.
- **Vérification finale** : « L'hôte vérifie les scores… » et le dernier classement publié, figé.
- **Résultats finaux** : podium, classement complet, ajustements finaux affichés.
- **Réglages** : volume local ; latence audio manuelle à partir de la V0.2.

Les préférences locales (volume, et latence à partir de la V0.2) sont stockées dans `localStorage` sous des clés préfixées `openblindysir:`.

**Interface hôte**
- **Host Player Mode** : la vue joueur plus un **tiroir de contrôle** repliable (lancer, forcer, rejouer, stop, passer, fermer, +temps, noter, publier, terminer). Aucune métadonnée du morceau avant le reveal, ni sur les morceaux à venir.
- **MC Mode** : tableau de bord complet (joueurs, connexions, états audio, RTT, prochain morceau, nom de fichier) et mêmes commandes.
- **REVIEW**, dans les deux modes : voir §6.4.
- **FINAL_SCORE_REVIEW** : voir §6.6.
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
Aucune en V0.1. Voir §14.

---

## 6. Règles de jeu

### 6.1 Déroulé d'un round
1. Le serveur prend le morceau suivant dans une file mélangée au démarrage, sans répétition sur toute la session.
2. L'asset est normalement déjà `STORED` grâce au préchargement. Sinon le round reste en PREPARING.
3. La vue publie l'extrait. Les clients le téléchargent, le décodent et répondent `READY` (ready check, §9.4).
4. Compte à rebours de 3 s, puis **`official_start_at`** : lecture synchronisée et **ouverture des réponses**. Il n'y a pas de phase de réponse séparée : on répond dès la première note.
5. Les joueurs écrivent. Le brouillon est synchronisé de façon invisible. **VALIDER** est définitif.
6. Fermeture des réponses dans le premier de ces cas :
   - la deadline est atteinte (`official_start_at + durée de l'extrait + ANSWER_GRACE`, 15 s par défaut) ;
   - tous les joueurs en ligne ont validé ;
   - l'hôte ferme.

   L'hôte peut aussi ajouter 15 s, rejouer l'extrait, l'arrêter ou passer le morceau.
7. **REVIEW** : l'hôte voit toutes les réponses et leurs données temporelles, et note en brouillon.
8. **Publication**, puis **reveal** pour tous.
9. Round suivant. Après le dernier round, passage à la **vérification finale** (§6.6).

### 6.2 Réponses
- Texte libre d'au plus 200 caractères, dans un seul champ « Ta réponse ».
- **Brouillon** : envoyé par `ANSWER_DRAFT` avec un debounce de 500 ms. Il est invisible pour tout le monde, hôte compris, avant la fermeture, et il est restauré à la reconnexion.
- **Validation** : `ANSWER_SUBMIT` est **définitif**. Une seconde soumission est ignorée.
- **À la fermeture**, un brouillon non vide et non validé devient `CAPTURED`. L'hôte le voit comme « non validée ». Il **n'a pas de rang officiel, n'est pas compté comme ayant répondu et ne déclenche rien automatiquement**. L'hôte peut quand même lui donner des points s'il le juge juste.
- **Réception après la fermeture** : rejetée (`ANSWER_ACK rejected: closed`). Le dernier brouillon reçu est conservé comme `CAPTURED`. Comme la boucle unique traite les messages un par un, la décision ne dépend que de l'ordre de traitement.

### 6.3 Rapidité : règle canonique
**Mesure**
```
elapsed = answer_received_at_server − official_start_at
```
- `answer_received_at_server` : horloge **monotone** du serveur, lue **à l'entrée du handler** `ANSWER_SUBMIT`, avant tout `await` ou toute validation coûteuse.
- `official_start_at` : le `start_at` du **premier** `PLAY` du round. **Il ne change jamais**, ni sur un replay, ni après un stop.
- **Aucun timestamp client n'est accepté.** Le schéma de `ANSWER_SUBMIT` interdit tout champ supplémentaire.
- **Aucune compensation RTT ou réseau.** Les sources d'erreur sont la latence aller (10 à 200 ms), la synchronisation audio (environ ±60 ms), le Bluetooth (100 à 300 ms) et surtout le temps de réaction humain (plusieurs secondes). Une compensation ne corrigerait que la première, en partie, et ouvrirait une possibilité de triche (gonfler son RTT).
- La pause, prévue en V0.2, exclura le temps passé en pause.

**Données produites pour chaque réponse validée**
| Donnée | Définition |
|---|---|
| `elapsed_ms` | Mesure ci-dessus |
| `order` | Rang de validation (1, 2, 3…), strict et déterministe car les messages sont traités en série. Seules les réponses `LOCKED` ont un rang. |
| `near_tie` | Vrai si l'écart avec la réponse validée juste avant est inférieur à `NEAR_TIE_MS` (300 ms par défaut, réglable). Affiché « 2≈ ». Indique que l'ordre n'est pas significatif. |
| `late_start_ms` | **Mesure serveur** : `max(0, ready_received_at − official_start_at)`. Vaut aussi la durée de déconnexion pendant la lecture. Le joueur a entendu l'extrait en retard. |

**Affichage** au dixième de seconde, avec une virgule en français : « 4,2 s ».

**Usage** : ces données servent **uniquement d'aide à la décision** de l'hôte. Le serveur n'applique **aucun barème**, ne pré-remplit **aucun point**, et ne propose **aucun bouton du type « appliquer 3/2/1 »**. L'hôte peut donner +3 au premier bon, +2 au deuxième, +1 aux autres, ou +1 à tout le monde, ou tout autre barème.

**Brouillon non validé** : le serveur garde `draft_last_changed_at`, l'heure monotone de réception du dernier `ANSWER_DRAFT`, précise à environ 0,5 s près à cause du debounce.
- Cela coûte un seul champ.
- C'est utile en cas de discussion du type « j'avais écrit la réponse mais j'ai oublié de cliquer ».
- Cette valeur **ne donne aucun rang, aucun bonus, et n'entre dans aucun calcul**.
- En V0.1, elle n'apparaît **pas dans l'interface principale**, seulement dans le panneau Diagnostic de l'hôte, au niveau du détail du round.

### 6.4 Notation d'un round (REVIEW)
Vue hôte, triée par ordre de validation, puis les réponses non validées, puis les joueurs sans réponse :
```
1.  Ayoub    « Pokémon Route 1 »   4,2 s                 [0] [+1] [+2] [+3] [ ±N ]
2≈  Mehdi    « Route 1 Pokémon »   4,4 s                 [0] [+1] [+2] [+3] [ ±N ]
3.  Sofiane  « Pokémon »          13,4 s  ⚠ audio +2,3 s [0] [+1] [+2] [+3] [ ±N ]
—   Adam     « pikach »  (non validée)                    [0] [+1] [+2] [+3] [ ±N ]
—   Yo (toi) — pas de réponse                              [0] [+1] [+2] [+3] [ ±N ]
```
- Chaque ligne a des boutons rapides et un champ libre ±N : entier signé, négatifs autorisés, bornes ±1000.
- L'hôte se note lui-même comme n'importe quel joueur.
- Les points sont un **brouillon côté serveur**, visible uniquement par l'hôte. Il se modifie librement et survit à un rafraîchissement ou à une reconnexion de l'hôte.
- **Publier** :
  - crée un `ScoreEvent(kind="round")` par joueur dont le delta est non nul ;
  - passe le round en REVEALED ;
  - affiche le reveal aux joueurs.

### 6.5 Corrections pendant la partie
- **Ajustement ponctuel** : depuis le classement, l'hôte peut appliquer ±N à n'importe quel joueur, lui compris, à tout moment pendant `IN_GAME`. Une confirmation courte est demandée. Cela crée immédiatement un `ScoreEvent(kind="adjustment")`, avec en option le round concerné et une note.
- **Annuler la dernière publication** :
  - possible uniquement sur le round REVEALED le plus récent, tant que le round suivant n'a pas atteint COUNTDOWN ;
  - crée des `ScoreEvent(kind="revoke")` qui annulent ceux du round ;
  - remet le round en REVIEW avec le brouillon précédent restauré.

### 6.6 Vérification finale (FINAL_SCORE_REVIEW), obligatoire
On y entre après la publication du dernier round : l'hôte clique « Vérification finale » depuis le reveal. On y entre aussi par toute **fin anticipée** (§7.1). **Il n'existe aucun chemin vers les résultats qui évite cette phase.**

Vue hôte :
```
VÉRIFICATION FINALE DES SCORES

Ayoub     22   [−] [ +2 ] [+]   22 → +2 → 24     ▸ détail
Mehdi     22   [−] [ −1 ] [+]   22 → −1 → 21     ▸ détail
Sofiane   18   [−] [  0 ] [+]   18 →  0 → 18     ▸ détail
Adam      16   [−] [  0 ] [+]   16 →  0 → 16     ▸ détail
Yo (toi)  15   [−] [ +1 ] [+]   15 → +1 → 16     ▸ détail

[ Réinitialiser les corrections ]
[ VALIDER LES SCORES ET AFFICHER LES RÉSULTATS ]
```
- Sur chaque ligne : **score actuel** (somme des événements), **ajustement en brouillon** (boutons −/+ ou saisie directe d'un entier signé), **score résultant**.
- **« ▸ détail »** affiche l'historique du joueur round par round (réponse, temps, rang, points, corrections), pour repérer une erreur commise pendant un round.
- Tous les joueurs peuvent être corrigés, **hôte compris**, sans limite sur le nombre de corrections.
- Le brouillon est **côté serveur** et visible uniquement par l'hôte. Il survit à un rafraîchissement, une déconnexion ou un changement d'appareil.
- **Validation** :
  1. une confirmation récapitule les corrections, par exemple « 3 corrections : Ayoub +2, Mehdi −1, Yo +1 — confirmer ? » ;
  2. elle crée un `ScoreEvent(kind="final_adjustment")` par joueur dont le delta est non nul ;
  3. elle fait passer la partie en `FINAL_RESULTS`.

  La commande porte la phase attendue, ce qui la rend **idempotente** (double clic, deux appareils hôtes).
- Les joueurs voient « L'hôte vérifie les scores… » et le dernier classement publié, figé. **Ils ne voient aucun brouillon.**

### 6.7 Résultats finaux (FINAL_RESULTS)
- Classement final. En cas d'égalité, le rang est partagé (1, 1, 3) et il n'y a pas de départage automatique ; l'hôte peut départager pendant la vérification.
- Podium (trois premiers) puis classement complet, nombre de rounds joués, et **ajustements finaux affichés** en toute transparence (« ajustement final : Ayoub +2 »).
- **Les scores de la partie sont figés en V0.1** : aucun `ScoreEvent` ne peut plus être ajouté à cette partie.
- Actions possibles : nouvelle partie (scores à zéro, joueurs conservés) ou fin de session.

### 6.8 Visibilité des informations

**Pendant OPEN**
| Information | Joueur | Hôte (Player Mode) | Hôte (MC Mode) |
|---|---|---|---|
| Son propre brouillon ou sa réponse | ✓ | ✓ | — |
| Réponses des autres | ✗ | ✗ | ✗ |
| Progression | `n/m ont validé` (anonyme, masqué si `m < 3`) | identique au joueur | ✓ statut par joueur (sans texte) |

**Règle du compteur de progression (OPEN)**
- Les joueurs, y compris l'hôte en Host Player Mode, voient uniquement `n/m ont validé`.
  - `n` = nombre de réponses `LOCKED`.
  - `m` = `n` + nombre de joueurs **en ligne** qui n'ont pas encore validé. L'hôte en MC Mode n'est pas compté.
- **Aucune donnée par joueur** n'apparaît dans la vue joueur pendant OPEN : ni statut de réponse, ni rang, ni temps.
- **Le compteur est masqué si `m < 3`.** À deux joueurs, voir « 1/2 » suffirait à savoir que l'autre a validé, et à quel moment. Le compteur n'indique donc jamais qui a répondu ni à quelle vitesse.
- Le compteur est purement informatif. La fermeture automatique quand tout le monde a validé n'apprend rien de plus aux joueurs.
- Dans la vue envoyée au client, il correspond au champ `progress {validated, expected}` de `STATE` (§8.2).

**En REVIEW**
| Information | Joueur | Hôte (les deux modes) |
|---|---|---|
| Réponses des autres | ✗ | ✓ |
| Temps, rang, quasi-égalité, retard audio | ✗ | ✓ |

**En REVEALED**
| Information | Joueur | Hôte |
|---|---|---|
| Réponses, temps, rangs, quasi-égalités, points de tous | ✓ | ✓ |
| Titre ou nom du morceau | ✓ | ✓ |

**Métadonnées du morceau**
| Phase | Joueur | Hôte (Player Mode) | Hôte (MC Mode) |
|---|---|---|---|
| Avant REVEALED | ✗ | ✗ | ✓ |
| Morceaux à venir | ✗ | ✗ | ✓ |

**En FINAL_SCORE_REVIEW**
| Information | Joueur | Hôte |
|---|---|---|
| Brouillon d'ajustements | ✗ | ✓ |
| Classement | dernier classement publié, figé | ✓ |

### 6.9 Sélection des morceaux
- L'hôte coche des dossiers dans une arborescence, à n'importe quel niveau ; la racine équivaut à toute la bibliothèque. Le pool est l'ensemble des morceaux dont le chemin relatif commence par l'un des dossiers cochés.
- La file est mélangée au lancement de la partie. Les morceaux déjà joués dans la session sont exclus. Si le pool est épuisé, l'hôte est averti et peut autoriser les répétitions.
- Prévu plus tard : sélection manuelle (MC Mode, V0.3) et équilibrage par dossier (V0.2).

---

## 7. Machines à états

### 7.1 Partie (état global)
```
            host:start_game
  LOBBY ───────────────────► IN_GAME
    ▲                           │  dernier round publié + host:to_final_review
    │                           │  ou host:end_game (fin anticipée, cf. tableau)
    │                           ▼
    │                  FINAL_SCORE_REVIEW      ← obligatoire, aucun contournement
    │                           │  host:final_validate (confirmation explicite)
    │                           ▼
    └──── host:new_game ─── FINAL_RESULTS      (scores figés)

  host:end_session (depuis n'importe quel état) → tous les tokens révoqués → LOBBY vide
```
**Il n'existe aucune transition `IN_GAME → FINAL_RESULTS`.**

**Fin anticipée** (`host:end_game {current_round}`)
| Phase du round courant | Effet |
|---|---|
| QUEUED, PREPARING, LOADING, COUNTDOWN | Round `CANCELLED`, sans points, puis `FINAL_SCORE_REVIEW` |
| OPEN ou REVIEW | `current_round = "score"` : fermeture, REVIEW, publication, puis `FINAL_SCORE_REVIEW`. `current_round = "abandon"` : `CANCELLED`, puis `FINAL_SCORE_REVIEW` |
| REVEALED | `FINAL_SCORE_REVIEW` directement |

Le préchargement s'arrête dès que le dernier round est atteint ou que la fin est demandée. Les jobs en cours reçoivent `CANCEL` et les assets inutiles sont évincés.

### 7.2 Round
```
 QUEUED ──► PREPARING ──(asset STORED)──► LOADING ──(prêts | timeout | host:force)──► COUNTDOWN
             │   ▲                          │                                           │ t ≥ official_start_at
             │   └─ autre morceau (auto,    │ host:skip                                 ▼
             ▼      max 3 essais)           ▼                          ┌──────────── OPEN ─────────────┐
          FAILED ─────────────────────► round suivant                  │ réponses ouvertes             │
                                                                       │ audio: SCHEDULED→PLAYING→ENDED│
          (fin anticipée : n'importe quel état → CANCELLED)            │ host:replay ↺ (new play_id)   │
                                                                       │ host:stop, host:add_time      │
                                                                       └──────────────┬────────────────┘
                  deadline | tous les joueurs en ligne ont validé | host:close        │
                                                                                      ▼
   REVEALED ◄───────────── host:publish ───────────── REVIEW (hôte : réponses + temps, brouillon de points)
      │  ▲                                                ▲
      │  └──────── host:undo_publish (si round suivant    │
      │            pas encore en COUNTDOWN) ──────────────┘
      └─ host:next → round suivant | dernier round → host:to_final_review
```
- COUNTDOWN n'a lieu qu'avant la première lecture. Un replay reste dans OPEN avec un nouveau `play_id` et un nouveau `start_at`. **`official_start_at` ne change pas.**
- Les validations ne sont acceptées qu'en OPEN.

### 7.3 Asset (préparation de l'audio, indépendante du round)
```
REQUESTED ─► ENCODING ─► UPLOADING ─► STORED ─► EVICTED
    └───────────┴────────────┴──► FAILED(code: NOT_FOUND | DECODE_ERROR | TOO_SHORT |
                                         TIMEOUT | BRIDGE_OFFLINE | INVALID_UPLOAD | CANCELLED)
```
**Préchargement**
- Dès que le round N passe en LOADING, le serveur demande l'asset N+1.
- Les **clients** téléchargent l'asset N+1 quand le round N entre en REVIEW, jamais pendant la lecture.

### 7.4 Joueur (trois dimensions indépendantes)
| Dimension | États |
|---|---|
| **Connexion** | `ONLINE ⇄ OFFLINE` (fermeture du WebSocket ou heartbeat manqué environ 20 s) → `REMOVED` (kick). Un joueur hors ligne reste au classement, grisé. |
| **Audio** (déclaré par le client, affiché à l'hôte) | `LOCKED → IDLE → LOADING → READY(asset_id) → PLAYING → IDLE` ; `ERROR(code)` |
| **Réponse** (round courant) | `NONE → DRAFT → LOCKED` ; à la fermeture, `DRAFT` non vide devient `CAPTURED` |

**Identité et reconnexion**
| Cas | Comportement |
|---|---|
| Rafraîchissement, onglet rouvert, changement de réseau | Le cookie est renvoyé, c'est le même joueur, il reçoit la vue complète avec son brouillon. Aucune liaison à l'IP, aucun fingerprinting. |
| Deux onglets avec le même token | **La dernière connexion gagne.** L'ancienne reçoit le code `4001 SUPERSEDED` et affiche « Ouvert ailleurs — reprendre ici ». |
| Pseudo déjà pris | Refusé (comparaison insensible à la casse après NFKC). L'hôte peut retirer ou renommer un joueur fantôme. |
| Reconnexion pendant un round | Vue complète. Si l'extrait est encore en cours, la lecture reprend **à la bonne position**. |
| Arrivée en cours de partie | Autorisée. Score à 0, ajustable. Le joueur peut répondre au round en cours. Son `late_start_ms` est mesuré. |
| Déconnexion définitive | Reste au classement, grisé, ignoré par le ready check, peut être retiré. |
| Cookie perdu (autre appareil) | V0.1 : nouveau pseudo et ajustement manuel par l'hôte. V0.2 : code de récupération à 6 caractères. |

### 7.5 Bridge
- **Vu du serveur** : `OFFLINE → CONNECTED (secret OK) → SYNCING (catalogue) → ONLINE (idle/busy) → OFFLINE`, ou `REJECTED` (secret ou version de protocole).
- **Vu localement** : `SCANNING → CONNECTING ⇄ BACKOFF (1→30 s, jitter) → ONLINE`.

### 7.6 Scénarios d'échec

| Scénario | V0.1 | Comportement |
|---|---|---|
| Bridge fermé ou sans Internet | ✅ | Les assets `STORED` restent jouables (1 à 2 rounds d'avance). Le round suivant attend en PREPARING, l'hôte voit « Bridge déconnecté ». Reprise automatique. |
| Fichier supprimé ou renommé, catalogue périmé | ✅ | `JOB_FAILED NOT_FOUND` → morceau marqué indisponible → **remplacement automatique** (3 essais), sans que les joueurs le voient. |
| Échec FFmpeg, codec invalide, morceau trop court | ✅ | Même mécanisme. Moins de 8 s : FAILED. Plus court que l'extrait demandé : morceau entier. |
| Upload incomplet ou invalide | ✅ | Jamais `STORED`. Un nouvel essai, puis remplacement. |
| Mémoire du cache pleine | ✅ | Éviction de tout ce qui n'est ni courant ni suivant, puis refus du job avec un log. |
| Redémarrage ou crash du conteneur | ⚠️ documenté | Session perdue, les clients reviennent à l'accueil. Le snapshot est candidat pour la V0.2. |
| Échec de téléchargement côté joueur | ✅ | 3 essais avec backoff, puis `ERROR` visible par l'hôte, qui peut forcer le départ. |
| AudioContext suspendu, autoplay bloqué | ✅ | Détecté via `ctx.state` → overlay « Touchez pour réactiver le son » → état `LOCKED` signalé. |
| Téléphone verrouillé, onglet en arrière-plan | ✅ partiel | Au retour : rafale de synchro, reconnexion, réactivation, rattrapage de position. Lecture en arrière-plan **non garantie sur iOS** (documenté). |
| Hôte déconnecté | ✅ | Le jeu continue jusqu'au prochain point de décision (la deadline ferme d'elle-même). REVIEW et FINAL_SCORE_REVIEW attendent l'hôte, **leurs brouillons sont conservés côté serveur**. N'importe qui ayant `HOST_PASSWORD` peut reprendre. |
| Erreur de notation | ✅ | Brouillon modifiable avant publication. Ensuite : annulation de la dernière publication, ajustement ponctuel, ou ajustement en vérification finale. |
| Double clic ou deux appareils hôtes | ✅ | Les commandes portent le `round_id` ou la phase attendus, ce qui les rend idempotentes. |
| Bluetooth non compensé | ⚠️ documenté | Curseur de latence manuel en V0.2. |

---

## 8. Protocole réseau

Règles clés :
- **Enveloppe** `{ "t": "TYPE", ...champs }` : union discriminée Pydantic avec `extra="forbid"` sur tous les messages entrants. Un entier `protocol` est échangé à la connexion ; en cas d'incompatibilité, le serveur force le rechargement de la SPA.
- **HTTP (§8.1)** : `POST /api/session/join {password, nickname}` pose le cookie `__Host-openblindysir` ; élévation hôte par `POST /api/session/host` ; audio servi par `GET /api/audio/{asset_id}` (URL opaque, `no-store`) ; le Bridge envoie son catalogue et ses extraits par `PUT` (secret Bridge, puis upload token à usage unique).
- **WebSocket joueur `/api/ws` (§8.2)** : cookie + vérification de l'`Origin`. Le serveur envoie `STATE {v, view}`, la vue complète filtrée par `view_for()` selon la matrice du §6.8. Pendant OPEN, la vue joueur et celle de l'hôte en Host Player Mode ne donnent sur les réponses que `progress {validated, expected} | null` (à `null` si `expected < 3`) ; `players[]` ne contient aucun champ lié à la réponse du round en cours.
- `ANSWER_SUBMIT` est horodaté par le serveur et tout champ supplémentaire est rejeté ; `ANSWER_ACK` ne contient aucune donnée temporelle ; les commandes `HOST` sont refusées hors session hôte et idempotentes (`round_id` / `expected_phase`).
- **WebSocket Bridge `/api/bridge/ws` (§8.3)** : `Authorization: Bearer BRIDGE_SECRET`. `PREPARE` est la seule commande métier, sans chemin ni argument FFmpeg ; `JOB_FAILED` ne contient jamais de chemin absolu ; les tags renvoyés par `JOB_DONE` servent uniquement au reveal.

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

```
D:\Music\Anime\foo.flac (70 Mo)
  │ 1. Bridge reçoit PREPARE{track_id, start_fraction, duration}
  │ 2. lookup track_id → relpath → realpath + confinement + fichier régulier
  │ 3. ffprobe (timeout 10 s) → durée + tags title/artist (reveal uniquement)
  │ 4. calcul du point de départ (règle ci-dessous)
  │ 5. ffmpeg (gabarit fixe, 1 thread, timeout 30 s) → fichier temporaire privé
  ▼
extrait .m4a AAC-LC 128 kbps 48 kHz stéréo, ~400 Ko, SANS métadonnées
  │ 6. PUT /api/bridge/assets/{id} + upload token + sha256 → fichier temporaire supprimé
  ▼
VPS : taille ≤ 2 Mo, magic bytes, sha256 → RAM → asset STORED
  │ 7. URL opaque publiée dans la vue (rôle current/next)
  ▼
Navigateur : fetch (cookie, no-store) → decodeAudioData → AudioBuffer (~11,5 Mo pour 30 s)
  │ 8. READY → PLAY{start_at} → source.start(T) → GainNode (volume local) → sortie
```

**Gabarit FFmpeg** (spécification ; arguments passés en liste, jamais via un shell)
- `-nostdin -hide_banner -loglevel error -threads 1`
- `-protocol_whitelist file`, et une entrée **préfixée `file:` suivie du chemin absolu résolu**
- `-format_whitelist mp3,flac,wav,mov,ogg,aiff,asf,aac` (ffprobe **et** ffmpeg, avant `-i`) : liste fermée de démultiplexeurs audio. Sans elle, un fichier à extension audio contenant une playlist `ffconcat` (démultiplexeur choisi d'après le contenu) peut faire lire un fichier hors de la racine, par exemple à travers une junction située dans la bibliothèque ; `-protocol_whitelist` ne bloque pas ce cas (constat du spike S1).
- `-ss <départ>` placé avant `-i`, puis `-t <durée>`
- `-map 0:a:0 -vn -sn -dn` : uniquement la première piste audio, **sans pochette**
- **`-map_metadata -1 -map_chapters -1`** : aucun tag recopié
- `-ac 2 -ar 48000`, `afade` (entrée 0,3 s, sortie 1,5 s)
- `-c:a aac -b:a 128k -movflags +faststart`, ou `libopus 96k` si le spike S0 retient Opus

Seules variables : le chemin (issu du catalogue), le départ et la durée (des flottants plafonnés **par le Bridge**, durée entre 5 et 60 s), le format (une valeur parmi une liste fixe).

**Contrôle de sortie** : avant l'upload, le Bridge mesure la durée réelle de l'extrait produit (ffprobe). En dessous de la moitié de la durée demandée (ou du morceau entier s'il est plus court), le job échoue en `DECODE_ERROR`. Un fichier tronqué dont l'en-tête annonce une durée trop longue produit sinon un conteneur valide mais vide, que les magic bytes ne détectent pas (constat du spike S1).

**Choix du point de départ**
- Le serveur envoie `start_fraction ∈ [0,1)`. Le Bridge l'applique à la fenêtre valide, qui va de `max(10 s, 8 % de la durée)` à `durée − extrait − max(20 s, 10 % de la durée)`.
- Si la fenêtre est vide : départ au tiers du morceau. Si le morceau est plus court que l'extrait : morceau entier.
- V0.2 : `volumedetect` dans la même passe ; en dessous de −45 dB on retente à une autre fraction (2 essais maximum). `loudnorm` pour homogénéiser les volumes.

**Pourquoi télécharger l'extrait en entier** : 400 Ko se téléchargent en moins d'une seconde. Le décodage complet garantit un départ précis et rend le replay gratuit. Le streaming réintroduirait un buffering imprévisible.

---

## 11. Bridge

Règles clés :
- **OpenBlindySir Bridge** est une CLI Python (jusqu'à la V1 au moins) qui n'ouvre que des connexions **sortantes** (WSS + HTTPS) ; `ws://` et `http://` sont refusés hors `localhost` et la vérification TLS est toujours active. Configuration unique dans `%APPDATA%\OpenBlindySir\bridge\config.toml` (Windows) ou `~/.config/openblindysir/bridge/config.toml` (Linux, macOS), avec la priorité CLI > env > fichier.
- **Scan** d'une racine unique avec `os.scandir`, sans suivre ni liens symboliques ni junctions ; `track_id = "t_" + sha256(relpath)[:16]`, stable et opaque.
- **Protocole fermé** : le Bridge n'accepte que `WELCOME`, `PREPARE`, `CANCEL` et `PING`. Le serveur ne désigne jamais un chemin et ne passe aucun argument FFmpeg ; le Bridge plafonne lui-même durée, départ et format.
- **Avant chaque ouverture** : nouvelle résolution de `realpath`, confinement par `commonpath` sous la racine, fichier régulier dont taille et mtime sont cohérents.
- **Jobs** : 1 à la fois (2 au maximum), file de 4, timeouts (ffprobe 10 s, ffmpeg 30 s, upload 60 s), fichiers temporaires privés préfixés `openblindysir-bridge-`.
- **Console sans noms de fichiers** par défaut (`--verbose-paths` pour le débogage) ; FFmpeg n'est pas embarqué en V0.x ; le mode `--demo` produit des sons synthétiques, sans aucun contenu protégé.
- **Packaging** : `uv run openblindysir-bridge` en V0.1, puis `uvx openblindysir-bridge` et binaires PyInstaller onedir en V0.3. Les références `(bridge_id, track_id)` préparent plusieurs Bridges ; en V0.1, un second Bridge remplace le premier.

Détail complet : [docs/bridge-security.md](bridge-security.md)

---

## 12. Sécurité et modèle de menaces

| Menace | Impact | Mitigation | Quand |
|---|---|---|---|
| Joueur qui envoie des commandes hôte | Triche, sabotage | Rôle stocké côté serveur et vérifié à chaque commande `HOST`. Test paramétré sur toutes les commandes. | V0.1 |
| Joueur qui falsifie son temps de réponse | Avantage indu si l'hôte tient compte de la vitesse | Horodatage serveur uniquement, `extra="forbid"`, aucune compensation calculée à partir de données client. `late_start_ms` mesuré côté serveur. | V0.1 |
| Joueur qui découvre le morceau à l'avance (DevTools) | Spoiler | URL aléatoire de 128 bits sans lien avec `track_id`, extrait **sans métadonnées**, `no-store`, préchargement client seulement pendant REVIEW, `view_for()` sans métadonnées avant le reveal. Écouter le morceau suivant quelques secondes plus tôt reste possible : risque accepté. | V0.1 |
| Token de session volé | Usurpation d'identité | Cookie `__Host-openblindysir`, HttpOnly, Secure, SameSite=Strict ; token de 256 bits **stocké haché** ; expiration avec la session (fin, kick, 24 h d'inactivité). La reconnexion du vrai joueur expulse l'autre. Kick possible. | V0.1 |
| Force brute sur les mots de passe | Accès au jeu, puis aux droits hôte | Limitation par IP des tentatives **échouées** (join 5/min, host 3/min), plafond global, `hmac.compare_digest` ; les connexions réussies ne sont pas comptées, pour ne pas bloquer des amis derrière la même box. **Démarrage refusé** si un secret manque, est faible (< 12 caractères, `BRIDGE_SECRET` < 32), vaut « changeme », ou si `HOST_PASSWORD == BLIND_PASSWORD`. IP réelle via `--proxy-headers`, uniquement depuis le proxy de confiance. | V0.1 |
| XSS par pseudo ou réponse | Vol de session | Échappement React, `dangerouslySetInnerHTML` interdit par le lint, CSP stricte (`default-src 'self'`, pas d'inline, `media-src 'self' blob:`, `frame-ancestors 'none'`). Pseudo : NFKC, 1 à 24 caractères, sans caractères de contrôle, zero-width ni **bidi override**. Réponse ≤ 200 caractères. | V0.1 |
| CSRF / détournement de WebSocket inter-site | Actions faites au nom d'un joueur | SameSite=Strict, **vérification de l'`Origin`** sur les POST et le WebSocket, corps JSON obligatoire, aucun CORS. | V0.1 |
| Path traversal depuis le serveur | Lecture de fichiers hors du dossier | `track_id` sert de **clé de dictionnaire, jamais de chemin**. ID inconnu : erreur. | V0.1 |
| Évasion par symlink ou junction | Idem | Liens ignorés au scan, `realpath` et confinement vérifiés au scan **et** à l'ouverture, tests sur un runner Windows. | V0.1 |
| Serveur malveillant vu du Bridge | Lecture de fichiers, exécution, saturation du PC | Protocole fermé de 4 messages, aucun argument FFmpeg libre, bornes fixées par le Bridge, file limitée, timeouts, préfixe `file:`, `protocol_whitelist` et `format_whitelist`, contrôle de la durée produite. Fuite résiduelle (documentée) : arborescence et noms de fichiers. | V0.1 |
| Faux Bridge (secret volé) | Diffusion d'audio choisi par l'attaquant, saturation | Secret fort, upload uniquement pour un job en attente (token à usage unique), ≤ 2 Mo, magic bytes, un seul Bridge actif. Rotation par `.env`. Un secret par Bridge en V1. | V0.1 / V1 |
| Audio malformé | Plantage du décodeur | Décodage dans le bac à sable du navigateur ; en cas d'échec, `ERROR`. Si la majorité des clients échoue, l'asset passe FAILED. | V0.1 |
| Fichier piégé visant FFmpeg | Exécution de code sur le PC | Fichiers fournis par l'utilisateur (risque faible), vérification de la version de FFmpeg, timeouts, et consigne de ne pas lancer le Bridge en administrateur. | V0.1 (doc) |
| DoS trivial | Soirée gâchée | Messages WS limités à 16 Ko (joueur) et 64 Ko (Bridge), débit plafonné par connexion, 20 connexions par IP au plus (NAT partagé entre amis), `MAX_PLAYERS`, taille des requêtes HTTP bornée. Un DDoS réel est hors périmètre. | V0.1 |
| MITM / absence de TLS | Vol des secrets | HTTPS obligatoire (Caddy + HSTS), cookie Secure, le Bridge refuse toute connexion non TLS hors localhost. | V0.1 |
| Secrets dans les logs ou le dépôt | Fuite | Filtre de masquage dans les logs, aucun secret dans une URL. Hygiène Git au §19.7, secret scanning et push protection GitHub. | V0.1 |
| Chaîne d'approvisionnement | Code malveillant | Lockfiles, Dependabot groupé, actions épinglées par SHA, image de base slim. | V0.1 |
| Évasion du conteneur | Accès au VPS | Utilisateur non root, `read_only`, `no-new-privileges`, aucun volume monté sur l'app. | V0.1 |
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
| `latency_ms` | V0.2 |
| `joined_at`, `last_seen` | |
| connexion | Non sérialisée |

**GameSettings** : `rounds`, `clip_seconds`, `answer_grace_s`, `sources[] (bridge_id, folder_prefix)`, `auto_start`, `prefetch_depth`, `allow_repeats`.

**GameState**
- `phase` : LOBBY / IN_GAME / FINAL_SCORE_REVIEW / FINAL_RESULTS
- `settings`, `queue[] TrackRef`, `played set<TrackRef>` (à l'échelle de la session), `rounds[]`, `current_index`
- `final_draft {player_id → delta}`, `finalized_at?`

**Round**
- `id` aléatoire, `number`, `track_ref`, `asset_id`, `state`
- **`official_start_at`** : fixé au premier `PLAY`, jamais modifié
- `plays[] {play_id, start_at, clip_offset}`, `deadline`
- `answers {player_id → Answer}`, `ready_received_at {player_id → t}`
- `score_draft {player_id → int}`, `published_at?`, `reveal {display_name, folder, tags}`

**Answer**
| Champ | Contenu |
|---|---|
| `player_id` | |
| `status` | NONE / DRAFT / LOCKED / CAPTURED |
| `text` | Validé ou capturé |
| `draft_text` | |
| `draft_last_changed_at` | Monotone serveur. Diagnostic uniquement, jamais utilisé pour classer. |
| `received_at` | Monotone serveur, renseigné si LOCKED |
| `received_at_wall` | ISO, pour l'export et les logs |
| `elapsed_ms` | Si LOCKED |
| `order` | Si LOCKED, sinon null |
| `near_tie` | |
| `late_start_ms` | |

**ScoreEvent** : journal en ajout seul.
- Champs : `id`, `game_id`, `player_id`, `round_id?`, `delta` (entier signé, borné à ±1000), `kind`, `by` (joueur hôte), `at`, `note?`, `revokes?` (liste d'ids).
- Valeurs de `kind` :

| `kind` | Créé par | `round_id` |
|---|---|---|
| `round` | Publication de la notation d'un round, un événement par joueur dont le delta est non nul | oui |
| `adjustment` | Correction ponctuelle pendant IN_GAME | optionnel |
| `final_adjustment` | `final_validate`, un événement par joueur dont le delta est non nul | non |
| `revoke` | `undo_publish` (annule des événements `round` désignés) | oui |

- **Invariants** :
  - `score(joueur) = Σ delta des événements actifs`, c'est-à-dire non révoqués ; un `revoke` porte lui-même un delta de 0 ;
  - **aucun champ `score` n'est stocké** ;
  - les brouillons (`score_draft`, `final_draft`) ne sont jamais des événements ;
  - après `FINAL_RESULTS`, aucun événement ne peut s'ajouter pour ce `game_id`.

**TrackRef** : `bridge_id`, `track_id`, `relpath` (**côté serveur uniquement**), `folder`, `ext`, `available`.

**Bridge** : `bridge_id`, `name`, `version`, `state`, `catalog_hash`, `track_count`, `jobs_in_flight`, `last_seen`.

**AudioAsset** : `asset_id` (128 bits aléatoires), `track_ref`, `job_id`, `upload_token_hash`, `state`, `bytes`, `mime`, `actual_start`, `clip_duration`, `tags?`, `role`, `error?`.

---

## 14. Persistance

| Donnée | Emplacement | Après un redémarrage | Raison |
|---|---|---|---|
| Joueurs, tokens hachés, rôles | RAM | Perdus | La session est l'unité de vie ; l'expiration est naturelle |
| Partie, rounds, réponses, journal des scores, brouillons | RAM | Perdus (V0.1) | Aucune requête, un seul processus |
| Catalogues | RAM | Perdus | Renvoyés automatiquement à la reconnexion du Bridge |
| Assets audio | RAM | Perdus | Temporaires par nature |
| Secrets, limites | `.env` | — | Source de vérité du déploiement |
| Réglages de partie | RAM, choisis par l'hôte | Perdus | Valeurs par défaut dans le code, bornées par l'environnement |
| *(V0.2, candidat)* Snapshot | `data/session.json`, écriture atomique à chaque publication et à chaque `final_validate` | Restauré s'il date de moins de 12 h | Survivre à un crash en pleine soirée ; le journal des scores se rejoue tel quel |
| *(V1)* Historique des morceaux joués | `history.json` | Conservé | Éviter les répétitions d'une soirée à l'autre (Track IDs stables) |

**Pas de SQLite**, V1 comprise.

---

## 15. Configuration

| Niveau | Où | Contenu |
|---|---|---|
| Secrets | `.env` | `BLIND_PASSWORD`, `HOST_PASSWORD`, `BRIDGE_SECRET` |
| Déploiement | `.env` | `DOMAIN` (ex. `openblindysir.example.com`), `TRUSTED_PROXIES`, `LOG_LEVEL`, `LOG_FORMAT=text\|json`, `LOG_TRACK_NAMES=false` |
| Limites serveur (valeurs par défaut raisonnables) | `.env` | `MAX_PLAYERS=20`, `CLIP_MIN_S=5`, `CLIP_MAX_S=60`, `CLIP_FORMAT=aac`, `CLIP_BITRATE=128`, `AUDIO_CACHE_MB=32`, `MAX_CLIP_MB=2`, `READY_TIMEOUT_S=10`, `ANSWER_MAX_CHARS=200`, `NEAR_TIE_MS=300`, `SESSION_IDLE_TTL_H=24` |
| Développement | `.env` | `DEV_MODE=1` : cookie non Secure, mots de passe faibles tolérés, logs verbeux. **Jamais en production.** |
| Réglages de partie | Interface hôte, dans les bornes de l'environnement | Nombre de rounds, durée des extraits, délai de grâce, sources, mode hôte, départ automatique |
| Bridge | CLI > env > `config.toml` (§11) | URL du serveur, dossier, secret, nom, chemin de FFmpeg, extensions |

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
│   ├── workflows/ci.yml, e2e.yml, release.yml
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

**Image** `ghcr.io/primokg/openblindysir`
- Multi-stage (build Node, puis `python:3.13-slim`).
- **Sans FFmpeg.**
- Utilisateur 10001, endpoint `/healthz`.
- Multi-architecture amd64 et arm64.
- Commande par défaut : `openblindysir-server`.
- Labels OCI : `org.opencontainers.image.title=OpenBlindySir`, `org.opencontainers.image.licenses=MIT`, `org.opencontainers.image.source=https://github.com/PrimoKG/OpenBlindySir`, `org.opencontainers.image.version`.

**Tags de l'image**
| Tag | Exemple | Quand |
|---|---|---|
| `edge` | `edge` | Chaque merge sur `main` |
| `X.Y.Z-rc.N` | `0.1.0-rc.1` | Pré-release, sans `latest` |
| `X.Y.Z`, `X.Y`, `latest` | `0.1.0`, `0.1`, `latest` | Releases uniquement. **Aucun `latest` avant une v0.1.0 réellement jouable.** |

**`compose.yaml`**
- **`name: openblindysir`** : préfixe stable pour les conteneurs et les volumes, quel que soit le dossier de téléchargement.
- **`app`** :
  - `image: ghcr.io/primokg/openblindysir`, `env_file: .env` ;
  - `read_only: true`, `tmpfs: /tmp:size=16m`, `security_opt: no-new-privileges` ;
  - `restart: unless-stopped`, healthcheck ;
  - **aucun port publié**.
- **`caddy`** :
  - image officielle ;
  - `command: caddy reverse-proxy --from ${DOMAIN} --to app:8000` ;
  - ports 80 et 443 ;
  - volumes **`caddy_data`** (persistant) et `caddy_config`.

**Parcours utilisateur**
- **Débutant ou VPS** :
  1. un VPS avec Docker et un domaine. Sans domaine, `1-2-3-4.sslip.io` fonctionne aussi avec Let's Encrypt ;
  2. télécharger **seulement** `compose.yaml` et `.env.example` depuis la release, sans clone Git ;
  3. remplir `.env`. Les secrets se génèrent avec `openssl rand` ou avec `docker run --rm ghcr.io/primokg/openblindysir openblindysir-server gen-secrets` ;
  4. `docker compose up -d` ;
  5. installer FFmpeg sur le PC et lancer le Bridge ;
  6. envoyer l'URL et le mot de passe aux amis, puis ouvrir `/host`.
- **Proxy déjà en place** : `deploy/compose.no-proxy.yaml` (app sur `127.0.0.1:8000`), avec des exemples pour nginx (en-têtes `Upgrade`, timeouts WebSocket) et Traefik.
- **Développement** :
  - sans Docker : `DEV_MODE=1 uv run openblindysir-server` pour le serveur, `npm run dev` (proxy Vite vers `/api` et le WebSocket), `uv run openblindysir-bridge --demo` ou le Bridge sur un vrai dossier ;
  - `compose.dev.yaml` sert uniquement à tester l'image.

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
  ou une release ; le parcours Docker ci-dessus reste prévu pour l'étape 8.

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

> L'anglais pour l'interface (`en.ts`) et pour le Bridge reste prévu en V0.2 (§25) et **hors MVP** (§24). `SECURITY.md`, en anglais, résume le modèle de menaces et renvoie à `docs/bridge-security.md`, en français.

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
| `e2e` | Playwright (Chromium) | `main`, nightly, PR étiquetée |
| `docker` | Build de l'image sur PR, push `edge` sur `main` | PR et `main` |
| `release` | Images versionnées, GitHub Release (binaires du Bridge à partir de la V0.3) | Tag `v*` |

**Dependabot** : écosystèmes uv/pip, npm, github-actions et docker, avec des **mises à jour groupées et mensuelles**.

### 19.9 Versions et releases
- **SemVer**, une version unique pour tout le monorepo (`VERSION`), et un entier `protocol` distinct. On reste en `0.x` tant que le protocole bouge.
- **Procédure de release** :
  1. tests complets ;
  2. mise à jour du `CHANGELOG.md` ;
  3. mise à jour de `VERSION` ;
  4. tag Git `vX.Y.Z` ;
  5. push du tag ;
  6. la CI construit les images ;
  7. push sur GHCR : `ghcr.io/primokg/openblindysir:X.Y.Z` (et `X.Y`, `latest` pour une version finale) ;
  8. GitHub Release intitulée **« OpenBlindySir vX.Y.Z »** ;
  9. notes reprises du CHANGELOG, terminées par « Licensed under MIT ».
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
- `CAPTURED` n'a ni rang ni temps.

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
- `publish` crée un événement `round` par delta non nul.
- `undo_publish` crée un `revoke` et restaure le brouillon ; il est impossible une fois le round suivant en COUNTDOWN.
- `adjust` fonctionne, y compris sur l'hôte.
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

| Phase | `view_for(player)` | `view_for(host, player_mode)` | `view_for(host, mc)` |
|---|---|---|---|
| OPEN | Ni texte ni temps des autres, ni métadonnée du morceau. **Seulement `progress` agrégé**, sans aucun statut par joueur. | Identique à `player`, plus les commandes. **Aucune métadonnée.** | Métadonnées, morceau suivant, statut par joueur |
| REVIEW | **Ni réponse, ni temps, ni rang des autres** | **Toutes les réponses, statuts, temps, rangs, `near_tie`, `late_start_ms`**. Pas de métadonnée du morceau. | Idem + métadonnées |
| REVEALED | Réponses, temps, rangs, points, morceau | Idem | Idem |
| FINAL_SCORE_REVIEW | Dernier classement figé. **Ni `draft_delta` ni `score_after`.** | `final_review[]` complet | `final_review[]` complet |
| Toutes | Jamais de `relpath`, de `track_id`, ni de `draft_last_changed_at` | Jamais de `relpath` ni de `track_id` avant le reveal | — |

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
- notation, publication ;
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
- WebKit en nightly. **Ne remplace pas** un vrai iPhone.

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

## 24. Exclu du MVP

- **Calcul automatique de points ou de bonus de vitesse**, y compris les barèmes pré-remplis ou les boutons « appliquer 3/2/1 ». *La mesure du temps, l'ordre et leur affichage font partie du MVP ; seule l'attribution automatique est exclue, et elle l'est définitivement.*
- Compensation de latence sur les temps de réponse.
- Affichage du temps au joueur pendant le round (il est montré au reveal).
- Affichage de `draft_last_changed_at` dans l'interface principale.
- Réouverture de la vérification finale après `FINAL_RESULTS`.
- Plusieurs Bridges, un secret par Bridge.
- Pause et reprise.
- Exécutables du Bridge, paquet PyPI, FFmpeg embarqué.
- Snapshot ou restauration après crash ; historique d'une soirée à l'autre.
- Détection de silence, normalisation du volume (`loudnorm`).
- Curseur de latence manuel, code de récupération, verrouillage des inscriptions.
- Sélection manuelle des morceaux, playlists, équilibrage par dossier.
- Export des résultats.
- Traduction anglaise (l'architecture est prête, pas le contenu).
- Réponses visibles en direct en MC Mode.
- Chat, avatars, thèmes, effets sonores, waveform, PWA.
- Import Spotify, Deezer, YouTube ou CSV.
- Comptes, rooms, multi-session (exclus définitivement).

---

## 25. Feuille de route

| Version | Nom | Contenu |
|---|---|---|
| **V0.1** | « Une vraie soirée » | §23, validée par **une vraie soirée test** entre amis |
| **V0.2** | « Confort et robustesse » | Pause (temps exclu de `elapsed`), curseur de latence, détection de silence et `loudnorm`, snapshot JSON (à confirmer après la soirée test), code de récupération, verrouillage des inscriptions, export JSON/CSV (avec `draft_last_changed_at`), réponses en direct en MC Mode, équilibrage par dossier, traduction anglaise |
| **V0.3** | « Distribution » | `uvx openblindysir-bridge` (PyPI), binaires PyInstaller onedir `OpenBlindySir-Bridge-<version>-<os>-<arch>.zip`, assistant de premier lancement, documentation (dépannage, proxies), sélection manuelle en MC Mode |
| **V1.0** | « Stable » | Protocole figé, **plusieurs Bridges**, un secret par Bridge, historique d'une soirée à l'autre, passe accessibilité, revue de sécurité, retrait du bandeau « early development » |

**Après la V1, si c'est utile** :
- Import d'une liste « artiste – titre » (CSV, export Exportify) mise en correspondance avec la bibliothèque locale. Une URL Spotify ne serait qu'un raccourci vers cette liste, via l'API officielle, **sans jamais télécharger d'audio**.
- Nouveaux types de rounds.

---

## 26. Ordre d'implémentation

Chaque étape suit le même enchaînement : tests, DEVLOG, commits, puis push au jalon.

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
