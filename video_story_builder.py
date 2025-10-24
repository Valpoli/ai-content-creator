import os
import random
import re
import time

import cv2
import numpy as np
import yaml
from databases.story_database import StoryDatabase
from moviepy.audio.fx import AudioLoop
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    VideoFileClip,
    concatenate_videoclips,
)
from subtitle_generator import SubtitleGenerator
from tqdm import tqdm


class VideoStoryBuilder:
    def __init__(self, config_path="config.yaml"):
        self.story_db = StoryDatabase()
        self.subtitle_gen = SubtitleGenerator()

        try:
            with open(config_path, encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ Fichier config introuvable : {config_path}")
            self.config = {}

    def random_pan_zoom(self, image_path, output_path, zoom_factor=1.5, duration=5, fps=30, max_speed_px_per_sec=None):
        img = cv2.imread(image_path)
        height, width = img.shape[:2]
        zoomed = cv2.resize(img, None, fx=zoom_factor, fy=zoom_factor, interpolation=cv2.INTER_LINEAR)
        zh, zw = zoomed.shape[:2]

        direction = random.choice(["up", "down", "left", "right"])
        total_frames = int(duration * fps)

        if direction == "up":
            x, y = (zw - width) // 2, zh - height
            dx_total, dy_total = 0, -(zh - height)
        elif direction == "down":
            x, y = (zw - width) // 2, 0
            dx_total, dy_total = 0, (zh - height)
        elif direction == "left":
            x, y = zw - width, (zh - height) // 2
            dx_total, dy_total = -(zw - width), 0
        else:
            x, y = 0, (zh - height) // 2
            dx_total, dy_total = (zw - width), 0

        # Limitation de la vitesse maximale (si demandé)
        if max_speed_px_per_sec is not None:
            total_distance = np.sqrt(dx_total**2 + dy_total**2)
            max_total_distance = max_speed_px_per_sec * duration
            if total_distance > max_total_distance:
                scale = max_total_distance / total_distance
                dx_total *= scale
                dy_total *= scale

        dx = dx_total / total_frames
        dy = dy_total / total_frames

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        for _ in tqdm(range(total_frames), desc="Animation"):
            frame = zoomed[int(y) : int(y) + height, int(x) : int(x) + width]
            out.write(frame)
            x, y = x + dx, y + dy

        out.release()
        time.sleep(1)

    def make_animated_clip(self, image_path, duration, temp_out="temp_animation.mp4"):
        self.random_pan_zoom(image_path, temp_out, duration=duration, fps=24, max_speed_px_per_sec=75)
        return VideoFileClip(temp_out)

    def concat_video_parts(self, folder_path, output_path):
        files = sorted([f for f in os.listdir(folder_path) if f.endswith(".mp4")], key=self._natural_sort)
        if not files:
            raise ValueError("❌ Aucun fichier .mp4 trouvé.")

        clips = [VideoFileClip(os.path.join(folder_path, f)) for f in files]
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        print(f"✅ Exporté : {output_path}")

    def generate_story_video(self, img_folder, sound_folder, video_parts_folder, title, output_path):
        # make subtitles
        self.subtitle_gen.generate_whisper_jsons(title, sound_folder)
        # generate videos
        parts = self.story_db.get_story_parts(title)
        print(f"🎞️ Génération vidéo pour : {title} ({len(parts)} parties)")
        for idx, part in enumerate(parts):
            epc = part["epc"]
            img = os.path.join(img_folder, f"{epc}.png")
            audio = os.path.join(sound_folder, f"{epc}.wav")
            part_video = os.path.join(video_parts_folder, f"{epc}.mp4")

            # Si l'image .png n'existe pas, on tente avec .jpg
            if not os.path.exists(img):
                alt_img = os.path.join(img_folder, f"{epc}.jpg")
                if os.path.exists(alt_img):
                    img = alt_img  # on utilise l’image jpg à la place
                else:
                    print(f"⚠️ Fichiers manquants pour epc: {epc}")
                    print(f"   ❌ Image manquante : {img} et {alt_img}")
                    if not os.path.exists(audio):
                        print(f"   ❌ Audio manquant : {audio}")
                    continue

            # Vérifie maintenant l'audio
            if not os.path.exists(audio):
                print(f"⚠️ Fichier audio manquant pour epc: {epc}")
                print(f"   ❌ Audio manquant : {audio}")
                continue

            audio_clip = AudioFileClip(audio)
            # Générer l'animation sans audio et l'enregistrer
            # make_short = self.config.get("short", False)
            if not os.path.exists(part_video):
                clip = self.make_animated_clip(img, audio_clip.duration)
                animated = clip.set_audio(audio_clip).fadein(1).fadeout(1)

                if idx < len(parts) - 1:
                    black = ColorClip(size=animated.size, color=(0, 0, 0), duration=1).fadein(0.5).fadeout(0.5)
                    animated = concatenate_videoclips([animated, black], method="compose")

                animated.write_videofile(part_video, fps=24, codec="libx264", audio=True)
                time.sleep(1)
                clip.close()

                json_path = os.path.join(sound_folder, f"{epc}.json")
                final_subtitled = os.path.join(video_parts_folder, f"{epc}_subtitled.mp4")
                self.subtitle_gen.burn_subtitles_on_video_from_json(part_video, json_path, final_subtitled)
                os.replace(final_subtitled, part_video)
            else:
                print(f"📂 Déjà existant : {epc}")

        self.concat_video_parts(video_parts_folder, output_path)

    def add_background_music(self, video_path, music_path, output_path="final_with_music.mp4", music_volume=0.16):
        print("🎶 Ajout musique d’ambiance...")
        video = VideoFileClip(video_path)
        original_audio = video.audio
        music = AudioFileClip(music_path)

        # Boucle la musique si elle est trop courte
        if music.duration < video.duration:
            music = AudioLoop(music, duration=video.duration)
        music = music.volumex(music_volume)

        combined_audio = CompositeAudioClip([music.set_duration(video.duration), original_audio])
        final = video.set_audio(combined_audio)
        final.write_videofile(output_path, codec="libx264", audio_codec="aac")
        print(f"✅ Vidéo finale avec musique : {output_path}")

    def _natural_sort(self, s):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"([0-9]+)", s)]


# if __name__ == "__main__":
#     builder = VideoStoryBuilder()
#     builder.random_pan_zoom(
#         image_path="histoire/coccinelle/img/lili_la_coccinelle_et_le_grand_voyage_56.png",
#         output_path="test_video.mp4",
#         duration=20,
#         max_speed_px_per_sec=75
#     )


# if __name__ == "__main__":
#     # ⚙️ Initialisation du builder avec le fichier de config
#     builder = VideoStoryBuilder(config_path="config.yaml")

#     # 📁 Dossiers sources
#     img_folder = "histoire/jim_nem/img"
#     sound_folder = "histoire/jim_nem/voice"
#     video_parts_folder = "to_del/"

#     # 🎬 Infos de la vidéo
#     title = "la sauce secrète des nems du chef jimmy"
#     output_path = "test_to_del.mp4"

#     # 💥 Lancement de la génération vidéo
#     builder.generate_story_video(
#         img_folder=img_folder,
#         sound_folder=sound_folder,
#         video_parts_folder=video_parts_folder,
#         title=title,
#         output_path=output_path
#     )
