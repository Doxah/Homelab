# Documentation du homelab

Documentation publique. Les adresses IP, règles de pare-feu, configuration VPN et autres détails sensibles sont tenus à part, hors du dépôt.

| Fichier | Contenu |
|---|---|
| [01-materiel.md](01-materiel.md) | Machines en service et retirées |
| [02-reseau.md](02-reseau.md) | Architecture réseau et plan de simplification |
| [03-proxmox.md](03-proxmox.md) | Le nœud Proxmox (Dell T130) |
| [04-services.md](04-services.md) | Services par machine |
| [05-stockage-sauvegardes.md](05-stockage-sauvegardes.md) | NAS, sauvegardes, lacunes |
| [06-serveurs-de-jeu.md](06-serveurs-de-jeu.md) | Minecraft moddé, CS2 |
| [07-historique-incidents.md](07-historique-incidents.md) | Pannes passées et correctifs |
| [08-outils-depannage.md](08-outils-depannage.md) | Commandes et méthode de dépannage |
| [09-feuille-de-route.md](09-feuille-de-route.md) | Objectifs : simplification et apprentissage DevOps |
| [10-secrets.md](10-secrets.md) | Gestion des secrets avec SOPS + age |

## Principes
- Docker Compose plutôt que LXC (les LXC sont jugés opaques).
- Exposition par tunnels Cloudflare sortants plutôt que redirection de ports.
- Matériel économe : moins de serveurs, plus modernes.
- Dépannage : les causes simples d'abord.
