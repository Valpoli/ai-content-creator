import argparse
import json
import os
import random

import yaml
from databases.story_database import StoryDatabase
from story_builder import StoryBuilder
from story_image_generator import StoryImageGenerator
from story_processor import StoryProcessor
from video_story_builder import VideoStoryBuilder
from voice_generator import VoiceGenerator


class MagicStory:
    def __init__(self, config_path="config.yaml"):
        self.story_builder = StoryBuilder()
        self.story_processor = StoryProcessor()
        self.story_image_generator = StoryImageGenerator()
        self.voice_generator = VoiceGenerator()
        self.video_story_builder = VideoStoryBuilder()
        self.story_database = StoryDatabase()

        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.global_folder = self.config["base_story_dir"]

    def demander_nom_dossier(self):
        while True:
            nom_dossier = input("Entrez le nom du dossier : ").strip()
            confirmation = input(f"Confirmer le nom '{nom_dossier}' ? (o/n) : ").strip().lower()
            if confirmation == "o":
                return nom_dossier

    def attendre_confirmation(self, message):
        print(message)
        while input("Entrez 'o' pour continuer : ").strip().lower() != "o":
            print("⏳ En attente...")

    def init_folder_story_picture(self):
        # 1 - créer le dossier qui va contenir tous nos éléments
        nom_dossier = self.demander_nom_dossier()
        if not self.story_builder.create_story_folder(nom_dossier):
            return None, None

        # 2 - générer notre histoire
        path_txt = os.path.join(self.global_folder, nom_dossier, f"{nom_dossier}.txt")
        self.attendre_confirmation(f"📁 Veuillez mettre votre histoire ici : {path_txt}")

        titre = self.story_processor.insert_new_story_in_db(nom_dossier)
        if not titre:
            return None, None

        # 3 - stocker en base de données et générer les futures prompts pour les images
        if self.config.get("leonardo"):
            generation_id_list = self.story_image_generator.generate_all_story_images(titre, nom_dossier)
            if generation_id_list:
                self.story_image_generator.store_all_generated_images(generation_id_list, nom_dossier)
        else:
            parts = self.story_database.get_story_parts(titre)
            print("\n🔍 Liste des images à générer :")
            for part in parts:
                epc = part.get("epc", "❓")
                prompt = part.get("image_prompt", "(aucun prompt)")
                print(f"🖼️ {epc} → {prompt}\n")
            # rename avec le bonne ordre
            epcs = [p["epc"] for p in parts if "epc" in p]
            img_folder = os.path.join(self.global_folder, nom_dossier, "img")
            print("Mettez vos images dans :", img_folder)
            self.attendre_confirmation("⏳ Tapez 'o' quand vos images sont prêtes.")
            self.story_image_generator.rename_images_by_epc_order(img_folder, epcs)

        return nom_dossier, titre

    def store_story_in_json(self, count=1):
        stories = []
        if os.path.exists("story_todo.json"):
            with open("story_todo.json", encoding="utf-8") as f:
                try:
                    stories = json.load(f)
                except json.JSONDecodeError:
                    pass

        for _ in range(count):
            nom_dossier, titre = self.init_folder_story_picture()
            if nom_dossier and titre:
                stories.append({"nom_dossier": nom_dossier, "titre": titre, "voice": False})
                with open("story_todo.json", "w", encoding="utf-8") as f:
                    json.dump(stories, f, indent=4, ensure_ascii=False)

    def make_all_voice_parts(self):
        if not os.path.exists("story_todo.json"):
            return
        with open("story_todo.json", encoding="utf-8") as f:
            story_list = json.load(f)

        # personnage = random.choice(["nathan", "elisa"])
        personnage = self.config.get("voice", "nathan")
        for story in story_list:
            if not story.get("voice"):
                self.voice_generator.create_voices_for_story(story["nom_dossier"], story["titre"], personnage)
                story["voice"] = True

        with open("story_todo.json", "w", encoding="utf-8") as f:
            json.dump(story_list, f, indent=4, ensure_ascii=False)

    def generate_final_videos(self):
        if not os.path.exists("story_todo.json"):
            return
        with open("story_todo.json", encoding="utf-8") as f:
            story_list = json.load(f)

        while story_list:
            story = story_list.pop(0)
            nom_dossier, titre = story["nom_dossier"], story["titre"]
            # 4 - fusionner toute les voix off
            self.voice_generator.merge_voices(nom_dossier, titre)
            # 5 - générer la vidéo + le montage
            self.video_story_builder.generate_story_video(
                img_folder=os.path.join(self.global_folder, nom_dossier, "img"),
                sound_folder=os.path.join(self.global_folder, nom_dossier, "voice"),
                video_parts_folder=os.path.join(self.global_folder, nom_dossier, "video_parts"),
                title=titre,
                output_path=os.path.join(self.global_folder, nom_dossier, "final_video_without_music.mp4"),
            )

            if self.config.get("libre_de_droit"):
                music_path = f"assets/musique/libre_de_droit/suno_{random.randint(1, 17)}.mp3"
            else:
                music_path = f"assets/musique/{self.config['music']}.mp3"

            self.video_story_builder.add_background_music(
                video_path=os.path.join(self.global_folder, nom_dossier, "final_video_without_music.mp4"),
                music_path=music_path,
                output_path=os.path.join(self.global_folder, nom_dossier, "final_video_with_music.mp4"),
            )

            with open("story_todo.json", "w", encoding="utf-8") as f:
                json.dump(story_list, f, indent=4, ensure_ascii=False)

    def run(self):
        parser = argparse.ArgumentParser(description="Générateur d'histoires automatiques.")
        parser.add_argument("action", choices=["write", "voice", "generate", "all"])
        parser.add_argument("--count", type=int, default=1)
        args = parser.parse_args()

        if args.action == "write":
            self.store_story_in_json(args.count)
        elif args.action == "voice":
            self.make_all_voice_parts()
        elif args.action == "generate":
            self.generate_final_videos()
        elif args.action == "all":
            self.store_story_in_json(args.count)
            self.make_all_voice_parts()
            self.generate_final_videos()


if __name__ == "__main__":
    MagicStory().run()
