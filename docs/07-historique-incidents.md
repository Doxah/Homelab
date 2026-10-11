# 07 — Historique des incidents

Pannes déjà rencontrées, utiles pour orienter un diagnostic. Certaines concernent des composants remplacés depuis (indiqué).

| Sujet | Symptôme | Cause | Correctif |
|---|---|---|---|
| Jellyfin inaccessible | Service KO de l'extérieur | Couche reverse proxy / TLS, pas Jellyfin | Réparation du proxy |
| NPM cassé *(remplacé depuis par npmplus)* | NPM ne démarre plus | **Disque plein** → cache node corrompu, utilisateur `npm` manquant, `CERTBOT_VERSION` absente | Nettoyage, recréation de l'utilisateur, drop-in systemd `CERTBOT_VERSION` |
| Migration Jellyfin Docker → LXC *(Jellyfin revenu depuis en Docker)* | Chemins invalides | Chemins en dur dans `system.xml`, propriétaires | Réécriture des chemins, `chown` |
| Cluster Proxmox *(dissous)* | Perte de quorum récurrente | Nœud hors ligne | Cluster dissous |
| UI Proxmox | Balises HTML affichées en texte | Régression `proxmox-widget-toolkit` | Mise à jour / réinstallation |
| Sauvegarde Vaultwarden | Erreurs `chgrp` rsync | Permissions côté Synology | `--no-perms --no-owner --no-group` |
| Certificat | `SSL_ERROR_BAD_CERT_DOMAIN` | Inspection SSL sur le poste client | Côté client |
| Jellyfin UI | Fond noir sur les pages détail | Option client « Arrière-plans » décochée | Réactiver l'option |
| Minecraft | Crash au démarrage | Conflits mixin (Sable) | Retrait du mod |
| Arcane | Problèmes d'utilisation | À préciser | Contournement en CLI |

## Leçons
- Un disque plein casse les services de façon déroutante : toujours vérifier `df -h` en premier.
- Quand un service « tombe » derrière un proxy, tester le backend en direct avant d'accuser le service.
- Un cluster Proxmox à nœuds intermittents perd le quorum : mieux vaut un nœud seul qu'un cluster bancal.
