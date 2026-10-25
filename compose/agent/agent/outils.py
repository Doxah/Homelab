#!/usr/bin/env python3
"""Outils de l'agent : les SEULES commandes que Claude peut lancer (voir consignes/settings.json).

Chaque outil est un lien symbolique vers ce fichier ; le nom appelé choisit la commande.
Lecture seule (API Docker filtrée par socket-proxy-agent, Loki, Prometheus), sauf « action » qui DÉPOSE une demande
exécutée par l'hôte (scripts/agent-actions.sh) après contrôle de la liste blanche.

  conteneurs                                        état de tous les conteneurs (arrêtés compris)
  conteneur <nom>                                   détail d'un conteneur (variables d'environnement masquées)
  journaux <nom> [--depuis 1h] [--lignes 150] [--filtre REGEX]
  evenements [--depuis 2h] [--conteneur nom]        événements Docker (die, oom, health_status, restart…)
  loki '<LogQL>' [--depuis 1h] [--limite 100]       journaux / métriques LogQL ; loki --valeurs container
  prom '<PromQL>' [--depuis 6h --pas 5m]            requête Prometheus instantanée, ou sur une période
  hote                                              synthèse de l'hôte : disques, mémoire, charge, alertes, redémarrages
  historique [chemin] [--diff]                      derniers commits du dépôt (Renovate, déploiements…)
  action <stack> <restart|up> [service] --raison "…"   ;   action --liste
"""
import subprocess
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DOCKER = os.environ.get("DOCKER_API", "http://socket-proxy-agent:2375").rstrip("/")
LOKI = os.environ.get("LOKI_URL", "http://loki:3100").rstrip("/")
PROM = os.environ.get("PROM_URL", "http://prometheus:9090").rstrip("/")
ACTIONS = Path(os.environ.get("DOSSIER_ACTIONS", "/actions"))
DEPOT = Path(os.environ.get("DOSSIER_DEPOT", "/data/depot"))
ATTENTE_ACTION_S = int(os.environ.get("ACTION_ATTENTE_S", "180"))
MAX_ACTIONS = int(os.environ.get("MAX_ACTIONS_PAR_DIAGNOSTIC", "3"))
LONGUEUR_LIGNE = 600
NOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


def erreur(message):
    print(f"ERREUR : {message}", file=sys.stderr)
    sys.exit(1)


def get(url, delai=20, brut=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=delai) as r:
            donnees = r.read()
    except urllib.error.HTTPError as e:
        corps = e.read().decode(errors="replace")[:300]
        erreur(f"HTTP {e.code} sur {url.split('?')[0]} : {corps}")
    except (urllib.error.URLError, TimeoutError) as e:
        erreur(f"{url.split('?')[0]} injoignable : {e}")
    return donnees if brut else json.loads(donnees or b"null")


def duree_s(texte):
    m = re.fullmatch(r"(\d+)([smhd])", texte or "")
    if not m:
        erreur(f"durée invalide « {texte} » (exemples : 30m, 2h, 1d)")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def tronquer(ligne):
    ligne = ligne.rstrip("\n")
    return ligne if len(ligne) <= LONGUEUR_LIGNE else ligne[:LONGUEUR_LIGNE] + " […]"


def heure(ts):
    return datetime.fromtimestamp(ts).strftime("%F %T")


# --------------------------------------------------------------------------------------------- Docker

def cmd_conteneurs(args):
    argparse.ArgumentParser(prog="conteneurs", description="tous les conteneurs, arrêtés compris").parse_args(args)
    liste = get(f"{DOCKER}/containers/json?all=1") or []
    liste.sort(key=lambda c: (c.get("Labels", {}).get("com.docker.compose.project", ""), c["Names"][0]))
    print(f"{'STACK':<14} {'CONTENEUR':<28} {'ÉTAT':<9} {'STATUT':<32} IMAGE")
    for c in liste:
        print(f"{c.get('Labels', {}).get('com.docker.compose.project', '-'):<14} {c['Names'][0].lstrip('/'):<28} "
              f"{c.get('State', ''):<9} {c.get('Status', ''):<32} {c.get('Image', '')}")


