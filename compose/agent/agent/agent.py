#!/usr/bin/env python3
"""Agent de dépannage du homelab (stack compose/agent, voir README.md).

Rôle de ce programme (le « chef d'orchestre », pas l'IA) :
  - reçoit les alertes d'Alertmanager (POST /alertes, jeton partagé) et surveille les conteneurs « unhealthy » ;
  - regroupe, filtre (arrêts Backrest, anti-rebond, plafond quotidien) et met en file ;
  - lance Claude Code en mode non interactif (claude -p) avec l'abonnement Pro (CLAUDE_CODE_OAUTH_TOKEN, jamais de clé API),
    des outils en lecture seule et des permissions « dontAsk » (tout ce qui n'est pas autorisé est refusé) ;
  - relit le correctif éventuel de Claude dans le clone du dépôt, le vérifie, le pousse sur une branche agent/… et ouvre une PR ;
  - écrit le rapport Markdown, notifie ntfy et publie des métriques pour la supervision.

Claude ne voit jamais : le token GitHub, le token ntfy, la clé SOPS, le socket Docker en écriture.
Sous-commandes : serveur (défaut) | tester <conteneur> [alerte] | quotidien | etat
"""
import base64
import hmac
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------------------------- configuration

def env(nom, defaut=""):
    return os.environ.get(nom, defaut).strip()

def env_int(nom, defaut):
    try:
        return int(env(nom, str(defaut)))
    except ValueError:
        return defaut

TZ = ZoneInfo(env("TZ", "Europe/Paris"))
DOSSIER_CODE = Path(__file__).resolve().parent
CONSIGNES = DOSSIER_CODE / "consignes"
CLAUDE = env("CLAUDE_BIN", "claude")

DEPOT = Path(env("DOSSIER_DEPOT", "/data/depot"))
RAPPORTS = Path(env("DOSSIER_RAPPORTS", "/data/rapports"))
ETAT = Path(env("DOSSIER_ETAT", "/data/etat"))
ACTIONS = Path(env("DOSSIER_ACTIONS", "/actions"))
ETAT_BACKREST = Path(env("DOSSIER_ETAT_BACKREST", "/etat-backrest"))
TEXTFILE = Path(env("DOSSIER_TEXTFILE", "/textfile"))
JOURNAUX = ETAT / "journaux"                       # transcriptions complètes des exécutions (illisibles par Claude)

PORT = env_int("PORT", 8080)
JETON = env("AGENT_TOKEN_ALERTMANAGER")
NTFY_URL = env("NTFY_URL").rstrip("/")
NTFY_TOPIC = env("NTFY_TOPIC", "homelab-agent")
NTFY_TOKEN = env("NTFY_TOKEN")
GITHUB_TOKEN = env("GITHUB_TOKEN")
DEPOT_GITHUB = env("DEPOT_GITHUB", "Doxah/Homelab")
DEPOT_URL = env("DEPOT_URL", f"https://github.com/{DEPOT_GITHUB}.git")   # clone public, sans token
BRANCHE = env("BRANCHE", "main")
DOMAINE_INTERDIT = env("DOMAINE_INTERDIT").lower()
DOCKER_API = env("DOCKER_API", "http://socket-proxy-agent:2375").rstrip("/")

MODELE = env("MODELE", "sonnet")
MODELE_QUOTIDIEN = env("MODELE_QUOTIDIEN", MODELE)
EFFORT = env("EFFORT")                              # vide = valeur par défaut de Claude Code
TOURS_MAX_INCIDENT = env_int("TOURS_MAX_INCIDENT", 40)
TOURS_MAX_QUOTIDIEN = env_int("TOURS_MAX_QUOTIDIEN", 50)
DUREE_MAX_MIN = env_int("DUREE_MAX_MIN", 20)
RECHERCHE_WEB = env("RECHERCHE_WEB", "1") == "1"

ALERTES_GEREES = re.compile(env("ALERTES_GEREES",
    r"Conteneur.*|ServiceInjoignable|TunnelCloudflareCoupe|TraefikErreurs5xx"))
EXCLUS = set(env("CONTENEURS_EXCLUS", "agent,socket-proxy-agent").split(","))
DELAI_REGROUPEMENT_S = env_int("DELAI_REGROUPEMENT_S", 90)
DELAI_ENTRE_DIAGNOSTICS_MIN = env_int("DELAI_ENTRE_DIAGNOSTICS_MIN", 120)
MAX_DIAGNOSTICS_JOUR = env_int("MAX_DIAGNOSTICS_JOUR", 8)
DELAI_QUOTA_MIN = env_int("DELAI_QUOTA_MIN", 60)
HEURE_QUOTIDIEN = env("HEURE_RAPPORT_QUOTIDIEN", "07:30")   # vide = pas de rapport quotidien
SURVEILLER_UNHEALTHY = env("SURVEILLER_UNHEALTHY", "1") == "1"

