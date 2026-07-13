import pywikibot
import mwparserfromhell
import re
import logging


class DicoAdoBot:
    def __init__(self):
        self.setup_logging()
        self.setup_site()

    def setup_logging(self):
        """Configure logging system"""
        logging.basicConfig(
            filename='dicoado_bot.log',
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        self.logger = logging.getLogger('DicoAdoBot')

    def setup_site(self):
        """Configure MediaWiki site connection"""
        print("Configuration de la connexion au site MediaWiki...")
        self.site = pywikibot.Site('fr', 'dicoado')
        self.robust_login()

    def robust_login(self, max_retries=3):
        """Robust login with multiple attempts"""
        for attempt in range(max_retries):
            try:
                print(f"Tentative de connexion {attempt + 1}/{max_retries}...")
                self.site.login()
                print("Connexion réussie.")
                return True
            except pywikibot.exceptions.NoUsername:
                self.logger.error("Nom d'utilisateur non configuré")
                print("Nom d'utilisateur non configuré.")
                return False
            except Exception as e:
                self.logger.error(f"Tentative de connexion échouée : {e}")
                print(f"Tentative de connexion échouée : {e}")
                if attempt < max_retries - 1:
                    continue
        return False

    def clean_text(self, text):
        """Nettoie le texte selon les règles du Dico des Ados"""
        print("Nettoyage du texte...")
        wikicode = mwparserfromhell.parse(text)
        for template in wikicode.filter_templates():
            if template.name.matches("Article"):
                self.clean_article_template(template)
        return str(wikicode)

    def clean_article_template(self, template):
        """Nettoie le modèle {{Article}}"""
        if template.has("def"):
            definitions = template.get("def").value.strip()
            cleaned_defs = self.clean_definitions(definitions)
            template.add("def", cleaned_defs)
        if template.has("ex"):
            examples = template.get("ex").value.strip()
            cleaned_examples = self.clean_examples(examples)
            template.add("ex", cleaned_examples)
        if template.has("légende"):
            legend = template.get("légende").value.strip()
            cleaned_legend = self.clean_legend(legend)
            template.add("légende", cleaned_legend)

    def clean_definitions(self, definitions):
        """Nettoie les définitions"""
        if not definitions.strip():
            return definitions

        # Séparer les définitions multiples
        definition_lines = definitions.strip().split('\n')
        cleaned_defs = []

        for line in definition_lines:
            original_line = line.strip()
            # Vérifie si la ligne avait déjà un '#'
            had_hash = original_line.startswith('#')

            # On enlève éventuellement le '#' pour appliquer les transformations
            if had_hash:
                hash_and_space = original_line[:2] if original_line[1:2] == ' ' else '#'
                d = original_line[1:].lstrip()  # Conserver l'espace après le '#', si présent
            else:
                hash_and_space = ''
                d = original_line.strip()

            # Retirer la ponctuation en fin de définition
            d = d.rstrip('.;,!?')

            # Remplacer les apostrophes simples isolées par des apostrophes courbes
            d = re.sub(r"(?<!')\'(?!')", "’", d)

            # Autoriser les définitions commençant par "État" ou "[[État]]" avec majuscule
            if d.startswith("État") or d.startswith("[[État]]"):
                cleaned_defs.append('#' + d if had_hash else d)
                continue

            # Mettre la première lettre alphabétique en minuscules
            for idx, char in enumerate(d):
                if char.isalpha():
                    d = d[:idx] + char.lower() + d[idx+1:]
                    break

            # Réinsérer le '#' uniquement si la ligne en avait un au départ
            cleaned_defs.append(hash_and_space + d if had_hash else d)

        return '\n'.join(cleaned_defs)

    def clean_examples(self, examples):
        """Nettoie les exemples"""
        if not examples.strip():
            return examples

        # Sépare les exemples multiples
        example_lines = examples.strip().split('\n')
        cleaned_exs = []

        for line in example_lines:
            original_line = line.strip()
            # Vérifie si la ligne avait déjà un '#'
            had_hash = original_line.startswith('#')

            # On enlève éventuellement le '#' pour appliquer les transformations
            if had_hash:
                hash_and_space = original_line[:2] if original_line[1:2] == ' ' else '#'
                ex = original_line[1:].lstrip()  # Conserver l'espace après le '#', si présent
            else:
                hash_and_space = ''
                ex = original_line.strip()

            # Remplacer les apostrophes simples isolées par des apostrophes courbes
            ex = re.sub(r"(?<!')\'(?!')", "’", ex)

            # Vérifier le gras sur le lemme
            if not re.search(r"'''.*?'''", ex):
                lemma = self.get_lemma(ex)
                if lemma:
                    # Créer un pattern qui capture le lemme et ses variations (pluriel, etc.)
                    lemma_pattern = f"{lemma}s?"
                    # Utiliser re.search pour trouver le mot complet
                    match = re.search(lemma_pattern, ex, re.IGNORECASE)
                    if match:
                        found_word = match.group(0)
                        ex = ex.replace(found_word, f"'''{found_word}'''")

            # Vérifier si le texte se termine par un signe de ponctuation
            if not ex.endswith(('.', '!', '?', '…', '}}')):
                ex += '.'

            # Réinsérer le '#' uniquement si la ligne en avait un au départ
            cleaned_exs.append(hash_and_space + ex if had_hash else ex)

        # Joindre les exemples avec des retours à la ligne
        return '\n'.join(cleaned_exs)

    def get_lemma(self, text):
        """Extrait le lemme (mot-vedette) de la page"""
        title = self.current_page.title() if hasattr(self, 'current_page') else ""
        if title:
            title = re.sub(r'\s*$.*?$', '', title)
            return title
        return None

    def clean_legend(self, legend):
        """Nettoie la légende"""
        if not legend.strip():
            return legend

        # Sauvegarde les modèles
        templates = []
        def save_template(match):
            templates.append(match.group(0))
            return f"__TEMPLATE__{len(templates)-1}__"

        # Protège les modèles
        legend = re.sub(r'\{\{[^}]+\}\}', save_template, legend)

        # Nettoyage de base
        legend = legend.strip()
        legend = re.sub(r"(?<!')\'(?!')", "’", legend)

        # Restaure les modèles sans ajouter de retour à la ligne
        for i, template in enumerate(templates):
            legend = legend.replace(f"__TEMPLATE__{i}__", template)

        return legend

    def process_page(self, page):
        print(f"Traitement de la page : {page.title()}")
        self.current_page = page
        try:
            original_text = page.text
            cleaned_text = self.clean_text(original_text)

            if cleaned_text != original_text:
                page.text = cleaned_text
                page.save("Nettoyage automatique (apostrophes, majuscules, ponctuation)")
                print(f"Page {page.title()} nettoyée.")
                self.logger.info(f"Page {page.title()} nettoyée.")
            else:
                print(f"Aucun changement nécessaire pour la page {page.title()}.")
                self.logger.info(f"Aucun changement nécessaire pour la page {page.title()}.")
        except Exception as e:
            print(f"Erreur lors du traitement de la page {page.title()} : {e}")
            self.logger.error(f"Erreur lors du traitement de la page {page.title()} : {e}")

    def run(self):
        """Demande une lettre et parcourt les pages correspondantes"""
        print("Démarrage du bot...")
        self.logger.info("Démarrage du bot...")

        # Demander une lettre et la casse au démarrage
        start_letter = input("Entrez une lettre pour commencer le nettoyage des pages : ").strip().lower()
        case_choice = input("Voulez-vous traiter les pages en minuscules (m), majuscules (M) ou les deux (t) ? ").strip().lower()

        if len(start_letter) != 1 or not start_letter.isalpha():
            print("Erreur : Vous devez entrer une seule lettre.")
            return

        # Dictionnaire des correspondances de lettres avec diacritiques
        diacritic_maps = {
            'a': '[aàáâãäåāăąǎǟǡǻȁȃạảấầẩẫậắằẳẵặ]',
            'e': '[eèéêëēĕėęěȅȇẹẻẽếềểễệ]',
            'i': '[iìíîïĩīĭįǐȉȋḭỉịớờởỡợ]',
            'o': '[oòóôõöōŏőơǒǫǭȍȏọỏốồổỗộớờởỡợ]',
            'u': '[uùúûüũūŭůűųưǔǖǘǚǜȕȗụủứừửữự]',
            'y': '[yýÿŷȳỳỵỷỹ]',
        }

        # Obtenir le pattern de recherche approprié
        search_pattern = diacritic_maps.get(start_letter, start_letter)

        # Ajuster le pattern selon le choix de casse
        if case_choice == 'm':
            search_pattern = f"^{search_pattern}"
            print(f"Nettoyage des pages commençant par {search_pattern} en minuscules")
        elif case_choice == 'M':
            search_pattern = f"^{search_pattern.upper()}"
            print(f"Nettoyage des pages commençant par {search_pattern} en majuscules")
        else:  # 't' pour tous
            search_pattern = f"^{search_pattern}"
            print(f"Nettoyage de toutes les pages commençant par {search_pattern} (minuscules ou majuscules)")

        self.logger.info(f"Nettoyage des pages commençant par : {search_pattern}")

        try:
            for page in self.site.allpages(namespace=0):
                page_title = page.title()

                # Vérifier si le titre correspond au pattern selon la casse choisie
                if case_choice == 'm':
                    if not re.match(search_pattern, page_title) or page_title[0].isupper():
                        continue
                elif case_choice == 'M':
                    if not re.match(search_pattern, page_title) or page_title[0].islower():
                        continue
                else:  # 't' pour tous
                    if not re.match(search_pattern, page_title, re.IGNORECASE):
                        continue

                print(f"Analyse de la page : {page_title}")
                self.process_page(page)

                # Vérifier si on a dépassé la lettre dans l'ordre alphabétique
                first_char = page_title[0].lower()
                if first_char > start_letter and first_char not in diacritic_maps.get(start_letter, ''):
                    break

        except Exception as e:
            print(f"Erreur fatale : {e}")
            self.logger.error(f"Erreur fatale : {e}")
        finally:
            print("Bot terminé.")
            self.logger.info("Bot terminé.")


if __name__ == '__main__':
    bot = DicoAdoBot()
    bot.run()