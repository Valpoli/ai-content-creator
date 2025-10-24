import os

import torch
import yaml
from databases.story_database import StoryDatabase
from pydub import AudioSegment
from torch import serialization
from TTS.api import TTS
from TTS.config.shared_configs import BaseDatasetConfig
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsArgs, XttsAudioConfig

# Whitelist pour torch
serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])


class VoiceGenerator:
    def __init__(self, config_path="config.yaml"):
        self.story_db = StoryDatabase()
        self.config = self._load_config(config_path)
        self.story_base_path = self.config["base_story_dir"]
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)

    def _load_config(self, config_path):
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Le fichier '{config_path}' n'existe pas.")
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @property
    def tts(self):
        if not hasattr(self, "_tts"):
            self._tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
        return self._tts

    def _tts_to_file(self, text, speaker_path, output_path):
        self.tts.tts_to_file(text=text, speaker_wav=speaker_path, language="fr", file_path=output_path)

    def _get_voice_path(self, personnage):
        return f"assets/voices/personnages/{personnage}.wav"

    def _read_by_character(self, file_name, text, personnage):
        voice_path = self._get_voice_path(personnage)
        if not os.path.exists(voice_path):
            raise ValueError(f"Voix non trouvée pour le personnage : {personnage}")
        print(f"🔊 Génération avec {personnage} → {file_name}")
        self._tts_to_file(text, voice_path, file_name)

    def _get_intro_outro(self, story_folder):
        path = os.path.join(self.story_base_path, story_folder, "intro_outro.txt")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"intro_outro.txt manquant : {path}")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        intro = content.split("Intro :", 1)[1].split("Outro :", 1)[0].strip()
        outro = content.split("Outro :", 1)[1].strip()
        return intro, outro

    def create_voices_for_story(self, story_folder, title, personnage="elisa"):
        print(f"🎙️ Création des voix pour : {title}")
        story_parts = self.story_db.get_story_parts(title)
        print(f"🔍 {len(story_parts)} parties détectées.")
        intro, outro = self._get_intro_outro(story_folder)

        for i, part in enumerate(story_parts):
            epc = part["epc"]
            voice_path = os.path.join(self.story_base_path, story_folder, "voice", f"{epc}.wav")

            if os.path.exists(voice_path):
                print(f"⏭️ Skipped (déjà existant) : {epc}")
                continue

            text = part["text_part"]
            if i == 0:
                text = intro + "\n" + text
            if i == len(story_parts) - 1:
                text = text + "\n" + outro

            self._read_by_character(voice_path, text, personnage)

    def merge_voices(self, story_folder, title):
        story_parts = self.story_db.get_story_parts(title)
        silence = AudioSegment.silent(duration=1000)
        final_audio = AudioSegment.empty()
        total_duration_sec = 0

        output_path = os.path.join(self.story_base_path, story_folder, "complete_sound.wav")

        for part in story_parts:
            epc = part["epc"]
            audio_path = os.path.join(self.story_base_path, story_folder, "voice", f"{epc}.wav")
            if os.path.exists(audio_path):
                audio = AudioSegment.from_wav(audio_path)
                final_audio += audio + silence
                duration = len(audio) / 1000
                total_duration_sec += duration
                self.story_db.update_reading_time(epc, int(duration))
            else:
                print(f"⚠️ Audio manquant pour : {epc}")

        final_audio.export(output_path, format="wav")
        print(f"\n✅ Fichier final exporté : {output_path}")
        print(f"🕒 Durée approx. (hors silences) : {total_duration_sec} sec")
