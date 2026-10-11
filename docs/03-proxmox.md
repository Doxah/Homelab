# 03 — Proxmox (Dell T130)

Seul hôte Proxmox VE restant. Le Mini PC tourne en Debian + Docker direct.

## Conteneurs LXC
| Contenu | Statut |
|---|---|
| **Vaultwarden** | Actif |
| **npmplus** — reverse proxy principal (a remplacé Nginx Proxy Manager) | Actif |
| DiscoPanel | Plus utilisé, à supprimer |
| cloudflared | Plus utilisé (les tunnels tournent sur le Mini PC), à supprimer |
| AdGuard | Rôle à confirmer |
| Ancien Jellyfin (CT 135) | Inutile, à supprimer (Jellyfin est en Docker sur le Mini PC) |

## Historique
- Ancien cluster de 3 nœuds dissous à cause de pertes de quorum récurrentes ; les R710 sont retirés.
- Régression `proxmox-widget-toolkit` (HTML affiché en texte) corrigée.

## Sauvegardes
- **Aucune sauvegarde des CT pour l'instant** (à mettre en place : Proxmox Backup Server ou vzdump vers un NAS). Vaultwarden a sa propre sauvegarde rsync.

## Rôle futur
Le T130 deviendra l'hôte des VMs du cluster K3s, créées avec Terraform/OpenTofu (voir [09-feuille-de-route.md](09-feuille-de-route.md)).

## Commandes d'inventaire
```bash
pct list ; qm list ; pvesm status
pct config <id>
```
