import os

import yaml
from llm_client import LLMClient
from prompt import (
    prompt_generate_history,
    prompt_youtube_description,
    prompt_youtube_tag,
    prompt_youtube_title,
    system_prompt_generate_history,
)


class StoryBuilder:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.llm_client = LLMClient()
        self.config = self._load_config()
        self.base_story_dir = self.config.get("base_story_dir", "") if self.config else ""

    def _load_config(self):
        try:
            with open(self.config_path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ Le fichier '{self.config_path}' n'existe pas.")
            return None

    def create_story_folder(self, folder_name):
        if not self.config:
            print("⚠️ Impossible de créer les dossiers, configuration non chargée.")
            return False

        os.makedirs(self.base_story_dir, exist_ok=True)
        story_path = os.path.join(self.base_story_dir, folder_name)

        if not os.path.exists(story_path):
            os.makedirs(os.path.join(story_path, "img"))
            os.makedirs(os.path.join(story_path, "voice"))
            os.makedirs(os.path.join(story_path, "video_parts"))
            print(f"📁 Dossier '{folder_name}' créé avec /img, /voice et /video_parts.")

            # Création du fichier texte initial
            txt_path = os.path.join(story_path, f"{folder_name}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"Fichier de la story : {folder_name}\n")
            print(f"📝 Fichier '{folder_name}.txt' créé.")
        else:
            print(f"ℹ️ Le dossier '{folder_name}' existe déjà.")

        return True

    def write_story_from_idea(self, folder_name, idea):
        if not self.config:
            print("⚠️ Configuration manquante, arrêt.")
            return None, None

        story_path = os.path.join(self.base_story_dir, folder_name)
        txt_path = os.path.join(story_path, f"{folder_name}.txt")

        print("✨ Génération de l'histoire à partir de l'idée :", idea)

        prompt_generate_history.format(idea=idea)

        story = self.llm_client.chat(
            model=self.config["ia_generative"], user_prompt=idea, system_prompt=system_prompt_generate_history
        )

        if story:
            with open(txt_path, "a", encoding="utf-8") as f:
                f.write("\n\n=== Histoire générée ===\n\n")
                f.write(story)
            print(f"✅ Histoire ajoutée dans : {txt_path}")
            return story, txt_path
        else:
            print("❌ Échec de la génération de l’histoire.")
            return None, None

    def generate_youtube_info(self, folder_name, story_text):
        """
        Génère et écrit un fichier YouTube SEO (titre, description, tags) basé sur une histoire.
        """
        if not self.config:
            print("⚠️ Configuration introuvable.")
            return

        model = self.config.get("ia_generative")
        output_path = os.path.join(folder_name, "youtube_info.txt")

        if os.path.exists(output_path):
            print(f"⏭️ Fichier déjà existant : {output_path} → skip")
            return

        print("🎯 Génération SEO YouTube en cours...")

        # Préparation des prompts
        prompt_tag = prompt_youtube_tag.replace("{story}", story_text)
        prompt_title = prompt_youtube_title.replace("{story}", story_text)
        prompt_description = prompt_youtube_description.replace("{story}", story_text)

        try:
            tags = self.llm_client.chat(model, prompt_tag)
            title = self.llm_client.chat(model, prompt_title)
            description = self.llm_client.chat(model, prompt_description)
            if not tags or not title or not description:
                print("❌ Erreur : une ou plusieurs réponses sont vides.")
                return
            tags = tags.strip()
            title = title.strip()
            description = description.strip()
        except Exception as e:
            print(f"❌ Erreur lors de la génération YouTube : {e}")
            return

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Titre : {title}\n\n")
            f.write("Description :\n")
            f.write(description + "\n\n")
            f.write("Tags :\n")
            f.write(tags)

        print(f"✅ YouTube info générée dans : {output_path}")
