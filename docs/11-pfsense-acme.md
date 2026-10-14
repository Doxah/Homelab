# 11 — Certificat Let's Encrypt pour pfSense (ACME + Cloudflare)

Certificat Let's Encrypt valide pour le webGUI de pfSense (`pfsense.<domaine>`). Il est obtenu avec le paquet **ACME** et validé par **DNS-01 via l'API Cloudflare**.

- Le pfSense n'a pas besoin d'être joignable depuis Internet : la validation passe uniquement par un enregistrement TXT temporaire.
- Aucun enregistrement A public n'est nécessaire : le nom est résolu en interne par Unbound.
- L'authentification Cloudflare se fait par **API Token**, limité à une zone. La Global API Key utilisée dans les anciens tutos n'est pas utilisée.

## Prérequis
- Domaine `<domaine>` géré par Cloudflare.
- Paquet **acme** installé : System → Package Manager → Available Packages.
- Host Override dans Services → DNS Resolver : `pfsense.<domaine>` → IP LAN du pfSense.

## 1. Côté Cloudflare

### API Token
My Profile → API Tokens → **Create Token** → modèle *Edit zone DNS* :

| Paramètre | Valeur |
|---|---|
| Permissions | `Zone → DNS → Edit` **et** `Zone → Zone → Read` |
| Zone Resources | `Include → Specific zone → <domaine>` |
| Client IP Address Filtering | Optionnel : IP WAN publique |

Le token ne s'affiche qu'une fois : il est conservé hors du dépôt.

### Zone ID
Account Home → `<domaine>` → **Overview** → colonne de droite, section **API** → *Zone ID*.
C'est le Zone ID du domaine, pas celui d'un sous-domaine : un sous-domaine n'a pas de zone propre.

## 2. Côté pfSense

### Clé de compte ACME
Services → Acme Certificates → **Account keys** → Add :

| Champ | Valeur |
|---|---|
| Name | `Cloudflare Token` |
| ACME Server | Let's Encrypt Production ACME v2 |
| E-Mail Address | adresse de contact (avis d'expiration) |
| Account key | **Create new account key**, puis **Register ACME account key** |

### Certificat
Services → Acme Certificates → **Certificates** → Add :

| Champ | Valeur |
|---|---|
| Name | `pfsense.<domaine>` |
| Status | Active |
| Acme Account | `Cloudflare Token` |

**Validation → SAN list**, une seule ligne :

| Champ | Valeur |
|---|---|
| SAN | `pfsense.<domaine>` |
| Validation Method | DNS-Cloudflare |
| Token | l'API Token |
| Token Zone ID | le Zone ID de `<domaine>` |
| Token Account ID | vide (sert seulement pour les certificats multi-zones) |
| Global Key / Global Email | **vides** (mode Global API Key, non utilisé) |
| DNS alias mode | vide / décoché |

**Actions list** : ajouter une action *Shell Command* `/etc/rc.restart_webgui` pour que le webGUI recharge le certificat après chaque renouvellement.

Enregistrer, puis cliquer sur **Issue/Renew**. Résultat attendu dans le log :
```
Renewing certificate: pfsense.<domaine>
account: Cloudflare Token
server: letsencrypt-production-2
Certificate issued successfully.
```

### Utilisation par le webGUI
System → Advanced → Admin Access → **SSL/TLS Certificate** → sélectionner le certificat ACME → Save.

### Renouvellement automatique
Services → Acme Certificates → **General settings** → cocher **Cron Entry**.
Le renouvellement a lieu par défaut 60 jours après l'émission (champ *Certificate renewal after*).

## Dépannage

| Symptôme | Piste |
|---|---|
| `invalid domain`, `Error adding TXT record` | Permissions du token (DNS Edit + Zone Read) ou Zone ID erroné |
| Ancien certificat toujours présenté | Action `/etc/rc.restart_webgui` absente : redémarrer le webGUI à la main |
| Erreur de nom dans le navigateur | Accès par IP au lieu du FQDN, ou Host Override manquant |
| Vérification | `openssl s_client -connect pfsense.<domaine>:443 -servername pfsense.<domaine>` |
| Alerte « error uploading … acb.netgate.com (35) » juste après | Sans rapport avec le certificat : l'AutoConfigBackup est déclenché à chaque changement de config. Relancer Services → Auto Config Backup → **Backup now** |
