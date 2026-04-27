"""Reset StarLin's portrait URLs so generate_base_portraits.py will regenerate only StarLin."""
import sqlite3

conn = sqlite3.connect("soulpulse.db")
conn.execute("UPDATE ai_personas SET base_face_url = NULL, avatar_url = '' WHERE name = '林星野'")
conn.commit()
print("Reset StarLin base_face_url and avatar_url")
conn.close()
