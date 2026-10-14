# Serveur MCP GLPI

[mcp-glpi](https://github.com/GMS64260/mcp-glpi) (MIT) : expose GLPI à Claude (tickets, ITIL, parc, base de connaissances, stats).
Serveur **stdio** lancé par Claude Desktop sur le poste Windows, via l'API REST v1 (`apirest.php`) de GLPI.

- Version figée : **3.2.0** (dernière publiée sur npm ; la 3.3.0 n'existe que sur GitHub).
- Revue : le code ne contacte que `GLPI_URL`, n'exécute aucune commande. Le paquet npm 3.2.0 est identique au source GitHub compilé.
- 84 outils dont des écritures et suppressions : les droits réels sont ceux du **compte GLPI** utilisé, d'où un compte dédié.

## 1. Côté GLPI
1. Configuration > Générale > **API** :
   - activer l'API REST ;
   - activer « connexion avec un jeton externe » ;
   - désactiver « connexion avec les identifiants » (pas de mot de passe dans le MCP).
2. Même onglet, **clients de l'API** : créer un client `claude-mcp`, actif, avec un **jeton d'application** (app token).
   Plage IP : GLPI voit l'IP du reverse proxy (npmplus), pas celle du PC. Mettre l'IP de npmplus (dans `private/`).
3. Créer un utilisateur dédié `svc-claude` avec un profil **Technicien** (pas Super-Admin), sur l'entité voulue.
4. Préférences de `svc-claude` > **Clé d'accès distant** : générer le jeton utilisateur.

## 2. Secrets (`secrets.sops.env`, chiffré)
Le fichier est déjà dans le dépôt, avec les variables en commentaire : `sops mcp/glpi/secrets.sops.env`, décommenter et remplir.
```dotenv
GLPI_URL=https://glpi.<domaine>
GLPI_APP_TOKEN=...
GLPI_USER_TOKEN=...
```
Pas de guillemets autour des valeurs.

## 3. Claude Desktop
Prérequis sur le PC : Node.js ≥ 18 (`winget install OpenJS.NodeJS.LTS`), sops et la clé age (voir `docs/10-secrets.md`).

Dans `%APPDATA%\Claude\claude_desktop_config.json` :
```json
{
  "mcpServers": {
    "glpi": {
      "command": "powershell.exe",
      "args": ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", "D:\\homelab\\scripts\\mcp-glpi.ps1"]
    }
  }
}
```
Redémarrer Claude Desktop. Dans les réglages des connecteurs, laisser les outils d'écriture/suppression en « demander ».

## Test
```powershell
$env:GLPI_URL="https://glpi.<domaine>"   # ou via sops exec-env
sops -d mcp/glpi/secrets.sops.env               # vérifier le déchiffrement
# Test API sans le MCP :
curl.exe -s -H "App-Token: <app>" -H "Authorization: user_token <user>" https://glpi.<domaine>/apirest.php/initSession
```
Réponse attendue : `{"session_token":"..."}`. Erreurs fréquentes : `ERROR_APP_TOKEN_PARAMETERS_MISSING` (app token), `ERROR_NOT_ALLOWED_IP` (plage IP du client API).
