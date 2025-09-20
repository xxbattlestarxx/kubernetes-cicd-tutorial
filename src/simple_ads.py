import re
import sqlite3
import os
import yaml
import json
import requests
from datetime import datetime, timedelta
from marktplaats import SearchQuery, SortBy, SortOrder, category_from_name # Let op: Category class wordt hier niet direct geïmporteerd
import time # Importeer time voor de sleep functie

# --- Laad configuratie ---
# Het config-bestand bevindt zich in de bovenliggende map 'Config'
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Config", "config.yaml")
try:
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print(f"Fout: Config-bestand niet gevonden op {config_path}. Zorg ervoor dat het bestaat.")
    config = {} # Lege config als bestand niet gevonden is

# Configuratieparameters
CATEGORY_ID = os.getenv('category_id')
POLL_INTERVAL_MINUTES = os.getenv('poll_interval')
BRANDS_TO_MONITOR = os.getenv('BRANDS_TO_MONITOR')  # Let op de hoofdletters

API_KEY = os.getenv('GEMINI_API_KEY')  # Let op de hoofdletters
TELEGRAM_BOT_TOKEN_BRAND_MATCH = os.getenv('TELEGRAM_BOT_TOKEN_KOOPJE')  # Let op de hoofdletters
TELEGRAM_CHAT_ID_BRAND_MATCH = os.getenv('TELEGRAM_CHAT_ID_KOOPJE')  # Let op de hoofdletters


# --- Database pad ---
# De database bevindt zich in dezelfde map als dit script (/data/)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simple_ads.db")

# --- Helper functies voor Telegram ---
def escape_markdown_v2(text):
    """
    Escapes special characters for Telegram MarkdownV2 parse mode.
    """
    text = text.replace('\\', '\\\\')
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    escaped_text = ""
    for char in text:
        if char in escape_chars:
            escaped_text += '\\' + char
        else:
            escaped_text += char
    return escaped_text

def send_telegram_message(message, bot_token, chat_id):
    """
    Verstuurt een bericht naar de opgegeven Telegram chat met de gegeven bot token.
    Het bericht wordt geacht al ge-escaped te zijn voor MarkdownV2 indien nodig.
    """
    if not bot_token or not chat_id:
        print("WAARSCHUWING: Telegram bot token of chat ID is niet ingesteld voor deze notificatie. Kan geen bericht versturen.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "MarkdownV2"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Telegram bericht verstuurd naar chat {chat_id}: {message[:50]}...")
        return True # Bericht succesvol verstuurd
    except requests.exceptions.RequestException as e:
        print(f"Fout bij versturen Telegram bericht naar chat {chat_id}: {e}")
        return False # Fout bij versturen

# --- Helper functies voor Database ---
def save_advertisement(title, description, link, price):
    """
    Slaat een advertentie op in de 'advertisements' tabel.
    De link dient als UNIQUE identifier. Initiële 'brand' en 'brand_notified' zijn NULL/0.
    """
    timestamp = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO advertisements (timestamp, title, description, link, price, brand, brand_notified)
        VALUES (?, ?, ?, ?, ?, NULL, 0)
    """, (timestamp, title, description, link, price))
    conn.commit()
    conn.close()
    if c.rowcount > 0:
        print(f"Advertentie '{title}' opgeslagen in DB met link: {link}")
        return True
    else:
        # print(f"Advertentie '{title}' met link '{link}' bestaat al in de DB. Overgeslagen.")
        return False

def update_advertisement_brand(link, brand):
    """
    Werkt de 'brand' bij in de 'advertisements' tabel.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE advertisements SET brand = ? WHERE link = ?", (brand, link))
    conn.commit()
    conn.close()

def update_advertisement_brand_notified_status(link, notified_status):
    """
    Werkt de 'brand_notified' status bij in de 'advertisements' tabel.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE advertisements SET brand_notified = ? WHERE link = ?", (notified_status, link))
    conn.commit()
    conn.close()

def get_unprocessed_ads_for_brand_identification():
    """
    Haalt alle advertenties op die nog geen 'brand' hebben (of NULL is) en een beschrijving hebben.
    Retourneert een lijst van (description, link) tuples.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT description, link FROM advertisements WHERE (brand IS NULL OR brand = '') AND description IS NOT NULL AND description != ''")
    unprocessed_ads = c.fetchall()
    conn.close()
    return unprocessed_ads

