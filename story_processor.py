import csv
import json
import os
import random
import re

import yaml
from databases.personnage_database import PersonnageDatabase
from databases.story_database import StoryDatabase
from llm_client import LLMClient
from prompt import intro_generique, outro_generique, prompt_intro, prompt_outro, sys_prompt_intro, sys_prompt_outro
from story_builder import StoryBuilder
from story_image_generator import StoryImageGenerator


class StoryProcessor:
    def __init__(self, config_path="config.yaml"):
        self.llm = LLMClient()
        self.story_image_generator = StoryImageGenerator()
        self.builder = StoryBuilder()
        self.story_db = StoryDatabase()
        self.character_db = PersonnageDatabase()
        self.config = self._load_config(config_path)

    def _load_config(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ Fichier de configuration introuvable : {path}")
            exit(1)

    def generate_intro_outro(self, story, part):
        sys_prompt = sys_prompt_intro if part == "intro" else sys_prompt_outro
        prompt_template = prompt_intro if part == "intro" else prompt_outro
        prompt_final = prompt_template.format(story=story)

        response = self.llm.chat(self.config["ia_generative"], sys_prompt, prompt_final)

        if part == "intro":
            return self._extract_or_default(response, "text_intro", intro_generique)
        else:
            return self._extract_or_default(response, "text_outro", outro_generique)

    def _extract_or_default(self, response, key, fallback):
        if response and f"{key} :" in response:
            print(f"{key} généré : {response}")
            return response.split(f"{key} :", 1)[1].strip()
        else:
            print(f"{key} générique utilisé.")
            return fallback

    def get_or_create_intro_outro(self, file_path, story_parts):
        folder = os.path.dirname(file_path)
        intro_outro_path = os.path.join(folder, "intro_outro.txt")

        if os.path.exists(intro_outro_path):
            with open(intro_outro_path, encoding="utf-8") as f:
                content = f.read()
            intro = content.split("Intro :", 1)[1].split("Outro :", 1)[0].strip()
            outro = content.split("Outro :", 1)[1].strip()
        else:
            full_story = "\n\n".join(story_parts)
            intro = self.generate_intro_outro(full_story, "intro")
            outro = self.generate_intro_outro(full_story, "outro")
            with open(intro_outro_path, "w", encoding="utf-8") as f:
                f.write(f"Intro : {intro}\n\nOutro : {outro}")

        return intro, outro

    def process_story_file(self, file_path):
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        # 1. Récupérer le titre
        if not lines or not lines[0].lower().startswith("titre :"):
            raise ValueError("La première ligne doit commencer par 'Titre :'")

        title = lines[0].split("Titre :", 1)[1].strip()

        # 2. Lire les lignes suivantes
        full_content = "".join(lines[1:])

        # 3. Séparer le texte et la section Personnages
        if "Personnages :" in full_content:
            story_text, character_section = full_content.split("Personnages :", 1)
        else:
            story_text, character_section = full_content, ""

        # 4. Découper le texte par pages
        parts = [p.strip() for p in story_text.split("!!!new page!!!") if p.strip()]

        # 4.1 intro et outro
        intro, outro = self.get_or_create_intro_outro(file_path, parts)

        # 4.2 youtube info
        folder = os.path.dirname(file_path)
        story = "\n\n".join(parts)
        self.builder.generate_youtube_info(folder, story)

        for part in parts:
            self.story_db.add_or_update_story(title, part)

        # 5. Traiter les personnages
        self._process_characters(character_section, title)

        return title

    def _process_characters(self, text, title):
        pattern = re.compile(
            r"nouveau personnage *: *(.*?)\s*"
            r"description du nouveau personnage *: *(.*?)(?=\n\n|nouveau personnage *:|$)",
            re.DOTALL | re.IGNORECASE,
        )
        matches = pattern.findall(text)

        for names, description in matches:
            name_list = [n.strip() for n in names.split(",") if n.strip()]
            description = description.strip()
            print(f"👤 Personnage détecté : {name_list} — {description}")
            self.character_db.add_or_update(title, name_list, description)

    def enrich_story_with_descriptions(self, story_parts):
        for element in story_parts:
            title = element["titre"]
            epc = element["epc"]
            original_text = element["text_part"]
            enriched_text = original_text
            modified = set()

            characters = self.character_db.get_by_title(title)

            for char in characters:
                try:
                    names = json.loads(char["noms"])
                except Exception as e:
                    print(f"⚠️ Erreur JSON pour {char} : {e}")
                    continue

                description = char["description"]
                for name in names:
                    if name in modified:
                        continue

                    pattern = r"\b" + re.escape(name) + r"\b"

                    def replacer(match):
                        modified.update(names)
                        return f"{match.group(0)} ({description})"

                    enriched_text, count = re.subn(pattern, replacer, enriched_text, count=1)
                    if count > 0:
                        break

            self.story_db.add_or_update_story(titre=title, text_part=original_text, text_with_description=enriched_text, epc=epc)
            print(f"✅ Texte enrichi pour epc : {epc}")

    def add_prompts_to_story(self, story_parts, theme=None):
        for element in story_parts:
            epc = element["epc"]
            # title = element["titre"]
            enriched_text = element.get("text_with_description", "")

            if not enriched_text:
                print(f"⚠️ Aucun texte enrichi pour epc : {epc}")
                continue

            prompt, neg_prompt = self.story_image_generator.get_picture_prompt(self.config["ia_generative"], enriched_text, theme)
            self.story_db.update_prompts(epc, prompt, neg_prompt)
            print(f"🧠 Prompt ajouté pour epc : {epc}")

    def insert_new_story_in_db(self, folder_name):
        story_path = os.path.join(self.config.get("base_story_dir", ""), folder_name, f"{folder_name}.txt")
        title = self.process_story_file(story_path)
        parts = self.story_db.get_story_parts(title)

        self.enrich_story_with_descriptions(parts)

        parts_with_description = self.story_db.get_story_parts(title)
        # Chemin du fichier CSV
        csv_path = os.path.join(self.config.get("base_story_dir", ""), folder_name, "prompts.csv")

        # Si le fichier existe déjà, on le recrée PAS
        if not os.path.exists(csv_path):
            with open(csv_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["epc", "text_with_description"])  # Header

                for part in parts_with_description:
                    epc = part.get("epc")  # À ajuster selon ta structure réelle
                    text_with_description = part.get("text_with_description")
                    if epc and text_with_description:
                        print(f"{epc} → {text_with_description}")
                        writer.writerow([epc, text_with_description])
        else:
            print(f"[INFO] Le fichier prompts.csv existe déjà pour {folder_name}, on ne le recrée pas.")

        # on génère les prompts
        print(f"📈 Prêt à générer les prompts pour {len(parts)} parties (x2 calls)")

        confirm = input("Continuer ? (oui/non) : ").strip().lower()
        if confirm != "oui":
            print("🚫 Process interrompu.")
            return title

        theme = self.config.get("theme")
        if self.config.get("random"):
            theme = random.choice(self.config.get("all_themes", []))

        updated_parts = self.story_db.get_story_parts(title)
        self.add_prompts_to_story(updated_parts, theme)
        return title

    def print_story_info(self, title):
        self.character_db.print_by_title(title)
        self.story_db.print_story_by_title(title)