# Correctifs refusés d'office (vérifiés par ce programme, en plus des permissions de Claude)
CHEMINS_INTERDITS = re.compile(
    r"(\.sops\.|^\.sops\.yaml$|^\.git/|^\.github/|^private/|^compose/agent/|^compose/agent-actions\.txt$"
    r"|^scripts/agent-actions\.sh$|^\.pre-commit-config\.yaml$|^\.gitignore$|(^|/)\.claude/|(^|/)CLAUDE\.md$)")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IPV4_PERMISES = {"0.0.0.0", "127.0.0.1"}
MAX_FICHIERS_PR = 15
MAX_LIGNES_PR = 400

SCHEMA = {
    "type": "object",
    "properties": {
        "statut": {"type": "string", "enum": [
            "resolu", "resolu_temporairement", "non_resolu", "intervention_requise", "fausse_alerte", "rien_a_signaler"]},
        "titre": {"type": "string", "description": "Une ligne, 80 caractères max"},
        "resume": {"type": "string", "description": "2 à 4 phrases pour la notification téléphone"},
        "cause": {"type": "string", "description": "Cause racine, ou hypothèse la plus probable signalée comme telle"},
        "actions": {"type": "array", "items": {"type": "string"}, "description": "Actions RÉELLEMENT effectuées"},
        "recommandations": {"type": "array", "items": {"type": "string"}, "description": "À faire par Eliot"},
        "rapport": {"type": "string", "description": "Rapport complet en Markdown"},
        "pr_titre": {"type": "string", "description": "Vide si aucun fichier modifié dans /data/depot"},
        "pr_description": {"type": "string", "description": "Markdown, sans journaux, sans IP ni domaine"},
    },
    "required": ["statut", "titre", "resume", "cause", "actions", "recommandations", "rapport",
                 "pr_titre", "pr_description"],
    "additionalProperties": False,
}

EMOJI = {"resolu": "✅", "resolu_temporairement": "🩹", "non_resolu": "❌", "intervention_requise": "🙋",
         "fausse_alerte": "💤", "rien_a_signaler": "✅"}
PRIORITE = {"resolu": 3, "resolu_temporairement": 3, "non_resolu": 4, "intervention_requise": 4,
            "fausse_alerte": 2, "rien_a_signaler": 2}

# --------------------------------------------------------------------------------------------- utilitaires

def maintenant():
    return datetime.now(TZ)

def journal(niveau, message, **champs):
    """Journal au format logfmt (level=… msg=…) : le niveau est extrait par Alloy pour Grafana."""
    morceaux = [f"time={maintenant().isoformat(timespec='seconds')}", f"level={niveau}", f"msg={json.dumps(message, ensure_ascii=False)}"]
    morceaux += [f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, str) else v}" for k, v in champs.items()]
    print(" ".join(morceaux), flush=True)

def ecrire_atomique(chemin: Path, contenu: str, mode=0o640):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f".{chemin.name}.tmp")
    tmp.write_text(contenu, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, chemin)

def masquer(texte: str) -> str:
    """Retire le domaine et les IP d'un texte destiné au dépôt public (description de PR)."""
    if DOMAINE_INTERDIT:
        texte = re.sub(re.escape(DOMAINE_INTERDIT), "<domaine>", texte, flags=re.I)
    return IPV4.sub(lambda m: m.group(0) if m.group(0) in IPV4_PERMISES else "<ip>", texte)

def slug(texte: str, longueur=40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texte.lower()).strip("-")
    return s[:longueur].strip("-") or "x"

def http_json(methode, url, donnees=None, entetes=None, delai=15):
    corps = json.dumps(donnees).encode() if donnees is not None else None
    req = urllib.request.Request(url, data=corps, method=methode, headers=entetes or {})
    if corps is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=delai) as r:
        brut = r.read()
        return json.loads(brut) if brut else None

# --------------------------------------------------------------------------------------------- état persistant

