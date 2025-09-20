import sqlite3
import os
from datetime import datetime

# Bepaal het pad naar de database. Het wordt in dezelfde map als dit script aangemaakt.
current_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(current_dir, "simple_ads.db")

# Maak verbinding met de SQLite database (of maak deze aan als deze niet bestaat)
conn = sqlite3.connect(db_path)
c = conn.cursor()

# --- Tabel: advertisements (voor de gescrapete advertenties) ---
# Deze tabel slaat de naam, beschrijving, link, prijs, timestamp, het geïdentificeerde merk
# en de status van de merknotificatie op.
# De 'link' wordt gebruikt als een unieke identifier om duplicaten te voorkomen.
c.execute("""
CREATE TABLE IF NOT EXISTS advertisements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,              -- Tijdstip waarop de advertentie is toegevoegd
    title TEXT,                  -- Naam van de advertentie
    description TEXT,            -- Beschrijving van de advertentie
    link TEXT UNIQUE,            -- Unieke link naar de advertentie op Marktplaats of vergelijkbaar platform
    price REAL,                  -- Prijs van de advertentie
    brand TEXT DEFAULT NULL,     -- Geïdentificeerd merk door Gemini
    brand_notified INTEGER DEFAULT 0 -- Status voor Telegram notificatie voor merk: 0 = nog niet gemeld, 1 = gemeld
)
""")

# Voeg de 'brand' kolom toe aan de bestaande 'advertisements' tabel als deze er nog niet is
try:
    c.execute("ALTER TABLE advertisements ADD COLUMN brand TEXT DEFAULT NULL")
except sqlite3.OperationalError:
    pass # Kolom bestaat al

# Voeg de 'brand_notified' kolom toe als deze nog niet bestaat
try:
    c.execute("ALTER TABLE advertisements ADD COLUMN brand_notified INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass # Kolom bestaat al

# Sla de wijzigingen op in de database
conn.commit()
# Sluit de databaseverbinding
conn.close()

print(f"Database 'simple_ads.db' en 'advertisements' tabel succesvol aangemaakt/bijgewerkt op: {db_path}")
