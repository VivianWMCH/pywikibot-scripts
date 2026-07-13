#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pywikibot
import mwparserfromhell
import anthropic
import logging
import os
import time

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("Erreur : La variable d'environnement 'ANTHROPIC_API_KEY' n'est pas définie.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_example_from_claude(title, definition):
    """
    Fonction faisant un appel à l'IA Claude Haiku ou un autre service.
    Renvoie une courte phrase adaptée à des enfants de 8-10 ans,
    respectant la définition fournie (texte simple, clair, contexte).
    """
    client = anthropic.Client(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Tu es un assistant spécialisé dans la création d'exemples pour le Dico des Ados, un dictionnaire pour les 8-12 ans.

- Crée une phrase simple, concrète et claire utilisant le mot "{title}" dans le sens de la définition suivante : "{definition}".
- La phrase doit permettre de comprendre le sens du mot grâce au contexte.
- Utilise un langage adapté aux enfants de 8-12 ans, sans mots complexes ni langage soutenu.
- Mets le mot "{title}" en gras en l'entourant de trois apostrophes droits ('''{title}''')
- Commence la phrase par une majuscule et termine-la par une ponctuation.
- Si possible, utilise un maximum de mots différents de ceux déjà utilisés dans la définition donnée ci-dessus !
- **Ne produis qu'UNE SEULE COURTE phrase, sans texte supplémentaire.**"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )
        generated_text = response.content[0].text.strip()

        # Correction des cas où une apostrophe précède un mot en gras
        if f"l'''{title}'''" in generated_text or f"d'''{title}'''" in generated_text:
            # Ajouter un espace insécable (Unicode U+202F) après l'apostrophe pour éviter les conflits
            generated_text = generated_text.replace(f"l'''{title}'''", f"l’'''{title}'''")
            generated_text = generated_text.replace(f"d'''{title}'''", f"d’'''{title}'''")

        logger.info(f"Generated example for '{title}': {generated_text}")
        return generated_text

    except Exception as e:
        #print(f"Error generating example for '{title}': {e}")
        logger.error(f"Error generating example for '{title}': {e}")
        return "{{Exemple manquant}}"

def main():
    # Définissez le site cible :
    site = pywikibot.Site('fr', 'dicoado')
    site.login()  # Nécessite que vos informations de connexion soient configurées

    # Nom de la catégorie contenant les articles
    category_name = "Mot avec exemple manquant"

    # Récupère l'objet catégorie
    cat = pywikibot.Category(site, "Catégorie:" + category_name)

    # Parcourt toutes les pages de la catégorie
    for page in cat.articles():
        #print(f"Analyse de la page : {page.title()}")
        text = page.text
        wikicode = mwparserfromhell.parse(text)
        changed = False

        # Ajouter des logs de diagnostic
        template_found = False
        for template in wikicode.filter_templates():
            if template.name.matches("Article"):
                template_found = True
                # Parsing des définitions et exemples
                if template.has("def"):
                    def_block = str(template.get("def").value).strip()
                    def_lines = [d.strip() for d in def_block.split("#") if d.strip()]
                else:
                    def_lines = []

                if template.has("ex"):
                    ex_block = str(template.get("ex").value).strip()
                    ex_lines = [e.strip() for e in ex_block.split("#") if e.strip()]
                else:
                    ex_lines = []

                # S'assurer que la liste des exemples correspond à celle des définitions
                while len(ex_lines) < len(def_lines):
                    ex_lines.append("{{Exemple manquant}}")

                new_ex_lines = []
                for idx, ex_line in enumerate(ex_lines):
                    current_def = def_lines[idx] if idx < len(def_lines) else ""

                    if "exemple manquant" in ex_line.lower():
                        # On appelle la fonction IA pour générer l'exemple
                        generated_example = generate_example_from_claude(page.title(), current_def)
                        # On reconstruit la ligne en remplaçant l'exemple manquant
                        new_ex_lines.append(generated_example)
                        changed = True
                    else:
                        # On conserve l'exemple existant
                        new_ex_lines.append(ex_line)

                # Reconstruisons le bloc ex avec un “#” en début de chaque ligne
                updated_ex_block = "\n".join(f"#{line}" for line in new_ex_lines)
                # Mettre à jour le paramètre 'ex' du template
                template.add('ex', updated_ex_block, before=None, preserve_spacing=False)

        if not template_found:
            print(f"Aucun template 'Article' trouvé dans {page.title()}")
        elif not changed:
            print(f"Aucun exemple manquant trouvé dans {page.title()}")

        # Récupérer le texte mis à jour
        updated_text = str(wikicode)

        # Pas de sauvegarde si pas de changement
        if changed and updated_text != text:
            page.text = updated_text
            try:
                page.save(summary="Ajout d'exemples manquants (générés par IA) pour chaque définition")
                print(f"Page {page.title()} mise à jour.")
                time.sleep(60)  # 60-seconds delay between requests
            except pywikibot.exceptions.OtherPageSaveError as e:
                print(f"Erreur lors de la sauvegarde de la page {page.title()} : {e}")

if __name__ == "__main__":
    main()