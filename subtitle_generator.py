import json
import os
import subprocess
import tempfile
import textwrap

import yaml
from databases.story_database import StoryDatabase
from transcript import run_whisper_main


class SubtitleGenerator:
    def __init__(self, db_path=None):
        self.story_db = StoryDatabase(db_path)

        config_path = "config.yaml"
        try:
            with open(config_path, encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ Fichier config introuvable : {config_path}")
            self.config = {}

    def run_whisper_transcription(self, wav_path, json_output_path, reference_text):
        whisper_venv_python = os.path.abspath(os.path.join("..", "whisper", "whisper_env", "bin", "python"))
        transcript_script = os.path.abspath(os.path.join("..", "whisper", "transcript.py"))

        words_per_line = str(self.config.get("words_per_line", 5))

        if not os.path.isfile(whisper_venv_python):
            raise RuntimeError(f"❌ Python introuvable dans le venv : {whisper_venv_python}")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write(reference_text)
            tmp_path = tmp.name

        try:
            # command = [whisper_venv_python, transcript_script, wav_path, json_output_path, tmp_path, words_per_line]
            # print(f"🔁 Exécution de Whisper : {' '.join(command)}")
            # subprocess.run(command, check=True)
            run_whisper_main(wav_path, json_output_path, tmp_path, words_per_line)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def generate_whisper_jsons(self, title, voice_dir):
        story_elements = self.story_db.get_story_parts(title)
        intro_outro_path = os.path.join(os.path.dirname(voice_dir), "intro_outro.txt")

        with open(intro_outro_path, encoding="utf-8") as f:
            contenu = f.read()
        intro = contenu.split("Intro :", 1)[1].split("Outro :", 1)[0].strip()
        outro = contenu.split("Outro :", 1)[1].strip()

        for i, element in enumerate(story_elements):
            epc = element.get("epc")
            if not epc:
                print(f"⚠️ Élément {i} incomplet (epc manquant). Skippé.")
                continue

            wav_path = os.path.join(voice_dir, f"{epc}.wav")
            json_path = os.path.join(voice_dir, f"{epc}.json")

            if not os.path.isfile(wav_path):
                print(f"❌ WAV manquant pour '{epc}' → {wav_path}")
                continue

            reference_text = element.get("text_part", "")
            if i == 0:
                reference_text = intro + "\n" + reference_text
            if i == len(story_elements) - 1:
                reference_text = reference_text + "\n" + outro

            if not os.path.exists(json_path):
                self.run_whisper_transcription(wav_path, json_path, reference_text)
            else:
                print(f"⏩ JSON déjà présent, skip transcription pour '{epc}'")

            if not os.path.isfile(json_path):
                print(f"❌ JSON Whisper manquant pour '{epc}' → {json_path}")
                continue

            print(f"✅ json fixed pour {epc}: {json_path}")

    def burn_subtitles_on_video_from_json(self, video_path, json_subs_path, output_path):
        if not os.path.exists(json_subs_path):
            print(f"⚠️ JSON de sous-titres introuvable : {json_subs_path}")
            return

        with open(json_subs_path, encoding="utf-8") as f:
            segments = json.load(f)

        def format_ass_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centis = int((seconds % 1) * 100)
            return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"

        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1024
PlayResY: 768
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,
ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,30,&H00F5F5F5,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,2,0,2,40,40,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        ass_events = ""
        for seg in segments:
            start = format_ass_time(seg["start"])
            end = format_ass_time(seg["end"])
            wrapped_lines = textwrap.wrap(seg["text"], width=100)
            ass_text = r"\N".join(wrapped_lines)
            ass_events += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{ass_text}\n"

        ass_content = ass_header + ass_events

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ass", mode="w", encoding="utf-8") as tmp_ass:
            tmp_ass.write(ass_content)
            tmp_ass_path = tmp_ass.name

        command = [
            "ffmpeg",
            "-i",
            video_path,
            "-vf",
            f"ass={tmp_ass_path}",
            "-c:v",
            "libx264",
            "-c:a",
            "copy",
            "-shortest",
            output_path,
        ]

        print("🛠️ Commande ffmpeg :", " ".join(command))
        subprocess.run(command, check=True)
        print(f"✅ Vidéo exportée avec sous-titres : {output_path}")