def get_ads_for_brand_comparison():
    """
    Haalt alle advertenties op die een 'brand' hebben gekregen en nog niet gemeld zijn.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT
            title,
            description,
            link,
            price,
            brand
        FROM
            advertisements
        WHERE
            brand IS NOT NULL AND brand != ''
            AND brand_notified = 0
    """)
    comparison_data = c.fetchall()
    conn.close()
    return comparison_data

# --- Helper functies voor Gemini API ---
def get_gemini_brand_interpretation(descriptions_list):
    """
    Gebruikt de Gemini API om in BULK het merk en de titel te interpreteren op basis van advertentiebeschrijvingen.
    Retourneert een lijst van strings, elk met een geïdentificeerd merk.
    """
    identified_brands_from_gemini = []
    if not descriptions_list:
        return identified_brands_from_gemini

    if not API_KEY:
        print("WAARSCHUWING: GEMINI_API_KEY is niet ingesteld. Kan geen Gemini API gebruiken voor bulk aanvraag.")
        return []

    input_str = json.dumps(descriptions_list)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={API_KEY}"
    prompt = (
        f"Je krijgt nu een lijst met advertentiebeschrijvingen (in het Nederlands). "
        f"Identificeer voor ELKE beschrijving het belangrijkste merk van het product dat wordt aangeboden. "
        f"Als er ook een duidelijk, algemeen erkende *titel* van het product is, vermeld deze dan ook naast het merk. "
        f"Als er geen duidelijk merk of titel is, retourneer dan 'Onbekend'. "
        f"Geef dit terug als een JSON-lijst van strings, waarbij elke string het geïdentificeerde merk en eventueel de titel is, in het formaat 'Merk: [Merknaam], Titel: [Titelnaam]', in dezelfde volgorde als de input.\n\n"
        f"Advertentiebeschrijvingen (in JSON-lijst formaat):\n{input_str}\n\n"
        f"Voorbeeld van verwachte antwoordstructuur (array van strings):\n"
        f"[\n"
        f" \"Merk: LEGO, Titel: Technic Bugatti Chiron\",\n"
        f" \"Merk: Playmobil, Titel: Piratenschip\",\n"
        f" \"Merk: Onbekend, Titel: Onbekend\"\n"
        f"]"
    )
    
    chatHistory = [{"role": "user", "parts": [{"text": prompt}]}]

    payload = {
        "contents": chatHistory,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": { "type": "STRING" }
            }
        }
    }
    
    headers = { 'Content-Type': 'application/json' }
    
    retries = 3
    for i in range(retries):
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()

            if result.get("candidates") and result["candidates"][0].get("content") and \
               result["candidates"][0]["content"].get("parts") and \
               len(result["candidates"][0]["content"]["parts"]) > 0 and \
               "text" in result["candidates"][0]["content"]["parts"][0] and \
               isinstance(result["candidates"][0]["content"]["parts"][0]["text"], str):
                text_json = result["candidates"][0]["content"]["parts"][0]["text"]
                try:
                    parsed_array = json.loads(text_json)
                    if isinstance(parsed_array, list):
                        return parsed_array
                    else:
                        print(f"Gemini API antwoord was geen lijst van strings zoals verwacht. Antwoord: {parsed_array}")
                        return []
                except json.JSONDecodeError as e:
                    print(f"Fout bij parsen JSON van Gemini API: {e}. Antwoord: {text_json}")
                    return []
            else:
                print(f"Gemini API antwoord had geen verwachte structuur. Antwoord: {result}")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Fout bij aanroepen Gemini API (poging {i+1}/{retries}): {e}")
            if i < retries - 1:
                time.sleep(2 ** i) # Exponentiële backoff
            else:
                return []
    return []

