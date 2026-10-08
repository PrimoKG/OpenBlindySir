# Audit et corrections des soirées à thème — 8 octobre 2026

[English](2026-10-08-theme-autofix.en.md). Cette passe complète la
[livraison des thèmes](2026-10-08-themed-nights.md) et le
[précédent audit](2026-10-08-autofix.md).

## Problèmes reproduits et corrigés

| Cas | Effet observé | Correction |
|---|---|---|
| Références détectées dans un fichier | La recherche trouvait un titre ou artiste connu du cache, mais l’aperçu et le tirage excluaient le morceau. | Résolution commune dans la recherche, l’aperçu, la sélection et la reprise de queue. Les corrections explicites restent prioritaires et une suppression interdit le repli. Les références restent connues après éviction de l’audio. |
| Libellés longs | Les métadonnées acceptaient 256 caractères, les filtres seulement 128 ; un choix proposé pouvait produire une erreur. | Limite commune de 256 caractères Unicode, côté HTTP, protocole, saisie et presets. Tests des quatre catégories, y compris les emoji occupant deux unités UTF-16. |
| Tags et requêtes symboliques | Un tag uniquement composé d’emoji devenait une clé vide et pouvait correspondre à tous les morceaux. | Clé symbolique conservée ; les tags emoji restent distincts et une recherche purement symbolique cherche effectivement le symbole. |
| Presets non latins | Certains caractères de liaison et séquences emoji étaient acceptés par le serveur mais rejetés lors de la restauration locale. | Validation des contrôles interdits alignée, sans supprimer les caractères de liaison. Les surrogates isolés restent refusés dans le navigateur. |
| Année incomplète | La préparation envoyait un filtre invalide et affichait une erreur serveur générique. | Validation locale des années entières à quatre chiffres et de l’ordre. Pas de requête invalide ; message FR/EN précis et sauvegarde bloquée. |
| Aperçu après erreur réseau | Une erreur pouvait bloquer la préparation jusqu’à modification d’un filtre. | Bouton Réessayer, sans perte des critères ; annulation et protection contre les réponses anciennes conservées. |
| Tri des genres/langues | Les morceaux non classés pouvaient apparaître avant les catégories connues. | Inconnus placés à la fin dans les deux sens de tri. |
| Facettes d’un dossier | Des tags d’autres dossiers restaient proposés après restriction à un dossier. | Facettes calculées dans le dossier sélectionné. |
| Outil de test Docker | Une invocation sans argument utilisait l’installation réelle et pouvait créer des joueurs, modifier paramètres et scores. | Mode explicite obligatoire : `--profiles-only` valide sans contacter l’app ; `--allow-test-session-mutation` est réservé à une installation dédiée de test. La CI sur installation de démonstration l’active explicitement. Le fichier temporaire de profils contenant la configuration est protégé par les droits privés. |

Le snapshot remis au worker détache aussi les listes de filtres. Des régressions
vérifient qu’une révocation du rôle, un changement de phase ou de session pendant
le calcul refuse la réponse privée et libère le worker. Les accès anonymes,
joueurs ordinaires et mauvaises origines restent refusés.

## Compatibilité et installation réelle

Le protocole passe à **12**, serveur, Bridge et interface ensemble, avec types et
verrou de schéma régénérés. Le snapshot reste **9**, l’historique **2** et les
métadonnées **3**. Les anciens états sont toujours lus. Un retour au protocole 11
nécessite sa sauvegarde si de nouveaux libellés dépassent 128 caractères ; voir
[le guide de mise à jour](../themed-nights.md).

Sauvegarde native privée format 2 et toutes ses empreintes vérifiées avant
relance. Les conteneurs corrigés fonctionnent sur le LAN. Comparaison après
restauration : **300 morceaux, 211 génériques jouables, deux joueurs, 12 archives**,
scores, réponses, cookies, accès commun, métadonnées, paramètres, sources et
configuration du Bridge conservés. Montages musicaux en lecture seule et
certificat identiques ; HTTPS vérifié avec l’autorité locale. Aucun fichier
musical n’a été déplacé ou modifié. Aucune donnée privée n’entre dans Git ou le pack.