class Etat:
    """etat.json : anti-rebond par alerte, compteur du jour, historique court, file d'attente (survit au redémarrage)."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.verrou = threading.RLock()
        try:
            self.d = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}
        for cle, defaut in (("derniers", {}), ("historique", []), ("file", []), ("jour", ""), ("nb_jour", 0),
                            ("dernier_quotidien", ""), ("metriques", {}), ("plafond_notifie", "")):
            self.d.setdefault(cle, defaut)

    def sauver(self):
        with self.verrou:
            ecrire_atomique(self.chemin, json.dumps(self.d, ensure_ascii=False, indent=1))

    def compter_execution(self):
        with self.verrou:
            jour = maintenant().strftime("%F")
            if self.d["jour"] != jour:
                self.d["jour"], self.d["nb_jour"] = jour, 0
            self.d["nb_jour"] += 1
            self.sauver()

    def plafond_atteint(self):
        with self.verrou:
            return self.d["jour"] == maintenant().strftime("%F") and self.d["nb_jour"] >= MAX_DIAGNOSTICS_JOUR

    def ajouter_historique(self, entree):
        with self.verrou:
            self.d["historique"] = (self.d["historique"] + [entree])[-50:]
            self.sauver()

etat: Etat = None  # initialisé dans main()
reveil = threading.Event()

# --------------------------------------------------------------------------------------------- ntfy et métriques

def notifier(titre, message, priorite=3, tags=None, clic=None):
    """Publication JSON (titre UTF-8, emoji compris). Un échec n'interrompt jamais l'agent."""
    if not (NTFY_URL and NTFY_TOKEN):
        journal("warn", "ntfy non configuré, notification ignorée", titre=titre)
        return
    donnees = {"topic": NTFY_TOPIC, "title": titre[:250], "message": message[:3900], "priority": priorite,
               "tags": tags or [], "markdown": True}
    if clic:
        donnees["click"] = clic
    try:
        http_json("POST", NTFY_URL + "/", donnees, {"Authorization": f"Bearer {NTFY_TOKEN}"})
    except Exception as e:  # noqa: BLE001
        journal("warn", "envoi ntfy en échec", erreur=str(e))

def metriques(type_, succes):
    """Collecteur textfile de node_exporter (compose/monitoring/data/textfile/agent.prom)."""
    with etat.verrou:
        m = etat.d["metriques"]
        m[type_] = {"ts": int(time.time()), "succes": 1 if succes else 0, "total": m.get(type_, {}).get("total", 0) + 1}
        etat.sauver()
        if not TEXTFILE.is_dir():
            return
        lignes = [
            "# HELP homelab_agent_derniere_execution_timestamp_seconds Horodatage de la dernière exécution de l'agent.",
            "# TYPE homelab_agent_derniere_execution_timestamp_seconds gauge"]
        lignes += [f'homelab_agent_derniere_execution_timestamp_seconds{{type="{t}"}} {v["ts"]}' for t, v in m.items()]
        lignes += ["# HELP homelab_agent_derniere_execution_succes 1 si la dernière exécution s'est terminée normalement.",
                   "# TYPE homelab_agent_derniere_execution_succes gauge"]
        lignes += [f'homelab_agent_derniere_execution_succes{{type="{t}"}} {v["succes"]}' for t, v in m.items()]
        lignes += ["# HELP homelab_agent_executions_total Nombre d'exécutions de l'agent depuis sa création.",
                   "# TYPE homelab_agent_executions_total counter"]
        lignes += [f'homelab_agent_executions_total{{type="{t}"}} {v["total"]}' for t, v in m.items()]
        try:
            ecrire_atomique(TEXTFILE / "agent.prom", "\n".join(lignes) + "\n", 0o644)
        except OSError as e:
            journal("warn", "écriture de la métrique impossible", erreur=str(e))

# --------------------------------------------------------------------------------------------- dépôt Git

def git(*args, verifier=True, env_extra=None, cwd=DEPOT):
    """Git sans hooks ni invite : un fichier .git/hooks déposé par Claude ne serait jamais exécuté."""
    e = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp"), "GIT_TERMINAL_PROMPT": "0",
         "LANG": "C.UTF-8"}
    e.update(env_extra or {})
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
           "-c", "user.name=agent-homelab", "-c", "user.email=agent-homelab@users.noreply.github.com", *args]
    r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, timeout=180)
    if verifier and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} : {r.stderr.strip()[-500:]}")
    return r.stdout

def preparer_depot():
    """Clone public de GitHub, remis à zéro sur origin/main avant chaque exécution."""
    if not (DEPOT / ".git").is_dir():
        DEPOT.mkdir(parents=True, exist_ok=True)
        git("clone", "--quiet", DEPOT_URL, str(DEPOT), cwd="/")
    git("remote", "set-url", "origin", DEPOT_URL)
    git("fetch", "--quiet", "--prune", "origin", BRANCHE)
    git("checkout", "--quiet", "-B", "agent-travail", f"origin/{BRANCHE}")
    git("reset", "--quiet", "--hard", f"origin/{BRANCHE}")
    git("clean", "-qfdx")

def verifier_correctif():
    """Retourne (fichiers, diff) si le correctif est acceptable, lève ValueError sinon."""
    git("add", "-A")
    fichiers = [f for f in git("diff", "--cached", "--name-only").splitlines() if f]
    if not fichiers:
        return [], ""
    interdits = [f for f in fichiers if CHEMINS_INTERDITS.search(f)]
    if interdits:
        raise ValueError(f"fichiers non modifiables par l'agent : {', '.join(interdits)}")
    if len(fichiers) > MAX_FICHIERS_PR:
        raise ValueError(f"{len(fichiers)} fichiers modifiés (maximum {MAX_FICHIERS_PR})")
    diff = git("diff", "--cached", "--no-color", "--no-ext-diff")
    ajouts = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    retraits = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    if len(ajouts) + len(retraits) > MAX_LIGNES_PR:
        raise ValueError(f"{len(ajouts) + len(retraits)} lignes modifiées (maximum {MAX_LIGNES_PR})")
    for l in ajouts:
        if DOMAINE_INTERDIT and DOMAINE_INTERDIT in l.lower():
            raise ValueError("le domaine apparaît en clair dans le correctif (il doit rester dans les secrets)")
        ips = [ip for ip in IPV4.findall(l) if ip not in IPV4_PERMISES]
        if ips:
            raise ValueError(f"adresse IP en clair dans le correctif ({ips[0]}) : elle doit rester dans les secrets")
    return fichiers, diff

def ouvrir_pr(ident, titre, description, chemin_rapport):
    """Commit sur agent/<id>, push avec le token GitHub (en-tête HTTP via l'environnement, jamais dans l'URL), PR."""
    branche = f"agent/{ident}"
    titre = masquer(titre.strip())[:120] or "Correctif proposé par l'agent"
    corps = masquer(description.strip())
    corps += ("\n\n---\n🤖 PR ouverte automatiquement par l'agent de dépannage du homelab (Claude Code). "
              f"Rapport complet sur le Mini PC : `compose/agent/data/rapports/{chemin_rapport.name}`.\n"
              "**À relire avant de merger** : le déploiement automatique relancera les stacks concernées.")
    git("checkout", "--quiet", "-b", branche)
    git("commit", "--quiet", "-m", f"agent: {titre}", "-m", f"Incident {ident}")
    auth = base64.b64encode(f"x-access-token:{GITHUB_TOKEN}".encode()).decode()
    git("push", "--quiet", "origin", f"{branche}:{branche}", env_extra={
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}"})
    pr = http_json("POST", f"https://api.github.com/repos/{DEPOT_GITHUB}/pulls",
                   {"title": titre, "head": branche, "base": BRANCHE, "body": corps, "maintainer_can_modify": True},
                   {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "agent-homelab"}, delai=30)
    return pr.get("html_url", "")

# --------------------------------------------------------------------------------------------- Claude Code

class QuotaAtteint(Exception):
    pass

def env_claude(ident, type_):
    """Environnement minimal de Claude : AUCUN autre secret que son propre token d'abonnement."""
    e = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/home/agent"),
        "TZ": env("TZ", "Europe/Paris"),
        "LANG": "C.UTF-8",
        "CLAUDE_CODE_OAUTH_TOKEN": env("CLAUDE_CODE_OAUTH_TOKEN"),
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",   # ni télémétrie, ni rapport d'erreurs, ni mise à jour
        "BASH_DEFAULT_TIMEOUT_MS": "300000",               # l'outil « action » attend jusqu'à 3 min le résultat
        "BASH_MAX_TIMEOUT_MS": "600000",
        "DOCKER_API": DOCKER_API,
        "LOKI_URL": env("LOKI_URL", "http://loki:3100"),
        "PROM_URL": env("PROM_URL", "http://prometheus:9090"),
        "DOSSIER_ACTIONS": str(ACTIONS),
        "DOSSIER_DEPOT": str(DEPOT),
        "ID_INCIDENT": ident,
        "TYPE_EXECUTION": type_,
    }
    for nom in ("ACTION_ATTENTE_S", "MAX_ACTIONS_PAR_DIAGNOSTIC"):
        if env(nom):
            e[nom] = env(nom)
    return e

