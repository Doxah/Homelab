# 13 — Lancer les stacks (`scripts/compose-up.sh`)

Lance une ou plusieurs stacks de `compose/` avec leurs secrets SOPS injectés en mémoire (voir [10-secrets.md](10-secrets.md)).

## Utilisation
```bash
scripts/compose-up.sh jellyfin                   # docker compose up -d
scripts/compose-up.sh jellyfin soulsync down     # plusieurs stacks (down/stop : ordre inverse)
scripts/compose-up.sh jellyfin pull
scripts/compose-up.sh jellyfin -- logs -f        # « -- » termine la liste des stacks
```
Les premiers arguments qui correspondent à un dossier `compose/<nom>/compose.yaml` sont des stacks, le reste est la commande `docker compose` (`up -d` par défaut).

## Autocomplétion (Tab)
Sur la machine Docker, avec l'utilisateur qui lance les stacks :
```bash
echo "source $HOME/Homelab/scripts/compose-up.completion.bash" >> ~/.bashrc
# Si ~/.bash_profile existe, il masque ~/.profile et ~/.bashrc n'est pas lu en SSH :
[ -f ~/.bash_profile ] && echo '[ -f ~/.bashrc ] && . ~/.bashrc' >> ~/.bash_profile
```
Ouvrir un nouveau terminal, puis vérifier :
```bash
complete -p ./scripts/compose-up.sh   # attendu : complete -F _compose_up ...
```
`./scripts/compose-up.sh <Tab>` propose les stacks, puis les commandes `docker compose`.

**Tab affiche les fichiers de la racine du dépôt** : la complétion n'est pas chargée dans ce terminal (`complete -p` répond « pas d'indication de complètement » ou `_comp_complete_minimal`). Vérifier la ligne `source` dans `~/.bashrc` et la présence de `~/.bash_profile`.
