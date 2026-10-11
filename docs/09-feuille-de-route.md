# 09 — Feuille de route

## Objectifs de fond
- **Réduire la consommation électrique** avec du matériel moderne et économe (R710 retirés, Mini PC ajouté).
- **Simplifier le réseau** : moins de VLANs, plus de règles de pare-feu (voir [02-reseau.md](02-reseau.md)).
- **Apprendre le DevOps** en transformant ce homelab en infrastructure as code.

## Chantiers en cours
- Supprimer les serveurs CS2 de test et les CT inutiles du T130.
- Mettre en place les sauvegardes (CT Proxmox, configs et volumes Docker).
- Réinstaller Immich sur le Mini PC.
- Jellyfin : mettre en service le second QNAP.
- Stabiliser Arcane.

## Parcours DevOps
Chaque étape s'appuie sur la précédente.

| # | Objectif | Terminé quand |
|---|---|---|
| 1 | Assainir et versionner le homelab | Ce dépôt décrit tout ce qui tourne, une restauration a été testée |
| 2 | Git, conteneurs et secrets (SOPS + age, pre-commit, Renovate) | Aucun secret en clair, Renovate ouvre des PR |
| 3 | Conteneurs au moindre privilège (non-root, cap_drop, lecture seule, socket Docker protégé, Docker rootless) | Aucun conteneur en root ou privileged sans exception documentée, démon Docker sans root |
| 4 | Ansible | Une VM Debian vierge devient un clone du Mini PC en une commande |
| 5 | Terraform / OpenTofu (Proxmox + Cloudflare) | Les VMs du lab se recréent sans clic dans Proxmox |
| 6 | CI/CD | Un commit sur le site web arrive en production sans commande manuelle |
| 7 | Bases de Kubernetes (cluster local k3d) | Déployer une appli avec stockage, ingress et config sans tutoriel |
| 8 | Cluster K3s du homelab (3 nœuds sur le T130) | Le site web tourne sur K3s avec un certificat valide |
| 9 | GitOps (Flux ou Argo CD) | Un merge dans Git est la seule façon de changer le cluster |
| 10 | Observabilité (Prometheus, Grafana, Loki) | Être prévenu d'un problème avant de le constater |
| 11 | DevSecOps (Trivy, Kyverno, NetworkPolicies, Falco) | Une image vulnérable est refusée avant le cluster |
| 12 | Tout reconstruire depuis le dépôt | Le homelab complet se reconstruit en moins d'une heure |