def cmd_conteneur(args):
    if len(args) != 1 or not NOM.match(args[0]):
        erreur("usage : conteneur <nom>")
    c = get(f"{DOCKER}/containers/{args[0]}/json")
    etat, cfg, hote = c.get("State", {}), c.get("Config", {}), c.get("HostConfig", {})
    sante = etat.get("Health") or {}
    labels = cfg.get("Labels") or {}
    resume = {
        "nom": c.get("Name", "").lstrip("/"),
        "image": cfg.get("Image"),
        "cree": c.get("Created"),
        "etat": {k: etat.get(k) for k in ("Status", "Running", "Restarting", "OOMKilled", "Dead", "ExitCode",
                                          "Error", "StartedAt", "FinishedAt")},
        "redemarrages": c.get("RestartCount"),
        "politique_redemarrage": (hote.get("RestartPolicy") or {}).get("Name"),
        "sante": {"statut": sante.get("Status"), "echecs_consecutifs": sante.get("FailingStreak"),
                  "derniers_tests": [{"debut": h.get("Start"), "code": h.get("ExitCode"),
                                      "sortie": tronquer(h.get("Output", ""))} for h in (sante.get("Log") or [])[-3:]]},
        "healthcheck": (cfg.get("Healthcheck") or {}).get("Test"),
        "utilisateur": cfg.get("User") or "root (non défini)",
        "commande": cfg.get("Cmd"), "entrypoint": cfg.get("Entrypoint"),
        "environnement": sorted(v.split("=", 1)[0] + "=<masqué>" for v in cfg.get("Env") or []),
        "ressources": {"memoire_max_octets": hote.get("Memory"), "cpus": (hote.get("NanoCpus") or 0) / 1e9,
                       "pids_max": hote.get("PidsLimit"), "lecture_seule": hote.get("ReadonlyRootfs"),
                       "cap_drop": hote.get("CapDrop"), "cap_add": hote.get("CapAdd"),
                       "security_opt": hote.get("SecurityOpt")},
        "montages": [f"{m.get('Source')} -> {m.get('Destination')} ({'rw' if m.get('RW') else 'ro'}, {m.get('Type')})"
                     for m in c.get("Mounts", [])],
        "reseaux": sorted((c.get("NetworkSettings") or {}).get("Networks", {}).keys()),
        "ports": hote.get("PortBindings"),
        "compose": {k.split(".")[-1]: v for k, v in labels.items() if k.startswith("com.docker.compose.")
                    and k.split(".")[-1] in ("project", "service", "working_dir", "config_files", "depends_on")},
        "labels_traefik": sorted(k for k in labels if k.startswith("traefik.")),
    }
    print(json.dumps(resume, ensure_ascii=False, indent=1))


def demultiplexer(donnees):
    """Flux de journaux Docker sans TTY : trames [flux, 0, 0, 0, taille sur 4 octets] + contenu."""
    sortie, i = [], 0
    while i + 8 <= len(donnees):
        flux, taille = donnees[i], int.from_bytes(donnees[i + 4:i + 8], "big")
        if flux not in (0, 1, 2):
            return donnees.decode(errors="replace")      # pas multiplexé (conteneur avec TTY)
        morceau = donnees[i + 8:i + 8 + taille].decode(errors="replace")
        sortie.append(("ERR " if flux == 2 else "") + morceau)
        i += 8 + taille
    return "".join(sortie)


def cmd_journaux(args):
    p = argparse.ArgumentParser(prog="journaux")
    p.add_argument("nom")
    p.add_argument("--depuis", default="1h")
    p.add_argument("--lignes", type=int, default=150)
    p.add_argument("--filtre", help="expression régulière (insensible à la casse)")
    a = p.parse_args(args)
    if not NOM.match(a.nom):
        erreur("nom de conteneur invalide")
    lignes = max(1, min(a.lignes, 1000))
    depuis = int(time.time()) - duree_s(a.depuis)
    # Avec un filtre, on lit plus large puis on filtre ici
    queue = lignes if not a.filtre else 5000
    brut = get(f"{DOCKER}/containers/{a.nom}/logs?stdout=1&stderr=1&timestamps=1&since={depuis}&tail={queue}",
               delai=30, brut=True)
    texte = demultiplexer(brut).splitlines()
    if a.filtre:
        motif = re.compile(a.filtre, re.I)
        texte = [l for l in texte if motif.search(l)]
    texte = texte[-lignes:]
    if not texte:
        print(f"(aucune ligne depuis {a.depuis}{' correspondant au filtre' if a.filtre else ''})")
    for l in texte:
        print(tronquer(l))


