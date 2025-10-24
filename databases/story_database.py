import os
import sqlite3


class StoryDatabase:
    def __init__(self, db_path: str | None = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = db_path or os.path.join(base_dir, "histoires.db")
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _normalize_title(titre: str) -> str:
        return titre.strip().replace(" ", "_").replace("’", "").replace("'", "").lower()

    @staticmethod
    def _reading_time(nb_mots: int, mots_par_minute: int = 130) -> int:
        total_minutes = nb_mots / mots_par_minute
        minutes = int(total_minutes)
        secondes = int((total_minutes - minutes) * 60)
        total_secondes = minutes * 60 + secondes

        print(f"Temps estimé : {minutes} min {secondes} sec")
        print(f"Temps total en secondes : {total_secondes} sec")
        return total_secondes

    def _create_table(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS histoires (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titre TEXT NOT NULL,
                    text_part TEXT NOT NULL,
                    text_with_description TEXT,
                    image_prompt TEXT,
                    negative_prompt TEXT,
                    temps_lecture_sec INTEGER,
                    epc TEXT UNIQUE
                )
            """)
        # print("✅ Base de données des histoires créée (ou déjà existante).")

    def add_or_update_story(self, titre: str, text_part: str, text_with_description: str | None = None, epc: str | None = None):
        titre_normalise = self._normalize_title(titre)
        temps_sec = self._reading_time(len(text_part.split()))

        with self._connect() as conn:
            cursor = conn.cursor()

            if epc:
                cursor.execute("SELECT id FROM histoires WHERE epc = ?", (epc,))
                result = cursor.fetchone()

                if result:
                    cursor.execute(
                        """
                        UPDATE histoires
                        SET titre = ?, text_part = ?, text_with_description = ?, temps_lecture_sec = ?
                        WHERE id = ?
                    """,
                        (titre, text_part, text_with_description, temps_sec, result[0]),
                    )
                    print(f"🔁 Histoire mise à jour via epc : {epc}")
                else:
                    cursor.execute(
                        """
                        INSERT INTO histoires (titre, text_part, text_with_description, temps_lecture_sec, epc)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (titre, text_part, text_with_description, temps_sec, epc),
                    )
                    print(f"⚠️ epc fourni mais introuvable, nouvelle entrée créée avec epc : {epc}")
            else:
                cursor.execute("SELECT id, epc FROM histoires WHERE titre = ? AND text_part = ?", (titre, text_part))
                result = cursor.fetchone()

                if result:
                    cursor.execute(
                        """
                        UPDATE histoires
                        SET text_with_description = ?, temps_lecture_sec = ?
                        WHERE id = ?
                    """,
                        (text_with_description, temps_sec, result[0]),
                    )
                    print(f"🔁 Histoire mise à jour : {result[1]}")
                else:
                    cursor.execute(
                        """
                        INSERT INTO histoires (titre, text_part, text_with_description, temps_lecture_sec)
                        VALUES (?, ?, ?, ?)
                    """,
                        (titre, text_part, text_with_description, temps_sec),
                    )
                    last_id = cursor.lastrowid
                    epc_generated = f"{titre_normalise}_{last_id}"
                    cursor.execute("UPDATE histoires SET epc = ? WHERE id = ?", (epc_generated, last_id))
                    print(f"✅ Nouvelle histoire insérée avec epc : {epc_generated}")

    def update_prompts(self, epc: str, image_prompt: str, negative_prompt: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM histoires WHERE epc = ?", (epc,))
            result = cursor.fetchone()

            if result:
                cursor.execute(
                    """
                    UPDATE histoires
                    SET image_prompt = ?, negative_prompt = ?
                    WHERE id = ?
                """,
                    (image_prompt, negative_prompt, result[0]),
                )
                print(f"🎨 Prompts mis à jour pour epc : {epc}")
            else:
                print(f"❌ Aucune histoire trouvée avec epc : {epc}")

    def print_story_by_title(self, titre: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, epc, text_part, text_with_description, image_prompt, negative_prompt
                FROM histoires WHERE titre = ? ORDER BY id
            """,
                (titre,),
            )
            resultats = cursor.fetchall()

        if not resultats:
            print(f"❌ Aucun résultat trouvé pour le titre : {titre}")
        else:
            print(f"📚 Parties pour l’histoire « {titre} » :\n")
            for row in resultats:
                id_, epc, texte, desc, img_prompt, neg_prompt = row
                extrait = texte.replace("\n", " ") + "..." if len(texte) > 100 else texte
                desc_extrait = desc.replace("\n", " ") + "..." if desc else "(aucune description)"
                img_extrait = img_prompt.replace("\n", " ") + "..." if img_prompt else "(aucun image prompt)"
                neg_extrait = neg_prompt.replace("\n", " ") + "..." if neg_prompt else "(aucun negative prompt)"
                print(f"""🔹 ID: {id_} | EPC: {epc}
    ➤ Texte: {extrait}
    📝 Description: {desc_extrait}
    🎨 Image Prompt: {img_extrait}
    🚫 Negative Prompt: {neg_extrait}
""")

    def get_story_parts(self, titre: str, afficher=False) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM histoires WHERE titre = ? ORDER BY id", (titre,))
            rows = cursor.fetchall()

        results = [dict(row) for row in rows]

        if afficher:
            if results:
                print(f"\n📖 Résumé des parties pour le titre : « {titre} »\n")
                for row in results:
                    print(f"{row['epc']} - description image : {row.get('image_prompt', 'Aucune description')}")
            else:
                print(f"⚠️ Aucune partie trouvée pour le titre : « {titre} »")

        return results

    def update_reading_time(self, epc: str, temps_sec: int):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM histoires WHERE epc = ?", (epc,))
            result = cursor.fetchone()

            if result:
                cursor.execute(
                    """
                    UPDATE histoires
                    SET temps_lecture_sec = ?
                    WHERE id = ?
                """,
                    (temps_sec, result[0]),
                )
                print(f"⏱️ Temps de lecture mis à jour pour epc '{epc}' : {temps_sec} secondes")
            else:
                print(f"❌ Aucune histoire trouvée avec epc : {epc}")
