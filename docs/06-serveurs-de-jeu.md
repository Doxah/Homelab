# 06 — Serveurs de jeu

## Minecraft (moddé)
- **NeoForge 1.21.1**, environ 90 mods, image **`itzg/docker-minecraft-server`**, sur le Mini PC.
- Géré via **DiscoPanel** avec l'API CurseForge ; bug de détection du modloader NeoForge signalé en issue GitHub.
- Conflits mixin résolus en retirant **Sable** (conflit avec Distant Horizons / Lithostitched).
- Contraptions Create trop grosses : mod **Packet Fixer**.
- Soirées événement (Lucky Block : command blocks, scoreboards, équipes).
- Scintillement côté client résolu par la **VSync**.

## CS2
- 2 serveurs CS2 de test en Docker sur le Mini PC (RCON, cartes Workshop).
- **À supprimer** : ils prennent trop de place. Le projet de serveur d'entraînement façon Refrag est en pause.
