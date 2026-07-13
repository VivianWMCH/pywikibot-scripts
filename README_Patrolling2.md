# Patrolling2.py — DicoAdo Maintenance Bot

> Script de maintenance par lots pour le [Dico des Ados](https://fr.dicoado.org). Nettoie automatiquement le wikicode de toutes les pages commençant par une lettre donnée.

## Description

`Patrolling2.py` est un bot de **maintenance hors-ligne** (exécution manuelle) qui parcourt les pages du Dico des Ados par lettre alphabétique et applique des corrections typographiques et syntaxiques au wikicode. Contrairement à `AI_patrol.py`, il n'utilise pas d'IA et ne communique pas avec Discord — c'est un outil de nettoyage en masse, ciblé et efficace.

## Fonctionnalités

### Nettoyage du template `{{Article}}`

Le bot parse chaque page via `mwparserfromhell` et corrige les champs suivants :

| Champ          | Corrections appliquées                                                                           |
|----------------|--------------------------------------------------------------------------------------------------|
| `|def=`        | Suppression de la ponctuation finale (`.;,!?`), apostrophes typographiques, mise en minuscule    |
| `|ex=`         | Mise en gras du lemme (`'''mot'''`), ajout de ponctuation finale, apostrophes typographiques      |
| `|légende=`    | Apostrophes typographiques                                                                       |

### Filtrage par lettre et casse

Le bot offre un contrôle fin sur les pages à traiter :

- **Lettre** (`-l` / `--letter`) : préfixe alphabétique pour sélectionner les pages.
- **Casse** (`-c` / `--case`) :
  - `m` — uniquement les pages commençant par une **minuscule** (ex : `avion`)
  - `M` — uniquement les pages commençant par une **majuscule** (ex : `Avion`)
  - `t` — **toutes** les pages (défaut)

### Mode simulation

Le flag `--simulate` permet de faire un **dry run** : le bot parcourt et analyse les pages mais n'effectue aucune modification.

## Dépendances

| Paquet               | Usage                                      |
|----------------------|--------------------------------------------|
| `pywikibot`          | Interaction avec l'API MediaWiki           |
| `mwparserfromhell`   | Parsing du wikicode                        |

## Utilisation

```bash
# Nettoyer toutes les pages commençant par "a"
python Patrolling2.py -l a

# Nettoyer uniquement les pages en minuscule commençant par "b"
python Patrolling2.py -l b -c m

# Nettoyer les pages en majuscule commençant par "C" (simulation)
python Patrolling2.py -l C -c M --simulate
```

### Arguments CLI

| Argument              | Type     | Obligatoire | Description                                | Défaut |
|-----------------------|----------|:-----------:|--------------------------------------------|--------|
| `-l`, `--letter`      | `str`    | ✅          | Lettre de départ du scan                   | —      |
| `-c`, `--case`        | `str`    | ❌          | Filtre de casse : `m`, `M` ou `t`         | `t`    |
| `-s`, `--simulate`    | flag     | ❌          | Mode simulation (aucune modification)      | `false`|

## Logs

Les logs sont écrits dans `dicoado_maintenance.log` et affichés dans la console (`stdout`).

## Résumé de modification

Lorsqu'une page est modifiée, le résumé d'édition utilisé est :

> *Maintenance : Apostrophes, majuscules, ponctuation (Script Bot)*

## Différences avec AI_patrol.py

| Aspect                  | `AI_patrol.py`                    | `Patrolling2.py`             |
|-------------------------|-----------------------------------|------------------------------|
| Mode d'exécution        | Service continu (boucle async)    | Exécution manuelle unique    |
| Intelligence artificielle| Oui (Claude/Anthropic)           | Non                          |
| Discord                 | Oui (bot + commandes slash)       | Non                          |
| Portée                  | Modifications récentes            | Toutes les pages par lettre  |
| Cas d'usage             | Surveillance en temps réel        | Maintenance de masse         |

## Site wiki cible

Le bot opère sur le site `fr.dicoado.org` (famille `dicoado`, langue `fr`), configuré dans Pywikibot.
