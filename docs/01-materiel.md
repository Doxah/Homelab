# 01 — Matériel

## En service
| Machine | Spécifications | OS / rôle |
|---|---|---|
| **Mini PC HP** | i5-12500T, 24 Go DDR4 | Debian + Docker en direct (pas de Proxmox). Hôte principal des services |
| **Dell PowerEdge T130** | Xeon E3-1240 v5 | Proxmox VE, conteneurs LXC |
| **Synology DS216J** | — | Données perso, sauvegardes |
| **QNAP TS-259 Pro+** | 4 To RAID1 | Médias Jellyfin (presque plein) |
| **QNAP TS-228** | 4 To RAID1 | Extension prévue pour Jellyfin |
| **Sophos XG 106w** sous **pfSense CE** | Atom E3930, 4 ports igb | Routeur/pare-feu, DNS, VPN |
| **D-Link DGS-1210-24P** | Switch PoE 24 ports manageable | Commutation, VLANs |
| Box FAI | — | Accès Internet |

## Retiré / non utilisé
| Machine | Raison |
|---|---|
| 2× Dell R710 (2× X5650, 96 Go chacun) | Trop énergivores (220–250 W au repos). Anciens nœuds d'un cluster Proxmox dissous |
| QNAP TS-231P2 (2 To RAID1) | Non utilisé actuellement |
| Pas de point d'accès Wi-Fi | La carte Wi-Fi du Sophos n'est pas prise en charge par pfSense |