# --- Scraper functie ---
def scrape_and_process_ads():
    """
    Zoekt naar nieuwe advertenties op Marktplaats in de geconfigureerde categorie ID,
    slaat deze op in de DB, verwerkt merken met Gemini, en stuurt Telegram-notificaties.
    """
    print(f"\n[{datetime.now()}] Zoeken naar nieuwe advertenties op Marktplaats…")
    
    final_category_object = None
    category_name_to_use = "Accesspoints" # Naam die hoort bij ID 3022

    try:
        # Haal de categorie op via de naam, dit is de betrouwbare methode zoals in jouw eerdere werkende code
        final_category_object = category_from_name(category_name_to_use)
        print(f"Gebruik categorie: {category_name_to_use} (ID: {final_category_object.id})")
        
        # Controleer of het ID uit config.yaml overeenkomt met de opgehaalde categorie
        if CATEGORY_ID is not None and int(CATEGORY_ID) != final_category_object.id:
            print(f"WAARSCHUWING: Categorie ID in config.yaml ({CATEGORY_ID}) komt niet overeen met het ID verkregen via '{category_name_to_use}' ({final_category_object.id}). Het ID van de categorienaam wordt gebruikt voor het scrapen.")
        
    except Exception as e:
        print(f"Fout bij ophalen categorie '{category_name_to_use}': {e}. Kan niet doorgaan met scrapen.")
        return

    search = SearchQuery(
        query="", # Geen specifieke zoekterm hier
        zip_code="8334SX", # Pas dit aan indien nodig
        distance=1000000, # Max afstand
        limit=50, # Aangepast naar 50 resultaten per keer
        offset=0,
        sort_by=SortBy.DATE,
        sort_order=SortOrder.DESC,
        offered_since=datetime.now() - timedelta(days=8), # Advertenties van de afgelopen 8 dagen
        category=final_category_object
    )

    try:
        listings = search.get_listings()
        print(f"[{datetime.now()}] {len(listings)} advertenties gevonden in categorie '{category_name_to_use}' (ID: {final_category_object.id}).")
        
        for listing in listings:
            if listing.price is None:
                print(f"Advertentie zonder prijs overgeslagen: {listing.title} — {listing.link}")
                continue
            
            # Sla de titel, beschrijving, link en prijs op in de database
            # De functie save_advertisement controleert op duplicaten via de link
            save_advertisement(listing.title, listing.description, listing.link, listing.price)
            
    except Exception as e:
        print(f"Fout bij ophalen advertenties van Marktplaats: {e}")
    