def cmd_evenements(args):
    p = argparse.ArgumentParser(prog="evenements")
    p.add_argument("--depuis", default="2h")
    p.add_argument("--conteneur")
    a = p.parse_args(args)
    filtres = {"type": ["container"]}
    if a.conteneur:
        if not NOM.match(a.conteneur):
            erreur("nom de conteneur invalide")
        filtres["container"] = [a.conteneur]
    fin = int(time.time())
    url = (f"{DOCKER}/events?since={fin - duree_s(a.depuis)}&until={fin}"
           f"&filters={urllib.parse.quote(json.dumps(filtres))}")
    brut = get(url, delai=30, brut=True).decode(errors="replace")
    ignores = {"exec_create", "exec_start", "exec_die", "attach", "resize", "top", "archive-path"}
    n = 0
    for ligne in brut.splitlines():
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        action = e.get("Action") or e.get("status", "")
        if action.split(":")[0] in ignores:
            continue
        attr = (e.get("Actor") or {}).get("Attributes", {})
        details = " ".join(f"{k}={attr[k]}" for k in ("exitCode", "signal", "image") if k in attr)
        print(f"{heure(e.get('time', 0))}  {attr.get('name', '?'):<26} {action:<30} {details}")
        n += 1
    if not n:
        print(f"(aucun événement depuis {a.depuis})")


# --------------------------------------------------------------------------------------------- Loki / Prometheus

def cmd_loki(args):
    p = argparse.ArgumentParser(prog="loki")
    p.add_argument("requete", nargs="?")
    p.add_argument("--depuis", default="1h")
    p.add_argument("--limite", type=int, default=100)
    p.add_argument("--valeurs", metavar="LABEL", help="liste les valeurs d'un label (ex. container, level)")
    a = p.parse_args(args)
    fin = time.time()
    debut = fin - duree_s(a.depuis)
    if a.valeurs:
        if not re.fullmatch(r"[a-z_]+", a.valeurs):
            erreur("label invalide")
        r = get(f"{LOKI}/loki/api/v1/label/{a.valeurs}/values?start={int(debut * 1e9)}&end={int(fin * 1e9)}")
        print("\n".join(r.get("data", [])))
        return
    if not a.requete:
        erreur("usage : loki '<LogQL>' [--depuis 1h] [--limite 100]")
    params = urllib.parse.urlencode({"query": a.requete, "start": int(debut * 1e9), "end": int(fin * 1e9),
                                     "limit": max(1, min(a.limite, 1000)), "direction": "backward"})
    r = get(f"{LOKI}/loki/api/v1/query_range?{params}", delai=60).get("data", {})
    if r.get("resultType") == "streams":
        lignes = []
        for flux in r.get("result", []):
            conteneur = flux["stream"].get("container", "?")
            niveau = flux["stream"].get("level", "")
            for ts, l in flux["values"]:
                lignes.append((int(ts), f"{heure(int(ts) / 1e9)} [{conteneur}{'|' + niveau if niveau else ''}] {tronquer(l)}"))
        for _, l in sorted(lignes):
            print(l)
        if not lignes:
            print("(aucune ligne)")
    else:   # matrix : requête métrique (count_over_time, rate…)
        for serie in r.get("result", []):
            valeurs = serie.get("values", [])
            total = sum(float(v) for _, v in valeurs)
            dernier = valeurs[-1][1] if valeurs else "?"
            print(f"{json.dumps(serie.get('metric', {}), ensure_ascii=False)}  dernière={dernier}  somme={total:g}")
        if not r.get("result"):
            print("(aucune série)")