def lancer_claude(ident, type_, prompt):
    """Lance claude -p, enregistre la transcription (stream-json) et renvoie (sortie structurée, résultat brut)."""
    outils = ["Bash", "Read", "Grep", "Glob", "Edit", "Write"] + (["WebSearch"] if RECHERCHE_WEB else [])
    cmd = [CLAUDE, "-p",
           "--output-format", "stream-json", "--verbose",
           "--model", MODELE_QUOTIDIEN if type_ == "quotidien" else MODELE,
           "--max-turns", str(TOURS_MAX_QUOTIDIEN if type_ == "quotidien" else TOURS_MAX_INCIDENT),
           "--permission-mode", "dontAsk",                 # tout ce qui n'est pas dans settings.json est refusé
           "--setting-sources", "",                        # ni ~/.claude/settings.json, ni .claude/ du dépôt : seul --settings
           "--settings", str(CONSIGNES / "settings.json"),
           "--append-system-prompt-file", str(CONSIGNES / "CLAUDE.md"),
           "--strict-mcp-config",
           "--no-session-persistence",
           "--json-schema", json.dumps(SCHEMA),
           "--tools", ",".join(outils)]
    if type_ == "quotidien":
        cmd += ["--disallowedTools", "Bash(action *)"]   # le rapport quotidien ne touche à rien
    if EFFORT:
        cmd += ["--effort", EFFORT]

    JOURNAUX.mkdir(parents=True, exist_ok=True)
    transcription = JOURNAUX / f"{ident}.jsonl"
    debut = time.time()
    with open(transcription, "w", encoding="utf-8") as sortie:
        proc = subprocess.Popen(cmd, cwd=DEPOT, env=env_claude(ident, type_), stdin=subprocess.PIPE,
                                stdout=sortie, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            proc.communicate(prompt, timeout=DUREE_MAX_MIN * 60)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            journal("error", "Claude interrompu : durée maximale atteinte", id=ident, minutes=DUREE_MAX_MIN)

    resultat, source_cle = None, None
    for ligne in transcription.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            m = json.loads(ligne)
        except ValueError:
            continue
        if m.get("type") == "system" and m.get("subtype") == "init":
            source_cle = m.get("apiKeySource")
        elif m.get("type") == "result":
            resultat = m

    # Garde-fou facturation : avec le token d'abonnement, Claude Code annonce apiKeySource = "none".
    if source_cle not in (None, "none"):
        notifier("⚠️ Agent : facturation API détectée", f"Claude Code a démarré avec apiKeySource={source_cle}. "
                 "Agent arrêté : vérifier qu'aucune variable ANTHROPIC_* n'est définie.", 5, ["warning"])
        journal("critical", "apiKeySource inattendu, arrêt", source=source_cle)
        os._exit(2)

    duree = int(time.time() - debut)
    if resultat is None:
        return None, {"is_error": True, "result": "Claude s'est arrêté sans résultat (voir la transcription).",
                      "duree": duree}
    resultat["duree"] = duree
    texte = str(resultat.get("result", ""))
    if resultat.get("is_error") and (resultat.get("api_error_status") == 429
                                     or re.search(r"usage limit|rate limit|limit reached|quota", texte, re.I)):
        raise QuotaAtteint(texte[:300])
    return resultat.get("structured_output"), resultat

# --------------------------------------------------------------------------------------------- exécutions

def lire_modele(nom, **valeurs):
    return Template((CONSIGNES / nom).read_text(encoding="utf-8")).safe_substitute(**valeurs)

def historique_pour(cibles):
    lignes = [f"- {h['date']} [{h['statut']}] {h['titre']}" for h in etat.d["historique"]
              if h.get("type") == "quotidien" or set(h.get("cibles", [])) & set(cibles)]
    return "\n".join(lignes[-8:]) or "(aucun)"

def conteneurs_arretes_par_backrest():
    """Conteneurs arrêtés volontairement par le hook Backrest (fichiers <plan>.arretes non vides)."""
    noms = set()
    if ETAT_BACKREST.is_dir():
        for f in ETAT_BACKREST.glob("*.arretes"):
            try:
                noms.update(f.read_text().split())
            except OSError:
                pass
    return noms

def executer(type_, alertes=None):
    """Une exécution complète : dépôt, Claude, correctif, rapport, notification. Ne lève jamais d'exception."""
    alertes = alertes or []
    debut = maintenant()
    cibles = sorted({a["cible"] for a in alertes})
    ident = debut.strftime("%Y%m%d-%H%M%S") + "-" + (slug("-".join(cibles), 30) if cibles else type_)
    journal("info", "exécution de l'agent", id=ident, type=type_, cibles=",".join(cibles))
    if type_ == "incident":
        etat.compter_execution()                      # le plafond quotidien ne compte que les incidents
    succes = False
    try:
        preparer_depot()
        commit = git("rev-parse", "--short", "HEAD").strip()
        if type_ == "quotidien":
            prompt = lire_modele("quotidien.md", date=debut.strftime("%A %d %B %Y %H:%M"), id=ident,
                                 historique=historique_pour([]), commit=commit)
        else:
            prompt = lire_modele("incident.md", date=debut.strftime("%F %T %Z"), id=ident, commit=commit,
                                 alertes=json.dumps(alertes, ensure_ascii=False, indent=1),
                                 historique=historique_pour(cibles))
        sortie, brut = lancer_claude(ident, type_, prompt)
        if not sortie:
            raison = brut.get("subtype") or "sans sortie structurée"
            sortie = {"statut": "non_resolu", "titre": f"Diagnostic interrompu ({raison})",
                      "resume": "L'agent n'a pas pu terminer son analyse. Voir le rapport et la transcription.",
                      "cause": "inconnue", "actions": [], "recommandations": ["Relire la transcription sur le Mini PC"],
                      "rapport": str(brut.get("result", "")), "pr_titre": "", "pr_description": ""}

        # ---- correctif éventuel → PR
        lien_pr, note_pr = "", ""
        try:
            fichiers, diff = verifier_correctif()
            if fichiers:
                if not sortie.get("pr_titre"):
                    sortie["pr_titre"] = sortie["titre"]
                if GITHUB_TOKEN:
                    lien_pr = ouvrir_pr(ident, sortie["pr_titre"], sortie.get("pr_description", ""),
                                        RAPPORTS / f"{ident}.md")
                    note_pr = f"PR ouverte : {lien_pr}"
                else:
                    ecrire_atomique(RAPPORTS / f"{ident}.patch", diff)
                    note_pr = f"Pas de GITHUB_TOKEN : correctif gardé dans data/rapports/{ident}.patch"
        except ValueError as e:
            ecrire_atomique(RAPPORTS / f"{ident}.refuse.patch", git("diff", "--cached", "--no-color", verifier=False))
            note_pr = f"Correctif REFUSÉ par les garde-fous : {e} (gardé dans data/rapports/{ident}.refuse.patch)"
            journal("warn", "correctif refusé", id=ident, raison=str(e))
        except Exception as e:  # noqa: BLE001
            note_pr = f"Ouverture de la PR en échec : {e}"
            journal("error", "PR en échec", id=ident, erreur=str(e))

        # ---- rapport Markdown
        fichier = RAPPORTS / f"{ident}.md"
        entete = [f"# {EMOJI.get(sortie['statut'], '•')} {sortie['titre']}", "",
                  f"- **Date** : {debut.strftime('%F %T')} — durée {brut.get('duree', '?')} s, "
                  f"{brut.get('num_turns', '?')} tours, modèle {MODELE_QUOTIDIEN if type_ == 'quotidien' else MODELE}",
                  f"- **Type** : {type_} — **statut** : `{sortie['statut']}` — dépôt `{commit}`",
                  f"- **Cause** : {sortie['cause']}"]
        if alertes:
            entete.append("- **Alertes** : " + ", ".join(f"{a['alertname']} ({a['cible']})" for a in alertes))
        if note_pr:
            entete.append(f"- **Correctif** : {note_pr}")
        entete += ["", "## Actions effectuées"] + ([f"- {a}" for a in sortie["actions"]] or ["- aucune"])
        entete += ["", "## À faire"] + ([f"- {r}" for r in sortie["recommandations"]] or ["- rien"])
        entete += ["", "## Rapport détaillé", "", sortie["rapport"], "",
                   f"_Transcription complète : data/etat/journaux/{ident}.jsonl_"]
        ecrire_atomique(fichier, "\n".join(entete) + "\n")

        # ---- notification
        message = sortie["resume"]
        if sortie["actions"]:
            message += "\n\n**Actions** : " + " ; ".join(sortie["actions"])[:600]
        if sortie["recommandations"]:
            message += "\n\n**À faire** : " + " ; ".join(sortie["recommandations"])[:600]
        if note_pr:
            message += f"\n\n{note_pr}"
        message += f"\n\nRapport : `data/rapports/{fichier.name}`"
        prefixe = "📋 Rapport du jour — " if type_ == "quotidien" else "🔧 "
        notifier(f"{prefixe}{EMOJI.get(sortie['statut'], '')} {sortie['titre']}", message,
                 PRIORITE.get(sortie["statut"], 3), ["robot"], lien_pr or None)
        etat.ajouter_historique({"date": debut.strftime("%F %H:%M"), "type": type_, "cibles": cibles,
                                 "statut": sortie["statut"], "titre": sortie["titre"][:120]})
        succes = not brut.get("is_error")
        journal("info", "exécution terminée", id=ident, statut=sortie["statut"], duree=brut.get("duree"),
                tours=brut.get("num_turns"))
    except QuotaAtteint:
        raise
    except Exception as e:  # noqa: BLE001
        journal("error", "exécution en échec", id=ident, erreur=str(e), trace=traceback.format_exc()[-1500:])
        notifier("❌ Agent en échec", f"Exécution {ident} ({type_}) : {e}", 4, ["x"])
    finally:
        metriques(type_, succes)
        try:
            preparer_depot()                                  # rien ne traîne dans le clone
        except Exception:  # noqa: BLE001
            pass

# --------------------------------------------------------------------------------------------- file d'attente

def ajouter_alertes(alertes, source):
    """Filtre puis met en file. Renvoie le nombre d'alertes retenues."""
    arretes = conteneurs_arretes_par_backrest()
    retenues = 0
    with etat.verrou:
        en_file = {a["cle"] for a in etat.d["file"]}
        for a in alertes:
            cle = f"{a['alertname']}:{a['cible']}"
            if a["cible"] in EXCLUS:
                journal("info", "alerte ignorée : conteneur exclu", cle=cle)
                continue
            if a["cible"] in arretes:
                journal("info", "alerte ignorée : conteneur arrêté par Backrest", cle=cle)
                continue
            dernier = etat.d["derniers"].get(cle, 0)
            if time.time() - dernier < DELAI_ENTRE_DIAGNOSTICS_MIN * 60:
                journal("info", "alerte ignorée : déjà diagnostiquée récemment", cle=cle)
                continue
            if cle in en_file:
                continue
            a.update({"cle": cle, "recu": time.time(), "source": source})
            etat.d["file"].append(a)
            en_file.add(cle)
            retenues += 1
        etat.sauver()
    if retenues:
        journal("info", "alertes en file", nombre=retenues, source=source)
        reveil.set()
    return retenues

def prendre_lot():
    """Toutes les alertes en file si la plus ancienne attend depuis DELAI_REGROUPEMENT_S (une panne = une exécution)."""
    with etat.verrou:
        prets = [a for a in etat.d["file"] if a.get("pas_avant", 0) <= time.time()]
        if not prets or time.time() - min(a["recu"] for a in prets) < DELAI_REGROUPEMENT_S:
            return []
        etat.d["file"] = [a for a in etat.d["file"] if a not in prets]
        for a in prets:
            etat.d["derniers"][a["cle"]] = time.time()
        # Nettoyage de l'anti-rebond (> 7 jours)
        etat.d["derniers"] = {k: v for k, v in etat.d["derniers"].items() if time.time() - v < 7 * 86400}
        etat.sauver()
        return prets

def surveiller_unhealthy():
    try:
        filtre = urllib.parse.quote(json.dumps({"health": ["unhealthy"]}))
        conteneurs = http_json("GET", f"{DOCKER_API}/containers/json?filters={filtre}", delai=10) or []
    except Exception as e:  # noqa: BLE001
        journal("warn", "socket-proxy injoignable", erreur=str(e))
        return
    alertes = [{"alertname": "ConteneurUnhealthy", "cible": c["Names"][0].lstrip("/"), "statut": c.get("Status", ""),
                "labels": {"image": c.get("Image", "")}, "annotations": {"summary": "Healthcheck Docker en échec"}}
               for c in conteneurs if c.get("Names")]
    if alertes:
        ajouter_alertes(alertes, "docker")

def doit_lancer_quotidien():
    if etat.d.get("quotidien_demande"):              # « agent.py quotidien » : tout de suite, même si désactivé
        return True
    if not re.fullmatch(r"\d{2}:\d{2}", HEURE_QUOTIDIEN):
        return False
    m = maintenant()
    return m.strftime("%H:%M") >= HEURE_QUOTIDIEN and etat.d["dernier_quotidien"] != m.strftime("%F")

def boucle():
    dernier_controle = 0.0
    while True:
        reveil.wait(10)
        reveil.clear()
        try:
            if SURVEILLER_UNHEALTHY and time.time() - dernier_controle >= 60:
                dernier_controle = time.time()
                surveiller_unhealthy()
            lot = prendre_lot()
            type_ = "incident" if lot else ("quotidien" if doit_lancer_quotidien() else None)
            if not type_:
                continue
            if type_ == "quotidien":
                etat.d["dernier_quotidien"] = maintenant().strftime("%F")
                etat.d["quotidien_demande"] = False
                etat.sauver()
            elif etat.plafond_atteint():
                if etat.d["plafond_notifie"] != maintenant().strftime("%F"):
                    etat.d["plafond_notifie"] = maintenant().strftime("%F")
                    etat.sauver()
                    notifier("⏸️ Agent : plafond du jour atteint",
                             f"{MAX_DIAGNOSTICS_JOUR} diagnostics aujourd'hui : les alertes suivantes ne lancent plus "
                             "l'agent jusqu'à demain (quota de l'abonnement préservé). Alertes ignorées : "
                             + ", ".join(a["cle"] for a in lot), 4, ["pause_button"])
                continue
            try:
                executer(type_, lot)
            except QuotaAtteint as e:
                journal("warn", "quota de l'abonnement atteint", detail=str(e))
                if type_ == "quotidien":
                    notifier("⏳ Agent : quota Claude atteint", "Rapport du jour non produit : limite de l'abonnement "
                             f"Pro atteinte ({e}).", 3, ["hourglass"])
                    continue
                a_reessayer = [a for a in lot if not a.get("reessai")]
                with etat.verrou:
                    for a in a_reessayer:
                        a.update({"reessai": True, "pas_avant": time.time() + DELAI_QUOTA_MIN * 60, "recu": time.time()})
                        etat.d["derniers"].pop(a["cle"], None)
                    etat.d["file"] += a_reessayer
                    etat.sauver()
                notifier("⏳ Agent : quota Claude atteint",
                         f"Limite de l'abonnement Pro atteinte. Diagnostic de {', '.join(a['cle'] for a in lot)} "
                         + (f"reporté de {DELAI_QUOTA_MIN} min." if a_reessayer else "abandonné (déjà reporté une fois)."),
                         3, ["hourglass"])
        except Exception:  # noqa: BLE001
            journal("error", "erreur dans la boucle", trace=traceback.format_exc()[-1500:])
            time.sleep(30)

# --------------------------------------------------------------------------------------------- serveur HTTP

def alertes_depuis_alertmanager(charge):
    alertes = []
    for a in charge.get("alerts", []):
        if a.get("status") != "firing":
            continue
        labels = a.get("labels", {})
        nom = labels.get("alertname", "")
        if not ALERTES_GEREES.fullmatch(nom):
            continue
        cible = labels.get("name") or labels.get("nom") or labels.get("instance") or "inconnu"
        alertes.append({"alertname": nom, "cible": cible, "labels": labels,
                        "annotations": a.get("annotations", {}), "depuis": a.get("startsAt", "")})
    return alertes

class Recepteur(BaseHTTPRequestHandler):
    server_version = "agent-homelab"

    def log_message(self, *_):
        pass

    def repondre(self, code, texte):
        corps = texte.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        if self.path == "/sante":
            return self.repondre(200, "ok")
        self.repondre(404, "introuvable")

    def do_POST(self):
        recu = self.headers.get("Authorization", "")
        if not (JETON and hmac.compare_digest(recu.encode(), f"Bearer {JETON}".encode())):
            journal("warn", "requête refusée : jeton invalide", client=self.client_address[0])
            return self.repondre(401, "jeton invalide")
        taille = int(self.headers.get("Content-Length") or 0)
        if taille > 1_000_000:
            return self.repondre(413, "trop gros")
        try:
            charge = json.loads(self.rfile.read(taille) or b"{}")
        except ValueError:
            return self.repondre(400, "JSON invalide")
        if self.path == "/alertes":
            n = ajouter_alertes(alertes_depuis_alertmanager(charge), "alertmanager")
            return self.repondre(200, f"{n} alerte(s) en file")
        if self.path == "/declencher":                 # utilisé par « agent.py tester » et « agent.py quotidien »
            if charge.get("type") == "quotidien":
                with etat.verrou:
                    etat.d["quotidien_demande"] = True
                    etat.sauver()
                reveil.set()
                return self.repondre(200, "rapport quotidien demandé")
            cible = str(charge.get("cible", ""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}", cible):
                return self.repondre(400, "cible invalide")
            a = {"alertname": str(charge.get("alertname", "TestManuel"))[:60], "cible": cible,
                 "labels": {}, "annotations": {"summary": "Test manuel de l'agent"}}
            with etat.verrou:
                etat.d["derniers"].pop(f"{a['alertname']}:{cible}", None)
            n = ajouter_alertes([a], "manuel")
            return self.repondre(200, f"{n} alerte(s) en file")
        self.repondre(404, "introuvable")

# --------------------------------------------------------------------------------------------- démarrage

def verifier_configuration():
    interdites = [v for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                              "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
                  if os.environ.get(v)]
    if interdites:
        sys.exit(f"ERREUR : {', '.join(interdites)} défini(es). L'agent n'utilise QUE l'abonnement "
                 "(CLAUDE_CODE_OAUTH_TOKEN) : retirer ces variables pour ne jamais être facturé à l'usage API.")
    jeton = env("CLAUDE_CODE_OAUTH_TOKEN")
    if not jeton:
        sys.exit("ERREUR : CLAUDE_CODE_OAUTH_TOKEN manquant (claude setup-token, voir README.md).")
    if not jeton.startswith("sk-ant-oat"):
        journal("warn", "CLAUDE_CODE_OAUTH_TOKEN ne ressemble pas à un token d'abonnement (sk-ant-oat…)")
    if not JETON or len(JETON) < 32:
        sys.exit("ERREUR : AGENT_TOKEN_ALERTMANAGER manquant ou trop court (openssl rand -hex 32).")
    if not GITHUB_TOKEN:
        journal("warn", "GITHUB_TOKEN absent : les correctifs seront gardés en .patch au lieu d'une PR")
    for d in (RAPPORTS, ETAT, ACTIONS / "demandes", ACTIONS / "resultats"):
        d.mkdir(parents=True, exist_ok=True)

def client(chemin, donnees):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{chemin}", data=json.dumps(donnees).encode(),
                                 method="POST", headers={"Authorization": f"Bearer {JETON}",
                                                         "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        print(r.read().decode())

def main():
    global etat
    commande = sys.argv[1] if len(sys.argv) > 1 else "serveur"
    if commande == "tester":
        if len(sys.argv) < 3:
            sys.exit("Usage : agent.py tester <conteneur> [NomAlerte]")
        return client("/declencher", {"cible": sys.argv[2], "alertname": sys.argv[3] if len(sys.argv) > 3 else "TestManuel"})
    if commande == "quotidien":
        return client("/declencher", {"type": "quotidien"})
    if commande == "etat":
        print((ETAT / "etat.json").read_text(encoding="utf-8"))
        return None
    if commande != "serveur":
        sys.exit(__doc__)

    verifier_configuration()
    etat = Etat(ETAT / "etat.json")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    threading.Thread(target=boucle, daemon=True, name="boucle").start()
    journal("info", "agent démarré", port=PORT, modele=MODELE, quotidien=HEURE_QUOTIDIEN or "désactivé",
            plafond=MAX_DIAGNOSTICS_JOUR)
    ThreadingHTTPServer(("0.0.0.0", PORT), Recepteur).serve_forever()

if __name__ == "__main__":
    main()
