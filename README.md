# Homelab

Homelab personnel de Doxah : documentation, et à terme toute l'infrastructure en code (Ansible, Terraform/OpenTofu, Kubernetes/K3s, GitOps).

Ce dépôt est aussi mon support d'apprentissage DevOps : l'objectif est de pouvoir reconstruire tout le homelab depuis ce dépôt.

## Contenu

| Dossier | Contenu |
|---|---|
| [`docs/`](docs/) | Documentation publique : matériel, services, choix d'architecture, incidents et feuille de route |
| `ansible/` | Playbooks et rôles (à venir) |
| `terraform/` | Provisionnement Proxmox et Cloudflare (à venir) |
| `compose/` | Stacks Docker Compose du Mini PC, secrets chiffrés avec SOPS ([modèle](compose/_modele/)) |
| `scripts/` | Scripts utilitaires (lancement des stacks avec leurs secrets) |
| `k8s/` | Manifests et config GitOps du futur cluster K3s (à venir) |

## Vue d'ensemble

- **Mini PC HP** (i5-12500T, 24 Go) : Debian + Docker, hôte principal des services.
- **Dell PowerEdge T130** : Proxmox VE, futur hôte des VMs du cluster K3s.
- **3 NAS** (Synology + 2 QNAP) : données, médias, sauvegardes.
- **pfSense** sur une appliance Sophos XG 106w, switch PoE manageable D-Link.
- Exposition des services par **tunnels Cloudflare** (pas d'ouverture de port).