def prom_requete(requete, depuis=None, pas="5m"):
    if depuis:
        fin = time.time()
        params = urllib.parse.urlencode({"query": requete, "start": fin - duree_s(depuis), "end": fin,
                                         "step": duree_s(pas)})
        return get(f"{PROM}/api/v1/query_range?{params}").get("data", {})
    return get(f"{PROM}/api/v1/query?{urllib.parse.urlencode({'query': requete})}").get("data", {})


def afficher_prom(data, limite=60):
    resultats = data.get("result", [])
    if data.get("resultType") == "scalar":
        print(resultats[1])
        return
    for serie in resultats[:limite]:
        labels = ",".join(f'{k}="{v}"' for k, v in sorted(serie.get("metric", {}).items()))
        if "values" in serie:
            vals = [float(v) for _, v in serie["values"]]
            print(f"{{{labels}}}  min={min(vals):g} max={max(vals):g} dernière={vals[-1]:g} ({len(vals)} points)")
        else:
            print(f"{{{labels}}}  {serie['value'][1]}")
    if len(resultats) > limite:
        print(f"… {len(resultats) - limite} séries de plus")
    if not resultats:
        print("(aucun résultat)")


def cmd_prom(args):
    p = argparse.ArgumentParser(prog="prom")
    p.add_argument("requete")
    p.add_argument("--depuis")
    p.add_argument("--pas", default="5m")
    a = p.parse_args(args)
    afficher_prom(prom_requete(a.requete, a.depuis, a.pas))


def cmd_hote(args):
    requetes = [
        ("Alertes en cours", 'ALERTS{alertstate="firing"}'),
        ("Disques de l'hôte (% utilisé)",
         '100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})'),
        ("Mémoire disponible (%)", "100 * node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes"),
        ("Mémoire totale (Go)", "node_memory_MemTotal_bytes / 1e9"),
        ("Charge sur 15 min / nombre de cœurs",
         'node_load15 / on(instance) count by (instance) (node_cpu_seconds_total{mode="idle"})'),
        ("Démarrage de l'hôte (timestamp)", "node_boot_time_seconds"),
        ("Conteneurs redémarrés sur 24 h (nombre de démarrages)",
         'changes(container_start_time_seconds{name!=""}[24h]) > 0'),
        ("Conteneurs les plus proches de leur mem_limit (%)",
         'topk(5, 100 * container_memory_working_set_bytes{name!=""} / (container_spec_memory_limit_bytes{name!=""} > 0))'),
        ("Cibles de supervision en échec", "up == 0"),
    ]
    argparse.ArgumentParser(prog="hote", description="synthèse de l'hôte").parse_args(args)
    for titre, q in requetes:
        print(f"## {titre}")
        afficher_prom(prom_requete(q), 20)
        print()


# --------------------------------------------------------------------------------------------- dépôt

def cmd_historique(args):
    p = argparse.ArgumentParser(prog="historique")
    p.add_argument("chemin", nargs="?", default=".")
    p.add_argument("--diff", action="store_true", help="avec le détail des modifications")
    p.add_argument("--nombre", type=int, default=15)
    a = p.parse_args(args)
    chemin = (DEPOT / a.chemin).resolve()
    if not str(chemin).startswith(str(DEPOT.resolve())):
        erreur("chemin hors du dépôt")
    cmd = ["git", "-c", "core.pager=cat", "-c", "diff.external=", "log", f"-n{max(1, min(a.nombre, 50))}",
           "--date=format:%Y-%m-%d %H:%M", "--format=%h %ad %an : %s", "--no-ext-diff", "--no-color"]
    if a.diff:
        cmd.append("-p")
    r = subprocess.run(cmd + ["--", str(chemin)], cwd=DEPOT, capture_output=True, text=True, timeout=30,
                       env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "GIT_CONFIG_NOSYSTEM": "1"})
    sortie = (r.stdout or r.stderr).splitlines()
    print("\n".join(tronquer(l) for l in sortie[:800]) or "(aucun commit)")


# --------------------------------------------------------------------------------------------- actions