Pendant cette passe, l’ancienne invocation de l’outil Docker a effectivement créé
quatre sièges synthétiques et changé les paramètres de la partie terminée. Les
contrôles ont confirmé l’absence de changement des scores, réponses et archives.
Le snapshot sauvegardé a rétabli uniquement les deux joueurs réels et leurs
paramètres. Les snapshots primaire et secours ont ensuite été vérifiés. Les deux
régressions de l’outil empêchent une invocation implicite et tout contact avec
l’app en mode profils seuls. Les essais de jeu complets utilisent la pile isolée.

## Vérifications

- **1 196 tests Python généraux distincts réussis** : suite de 1 194, puis deux
  nouvelles régressions de garde de l’outil Docker (cinq tests de ce module rejoués),
  incluant FFmpeg, persistance, permissions,
  imports, restauration et sécurité. Deux contrôles POSIX/liens sautés sur Windows.
- **11 intégrations serveur/Bridge réussies** sur des fichiers synthétiques et
  ports isolés, soit **1 207 tests Python distincts réussis** au total.
- **55 tests Web réussis** ; TypeScript, build, Biome, Ruff, format, Pyright et schéma vérifiés.
- **12 parcours navigateur ciblés réussis**, Chromium et WebKit, FR et EN : thèmes
  combinés, transfert depuis la bibliothèque, reprise réseau, tags longs et années invalides.

Les profils Docker privé, public et Bridge individuel passent en mode sans mutation.
Les workflows CI couvrent aussi les installations CLI/native et les deux navigateurs.

## Sécurité des images

Scan local Grype épinglé sur les identités immuables des images livrées, avec base
**v6.1.10 du 7 octobre 2026, 06:31:48 UTC**. Un premier scan a utilisé une base
locale du 5 octobre ; il a été remplacé par ce scan avec la base la plus récente
déjà téléchargée. Aucun inventaire n’a été transmis et aucun volume n’a été monté.

| Image / composant | Critiques | Élevées | Moyennes | Faibles |
|---|---:|---:|---:|---:|
| Application | 0 | 55 | 50 | 10 |
| Bridge | 0 | 55 | 50 | 10 |
| Caddy | 0 | 8 | 14 | 8 |
| FFmpeg 9.0.2 compilé, source et image vérifiées | 0 | 0 | 0 | 0 |

Ces alertes élevées ne proposent aucun correctif dans cette base : 51 `wont-fix`
et quatre `not-fixed` par image Python, huit `unknown` pour Caddy. Elles ne sont
pas déclarées faux positifs ni résolues. Les deux alertes Python moyennes déjà
documentées proposent Python 3.15/alpha, hors de la plage 3.12–3.14 validée du
projet ; elles restent ouvertes. Aucun changement de dépendance Python/npm dans
cette passe. L’absence de correspondance FFmpeg ne prouve pas l’absence de faille.

Images vérifiées : application
`sha256:f7298b53656043fcebf3a53007f22b739adf8774d721f9052bab2f69560a292a`,
Bridge `sha256:1205454fd33a2babe93007bfb87a2d287d39adf96fcce9cc16efa5392e12b0f8`,
Caddy `sha256:b2877ff4fb23df45e83eb48e5dad0756b72b74468222f4cea6a1afc412506193`.

## Limites

Les téléphones physiques, l’écoute acoustique et l’installation sur machine vierge
restent des vérifications manuelles. Les métadonnées inconnues ne sont pas inventées.
Le bundle JavaScript de production est encore supérieur à 500 Kio : son découpage
est un axe de performance, sans régression bloquante confirmée dans cette passe.
Les alertes des images de base restent à examiner ; ce candidat local non signé
ne constitue pas une validation publique sans réserve. Aucun inventaire n’est
transmis à Docker Scout ; les scans utilisent uniquement des exports d’images,
sans réseau, socket Docker, volumes ou fichiers musicaux.

Preuves privées : `.local/theme-autofix-20261008/`, journaux
`.local/theme-autofix-*.log`, sauvegarde privée avant relance.
