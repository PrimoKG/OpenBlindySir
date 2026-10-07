# Approuver le certificat HTTPS local

[English](local-certificate.en.md). Ce guide concerne une installation privée
**LAN** avec Caddy. Un certificat local chiffre la connexion, mais les téléphones
ne connaissent pas son autorité : l'avertissement ne signifie pas à lui seul que
l'application contient un logiciel malveillant. Ne désactivez pas la protection
HTTPS du navigateur et ne publiez pas les ports du LAN pour contourner l'avertissement.

## Vérifier et transmettre le bon fichier

Depuis le dossier du projet, l'hôte exécute :

```powershell
./tools/docker-host.ps1 -Action certificate
```

Sur macOS/Linux : `./tools/docker-host.sh certificate`.
Le lanceur exporte **uniquement** l'autorité publique `root.crt` dans
`.local/docker/root.crt` et affiche son empreinte SHA-256 de fichier.
En hébergement PC sans Docker, utiliser le certificat public indiqué par le
lanceur PC ; consulter [déploiement](deployment.md). Garder l'autorité d'origine :
une régénération oblige tous les participants à installer la nouvelle.

L'hôte remet ce fichier aux participants par un canal connu et confirme son
empreinte. Sur Windows, `Get-FileHash -Algorithm SHA256 ./root.crt` permet de
comparer la même empreinte de fichier. Un téléphone sans outil de vérification
peut recevoir directement le fichier de l'hôte en personne. **N'installez pas un
certificat reçu d'une source inconnue.** Une autorité installée peut faire confiance
à d'autres sites signés avec sa clé ; la clé doit rester privée.

Ne partagez jamais `root.key`, `intermediate.key`, les volumes Caddy, les fichiers
`.env`, les mots de passe ou les sauvegardes. Le fichier `root.crt` est public.

## Windows (Edge et Chrome)

1. Ouvrir `root.crt` et choisir **Installer le certificat**.
2. Choisir **Utilisateur actuel** puis **Placer tous les certificats dans le magasin suivant**.
3. Choisir **Autorités de certification racines de confiance**. Vérifier l'autorité
   indiquée et valider seulement celle transmise par l'hôte.
4. Fermer et rouvrir le navigateur, puis revenir à l'adresse LAN exacte fournie.

Firefox peut utiliser son propre magasin de certificats : Paramètres → Vie privée
et sécurité → Certificats → Afficher les certificats → Autorités → Importer.

## iPhone / iPad

1. Ouvrir `root.crt` reçu de l'hôte. Installer le profil dans Réglages → Général
   → VPN et gestion de l'appareil (ou **Profil téléchargé**).
2. Aller dans Réglages → Général → Informations → **Réglages de confiance des certificats**.
3. Activer la confiance complète pour cette autorité locale, puis rouvrir Safari.

L'installation du profil seule ne suffit pas toujours : Apple décrit cette étape
supplémentaire dans [son guide officiel](https://support.apple.com/fr-fr/102390).
Un appareil géré peut interdire ces actions ; son administrateur contrôle alors le réglage.

## Android

Dans Paramètres, chercher **Installer un certificat** : Sécurité et confidentialité
→ Autres paramètres de sécurité → Chiffrement et identifiants → Installer un
certificat → **Certificat d'autorité de certification / certificat CA**. Choisir
`root.crt`, confirmer l'autorité, puis rouvrir le navigateur. Les noms et restrictions
varient selon le fabricant et la version ; ne choisir ni certificat Wi-Fi ni VPN.
Une notification sur les certificats utilisateur est normale après cette installation.

## Après la soirée et dépannage

- Pour retirer la confiance : supprimer l'autorité du magasin Windows, le profil
  et la confiance sur iOS, ou le certificat utilisateur sur Android.
- L'adresse doit correspondre à `OBS_ADDRESS` et au certificat émis ; un changement
  d'IP peut nécessiter une mise à jour de la configuration et un redémarrage.
- Un certificat expiré, une mauvaise date système, une autre autorité ou un profil
  non approuvé provoquent encore une alerte. Vérifier la cause au lieu de cliquer
  systématiquement sur « continuer ».
- Le test audio nécessite HTTPS et un geste utilisateur. Utiliser **Tester mon audio**
  après une mise en veille ou un changement de périphérique.

Pour supprimer cette installation manuelle à l'avenir, utiliser un domaine contrôlé
et un certificat public reconnu. L'installation actuelle reste en LAN, sans cette migration.