def liste_blanche():
    f = DEPOT / "compose" / "agent-actions.txt"
    regles = {}
    if f.is_file():
        for ligne in f.read_text(encoding="utf-8").splitlines():
            ligne = ligne.split("#", 1)[0].strip()
            m = re.fullmatch(r"([a-z0-9][a-z0-9_-]*)\s*:\s*(.*)", ligne)
            if m:
                mots = m.group(2).split()
                regles[m.group(1)] = {"actions": [x for x in mots if not x.startswith("!")],
                                      "exclus": [x[1:] for x in mots if x.startswith("!")]}
    return regles


def cmd_action(args):
    p = argparse.ArgumentParser(prog="action")
    p.add_argument("stack", nargs="?")
    p.add_argument("type", nargs="?", choices=["restart", "up"])
    p.add_argument("service", nargs="?")
    p.add_argument("--raison")
    p.add_argument("--liste", action="store_true", help="affiche la liste blanche")
    a = p.parse_args(args)
    regles = liste_blanche()
    if a.liste:
        for s, r in sorted(regles.items()):
            print(f"{s:<14} {' '.join(r['actions'])}" + (f"   (services exclus : {', '.join(r['exclus'])})" if r["exclus"] else ""))
        return
    if not (a.stack and a.type and a.raison):
        erreur('usage : action <stack> <restart|up> [service] --raison "…"')
    if os.environ.get("TYPE_EXECUTION") == "quotidien":
        erreur("aucune action pendant le rapport quotidien : proposer l'action dans le rapport")
    r = regles.get(a.stack)
    if not r or a.type not in r["actions"]:
        erreur(f"« {a.type} » n'est pas autorisé sur la stack « {a.stack} » (action --liste). Le proposer dans le rapport.")
    if a.service and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,60}", a.service):
        erreur("nom de service invalide")
    if r["exclus"] and not a.service:
        erreur(f"stack « {a.stack} » : préciser le service (services exclus : {', '.join(r['exclus'])})")
    if a.service in r["exclus"]:
        erreur(f"le service « {a.service} » est exclu des actions automatiques")

    ident = os.environ.get("ID_INCIDENT", "manuel")
    deja = list((ACTIONS / "demandes").glob(f"{ident}-*.demande")) + list((ACTIONS / "resultats").glob(f"{ident}-*.resultat"))
    if len(deja) >= MAX_ACTIONS:
        erreur(f"{MAX_ACTIONS} actions déjà demandées pendant ce diagnostic : s'arrêter et rédiger le rapport")
    num = f"{ident}-{len(deja) + 1}"
    raison = re.sub(r"[\x00-\x1f=]", " ", a.raison)[:300]
    contenu = f"id={num}\nstack={a.stack}\naction={a.type}\nservice={a.service or ''}\nraison={raison}\n"
    tmp = ACTIONS / "demandes" / f".{num}.tmp"
    tmp.write_text(contenu, encoding="utf-8")
    os.replace(tmp, ACTIONS / "demandes" / f"{num}.demande")
    print(f"Demande {num} déposée : {a.type} {a.stack} {a.service or '(toute la stack)'} — attente de l'hôte…", flush=True)

    resultat = ACTIONS / "resultats" / f"{num}.resultat"
    fin = time.time() + ATTENTE_ACTION_S
    while time.time() < fin:
        if resultat.is_file():
            print(resultat.read_text(encoding="utf-8", errors="replace"))
            return
        time.sleep(3)
    erreur(f"pas de réponse de l'hôte après {ATTENTE_ACTION_S} s (cron de scripts/agent-actions.sh absent ?). "
           "Ne pas redemander : le signaler dans le rapport.")


COMMANDES = {"conteneurs": cmd_conteneurs, "conteneur": cmd_conteneur, "journaux": cmd_journaux,
             "evenements": cmd_evenements, "loki": cmd_loki, "prom": cmd_prom, "hote": cmd_hote, "historique": cmd_historique,
             "action": cmd_action}

if __name__ == "__main__":
    nom = Path(sys.argv[0]).name
    if nom not in COMMANDES:
        if len(sys.argv) > 1 and sys.argv[1] in COMMANDES:
            nom, sys.argv = sys.argv[1], sys.argv[1:]
        else:
            sys.exit(__doc__)
    COMMANDES[nom](sys.argv[1:])
