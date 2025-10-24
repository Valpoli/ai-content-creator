import os
import sqlite3


class ImageDatabase:
    def __init__(self, db_path=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = db_path or os.path.join(base_dir, "images.db")
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    epc TEXT PRIMARY KEY,
                    width INTEGER,
                    height INTEGER,
                    inference_steps INTEGER,
                    prompt_magic BOOLEAN,
                    alchemy_mode BOOLEAN,
                    high_resolution BOOLEAN,
                    is_custom_model BOOLEAN,
                    is_sdxl BOOLEAN,
                    autres_parametres TEXT,
                    prompt TEXT,
                    negative_prompt TEXT,
                    model_id TEXT,
                    preset_style TEXT
                )
            """)
        # print("✅ Base de données des images créée ou déjà existante.")

    def add_entry(
        self,
        epc,
        width=None,
        height=None,
        inference_steps=None,
        prompt_magic=None,
        alchemy_mode=None,
        high_resolution=None,
        is_custom_model=None,
        is_sdxl=None,
        prompt=None,
        negative_prompt=None,
        model_id=None,
        preset_style=None,
        autres_parametres=None,
    ):
        fields = ["epc"]
        values = [epc]

        optional_fields = {
            "width": width,
            "height": height,
            "inference_steps": inference_steps,
            "prompt_magic": bool(prompt_magic) if prompt_magic is not None else None,
            "alchemy_mode": bool(alchemy_mode) if alchemy_mode is not None else None,
            "high_resolution": bool(high_resolution) if high_resolution is not None else None,
            "is_custom_model": bool(is_custom_model) if is_custom_model is not None else None,
            "is_sdxl": bool(is_sdxl) if is_sdxl is not None else None,
            "autres_parametres": autres_parametres,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "model_id": model_id,
            "preset_style": preset_style,
        }

        for field, value in optional_fields.items():
            if value is not None:
                fields.append(field)
                values.append(value)

        placeholders = ", ".join(["?"] * len(fields))
        fields_sql = ", ".join(fields)

        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT INTO images ({fields_sql})
                    VALUES ({placeholders})
                """,
                    values,
                )
                print(f"✅ Entrée ajoutée pour epc: {epc}")
        except sqlite3.IntegrityError:
            print(f"❌ Une entrée avec epc '{epc}' existe déjà.")

    def delete_entry(self, epc):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM images WHERE epc = ?", (epc,))
            deleted = cursor.rowcount

        if deleted:
            print(f"🗑️ Entrée avec epc '{epc}' supprimée.")
        else:
            print(f"⚠️ Aucune entrée trouvée avec epc '{epc}'.")

    def pretty_print_entry(self, epc):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM images WHERE epc = ?", (epc,))
            row = cursor.fetchone()

        if row is None:
            print(f"❌ Aucune entrée trouvée pour epc '{epc}'")
            return

        columns = [
            "epc",
            "width",
            "height",
            "inference_steps",
            "prompt_magic",
            "alchemy_mode",
            "high_resolution",
            "is_custom_model",
            "is_sdxl",
            "autres_parametres",
            "prompt",
            "negative_prompt",
            "model_id",
            "preset_style",
        ]

        print("\n🖼️  Entrée trouvée :")
        print("────────────────────────────────────")
        for col, val in zip(columns, row):
            print(f"{col.ljust(18)} : {val}")
        print("────────────────────────────────────\n")

    def exists(self, epc):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM images WHERE epc = ? LIMIT 1", (epc,))
            return cursor.fetchone() is not None

    def search_by_title(self, title):
        search_pattern = f"{title.lower().replace(' ', '_')}%"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT epc FROM images WHERE epc LIKE ?", (search_pattern,))
            rows = cursor.fetchall()

        epcs = [row[0] for row in rows]
        if not epcs:
            print(f"❌ Aucun EPC trouvé pour le titre : {title}")
        else:
            print(f"🔍 EPC trouvés pour le titre « {title} » :")
            for epc in epcs:
                print(f" - {epc}")
        return epcs
