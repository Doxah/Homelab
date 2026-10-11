# 08 — Outils et commandes de dépannage

Méthode : **causes simples d'abord** (disque plein, service arrêté, option cochée/décochée, DNS) avant les hypothèses complexes. Voir aussi [07-historique-incidents.md](07-historique-incidents.md).

## Réflexes généraux
```bash
df -h ; df -i                      # disque plein : cause de la panne NPM
free -h ; uptime ; htop
systemctl status <service> ; journalctl -u <service> -n 100 --no-pager
docker ps -a ; docker logs --tail 100 <conteneur> ; docker compose ps
ss -tlnp                           # ports en écoute
dig <nom> @<dns> ; curl -vk https://<url>
```

## Proxmox
| Problème | Outils / commandes |
|---|---|
| Inventaire VM/CT | `pct list`, `qm list`, `pvesm status`, `pvesh get /nodes` |
| Entrer dans un CT | `pct enter <id>`, `pct config <id>`, `pct set <id> -mp0 ...` |
| Quorum / cluster | `pvecm status`, `pvecm nodes`, `pvecm expected 1` (temporaire), puis dissolution : `systemctl stop pve-cluster corosync`, `pmxcfs -l`, suppression de `/etc/pve/corosync.conf` et `/etc/corosync/*`, nettoyage de `/etc/pve/nodes/<ancien-noeud>` |
| UI qui affiche les balises HTML | `apt install --reinstall proxmox-widget-toolkit`, vider le cache navigateur |

## Jellyfin
| Problème | Outils / commandes |
|---|---|
| Chemins codés en dur après migration | `grep -rn "/config\|/media" /etc/jellyfin /var/lib/jellyfin`, `sed -i` sur `system.xml` |
| Propriétaires | `chown -R jellyfin:jellyfin /var/lib/jellyfin /etc/jellyfin /var/cache/jellyfin` |
| Stockage NFS | `mount \| grep nfs`, `df -h <point>`, `showmount -e <nas>` |
| Fond noir pages détail | Côté client : Paramètres → Affichage → « Arrière-plans » |

## Reverse proxy (Nginx Proxy Manager / npmplus)
| Problème | Outils / commandes |
|---|---|
| Service « down » mais backend OK | `curl -I http://<backend>:<port>` puis `curl -vk https://<fqdn>` : isole la couche proxy/TLS |
| NPM cassé après disque plein | Nettoyage ; suppression du cache node ; `useradd --system npm` ; `systemctl edit npm` → `Environment=CERTBOT_VERSION=<version>` ; `systemctl daemon-reload && systemctl restart npm openresty` |
| Certificats | `openssl s_client -connect <fqdn>:443 -servername <fqdn>` |

## Cloudflare
| Problème | Outils |
|---|---|
| Tunnel | `docker logs cloudflared`, `cloudflared tunnel info <nom>`, dashboard Zero Trust → Networks → Tunnels |
| Filtrage | Security → WAF (règles custom, géo-restriction), Security Events, Access → Applications/Policies |
| `SSL_ERROR_BAD_CERT_DOMAIN` | `openssl s_client ... -showcerts` depuis le poste : émetteur inattendu → logiciel d'inspection SSL local |

## Pare-feu Docker
Docker contourne UFW en écrivant ses propres règles iptables : filtrer dans la chaîne `DOCKER-USER`.
```bash
ufw status verbose
iptables -L DOCKER-USER -n -v --line-numbers
ufw-docker install ; ufw-docker allow <conteneur> <port>
nmap -Pn <ip-publique>        # vérifier depuis l'extérieur ce qui est exposé
```

## pfSense
| Besoin | Où |
|---|---|
| IP réelle d'une machine | Status → DHCP Leases, Diagnostics → ARP Table |
| Flux bloqué | Status → System Logs → Firewall, Diagnostics → Packet Capture |
| VLANs | Interfaces → Assignments → VLANs |
| DNS internes | Services → DNS Resolver → Host Overrides |

Piège : le nom interne `wan` peut ne pas correspondre au vrai WAN si les interfaces ont été réassignées. Vérifier dans Interfaces → Assignments avant de lire les URLs `firewall_rules.php?if=...`.

## Docker (Mini PC)
```bash
docker compose -f <chemin>/compose.yaml up -d / logs -f / ps
docker system df ; docker system prune
```

## Sauvegardes
| Sujet | Commandes |
|---|---|
| rsync vers Synology | `rsync -a --no-perms --no-owner --no-group <src> rsync://<nas>/<module>`, planifié en cron ou timer systemd |
| MySQL PITR | `log_bin` activé, `mysqldump --single-transaction --flush-logs --source-data=2` nocturne ; restauration : `mysql < dump.sql` puis `mysqlbinlog --stop-datetime=... binlog.* \| mysql` |

## Serveurs de jeu
| Problème | Outils |
|---|---|
| Crash Minecraft NeoForge | `docker logs`, `crash-reports/*.txt`, `logs/latest.log` → erreurs *Mixin* pour identifier le mod ; retrait par dichotomie |
| Scintillement client | Vérifier la VSync en premier |
