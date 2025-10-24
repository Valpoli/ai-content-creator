import json
import os
import sqlite3


class PersonnageDatabase:
    def __init__(self, db_path=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = db_path or os.path.join(base_dir, "personnages.db")
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS personnages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titre TEXT NOT NULL,
                    noms TEXT NOT NULL,  -- liste JSON
                    description TEXT NOT NULL,
                    UNIQUE(titre, noms)
                )
            """)
        # print("✅ Table 'personnages' prête.")

    def add_or_update(self, titre: str, noms: list[str], description: str):
        noms_json = json.dumps(noms, ensure_ascii=False)
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM personnages WHERE titre = ? AND noms = ?
            """,
                (titre, noms_json),
            )
            result = cursor.fetchone()

            if result:
                cursor.execute(
                    """
                    UPDATE personnages
                    SET description = ?
                    WHERE titre = ? AND noms = ?
                """,
                    (description, titre, noms_json),
                )
                print(f"🔁 Personnage(s) mis à jour : {noms} ({titre})")
            else:
                cursor.execute(
                    """
                    INSERT INTO personnages (titre, noms, description)
                    VALUES (?, ?, ?)
                """,
                    (titre, noms_json, description),
                )
                print(f"✅ Nouveau personnage ajouté : {noms} ({titre})")

    def get_by_title(self, titre: str) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM personnages WHERE titre = ? ORDER BY noms
            """,
                (titre,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def print_by_title(self, titre: str):
        personnages = self.get_by_title(titre)
        if not personnages:
            print(f"❌ Aucun personnage trouvé pour : {titre}")
            return

        print(f"\n📖 Personnages de l’histoire : {titre}\n")
        for p in personnages:
            noms_liste = json.loads(p["noms"])
            noms_affiches = ", ".join(noms_liste)
            print(f"🔹 {noms_affiches} — {p['description']}")


# Utilisation de l'exemple
# if __name__ == "__main__":
#     db = PersonnageDB()
#     db.print_by_title("bataille_de_la_frite_chaude")
