# Exemples_manquants.py — Générateur d'exemples IA

> Script automatique qui génère des phrases d'exemple pour les articles du [Dico des Ados](https://fr.dicoado.org) dont les exemples sont manquants, en utilisant l'IA Claude (Anthropic).

## Description

`Exemples_manquants.py` parcourt tous les articles de la catégorie **« Mot avec exemple manquant »** et utilise l'API **Claude** pour générer automatiquement des phrases d'exemple adaptées aux enfants de 8-12 ans. Chaque exemple est créé en fonction de la définition correspondante dans le template `{{Article}}`.

## Fonctionnement

```
Catégorie "Mot avec exemple manquant"
  └─ Pour chaque page :
       ├─ Parse le template {{Article}} (mwparserfromhell)
       ├─ Compare le nombre de définitions (|def=) et d'exemples (|ex=)
       ├─ Pour chaque {{Exemple manquant}} trouvé :
       │    ├─ Envoie la définition correspondante à Claude
       │    ├─ Reçoit une phrase d'exemple générée
       │    └─ Remplace le placeholder par l'exemple
       └─ Sauvegarde la page si des modifications ont été faites
```

## Règles de génération (prompt IA)

Le prompt envoyé à Claude impose les contraintes suivantes :

- ✅ Phrase **simple, concrète et claire** adaptée aux 8-12 ans
- ✅ Le mot est mis en **gras** (`'''mot'''`)
- ✅ Le contexte de la phrase doit permettre de **comprendre le sens** du mot
- ✅ Vocabulaire **différent** de celui de la définition
- ✅ **Une seule courte phrase**, commençant par une majuscule et terminant par une ponctuation
- ❌ Pas de mots complexes ni de langage soutenu

## Gestion des apostrophes en wikicode

Le script gère un cas délicat du wikicode MediaWiki : lorsqu'une apostrophe précède directement un mot en gras (`l'''exemple'''`), cela crée un conflit de parsing. Le script insère automatiquement une apostrophe supplémentaire pour éviter ce problème.

## Dépendances

| Paquet               | Usage                                      |
|----------------------|--------------------------------------------|
| `pywikibot`          | Interaction avec l'API MediaWiki           |
| `mwparserfromhell`   | Parsing du wikicode                        |
| `anthropic`          | Appels à l'API Claude (génération IA)      |

## Variables d'environnement

| Variable              | Obligatoire | Description                    |
|-----------------------|:-----------:|--------------------------------|
| `ANTHROPIC_API_KEY`   | ✅          | Clé API Anthropic (Claude)     |

## Modèle IA utilisé

Le script utilise le modèle `claude-3-5-sonnet-20241022` avec un `max_tokens` de **50** (pour forcer des réponses courtes).

## Utilisation

```bash
# Configurer la clé API
export ANTHROPIC_API_KEY="votre_clé"

# Lancer le script
python Exemples_manquants.py
```

Le script :
1. Se connecte au site `fr.dicoado.org` via Pywikibot
2. Récupère toutes les pages de la catégorie « Mot avec exemple manquant »
3. Génère et insère les exemples manquants
4. Sauvegarde chaque page modifiée avec un délai de **60 secondes** entre les sauvegardes (pour respecter les limites de l'API)

## Résumé de modification

> *Ajout d'exemples manquants (générés par IA) pour chaque définition*

## Fallback en cas d'erreur

Si l'appel à Claude échoue, le placeholder `{{Exemple manquant}}` est conservé (aucune donnée erronée n'est insérée).

## Logs

Les logs sont affichés dans la console via le module `logging` (niveau `INFO`).

## Site wiki cible

Le bot opère sur le site `fr.dicoado.org` (famille `dicoado`, langue `fr`), configuré dans Pywikibot.
