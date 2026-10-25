Rapport quotidien $id — $date (dépôt : main @ $commit)

Rapports récents de l'agent :
$historique

Fais le bilan des dernières 24 heures du homelab. **Aucune action sur l'hôte** pendant ce rapport (la commande
`action` est désactivée) : tu observes, tu analyses, tu proposes. Un correctif de fichier reste possible (PR).

À couvrir, dans cet ordre, en restant bref sur ce qui va bien :
1. `hote` : alertes en cours, disques, mémoire, charge, conteneurs redémarrés, cibles de supervision en échec.
2. `conteneurs` : conteneurs arrêtés, en redémarrage ou unhealthy qui ne devraient pas l'être.
3. Erreurs dans les journaux : `loki 'sum by (container) (count_over_time({level=~"error|critical"}[24h]))' --depuis 24h`,
   puis les messages les plus fréquents des conteneurs concernés. Regroupe les répétitions ; signale ce qui est nouveau
   ou en hausse par rapport à un bruit de fond connu.
4. Sauvegardes : `homelab_sauvegarde_derniere_reussite_timestamp_seconds`, `homelab_deploiement_succes`,
   journaux de `backrest` de la nuit.
5. Tendances inquiétantes : disque qui se remplit, conteneur proche de son `mem_limit`, certificat qui expire.

Classe les problèmes trouvés par priorité (à traiter aujourd'hui / cette semaine / à surveiller), avec pour chacun la
preuve et l'action proposée. Statut `rien_a_signaler` si tout va bien, sinon `intervention_requise` ou `non_resolu`.
Le `resume` doit tenir en 3 phrases : l'essentiel de la journée.
