# Validation des parcours de soirée

## Vérification automatisée

Depuis la racine, avec FFmpeg et ffprobe accessibles dans le PATH :

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

Playwright lance le serveur et le Bridge démo, avec des données synthétiques.
En l'absence de `uv`, `E2E_PYTHON` peut désigner un interpréteur contenant les
paquets du workspace. `E2E_PORT` isole plusieurs piles. Les environnements WebKit
dépourvus de `AudioContext` ignorent explicitement les scénarios audio ; les
scénarios d'affichage continuent de s'exécuter.

Les comptes précis et limites de la dernière exécution sont dans
[DEVLOG](DEVLOG.md). La suite ne mesure pas la synchronisation acoustique.

## Essai manuel sur la vraie bibliothèque

Mettre à jour serveur, web et Bridge ensemble : protocole 2. Conserver une
sauvegarde du dossier `STATE_DIR` avant une mise à jour. Pour tester les crashes,
utiliser une soirée de test et un dossier de sauvegarde distinct.

1. **Préparation** : sélectionner un dossier et un sous-dossier, vérifier le
   compte sans doublon ; demander trop de manches, les réduire puis lancer avec
   « Enregistrer et lancer ». Vérifier la consigne et le barème côté joueurs.
2. **Invitation** : scanner le QR depuis un téléphone sur le même réseau et
   rejoindre avec le mot de passe communiqué. Le QR ne doit pas contenir ce secret.
3. **Participation** : former deux équipes et ajouter un spectateur. Vérifier
   qu'il entend le son, sans champ de réponse ni score et sans bloquer le départ.
4. **Réponse** : laisser finir l'extrait et vérifier le délai restant. Valider
   une réponse, garder un brouillon chez un autre joueur, puis faire une pause
   et une reprise. Vérifier son, saisie et délai sur plusieurs appareils.
5. **Revue** : vérifier le morceau courant chez l'hôte seulement ; corriger le
   titre/artiste. Saisir zéro et une valeur de plusieurs chiffres, puis sortir
   du champ. Vérifier l'accusé, le compteur et la confirmation des lignes
   non vérifiées. Vérifier aussi la règle « brouillons : zéro point ».
6. **Résultats** : contrôler réponses, points, corrections, équipes et totaux
   avec une feuille de score connue. Exporter JSON/CSV et rouvrir les fichiers.
7. **Nouvelle partie** : vérifier scores nuls et conservation des morceaux
   entendus. Épuiser un petit dossier : le message doit proposer une récupération.
8. **Reprise** : redémarrer le serveur pendant une réponse ; reconnecter les
   joueurs avec leurs cookies. La manche devient une revue signalée comme
   interrompue, avec réponses et brouillons récupérés. En Docker, vérifier
   aussi après recréation du conteneur en conservant `app_data`.
9. **Bibliothèque** : essayer un fichier silencieux, un morceau faible et un
   fichier corrompu. Vérifier les fichiers écartés dans les diagnostics hôte.
   Aucun audit préalable de toute la bibliothèque n'est annoncé.

## Appareils et mesures à réaliser

| Validation | Attendu | Statut |
|---|---|---|
| Safari réel sur iPhone/iPad | Déverrouillage, pause/reprise, arrière-plan, reconnexion, clavier | À faire |
| Chrome réel sur Android | Mêmes parcours, QR et absence d'ouverture automatique du clavier | À faire |
| AAC de production | Décodage et lecture avec les réglages Docker/natifs habituels | À faire |
| Réseau LAN/VPN et Bridge distant | Délais, reconnexions, erreurs et temps de préparation | À faire |
| Vraie bibliothèque | Temps de préparation, volume, silence, noms et taille des snapshots | À faire |
| G1 | Formats sur appareils réels, recette iOS, décalage acoustique p90 ≤ 60 ms sur 3 appareils hétérogènes ; [sync](sync.md) | `PENDING USER MEASUREMENT` |
| G2 | Préparation et upload p95 < 5 s sur vraie bibliothèque vers VPS, confinement des fichiers ; [architecture §26](architecture.md) | `PENDING USER MEASUREMENT` |

Les navigateurs headless, les captures et les tests Python ne remplacent aucune
de ces mesures.
