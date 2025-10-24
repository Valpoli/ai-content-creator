# whisper/transcript.py
from faster_whisper import WhisperModel
import json
import sys
import re
import difflib
from rapidfuzz import fuzz, process


class WhisperTranscriber:
    def __init__(self, model_size="medium", device="cpu"):
        self.model = WhisperModel(model_size, device=device)

    def transcribe_by_words(self, audio_path):
        segments, _ = self.model.transcribe(audio_path, word_timestamps=True)
        results = []
        
        for seg in segments:
            if hasattr(seg, 'words') and seg.words:
                for word_info in seg.words:
                    results.append({
                        "start": word_info.start,
                        "end": word_info.end,
                        "text": word_info.word.strip()
                    })
            else:
                print(f"⚠️ Segment sans mots détecté entre {seg.start:.2f}s et {seg.end:.2f}s ➔ Ignoré.")
        
        # print(f"✅ Transcription mot-à-mot réussie avec {len(results)} mots capturés.")
        return results

    def save_transcription(self, transcription, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcription, f, ensure_ascii=False, indent=2)
        print(f"✅ Transcript saved to {output_path}")

    def get_corrected_word(self, word, ref_words, current_index, search_window=5, threshold=15, min_score=25):
        search_zone = ref_words[current_index: current_index + search_window]
        
        # print("\n🔎 Nouveau mot à corriger :")
        # print(f"➡️  Mot entendu      : '{word}'")
        # print(f"➡️  Index actuel     : {current_index}")
        # print(f"➡️  Zone de recherche: {search_zone}")

        if not search_zone:
            print("🚫 Zone de recherche vide. Retour None.")
            return None, current_index

        lowered_search_zone = [w.lower() for w in search_zone]
        lowered_word = word.lower()

        candidates = []
        for idx, candidate_word in enumerate(lowered_search_zone):
            sim_score = fuzz.ratio(lowered_word, candidate_word)
            distance_penalty = idx * 15  # pénalité par distance
            final_score = sim_score - distance_penalty
            
            # BONUS spécial pour "a" ou "à"
            if lowered_word in ("a", "à") and candidate_word in ("a", "à"):
                # print("🎯 Bonus +20 appliqué pour mot spécial 'a' ou 'à'")
                final_score += 20

            candidates.append({
                "original_word": search_zone[idx],
                "score": sim_score,
                "distance_penalty": distance_penalty,
                "final_score": final_score,
                "relative_index": idx
            })

        candidates = sorted(candidates, key=lambda x: x["final_score"], reverse=True)

        # print("\n📝 Candidats évalués :")
        # for c in candidates:
        #     print(f"Mot: '{c['original_word']}' | Score: {c['score']} | Pénalité: {c['distance_penalty']} | Score final: {c['final_score']}")

        best = candidates[0] if candidates else None

        if best and best["final_score"] >= threshold:
            corrected_word = best["original_word"]
            new_index = current_index + best["relative_index"] + 1
            # print(f"\n✅ Correction acceptée : '{corrected_word}' ➔ Nouveau index: {new_index}")
            if best["final_score"] > min_score:
                return corrected_word, new_index
            return corrected_word, current_index
        else:
            # Attention ici : on NE change PAS d'index si score insuffisant (<40)
            print(f"\n⚠️ Score insuffisant ({best['final_score'] if best else 'N/A'}) ➔ Utilisation du mot original '{word}' (ref_index inchangé)")
            return None, current_index

    def extract_text_segment(self, reference_text, corrected_data, words_per_line=5):
        clean_reference_text = reference_text.replace('\n', ' ')

        segments = []
        ref_words = list(re.finditer(r'\w+', clean_reference_text))
        ref_index = 0
        data_index = 0
        segment_counter = 1

        while data_index < len(corrected_data):
            # Position du mot de départ
            start_time = corrected_data[data_index]['start']
            start_ref_word = corrected_data[data_index]['text']

            # Récupérer words_per_line mots valides
            group = corrected_data[data_index:data_index + words_per_line]
            if not group:
                break

            end_time = group[-1]['end']
            end_ref_word = group[-1]['text']

            # Maintenant on doit retrouver le texte exact entre les deux mots dans reference_text
            # On cherche où se trouve start_ref_word dans ref_words
            segment_start_pos = None
            segment_end_pos = None
            collected = []

            # print(f"\n🧠 Nouveau groupe : '{start_ref_word}' -> '{end_ref_word}'")
            # print("🔎 Recherche dans le texte brut...")

            while ref_index < len(ref_words):
                word = ref_words[ref_index]
                word_text = word.group(0)

                # print(f"  Mot brut : '{word_text}' (index {ref_index})")

                if word_text.lower() == start_ref_word.lower() and (len(word_text) == len(start_ref_word)) and segment_start_pos is None:
                    segment_start_pos = word.start()
                    # print(f"  🟢 Début trouvé : '{word_text}' (position {segment_start_pos})")

                collected.append(word_text)

                is_near_end = (data_index + words_per_line >= len(corrected_data))

                if ((len(collected) >= words_per_line) or is_near_end) and (word_text.lower() == end_ref_word.lower()) and (len(word_text) == len(end_ref_word)):
                    segment_end_pos = word.end()
                    # print(f"  🔴 Fin trouvée : '{word_text}' (position {segment_end_pos}) avec {len(collected)} mots")
                    ref_index += 1
                    break

                ref_index += 1

            if segment_start_pos is not None and segment_end_pos is not None:
                segment_text = clean_reference_text[segment_start_pos:segment_end_pos]

                # Affichage DEBUG clair
                # print(f"\n📋 Segment {segment_counter}:")
                # print(f"   Texte extrait        : '{segment_text.strip()}'")
                # print(f"   Start time            : {start_time:.2f}s (mot: '{start_ref_word}')")
                # print(f"   End time              : {end_time:.2f}s (mot: '{end_ref_word}')")
                # print(f"   Mots utilisés         : {[w['text'] for w in group]}")
                # print(f"   Ref words traités     : {collected}")

                segments.append({
                    'start': start_time,
                    'end': end_time,
                    'text': segment_text.strip()
                })
            else:
                print(f"\n⚠️ Impossible d'associer correctement '{start_ref_word}' -> '{end_ref_word}' dans le texte brut.")

            data_index += words_per_line
            segment_counter += 1

        # print(f"\n✅ {len(segments)} segments extraits proprement.")
        return segments

    
    def process_transcription(self, audio_path, output_path, reference_txt_path, words_per_line=5):
        transcription = self.transcribe_by_words(audio_path)
        
        with open(reference_txt_path, 'r', encoding='utf-8') as f:
            reference_text = f.read()

        ref_words = re.findall(r'\w+', reference_text)
        corrected_data = []
        ref_index = 0  # L'index dans ton texte de référence

        # 1. Correction mot à mot
        for item in transcription:
            original = item['text']
            corrected, ref_index = self.get_corrected_word(original, ref_words, ref_index)

            if corrected is None:
                # print(f"⚠️ Aucune correspondance trouvée pour : '{original}' ➔ Utilisation du texte brut.")
                # corrected = original
                print(f"⚠️ Aucune correspondance trouvée pour : '{original}' ➔ Ignoré.")
                continue
            
            item['original_text'] = original
            item['text'] = corrected
            corrected_data.append(item)

        # 2. Sauvegarder mot par mot
        word_by_word_output = output_path.replace(".json", "_word_by_word.json")
        self.save_transcription(corrected_data, word_by_word_output)
        # print(f"✅ Mot par mot sauvegardé ici : {word_by_word_output}")

       # Maintenant extract_text_segment fait TOUT le boulot
        segments = self.extract_text_segment(reference_text, corrected_data, words_per_line=words_per_line)

        # Sauvegarde directement
        self.save_transcription(segments, output_path)
        # print(f"✅ Segments sauvegardés ici : {output_path}")

def run_whisper_main(audio, output, reference_txt, words_per_line):
    transcriber = WhisperTranscriber()
    transcriber.process_transcription(audio, output, reference_txt, words_per_line)

if __name__ == "__main__":
    audio = sys.argv[1]
    output = sys.argv[2]
    reference_txt = sys.argv[3]
    words_per_line = int(sys.argv[4])

    transcriber = WhisperTranscriber()
    transcriber.process_transcription(audio, output, reference_txt, words_per_line)


    # ref_text = "Ce soir, les amis, préparez-vous à découvrir un mystère incroyable qu'aucun livre ne raconte."
    # segment = transcriber.extract_text_segment(ref_text, "Ce", "vous")
    # print(segment)

