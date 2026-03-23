import sqlite3

DB_PATH = r"D:\Github\personal_finances\data\finances.db"


def ejecutar_query(db_path: str, query: str):
    conn = None  # ← inicializar antes del try
    try:
        conn = sqlite3.connect(db_path)  # ← mover dentro del try
        cursor = conn.cursor()
        cursor.execute(query)
        query_upper = query.strip().upper()

        if query_upper.startswith("SELECT") or query_upper.startswith("PRAGMA"):
            columnas = [desc[0] for desc in cursor.description]
            filas = cursor.fetchall()

            print(" | ".join(columnas))
            print("-" * (len(" | ".join(columnas)) + 4))

            for fila in filas:
                print(" | ".join(str(v) for v in fila))

            print(f"\n📋 {len(filas)} fila(s) retornadas.")

        else:
            conn.commit()
            print(f"✅ Query ejecutada. Filas afectadas: {cursor.rowcount}")

    except sqlite3.Error as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()  # ← solo hacer rollback si conn existe
    finally:
        if conn:
            conn.close()  # ← solo cerrar si conn existe


if __name__ == "__main__":
    query = "UPDATE transactions SET category_id = 80 WHERE date BETWEEN '2026-03-09' AND '2026-03-22'"
    ejecutar_query(DB_PATH, query)