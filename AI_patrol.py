# -*- coding: utf-8 -*-
"""
  Copyright (C) 2026 Vivian Epiney (Wikimedia CH)

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU Affero General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU Affero General Public License for more details.

  You should have received a copy of the GNU Affero General Public License
  along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
"""
DicoAdoBot — Bot de relecture/nettoyage pour le Dico des Ados,
relié à Discord et propulsé par Claude (Anthropic).
"""
import os
import re
import sys
import time
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from urllib.parse import quote
from functools import wraps, partial
from typing import Optional, List

import pywikibot
import discord
import anthropic
import mwparserfromhell
import difflib
from discord import app_commands

# --- CONFIGURATION (via variables d'environnement) ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("Erreur : La variable d'environnement 'DISCORD_TOKEN' n'est pas définie.")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("Erreur : La variable d'environnement 'ANTHROPIC_API_KEY' n'est pas définie.")

DISCORD_CHANNEL_ID_STR = os.getenv("DISCORD_CHANNEL_ID", "1317111951305736254")
try:
    DISCORD_CHANNEL_ID = int(DISCORD_CHANNEL_ID_STR)
except ValueError:
    raise ValueError(f"Erreur : 'DISCORD_CHANNEL_ID' ({DISCORD_CHANNEL_ID_STR}) doit être un entier valide.")

VANDALISM_ROLE_ID = os.getenv("VANDALISM_ROLE_ID", "772094056053473310")

# Proxy settings (si nécessaire)
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

# Modèle Claude (centralisé)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# Intervalles de surveillance
INITIAL_INTERVAL = 60
CHECK_INTERVAL = 300
ERROR_BACKOFF = 300
VANDALISM_THRESHOLD = 50
DISCORD_MAX_MSG_LENGTH = 2000
CLAUDE_TIMEOUT = 60  # Timeout en secondes pour les appels à l'API Claude

# Messages de bienvenue
WELCOME_MSG_USER = (
    "{{subst:Bienvenue}}<small>· <i class=\"fal fa-lg fa-signature\"></i></small>&nbsp;"
    "[[User:Vivian|'''Vivian''']]<small>&nbsp;<span class=\"zoom\">"
    "[[User talk:Vivian|<i class=\"far fa-lg fa-comment-dots\" style=\"vertical-align: 40%\"></i>]]"
    "</span></small>"
)
WELCOME_MSG_IP = "{{subst:Bienvenue IP}}"

# Liste des catégories autorisées (set pour des tests d'appartenance rapides)
ALLOWED_CATEGORIES = {
    "vie en société", "métiers", "communication", "informatique", "politique", "police et droit",
    "militaire", "économie", "commerce", "éducation", "transport", "moyens de transport",
    "mode et apparence", "bijoux", "coiffure", "vêtements", "sciences", "biologie", "animaux",
    "végétaux", "champignons", "microbes", "anatomie", "chimie", "physique", "astronomie",
    "météorologie", "géologie", "écologie", "mathématiques", "géographie", "histoire", "temps",
    "médecine et santé", "alimentation", "boissons", "aliments", "sports et loisirs", "arts",
    "musique", "instruments de musique", "genres musicaux", "littérature", "cinéma",
    "arts du spectacle", "danse", "théâtre", "arts plastiques", "arts graphiques", "couleurs",
    "fiction", "pensée et esprit", "sentiments", "comportement et caractère", "religion",
    "mythologie", "constructions", "objets", "langue et langage", "expressions", "figures de style",
    "conjugaison", "pronominal", "soutenu", "familier", "néologismes",
    "orthographe rectifiée", "mélioratif", "péjoratif", "uniquement au pluriel",
    "anglicismes", "mots empruntés au japonais", "autres emprunts lexicaux",
    "helvétismes", "autres régionalismes",
}

logger = logging.getLogger("DicoAdoBot")


# --------------------------------------------------------------------------- #
#  Prompts (centralisés)
# --------------------------------------------------------------------------- #
def build_manual_prompt(page_name: str, text: str) -> str:
    return (
        f"Tu es relecteur expert du Dico des Ados (dictionnaire 8-12 ans). "
        f"Analyse brièvement la page « {page_name} » avec bienveillance et rigueur.\n"
        "RÈGLES CLÉS :\n"
        f"• Définition : vocabulaire simple, phrases courtes, BEAUCOUP d'[[interliens]], "
        f"sans mot de la même famille que « {page_name} », plusieurs sens séparés par « # »\n"
        f"• Exemple : phrase complète avec « {page_name} » en contexte concret, ZÉRO interlien\n"
        f"• Synonymes/contraires : même classe grammaticale que « {page_name} », "
        "pertinents et adaptés aux enfants\n"
        "• Catégories : spécifiques, précises (pas trop générales)\n"
        "• INTERDIT : vulgarités, encyclopédisme, opinions, publicité\n\n"
        "FORMAT DE RÉPONSE (max 150 mots) :\n"
        "OK : [1-2 points forts, une ligne]\n"
        "À corriger : [uniquement les vrais problèmes, en puces, ou « rien »]\n"
        "Suggestion : [une reformulation concrète si nécessaire]\n"
        f"[Encouragement court avec « {page_name} » + émoji]\n\n"
        "Ignore les modèles {{Media}} et {{Liens externes}}. Tutoie. Sois bref et constructif.\n\n"
        f"{text[:2000]}..."
    )


def build_category_prompt(title: str) -> str:
    allowed_cats_str = ", ".join(sorted(ALLOWED_CATEGORIES))
    return (
        f'Tu es un relecteur pour le Dico des Ados. La page "{title}" n\'a pas de catégorie.\n'
        "Suggère 1 à 3 catégories PERTINENTES dans cette liste UNIQUEMENT :\n"
        f"{allowed_cats_str}\n"
        "Format: liste à puces simple sans intro."
    )


def build_analysis_prompt(title: str, diff_text: str, edit_summary: str) -> str:
    summary_info = (
        f"\n<résumé_modification>"
        f"{edit_summary if edit_summary else '(aucun résumé fourni)'}"
        f"</résumé_modification>"
    )
    return (
        f'Tu es relecteur expert du Dico des Ados (dictionnaire 8-12 ans). '
        f'Analyse brièvement la nouvelle version du mot "{title}" avec bienveillance et rigueur :\n'
        f"<diff>{diff_text}</diff>\n"
        f"{summary_info}\n\n"
        "Utilise un langage simple et direct. Concentre-toi sur :\n"
        "- Suppressions massives injustifiées, insultes, spam, non-sens, article quasiment vide, "
        "mot inexistant, publicité, contenu non francophone, définitions erronées -> marquer "
        "comme vandalisme !\n"
        "- Exactitude des définitions, exemples, synonymes/contraires\n"
        "- Présence d'exemples pertinents/concrets/parlants\n"
        "- Clarté et simplicité du vocabulaire pour les 8-12 ans\n"
        "- Catégorie éventuelle spécifique\n"
        "- Aspect éducatif et ludique\n\n"
        "Sois direct et constructif. Tutoie. RÉPONDS EN 100 MOTS MAX, FORMAT STRICT :\n"
        "- Problème/s : [Liste à puce courte ou « aucun »]\n"
        "- Suggestion/s : <Améliorations concrètes>\n"
        "- Risque de vandalisme : <0-100>% (plus RIEN ensuite!)"
    )


# --------------------------------------------------------------------------- #
#  Décorateur d'édition sécurisée
# --------------------------------------------------------------------------- #
def safe_edit(func):
    """Décorateur pour l'édition sécurisée des pages (synchrone).

    Contrat de retour uniformisé : retourne le résultat de `func`, ou `False`
    en cas d'échec définitif (jamais d'exception propagée à l'appelant).
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(self, *args, **kwargs)
            except pywikibot.exceptions.EditConflictError:
                logger.warning("Conflit d'édition (tentative %d/%d)", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return False
            except (pywikibot.exceptions.LockedPageError,
                    pywikibot.exceptions.SpamblacklistError) as e:
                logger.error("Erreur d'édition (page verrouillée / spam) : %s", e)
                return False
            except Exception as e:
                logger.error("Erreur inattendue dans %s : %s", func.__name__, e)
                logger.error(traceback.format_exc())
                return False
        return False
    return wrapper


# --------------------------------------------------------------------------- #
#  Vue Discord (bouton de révocation)
# --------------------------------------------------------------------------- #
class RevertView(discord.ui.View):
    def __init__(self, bot, page_title: str, old_revid: int, user: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.page_title = page_title
        self.old_revid = old_revid
        self.user_responsible = user

    @discord.ui.button(label="Révoquer", style=discord.ButtonStyle.danger, emoji="↩️")
    async def revert_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "Vous n'avez pas la permission de révoquer.", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            success = await self.bot.revert_page(
                self.page_title,
                self.old_revid,
                f"Révocation des modifications de "
                f"[[User:{self.user_responsible}|{self.user_responsible}]] "
                f"(via Discord par {interaction.user.name})",
            )
            if success:
                button.disabled = True
                button.label = "Révoqué"
                button.style = discord.ButtonStyle.secondary
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, view=self
                )
                await interaction.followup.send(
                    f"✅ La page **{self.page_title}** a été révoquée avec succès.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send("❌ Échec de la révocation.", ephemeral=True)
        except Exception as e:
            logger.error("Erreur lors de la révocation : %s", e)
            await interaction.followup.send(
                f"❌ Erreur lors de la révocation : {e}", ephemeral=True
            )


# --------------------------------------------------------------------------- #
#  Bot principal
# --------------------------------------------------------------------------- #
class DicoAdoBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        self.setup_site()
        self.setup_claude()
        self.setup_monitoring()

        self.executor = None  # ThreadPoolExecutor par défaut
        self._bot_username: Optional[str] = None

        # Statistiques et historique
        self.stats_pages_scanned = 0
        self.stats_edits_made = 0
        self.last_reviews: List[str] = []

    # ----- Setup ---------------------------------------------------------- #
    def setup_site(self):
        self.site = pywikibot.Site("fr", "dicoado")
        self.robust_login()

    def setup_claude(self):
        # Client asynchrone natif : plus besoin d'envelopper dans run_sync.
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    def setup_monitoring(self):
        self.last_check = datetime.now(tz=timezone.utc)
        self.first_run = True

    # ----- Connexion ------------------------------------------------------ #
    def ensure_logged_in(self):
        """S'assure que le bot est connecté, sinon tente de se reconnecter."""
        try:
            if not self.site.logged_in():
                logger.info("Session expirée, reconnexion...")
                self.robust_login()
        except Exception as e:
            logger.error("Erreur vérification login : %s", e)
            self.robust_login()

    def robust_login(self, max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                self.site.login()
                if self.site.logged_in():
                    self._bot_username = self.site.username()
                    logger.info("Connecté en tant que %s", self._bot_username)
                    return True
            except Exception as e:
                logger.error("Tentative de connexion %d/%d échouée : %s",
                             attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    time.sleep(5)
        logger.warning("⚠️ Échec de connexion après plusieurs tentatives")
        return False

    async def setup_hook(self):
        """Appelé par discord.py après l'init du client, avant la connexion.
        C'est l'endroit recommandé pour lancer les tâches de fond."""
        self.bg_task = asyncio.create_task(self.monitor_recent_changes())
        logger.info("Tâche de surveillance démarrée via setup_hook.")


    # ----- Helpers async -------------------------------------------------- #
    async def run_sync(self, func, *args, **kwargs):
        """Exécute une fonction synchrone (Pywikibot/API) de manière asynchrone."""
        loop = asyncio.get_running_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(self.executor, pfunc)

    @staticmethod
    def _extract_text(response) -> str:
        """Extrait le texte d'une réponse Claude de façon défensive."""
        if not response or not getattr(response, "content", None):
            return ""
        first = response.content[0]
        return getattr(first, "text", "") or ""

    async def _call_claude(self, max_tokens: int, messages: list) -> str:
        """Appel centralisé à l'API Claude avec timeout de sécurité."""
        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=max_tokens,
                    messages=messages,
                ),
                timeout=CLAUDE_TIMEOUT,
            )
            return self._extract_text(response)
        except asyncio.TimeoutError:
            logger.error("Timeout de l'appel Claude après %ds", CLAUDE_TIMEOUT)
            return ""
        except Exception as e:
            logger.error("Erreur lors de l'appel Claude : %s", e)
            return ""

    # ----- Actions Pywikibot (synchrones internes) ------------------------ #
    def _get_page_text_sync(self, page_title: str) -> Optional[str]:
        self.ensure_logged_in()
        page = pywikibot.Page(self.site, page_title)
        return page.text if page.exists() else None

    def _get_page_sync(self, page_title: str) -> pywikibot.Page:
        self.ensure_logged_in()
        return pywikibot.Page(self.site, page_title)

    def _get_old_version_sync(self, page_title: str, old_revid: int) -> str:
        self.ensure_logged_in()
        page = pywikibot.Page(self.site, page_title)
        try:
            return page.getOldVersion(old_revid) or ""
        except Exception as e:
            logger.error("Impossible de récupérer la révision %s de %s : %s",
                         old_revid, page_title, e)
            return ""

    def _get_random_page_sync(self) -> str:
        self.ensure_logged_in()
        pages = list(self.site.randompages(total=1, namespaces=0))
        return pages[0].title() if pages else ""

    @safe_edit
    def _save_page_sync(self, page: pywikibot.Page, text: str, summary: str) -> bool:
        self.ensure_logged_in()
        page.text = text
        page.save(summary)
        return True

    @safe_edit
    def _revert_page_sync(self, page_title: str, old_revid: int, summary: str) -> bool:
        self.ensure_logged_in()
        if old_revid <= 0:
            return False
        page = pywikibot.Page(self.site, page_title)
        old_text = page.getOldVersion(old_revid)
        if old_text is None:
            return False
        page.text = old_text
        page.save(summary)
        return True

    def _get_recent_changes_sync(self, start, end):
        self.ensure_logged_in()
        return list(self.site.recentchanges(
            start=start, end=end, reverse=True,
            namespaces=0, minor=False, bot=False,
        ))

    def _check_user_edit_count_sync(self, username: str) -> int:
        self.ensure_logged_in()
        return pywikibot.User(self.site, username).editCount()

    def _is_ip_sync(self, username: str) -> bool:
        self.ensure_logged_in()
        return pywikibot.User(self.site, username).isAnonymous()

    @safe_edit
    def _post_welcome_message_sync(self, username: str, message: str) -> bool:
        self.ensure_logged_in()
        talk_page = pywikibot.User(self.site, username).getUserTalkPage()
        if not talk_page.exists():
            talk_page.text = message
            talk_page.save("Bienvenue sur le Dico des Ados !")
            return True
        return False

    # ----- Wrappers asynchrones ------------------------------------------ #
    async def get_page_text(self, page_title: str) -> Optional[str]:
        return await self.run_sync(self._get_page_text_sync, page_title)

    async def get_random_page(self) -> str:
        return await self.run_sync(self._get_random_page_sync)

    async def save_page(self, page_title: str, text: str, summary: str) -> bool:
        page = await self.run_sync(self._get_page_sync, page_title)
        result = await self.run_sync(self._save_page_sync, page, text, summary)
        if result:
            self.stats_edits_made += 1
        return bool(result)

    async def revert_page(self, page_title: str, old_revid: int, summary: str) -> bool:
        result = await self.run_sync(self._revert_page_sync, page_title, old_revid, summary)
        if result:
            self.stats_edits_made += 1
        return bool(result)

    # ----- Traitement de texte ------------------------------------------- #
    def replace_apostrophes(self, text: str) -> str:
        return re.sub(r"(?<!')'(?!')", "’", text)

    def clean_text(self, text: str, page_title: Optional[str] = None) -> str:
        wikicode = mwparserfromhell.parse(text)
        for template in wikicode.filter_templates():
            if template.name.matches("Article"):
                self.clean_article_template(template, page_title)
        return str(wikicode)

    def clean_article_template(self, template, page_title: Optional[str] = None):
        if template.has("def"):
            definitions = template.get("def").value.strip()
            template.add("def", self.clean_definitions(definitions))
        if template.has("ex"):
            examples = template.get("ex").value.strip()
            template.add("ex", self.clean_examples(examples, page_title))
        if template.has("légende"):
            legend = template.get("légende").value.strip()
            template.add("légende", self.clean_legend(legend))

    def clean_definitions(self, definitions: str) -> str:
        if not definitions.strip():
            return definitions
        cleaned = []
        for line in definitions.strip().split("\n"):
            original = line.strip()
            match = re.match(r"^(#+)(\s*)", original)
            if match:
                hashes, spaces = match.group(1), match.group(2)
                d = original[len(hashes) + len(spaces):].strip()
                prefix = hashes + spaces
            else:
                d = original
                prefix = ""

            d = d.rstrip(".;,!?")
            d = self.replace_apostrophes(d)

            if d:
                if d.startswith("[[") and "]]" in d:
                    end_link = d.find("]]")
                    link_content = d[2:end_link]
                    if "|" not in link_content and link_content:
                        link_content = link_content[0].lower() + link_content[1:]
                        d = f"[[{link_content}]]{d[end_link + 2:]}"
                    else:
                        rest = d[end_link + 2:]
                        for idx, char in enumerate(rest):
                            if char.isalpha():
                                d = d[:end_link + 2 + idx] + char.lower() + rest[idx + 1:]
                                break
                else:
                    for idx, char in enumerate(d):
                        if char.isalpha():
                            d = d[:idx] + char.lower() + d[idx + 1:]
                            break

            cleaned.append(prefix + d)
        return "\n".join(cleaned)

    def clean_examples(self, examples: str, page_title: Optional[str] = None) -> str:
        if not examples.strip():
            return examples
        cleaned = []
        for line in examples.strip().split("\n"):
            original = line.strip()
            match = re.match(r"^(#+)(\s*)(.*)", original)
            if match:
                hashes, spaces, ex = match.group(1), match.group(2), match.group(3)
            else:
                hashes, spaces, ex = "", "", original

            if not ex or "manquant}}" in ex:
                cleaned.append(original)
                continue

            # Protection des templates
            templates: List[str] = []

            def save_template(m):
                templates.append(m.group(0))
                return f"__TEMPLATE_{len(templates) - 1}__"

            ex = re.sub(r"\{\{[^{}]*\}\}", save_template, ex)
            ex = self.replace_apostrophes(ex)

            if ex:
                ex = ex[0].upper() + ex[1:]

            ex_clean = re.sub(r"(?:__TEMPLATE_\d+__\s*)+$", "", ex).rstrip()
            if not ex_clean.endswith((".", "!", "?", "…")):
                match_end = re.search(r"(\s*)(?:__TEMPLATE_\d+__\s*)+$", ex)
                if match_end:
                    insert_pos = match_end.start()
                    ex = ex[:insert_pos] + "." + ex[insert_pos:]
                else:
                    ex += "."

            for i, tmpl in enumerate(templates):
                ex = ex.replace(f"__TEMPLATE_{i}__", tmpl)

            # Mise en gras du lemme
            if page_title and not re.search(r"'''.*?'''", ex):
                lemma = self.get_lemma(page_title)
                if lemma:
                    match_lemma = re.search(rf"{re.escape(lemma)}s?", ex, re.IGNORECASE)
                    if match_lemma:
                        found_word = match_lemma.group(0)
                        ex = ex.replace(found_word, f"'''{found_word}'''")

            cleaned.append(f"{hashes}{spaces}{ex}")
        return "\n".join(cleaned)

    def clean_legend(self, legend: str) -> str:
        if not legend.strip():
            return legend
        templates: List[str] = []

        def save_template(m):
            templates.append(m.group(0))
            return f"__TEMPLATE_{len(templates) - 1}__"

        legend = re.sub(r"\{\{[^}]+\}\}", save_template, legend)
        legend = self.replace_apostrophes(legend.strip())
        for i, tmpl in enumerate(templates):
            legend = legend.replace(f"__TEMPLATE_{i}__", tmpl)
        return legend

    def get_lemma(self, title: str) -> Optional[str]:
        if title:
            return re.sub(r"\s*\(.*?\)$", "", title).strip()
        return None

    # ----- Boucles principales ------------------------------------------- #
    async def run_bot(self):
        logger.info("Démarrage du bot de surveillance DicoAdo...")
        try:
            async with self:                      # ferme proprement la session aiohttp
                await self.start(DISCORD_TOKEN)
        except Exception as e:
            logger.error("Erreur fatale dans run_bot() : %s", e)
            raise

    async def on_ready(self):
        logger.info("Bot connecté à Discord en tant que %s", self.user)
        try:
            synced = await self.tree.sync()
            logger.info("Synchronisé %d commandes slash.", len(synced))
        except Exception as e:
            logger.error("Erreur de synchronisation des commandes : %s", e)

    async def monitor_recent_changes(self):
        await self.wait_until_ready()
        while True:
            try:
                await self.run_sync(self.ensure_logged_in)
                await self.check_recent_changes()
                interval = INITIAL_INTERVAL if self.first_run else CHECK_INTERVAL
                self.first_run = False
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error("Erreur dans la boucle principale : %s", e)
                logger.error(traceback.format_exc())
                await asyncio.sleep(ERROR_BACKOFF)

    async def check_recent_changes(self):
        now = datetime.now(tz=timezone.utc)
        logger.info("[%s] Vérification des modifications...", now.strftime("%H:%M:%S"))
        try:
            changes = await self.run_sync(self._get_recent_changes_sync, self.last_check, now)
            if not changes:
                logger.info("Aucune modification récente.")

            for change in changes:
                await self.process_change(change)

            # Mis à jour uniquement après traitement complet réussi.
            self.last_check = now
        except Exception:
            logger.error("Erreur dans check_recent_changes : %s", traceback.format_exc())

    async def process_change(self, change: dict):
        title = change.get("title") if change else None
        try:
            if not change or not title:
                return
            if change.get("logtype") == "delete":
                return

            user = change.get("user") or "(inconnu)"
            comment = change.get("comment", "")

            # Anti-boucle : ignorer les modifications faites par le bot lui-même.
            if user and self._bot_username and user == self._bot_username:
                logger.debug("Modification du bot ignorée sur %s", title)
                return

            self.stats_pages_scanned += 1

            current_text = await self.get_page_text(title)
            if current_text is None:
                return

            logger.info("Traitement de %s par %s", title, user)

            # 1. Accueil
            if change.get("ns") == 0 and user:
                welcome_done = False
                is_ip = await self.run_sync(self._is_ip_sync, user)
                if is_ip:
                    welcome_done = await self.run_sync(
                        self._post_welcome_message_sync, user, WELCOME_MSG_IP
                    )
                else:
                    edit_count = await self.run_sync(self._check_user_edit_count_sync, user)
                    if edit_count == 1:
                        welcome_done = await self.run_sync(
                            self._post_welcome_message_sync, user, WELCOME_MSG_USER
                        )
                if welcome_done:
                    logger.info("Message de bienvenue envoyé à %s", user)

            # 2. Nettoyage
            cleaned_text = self.clean_text(current_text, page_title=title)
            if cleaned_text != current_text:
                saved = await self.save_page(
                    title, cleaned_text,
                    "Nettoyage automatique (apostrophes, majuscules, ponctuation)",
                )
                if saved:
                    logger.info("Page %s nettoyée", title)
                    current_text = cleaned_text

            # 3. Catégories
            suggested_categories: List[str] = []
            if "|cat=" not in current_text and change.get("ns") == 0:
                suggested_categories = await self.get_category_suggestions(title, current_text)

            # 4. Analyse IA
            old_revid = change.get("old_revid", 0)
            old_text = ""
            if old_revid > 0:
                old_text = await self.run_sync(self._get_old_version_sync, title, old_revid)

            await self.analyze_and_report(
                title, old_text, current_text, user, old_revid, suggested_categories, comment
            )
        except Exception as e:
            logger.error("Erreur lors du traitement de %s : %s", title, e)
            logger.error(traceback.format_exc())

    async def process_page(self, page_name: str):
        """Traitement manuel d'une page."""
        try:
            self.stats_pages_scanned += 1
            text = await self.get_page_text(page_name)
            if not text:
                await self.send_discord_message(f"Page {page_name} introuvable.")
                return

            cleaned = self.clean_text(text, page_title=page_name)
            if cleaned != text:
                saved = await self.save_page(
                    page_name, cleaned,
                    "Nettoyage automatique (apostrophes, majuscules, ponctuation)",
                )
                if saved:
                    text = cleaned
                    await self.send_discord_message(f"✅ Page **{page_name}** nettoyée.")

            analysis = await self._call_claude(
                max_tokens=600,
                messages=[{"role": "user", "content": build_manual_prompt(page_name, text)}],
            )
            if not analysis:
                await self.send_discord_message(
                    f"⚠️ Réponse vide de l'IA pour **{page_name}**."
                )
                return
            await self.send_discord_message(
                f"📝 Rapport demandé pour **{page_name}** :\n{analysis}"
            )
        except Exception as e:
            logger.error("Erreur dans process_page(%s) : %s", page_name, e)
            await self.send_discord_message(f"❌ Erreur : {e}")

    async def get_category_suggestions(self, title: str, text: str) -> List[str]:
        try:
            content = await self._call_claude(
                max_tokens=150,
                messages=[{"role": "user", "content": build_category_prompt(title)}],
            )
            if not content:
                return []
            return [
                line.strip().replace("- ", "").replace("* ", "")
                for line in content.split("\n")
                if line.strip().startswith(("-", "*"))
            ]
        except Exception as e:
            logger.error("Erreur suggestions de catégories pour %s : %s", title, e)
            return []

    async def analyze_and_report(self, title: str, old_text: str, new_text: str,
                                 user: str, old_revid: int, categories: List[str],
                                 edit_summary: str = ""):
        self.last_reviews.append(
            f"[{datetime.now().strftime('%H:%M')}] **{title}** (par {user})"
        )
        if len(self.last_reviews) > 5:
            self.last_reviews.pop(0)

        diff = difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(), lineterm=""
        )
        diff_text = "\n".join(diff)

        try:
            analysis = await self._call_claude(
                max_tokens=600,
                messages=[{
                    "role": "user",
                    "content": build_analysis_prompt(title, diff_text, edit_summary),
                }],
            )
            if not analysis:
                logger.warning("Réponse d'analyse vide pour %s", title)
                return

            encoded_title = quote(title.replace(" ", "_"))
            summary_display = (
                f"\n📝 **Résumé** : _{edit_summary}_" if edit_summary
                else "\n📝 **Résumé** : _(aucun)_"
            )
            msg = (
                f"🔍 **Analyse des modifications récentes** pour la page "
                f"[{title}](https://fr.dicoado.org/dico/{encoded_title}) "
                f"par {user}{summary_display}\n\n{analysis}"
            )
            if categories:
                msg += "\n\n**💡 Catégories suggérées** :\n" + "\n".join(
                    f"- `|cat={c}`" for c in categories
                )

            channel = await self._resolve_channel()
            if not channel:
                logger.error("Salon Discord introuvable (ID %s)", DISCORD_CHANNEL_ID)
                return

            # Tronquer le message si nécessaire (limite Discord)
            if len(msg) > DISCORD_MAX_MSG_LENGTH:
                msg = msg[:DISCORD_MAX_MSG_LENGTH - 4] + " …"

            # N'afficher le bouton Révoquer que si une révision antérieure existe
            if old_revid > 0:
                view = RevertView(self, title, old_revid, user)
                await channel.send(msg, view=view)
            else:
                await channel.send(msg)

            match = re.search(r"Risque de vandalisme\s*:\s*(\d+)%", analysis)
            if match and int(match.group(1)) >= VANDALISM_THRESHOLD:
                await channel.send(
                    f"<@&{VANDALISM_ROLE_ID}> ⚠️ **Vandalisme probable** sur [[{title}]] !"
                )
        except Exception as e:
            logger.error("Erreur lors du rapport pour %s : %s", title, e)
            logger.error(traceback.format_exc())

    async def _resolve_channel(self) -> Optional[discord.abc.Messageable]:
        channel = self.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            return channel
        try:
            return await self.fetch_channel(DISCORD_CHANNEL_ID)
        except Exception as e:
            logger.error("Impossible de récupérer le salon %s : %s", DISCORD_CHANNEL_ID, e)
            return None

    async def send_discord_message(self, message: str):
        if len(message) > DISCORD_MAX_MSG_LENGTH:
            message = message[:DISCORD_MAX_MSG_LENGTH - 4] + " …"
        channel = await self._resolve_channel()
        if channel:
            await channel.send(message)


# --------------------------------------------------------------------------- #
#  Configuration du logging
# --------------------------------------------------------------------------- #
def setup_logging():
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler("dicoado_bot.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


# --------------------------------------------------------------------------- #
#  Commandes slash
# --------------------------------------------------------------------------- #
bot = DicoAdoBot()


@bot.tree.command(name="verifie", description="Vérifie manuellement une page")
@app_commands.describe(page_name="Titre de la page")
async def verifie(interaction: discord.Interaction, page_name: str):
    await interaction.response.send_message(f"⏳ Vérification de **{page_name}**...")
    await bot.process_page(page_name)


@bot.tree.command(name="stat", description="Statistiques du bot")
async def stat(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"**Stats** 📊\n- Pages vues : {bot.stats_pages_scanned}\n"
        f"- Éditions auto : {bot.stats_edits_made}"
    )


@bot.tree.command(name="aide", description="Liste des commandes")
async def aide(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Commandes** 🛠️\n`/verifie [page]`\n`/stat`\n`/alea`\n`/rc`"
    )


@bot.tree.command(name="alea", description="Page au hasard")
async def alea(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        page = await bot.get_random_page()
        if page:
            await interaction.followup.send(f"🎲 Page trouvée : **{page}**. Analyse...")
            await bot.process_page(page)
        else:
            await interaction.followup.send("Erreur : impossible de trouver une page.")
    except Exception as e:
        logger.error("Erreur dans /alea : %s", e)
        await interaction.followup.send(f"❌ Erreur : {e}")


@bot.tree.command(name="rc", description="Dernières modifications")
async def rc(interaction: discord.Interaction):
    if not bot.last_reviews:
        await interaction.response.send_message("Aucune donnée récente.")
    else:
        await interaction.response.send_message(
            "**Récents** 🕒\n" + "\n".join(bot.last_reviews)
        )


# --------------------------------------------------------------------------- #
#  Point d'entrée
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(bot.run_bot())
    except KeyboardInterrupt:
        logger.info("Arrêt du bot...")
