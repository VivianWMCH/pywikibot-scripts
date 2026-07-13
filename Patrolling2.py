import pywikibot
import mwparserfromhell
import re
import logging
import argparse
import sys

class DicoAdoMaintenanceBot:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.setup_logging()
        self.setup_site()
        # Common diacritics map for regex filtering if needed later
        self.diacritics_map = {
            'a': '[aàáâãäåāăąǎǟǡǻȁȃạảấầẩẫậắằẳẵặ]',
            'e': '[eèéêëēĕėęěȅȇẹẻẽếềểễệ]',
            'i': '[iìíîïĩīĭįǐȉȋḭỉịớờởỡợ]',
            'o': '[oòóôõöōŏőơǒǫǭȍȏọỏốồổỗộớờởỡợ]',
            'u': '[uùúûüũūŭůűųưǔǖǘǚǜȕȗụủứừửữự]',
            'y': '[yýÿŷȳỳỵỷỹ]',
        }

    def setup_logging(self):
        logging.basicConfig(
            filename='dicoado_maintenance.log',
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        self.logger = logging.getLogger('DicoAdoMaintenance')
        # Also print INFO to console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)

    def setup_site(self):
        try:
            self.site = pywikibot.Site('fr', 'dicoado')
            if not self.site.logged_in():
                self.site.login()
            self.logger.info(f"Connected as {self.site.username()}")
        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            sys.exit(1)

    def _clean_generic_line(self, text, is_def=False):
        """
        Generic cleaning logic shared between definitions and examples.
        """
        original_line = text.strip()
        if not original_line:
            return ""

        # 1. Handle hash/list marker
        had_hash = original_line.startswith('#')
        if had_hash:
            # Check if there is a space after hash
            has_space = original_line.startswith('# ')
            content = original_line[1:].strip()
            prefix = "# " if has_space else "#"
        else:
            content = original_line
            prefix = ""

        # 2. Basic cleanup
        content = content.rstrip('.;,!?') if is_def else content
        content = re.sub(r"(?<!')\'(?!')", "’", content) # Curved apostrophes

        # 3. Lowercasing logic (mostly for definitions)
        if is_def:
            # Exceptions for proper nouns or specific formats
            if not (content.startswith("État") or content.startswith("[[État]]")):
                 for idx, char in enumerate(content):
                    if char.isalpha():
                        content = content[:idx] + char.lower() + content[idx+1:]
                        break
        
        # 4. Example specific logic (bolding lemma, punctuation)
        if not is_def:
            # Bolding Lemma
            if self.current_page_title and not re.search(r"'''.*?'''", content):
                 lemma = self.get_lemma(self.current_page_title)
                 if lemma:
                     # Match lemma + s (plurals) case insensitive
                     content = re.sub(f"(?i)\\b({re.escape(lemma)}s?)\\b", r"'''\1'''", content)
            
            # Ensure punctuation at end of example
            if not content.endswith(('.', '!', '?', '…', '}}')) and content:
                content += '.'

        return f"{prefix}{content}" if had_hash else content

    def clean_block(self, text, is_def=False):
        """Splits a block of text (defs or examples) and cleans each line."""
        if not text.strip(): 
            return text
        
        lines = text.strip().split('\n')
        cleaned_lines = []
        for line in lines:
            cleaned_lines.append(self._clean_generic_line(line, is_def=is_def))
        
        return '\n'.join(cleaned_lines)

    def clean_text(self, text):
        wikicode = mwparserfromhell.parse(text)
        for template in wikicode.filter_templates():
            if template.name.matches("Article"):
                # Clean Definitions
                if template.has("def"):
                    old_def = template.get("def").value.strip()
                    new_def = self.clean_block(old_def, is_def=True)
                    template.add("def", new_def)
                
                # Clean Examples
                if template.has("ex"):
                    old_ex = template.get("ex").value.strip()
                    new_ex = self.clean_block(old_ex, is_def=False)
                    template.add("ex", new_ex)
                
                # Clean Legend
                if template.has("légende"):
                    legend = template.get("légende").value.strip()
                    # Basic apostrophe fix for legend
                    cleaned_legend = re.sub(r"(?<!')\'(?!')", "’", legend)
                    template.add("légende", cleaned_legend)

        return str(wikicode)

    def get_lemma(self, title):
        if title:
            return re.sub(r'\s*\(.*?\)$', '', title).strip()
        return None

    def process_page(self, page):
        self.current_page_title = page.title()
        self.logger.info(f"Scanning: {self.current_page_title}")
        
        try:
            old_text = page.text
            new_text = self.clean_text(old_text)

            if old_text != new_text:
                if self.simulate:
                    print(f"   [SIMULATION] Would edit {page.title()}")
                    # print(f"Change: {new_text}") # Uncomment to see diffs in console
                else:
                    page.text = new_text
                    page.save("Maintenance : Apostrophes, majuscules, ponctuation (Script Bot)")
                    self.logger.info(f"   [EDIT] Saved {page.title()}")
            else:
                pass # No changes needed

        except Exception as e:
            self.logger.error(f"Error processing {page.title()}: {e}")

    def run(self, letter, case_mode):
        self.logger.info(f"Starting Scan -> Letter: '{letter}', Mode: '{case_mode}'")
        
        # Smart Prefixing: If the user wants specific casing, we might still 
        # need to fetch the letter and filter in python, but fetching by prefix 
        # is infinitely faster than fetching allpages().
        
        # Note: MediaWiki search is case-sensitive for the first letter usually?
        # DicoAdo might be configured differently, but usually 'a' prefix gets 'avion' and 'Avion'.
        
        # We fetch everything starting with the letter
        pages = self.site.allpages(prefix=letter, namespace=0)

        count = 0
        for page in pages:
            title = page.title()
            
            # Safety check: ensure we didn't drift into the next letter 
            # (allpages sometimes continues if not strictly bounded, though prefix usually binds it)
            if not title.lower().startswith(letter.lower()):
                break

            # Filter based on Case Mode
            first_char = title[0]
            if case_mode == 'm' and not first_char.islower():
                continue # Skip Uppercase
            if case_mode == 'M' and not first_char.isupper():
                continue # Skip Lowercase

            self.process_page(page)
            count += 1

        self.logger.info(f"Job complete. Processed {count} pages.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="DicoAdo Maintenance Bot")
    parser.add_argument("-l", "--letter", type=str, required=True, help="Letter to scan (e.g., 'a')")
    parser.add_argument("-c", "--case", type=str, choices=['m', 'M', 't'], default='t', help="m=lower, M=Upper, t=total")
    parser.add_argument("-s", "--simulate", action="store_true", help="Dry run (no edits)")
    
    args = parser.parse_args()
    
    bot = DicoAdoMaintenanceBot(simulate=args.simulate)
    bot.run(args.letter, args.case)