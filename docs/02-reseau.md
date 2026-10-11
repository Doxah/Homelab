# 02 — Réseau

## Topologie
```
Internet ── Box FAI (NAT #1)
              │
          pfSense (NAT #2, résolveur DNS Unbound, OpenVPN)
          ├─ LAN ............ poste d'administration
          └─ DATACENTER ..... switch D-Link (trunk VLANs)
               ├─ réseau serveurs (Mini PC)
               ├─ VLAN management (Proxmox, administration des NAS)
               ├─ VLAN DMZ (reverse proxy)
               └─ VLAN NAS
```

- Double NAT (box FAI puis pfSense).
- pfSense est le serveur DNS du réseau : les noms internes pointent vers le reverse proxy.
- Les services exposés sur Internet passent par des **tunnels Cloudflare** sortants, pas par des redirections de ports.
- Un reverse proxy interne (**npmplus**) gère les certificats Let's Encrypt.

## Constat
Le découpage a grossi au fil des tests : plusieurs VLANs ne servent plus (anciens labs VM, IoT, Kubernetes) et le filtrage entre réseaux est quasi inexistant.

## Cible
- **Moins de VLANs, plus de règles** : ne garder que les réseaux utilisés (admin, serveurs, management, DMZ, NAS), plus un réseau **LAB** pour le futur cluster K3s.
- Politique par défaut : chaque réseau n'accède qu'au DNS/NTP de pfSense, à ses flux internes nommés et à Internet. Tout le reste vers les réseaux privés est bloqué.
- Seuls le poste d'administration et le VPN admin peuvent administrer l'ensemble.
- La DMZ ne joint que les backends qu'elle publie.
- Nettoyer les redirections de ports et les noms DNS internes hérités d'anciens tests.