# --- Hoofdworkflow uitvoering ---
if __name__ == "__main__":
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



    while True: # De hoofdworkflow in een oneindige loop gezet
        print(f"\n--- SCRAPER RONDJE START: {datetime.now()} ---")

        # 1. Scrape de laatste advertenties en sla ze op in de 'advertisements' tabel.
        scrape_and_process_ads()

        # 2. Haal alle advertenties op die nog geen 'brand' hebben gekregen voor Gemini.
        unprocessed_ads = get_unprocessed_ads_for_brand_identification()
        
        if not unprocessed_ads:
            print("\nGeen nieuwe advertenties gevonden om te verwerken via Gemini API voor merkanalyse.")
        else:
            print(f"\nVerwerken van {len(unprocessed_ads)} advertenties via Gemini API voor merkanalyse…")

            # Extraheer alleen de beschrijvingen voor de Gemini bulk-aanroep
            ads_descriptions_only = [ad[0] for ad in unprocessed_ads]
            
            # 3. Vraag Gemini om de merk- en titelinterpretaties in BULK
            gemini_identified_brands_and_titles = get_gemini_brand_interpretation(ads_descriptions_only)
            
            if len(gemini_identified_brands_and_titles) != len(unprocessed_ads):
                print("WAARSCHUWING: Het aantal geïdentificeerde merken/titels van Gemini komt niet overeen met het aantal ingevoerde beschrijvingen. Dit kan leiden tot onjuiste koppelingen.")
            
            for i, (original_ad_description, ad_link) in enumerate(unprocessed_ads):
                interpreted_result = None
                if i < len(gemini_identified_brands_and_titles):
                    interpreted_result = gemini_identified_brands_and_titles[i]

                # Extract brand and title from the interpreted_result string
                brand_match = re.search(r"Merk: ([^,]+)", interpreted_result)
                title_match = re.search(r"Titel: (.+)", interpreted_result)
                
                interpreted_brand = brand_match.group(1).strip() if brand_match else "Onbekend"
                # Als je de titel van Gemini ook wilt opslaan, moet de DB structuur uitgebreid worden.
                # Voor nu focussen we op het merk zoals gevraagd in de DB structuur.
                # interpreted_title = title_match.group(1).strip() if title_match else ""

                if interpreted_brand and interpreted_brand != "Onbekend":
                    print(f"  Verwerken van advertentie (link: {ad_link[:50]}...)")
                    print(f"    Gemini geïdentificeerd merk: '{interpreted_brand}'")
                    update_advertisement_brand(ad_link, interpreted_brand) # Update alleen het merk
                else:
                    print(f"  Advertentie (link: {ad_link[:50]}...): Gemini kon geen duidelijk merk identificeren.")
                    update_advertisement_brand(ad_link, "Onbekend") # Markeer als verwerkt maar onbekend

        # 4. Vergelijk geïdentificeerde merken met de te monitoren merken en verstuur notificaties
        print("\nVergelijken van geïdentificeerde merken met de geconfigureerde merkenlijst…")
        ads_for_comparison = get_ads_for_brand_comparison() 

        if not ads_for_comparison:
            print("Geen nieuwe advertenties gevonden met geïdentificeerde merken om te vergelijken die nog niet gemeld zijn.")
        else:
            for title, description, link, price, brand in ads_for_comparison:
                found_match = False
                for monitored_brand in BRANDS_TO_MONITOR:
                    # Fuzzy zoeken: gebruik re.search voor een case-insensitive en gedeeltelijke match
                    # Dit zoekt of het gemonitorde merk (of een deel daarvan) voorkomt in het geïnterpreteerde merk.
                    # 're.escape' zorgt ervoor dat speciale karakters in 'monitored_brand' correct worden behandeld.
                    if re.search(r'\b' + re.escape(monitored_brand) + r'\b', brand, re.IGNORECASE):
                        message = (
                            f"MERK MATCH GEVONDEN\\!\n\n"
                            f"Advertentie: *{escape_markdown_v2(title)}*\n"
                            f"Geïdentificeerd merk: *{escape_markdown_v2(brand)}*\n"
                            f"Zoekterm: *{escape_markdown_v2(monitored_brand)}*\n"
                            f"Prijs: €{escape_markdown_v2(f'{price:.2f}')}\n"
                            f"Link: {escape_markdown_v2(link)}"
                        )
                        if send_telegram_message(message, TELEGRAM_BOT_TOKEN_BRAND_MATCH, TELEGRAM_CHAT_ID_BRAND_MATCH):
                            update_advertisement_brand_notified_status(link, 1) # Markeer als gemeld
                            print(f"MERK MATCH! '{title}' voor merk '{brand}' gemeld en status bijgewerkt.")
                        else:
                            print(f"WAARSCHUWING: Kon MERK MATCH '{title}' niet melden via Telegram. Status niet bijgewerkt.")
                        found_match = True
                        break # Stop met zoeken als een match is gevonden
                
                if not found_match:
                    # Markeer advertenties die geen match zijn wel als "verwerkt" als je niet wilt dat ze opnieuw worden gecontroleerd
                    # update_advertisement_brand_notified_status(link, 1) # Uncomment dit als je ze niet opnieuw wilt checken
                    print(f"Geen match voor merk '{brand}' in advertentie '{title}' met de gemonitorde merken.")


        print(f"--- SCRAPER RONDJE KLAAR: {datetime.now()} ---")
        time.sleep(POLL_INTERVAL_MINUTES * 60) # Wacht N minuten voordat het script opnieuw start
