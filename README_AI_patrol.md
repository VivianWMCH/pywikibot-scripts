# AI_patrol.py — DicoAdoBot

> Bot de patrouille automatique du [Dico des Ados](https://fr.dicoado.org), propulsé par l'IA Claude (Anthropic) et relié à Discord.

## Description

`AI_patrol.py` est le cœur du système de surveillance du Dico des Ados. Il s'agit d'un bot **Discord** qui surveille en temps réel les modifications récentes du wiki et les analyse grâce à l'API **Claude (Anthropic)**. Il combine trois fonctions principales :

1. **Surveillance automatique** — Vérifie les modifications récentes toutes les 5 minutes et analyse chaque diff via Claude.
2. **Nettoyage automatique** — Corrige les apostrophes typographiques (`'` → `'`), la casse des définitions, la ponctuation des exemples, et la mise en gras du lemme.
3. **Détection de vandalisme** — Évalue un score de risque de vandalisme (0-100 %) et alerte un rôle Discord si le seuil est dépassé.

## Architecture

```
Discord (bot client)
  ├─ Boucle de surveillance (asyncio)
  │    ├─ Récupère les modifications récentes via Pywikibot
  │    ├─ Nettoie le texte (mwparserfromhell)
  │    ├─ Analyse le diff via Claude API
  │    └─ Rapporte sur Discord + bouton "Révoquer"
  ├─ Commandes slash
  │    ├─ /verifie <page>  — Analyse manuelle d'une page
  │    ├─ /stat             — Statistiques du bot
  │    ├─ /aide             — Aide
  │    ├─ /alea             — Page au hasard
  │    └─ /rc               — Dernières modifications traitées
  └─ Accueil automatique des nouveaux contributeurs
```

## Dépendances

| Paquet               | Usage                                      |
|----------------------|--------------------------------------------|
| `pywikibot`          | Interaction avec l'API MediaWiki           |
| `discord.py`         | Bot Discord et commandes slash             |
| `anthropic`          | Appels à l'API Claude (analyse IA)         |
| `mwparserfromhell`   | Parsing du wikicode                        |
| `difflib`            | Calcul de diffs entre révisions            |

## Variables d'environnement

| Variable              | Obligatoire | Description                                         | Défaut                        |
|-----------------------|:-----------:|-----------------------------------------------------|-------------------------------|
| `DISCORD_TOKEN`       | ✅          | Token du bot Discord                                | —                             |
| `ANTHROPIC_API_KEY`   | ✅          | Clé API Anthropic (Claude)                          | —                             |
| `DISCORD_CHANNEL_ID`  | ❌          | ID du salon Discord de rapport                      | `1317111951305736254`         |
| `VANDALISM_ROLE_ID`   | ❌          | ID du rôle Discord à mentionner en cas de vandalisme| `772094056053473310`          |
| `CLAUDE_MODEL`        | ❌          | Modèle Claude à utiliser                            | `claude-sonnet-4-6`      |
| `HTTP_PROXY`          | ❌          | Proxy HTTP (si nécessaire)                          | —                             |
| `HTTPS_PROXY`         | ❌          | Proxy HTTPS (si nécessaire)                         | —                             |

## Constantes clés

| Constante             | Valeur  | Description                                            |
|-----------------------|---------|--------------------------------------------------------|
| `INITIAL_INTERVAL`    | 60 s    | Délai avant la première vérification                   |
| `CHECK_INTERVAL`      | 300 s   | Intervalle entre les vérifications (5 min)             |
| `ERROR_BACKOFF`       | 300 s   | Délai de recul après une erreur                        |
| `VANDALISM_THRESHOLD` | 50 %    | Seuil de risque de vandalisme pour l'alerte            |
| `CLAUDE_TIMEOUT`      | 60 s    | Timeout des appels à l'API Claude                      |

## Fonctionnalités détaillées

### Nettoyage automatique du wikicode

Le bot parse le template `{{Article}}` et applique les corrections suivantes :

- **Définitions (`|def=`)** : suppression de la ponctuation finale superflue, remplacement des apostrophes droites par des apostrophes typographiques, mise en minuscule de la première lettre (sauf liens wiki et noms propres).
- **Exemples (`|ex=`)** : ponctuation finale ajoutée si manquante, mise en gras automatique du lemme (`'''mot'''`), apostrophes typographiques.
- **Légendes (`|légende=`)** : apostrophes typographiques.

### Analyse IA (Claude)

Trois prompts spécialisés sont utilisés :

1. **Analyse de diff** (`build_analysis_prompt`) — Évalue les modifications récentes, détecte les problèmes et estime le risque de vandalisme.
2. **Analyse manuelle** (`build_manual_prompt`) — Relecture complète d'une page demandée via `/verifie`.
3. **Suggestions de catégories** (`build_category_prompt`) — Analyse le contenu de la page (titre + texte) et propose des catégories parmi une liste autorisée. Se déclenche lorsque `|cat=` est absent **ou vide**.

### Accueil des nouveaux contributeurs

- Envoie `{{subst:Bienvenue}}` aux nouveaux utilisateurs inscrits (1ère modification).
- Envoie `{{subst:Bienvenue IP}}` aux contributeurs anonymes (IP).

### Bouton de révocation Discord

Lorsqu'une modification suspecte est détectée, un bouton **↩️ Révoquer** apparaît dans le message Discord. Les utilisateurs ayant la permission `manage_messages` peuvent révoquer la modification en un clic.

## Utilisation

```bash
# Configurer les variables d'environnement
export DISCORD_TOKEN="votre_token"
export ANTHROPIC_API_KEY="votre_clé"

# Lancer le bot
python AI_patrol.py
```

## Logs

Les logs sont écrits dans `dicoado_bot.log` et affichés dans la console (`stdout`).

## Site wiki cible

Le bot opère sur le site `fr.dicoado.org` (famille `dicoado`, langue `fr`), configuré dans Pywikibot.
