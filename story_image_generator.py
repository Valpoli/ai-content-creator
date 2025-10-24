import platform
import time
from pathlib import Path

from databases.image_database import ImageDatabase
from databases.story_database import StoryDatabase
from leonardo_client import LeonardoClient
from llm_client import LLMClient
from prompt import (
    neg_prompt_crayon,
    neg_prompt_dreamworks,
    neg_prompt_ghibli,
    neg_prompt_leonardo,
    neg_prompt_pixar,
    sys_prompt_crayon,
    sys_prompt_dreamworks,
    sys_prompt_ghibli,
    sys_prompt_leonardo,
    sys_prompt_pixar,
    user_prompt_crayon,
    user_prompt_dreamworks,
    user_prompt_ghibli,
    user_prompt_leonardo,
    user_prompt_pixar,
)


class StoryImageGenerator:
    def __init__(self):
        self.llm_client = LLMClient()
        self.leonardo = LeonardoClient()
        self.story_db = StoryDatabase()
        self.image_db = ImageDatabase()

    def _get_theme_prompts(self, theme=None):
        theme = theme or self.config.get("theme", "ghibli")
        prompts = {
            "ghibli": (sys_prompt_ghibli, user_prompt_ghibli, neg_prompt_ghibli),
            "pixar": (sys_prompt_pixar, user_prompt_pixar, neg_prompt_pixar),
            "crayon": (sys_prompt_crayon, user_prompt_crayon, neg_prompt_crayon),
            "dreamworks": (sys_prompt_dreamworks, user_prompt_dreamworks, neg_prompt_dreamworks),
            "leonardo": (sys_prompt_leonardo, user_prompt_leonardo, neg_prompt_leonardo),
        }
        return prompts.get(theme, prompts["ghibli"])

    def get_picture_prompt(self, model: str, story_text: str, theme=None):
        sys_prompt, user_prompt_template, neg_prompt = self._get_theme_prompts(theme)
        user_prompt = user_prompt_template.format(story_part=story_text)

        response = self.llm_client.chat(model=model, user_prompt=user_prompt, system_prompt=sys_prompt)

        return response, neg_prompt

    def generate_all_story_images(self, story_title, story_folder):
        story_parts = self.story_db.get_story_parts(story_title)

        self.leonardo.print_user_info()

        to_generate = [p for p in story_parts if not self.image_db.exists(p["epc"])]
        print(f"\n🖼️ {len(to_generate)} image(s) à générer.")
        self.leonardo.get_total_cost(len(to_generate))

        confirmation = input("⚠️ Confirmer génération ? (oui / non) : ").strip().lower()
        if confirmation != "oui":
            print("⛔ Annulé par l'utilisateur.")
            return None

        print("✅ Lancement de la génération...")

        generation_id_list = []
        for part in to_generate:
            epc = part["epc"]
            prompt = part.get("image_prompt", "")
            negative_prompt = part.get("negative_prompt", "")

            if len(prompt) > 1499:
                print(f"⚠️ Prompt trop long pour {epc}, skip.")
                continue

            print(f"🎨 Génération d'image pour {epc}")
            response = self.leonardo.generate_image(epc, prompt, negative_prompt)

            if response.status_code == 200:
                data = response.json()
                generation_id = data.get("sdGenerationJob", {}).get("generationId")
                if generation_id:
                    generation_id_list.append((generation_id, epc))
                else:
                    print("❌ generationId manquant dans la réponse.")
            else:
                print(f"❌ Échec génération epc: {epc} ({response.status_code})")

        return generation_id_list

    def wait_for_completion(self, generation_id):
        while True:
            data = self.leonardo.get_generation_info(generation_id)
            status = data.get("generations_by_pk", {}).get("status")

            if status == "COMPLETE":
                print(f"✅ Génération complète : {generation_id}")
                return data
            print(f"⏳ En attente (status = {status})")
            time.sleep(3)

    def store_all_generated_images(self, generation_id_list, story_folder):
        for generation_id, epc in generation_id_list:
            print(f"⬇️ Téléchargement de : {generation_id}")
            gen_data = self.wait_for_completion(generation_id)
            self.leonardo.download_images(gen_data, story_folder, epc)

    def rename_images_by_epc_order(self, folder, epc_list):
        path = Path(folder)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"❌ Dossier invalide : {folder}")

        valid_exts = [".jpg", ".jpeg", ".png", ".webp"]
        images = [f for f in path.iterdir() if f.suffix.lower() in valid_exts]

        if not images:
            raise ValueError("⚠️ Aucune image trouvée.")
        if len(images) != len(epc_list):
            raise ValueError(f"❗ {len(images)} images ≠ {len(epc_list)} EPCs")

        images.sort(key=self._get_creation_time)

        for img, epc in zip(images, epc_list):
            new_name = f"{epc}{img.suffix.lower()}"
            new_path = path / new_name
            print(f"🔁 {img.name} ➡️ {new_name}")
            img.rename(new_path)

    def _get_creation_time(self, file: Path):
        if platform.system() == "Windows":
            return file.stat().st_ctime
        try:
            return file.stat().st_birthtime
        except AttributeError:
            return file.stat().st_mtime
