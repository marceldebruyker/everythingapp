# --- Imports ---
import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import json
import os
import gspread # For Google Sheets
from google.oauth2.service_account import Credentials # For authentication
from datetime import datetime # For timestamp

# --- Seitenkonfiguration ---
st.set_page_config(
    page_title="Beleg Scanner", # Simpler title maybe?
    page_icon="🧾",
    layout="wide"
)

# --- Titel und Beschreibung ---
st.title("🧾 Beleg Scanner mit Auto-Kategorisierung")
st.caption("Mache ein Foto oder lade Beleg-Bilder hoch für eine strukturierte Analyse inkl. Kategorie und Google Sheets Export.")

# --- API Key & Credentials Laden (Minimal Change for Render Fallback) ---
gemini_api_key = None
google_sheets_credentials_info = None
config_load_success = False # Flag to track successful loading

try:
    # Attempt standard loading (works locally, might fail partially on Render)
    gemini_api_key = st.secrets["GOOGLE_API_KEY"]
    google_sheets_credentials_info = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
    st.info("Secrets erfolgreich via st.secrets geladen.") # Will only show if both succeed here
    config_load_success = True # Mark as successful if try block completes

except (AttributeError, FileNotFoundError, KeyError, json.JSONDecodeError) as e:
    st.warning(f"Fehler beim direkten Laden via st.secrets: {e}. Versuche Umgebungsvariablen als Fallback.")

    # --- Fallback for API Key ---
    if not gemini_api_key: # Check if API key wasn't loaded in try block
        gemini_api_key = os.getenv("GOOGLE_API_KEY")
        if gemini_api_key:
             st.info("Gemini API Key via Umgebungsvariable geladen.")
        else:
             st.error("Google Gemini API Key konnte weder via st.secrets noch Umgebungsvariable gefunden werden!")
             st.stop() # Stop if API Key is definitely missing

    # --- Fallback for Sheets Credentials ---
    if not google_sheets_credentials_info: # Check if Sheets creds weren't loaded or parsed in try block
        google_sheets_credentials_str = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        if google_sheets_credentials_str:
            st.info("Google Sheets Credentials String via Umgebungsvariable gefunden. Versuche Parsing...")
            try:
                google_sheets_credentials_info = json.loads(google_sheets_credentials_str)
                # Add a basic validation check after parsing
                if not isinstance(google_sheets_credentials_info, dict) or "client_email" not in google_sheets_credentials_info:
                     raise ValueError("Ungültige Struktur oder fehlende 'client_email'.")
                st.success("Google Sheets Credentials via Umgebungsvariable erfolgreich geladen und geparst.")
                config_load_success = True # Mark success only if parsing env var works
            except json.JSONDecodeError as json_e:
                st.error(f"Konnte Google Sheets Credentials von Umgebungsvariable nicht parsen (ungültiges JSON): {json_e}")
                st.error(f"Empfangener String (Anfang): '{google_sheets_credentials_str[:70]}...'")
                st.info("Prüfe den Wert der 'GOOGLE_SHEETS_CREDENTIALS' Umgebungsvariable in Render. Er muss ein exakter, valider JSON-String sein.")
                st.stop() # Stop here if parsing env var fails
            except ValueError as val_e:
                 st.error(f"Fehler in Google Sheets Credentials Daten (aus Umgebungsvariable): {val_e}")
                 st.stop()
        else:
             # If we are here, st.secrets failed AND os.getenv returned None for Sheets
             st.error("Google Sheets Credentials konnten weder via st.secrets noch Umgebungsvariable gefunden werden!")
             st.stop() # Stop if Sheets creds are definitely missing

# Final verification using the flag
if not config_load_success:
     # This path should ideally not be reached if stops above work correctly, but as a safeguard:
     st.error("Konfiguration der Credentials konnte nicht erfolgreich abgeschlossen werden.")
     st.stop()

# Display loaded info for confirmation
st.write(f"✔️ Gemini API Key geladen (endet mit ...{gemini_api_key[-4:]}).")
st.write(f"✔️ Google Sheets Credentials geladen für: {google_sheets_credentials_info.get('client_email')}.")
st.divider()


# --- Google Services Konfiguration ---
spreadsheet = None
worksheet = None

try:
    # Gemini
    genai.configure(api_key=gemini_api_key)
    # Verwende das aktuelle leistungsfähige Modell
    model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')

    # Google Sheets
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file"
    ]
    credentials = Credentials.from_service_account_info(
        google_sheets_credentials_info,
        scopes=scopes
    )
    gc = gspread.authorize(credentials)
    GOOGLE_SHEET_ID = "1fKDqRooTtlIf7q4WsIczLEEvhC7FCHrH_gOVkjrbGcY"
    WORKSHEET_NAME = "Ausgaben"

    try:
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        st.success(f"Erfolgreich mit Google Sheet (ID: ...{GOOGLE_SHEET_ID[-6:]}) > '{WORKSHEET_NAME}' verbunden.")
    except gspread.exceptions.APIError as api_e:
        st.error(f"API Fehler: {api_e}")
        st.error(f"Sheet (ID: ...{GOOGLE_SHEET_ID[-6:]}) geteilt mit {google_sheets_credentials_info.get('client_email')} (Editor)?")
        st.stop()
    except gspread.WorksheetNotFound:
         st.error(f"Arbeitsblatt '{WORKSHEET_NAME}' im Sheet (ID: ...{GOOGLE_SHEET_ID[-6:]}) nicht gefunden.")
         st.stop()
    except Exception as sheet_e:
         st.error(f"Fehler beim Google Sheet Zugriff: {sheet_e}")
         st.stop()

except Exception as e:
     st.error(f"Fehler bei Konfiguration der Google Services: {e}")
     st.stop()

# --- Definitionen für Schema, Header und Kategorien ---

# Schema für Top-Level JSON (ohne Änderungen)
EXPECTED_SCHEMA = {
    "merchant_name": "", "merchant_address": "", "vat_id": "",
    "transaction_date": "", "transaction_time": "", "currency": "",
    "receipt_number": "", "items": [], "subtotal": None,
    "tax_details": [], "total_tax_amount": None, "total_amount": None
}

# Schema für jeden Artikel INKLUSIVE Kategorie
EXPECTED_ITEM_SCHEMA = {
    "description": "",
    "category": "Sonstiges / Unkategorisiert", # NEU: Default Kategorie
    "quantity": 1,
    "unit": "",
    "unit_price": None,
    "total_price": None,
    "vat_rate": None
}

# Schema für Steuerdetails (ohne Änderungen)
EXPECTED_TAX_DETAIL_SCHEMA = {
    "vat_percent": None, "net_amount": None, "tax_amount": None, "gross_amount": None
}

# Spaltenüberschriften für Google Sheets INKLUSIVE Kategorie
EXPECTED_HEADERS = [
    "Timestamp Added", "Receipt Date", "Receipt Time", "Store Name",
    "Receipt Number", "Receipt Total Amount", "Currency",
    "Item Category", # NEU: Spalte für Kategorie
    "Item Description", "Item Quantity", "Item Unit", "Item Unit Price",
    "Item Total Price", "Item VAT Rate", "Filename", "Receipt VAT ID",
    "Receipt Address", "Receipt Subtotal", "Receipt Total Tax Amount"
]

# Liste der erlaubten Kategorien für den LLM Prompt (detaillierter bei Lebensmitteln)
ALLOWED_CATEGORIES = [
    # --- Lebensmittel & Getränke (detailliert) ---
    "Lebensmittel: Milchprodukte & Eier",        # Milch, Joghurt, Käse, Quark, Butter, Eier
    "Lebensmittel: Backwaren",                   # Brot, Brötchen, Kuchen, Gebäck
    "Lebensmittel: Fleisch & Wurst",
    "Lebensmittel: Fisch",
    "Lebensmittel: Obst (frisch)",
    "Lebensmittel: Gemüse (frisch)",
    "Lebensmittel: Tiefkühlkost (Gemüse, Obst, Fisch, Fleisch, Fertiggerichte)", # Kombiniert TK
    "Lebensmittel: Konserven & Gläser",          # Eingemachtes Gemüse/Obst, Suppen, Fertigsaucen in Glas/Dose
    "Lebensmittel: Trockenwaren & Beilagen",     # Nudeln, Reis, Mehl, Zucker, Müsli, Haferflocken, Hülsenfrüchte
    "Lebensmittel: Öle, Fette & Gewürze",        # Speiseöl, Essig, Margarine, Salz, Pfeffer, Kräuter
    "Lebensmittel: Brotaufstriche (süß & herzhaft)", # Marmelade, Honig, Nuss-Nougat-Creme, Frischkäse (als Aufstrich), Leberwurst etc.
    "Lebensmittel: Süßigkeiten & Snacks",        # Schokolade, Chips, Kekse, Eis, Knabberzeug
    "Lebensmittel: Babynahrung",
    "Getränke: Wasser",
    "Getränke: Säfte & Softdrinks",
    "Getränke: Kaffee, Tee & Kakao",
    "Getränke: Bier",
    "Getränke: Wein & Sekt",
    "Getränke: Spirituosen",
    "Getränke: Pfand",                           # Explizite Kategorie für Pfandbeträge

    # --- Andere Kategorien (wie zuvor) ---
    "Haushalt: Reinigungsmittel",
    "Haushalt: Papier- & Hygieneartikel",        # Toilettenpapier, Küchenrolle, Taschentücher, Müllbeutel etc.
    "Drogerie: Körperpflege",                    # Shampoo, Duschgel, Zahnpasta, Deo etc.
    "Drogerie: Gesundheit & Apotheke",           # Rezeptfreie Medikamente, Pflaster, Vitamine
    "Drogerie: Kosmetik",                        # Make-up, spezielle Hautpflege
    "Außer Haus: Restaurant / Imbiss",
    "Außer Haus: Café / Bäckerei",
    "Außer Haus: Lieferdienste",
    "Außer Haus: Kantine / Mensa",
    "Transport: Tanken / Kraftstoff",
    "Transport: ÖPNV / Fahrkarten",
    "Transport: Parken",
    "Freizeit: Bücher & Medien",
    "Freizeit: Kultur & Events",
    "Freizeit: Hobbybedarf",
    "Freizeit: Sport",
    "Kleidung & Schuhe",
    "Kinder: Spielzeug",                         # Exkl. Babynahrung
    "Kinder: Schulbedarf",
    "Haustiere: Futter",
    "Haustiere: Bedarf & Tierarzt",
    "Haus & Garten: Werkzeug & Material",
    "Haus & Garten: Pflanzen & Bedarf",
    "Geschenke",
    "Sonstiges / Unkategorisiert"                # Auffangkategorie
]

# --- Hilfsfunktion: Schema erzwingen (aktualisiert für Item-Kategorie) ---
def ensure_json_schema(data, filename="Bild"):
    """Stellt sicher, dass das JSON-Objekt dem EXPECTED_SCHEMA entspricht, inkl. Item-Kategorie."""
    if not isinstance(data, dict):
        return data
    output = {k: data.get(k, d) for k, d in EXPECTED_SCHEMA.items()}
    # Items bereinigen (jetzt mit Kategorie)
    if isinstance(output["items"], list):
        processed_items = []
        for item in output["items"]:
            if isinstance(item, dict):
                # Verwende das aktualisierte EXPECTED_ITEM_SCHEMA
                processed_item = {k: item.get(k, d) for k, d in EXPECTED_ITEM_SCHEMA.items()}
                # Optional: Validieren, ob die vom LLM gewählte Kategorie erlaubt ist
                if processed_item["category"] not in ALLOWED_CATEGORIES:
                    st.warning(f"[{filename}] Ungültige Kategorie '{processed_item['category']}' für '{processed_item['description']}' erkannt, setze auf Default.")
                    processed_item["category"] = EXPECTED_ITEM_SCHEMA["category"] # Setze auf Default
                processed_items.append(processed_item)
        output["items"] = processed_items
    else: output["items"] = []
    # Tax Details bereinigen (unverändert)
    if isinstance(output["tax_details"], list):
        processed_tax_details = []
        for detail in output["tax_details"]:
             if isinstance(detail, dict):
                 processed_detail = {k: detail.get(k, d) for k, d in EXPECTED_TAX_DETAIL_SCHEMA.items()}
                 processed_tax_details.append(processed_detail)
        output["tax_details"] = processed_tax_details
    else: output["tax_details"] = []
    # Zahlen prüfen (unverändert)
    for key in ["subtotal", "total_tax_amount", "total_amount"]:
        if output[key] is not None and not isinstance(output[key], (int, float)):
            try: output[key] = float(output[key])
            except: output[key] = None
    return output

# --- Hilfsfunktion für die Gemini API Analyse (MIT KATEGORISIERUNG IM PROMPT) ---
def analyze_receipt_with_gemini(image_bytes, filename="Bild"):
    """Sendet Bild an Gemini, bittet um strukturierte Analyse INKL. Artikel-Kategorisierung."""
    img = None
    response = None
    potential_json_string = None
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Erstelle den String der erlaubten Kategorien für den Prompt
        categories_string = ", ".join([f'"{cat}"' for cat in ALLOWED_CATEGORIES])

        # --- ANGEPASSTER PROMPT MIT KATEGORISIERUNG ---
        prompt = f"""
        Analysiere diesen Kassenzettel oder diese Rechnung SEHR GENAU. Extrahiere die
        Informationen UND kategorisiere JEDEN Artikel. Gib das Ergebnis AUSSCHLIESSLICH
        als valides JSON-Objekt zurück.

        WICHTIG: Das JSON-Objekt MUSS IMMER ALLE unten aufgeführten Top-Level-Felder enthalten.
        Wenn eine Information nicht gefunden wird, setze den Wert auf `null` oder `""`.
        FÜR JEDEN ARTIKEL muss eine Kategorie zugewiesen werden!

        Erlaubte Kategorien für Artikel sind NUR die folgenden: {categories_string}.
        Verwende "Sonstiges / Unkategorisiert", wenn keine andere Kategorie passt.

        Gewünschte Felder:
        - "merchant_name": (string).
        - "merchant_address": (string, "" wenn nicht vorhanden).
        - "vat_id": (string, "" wenn nicht vorhanden).
        - "transaction_date": (string, YYYY-MM-DD).
        - "transaction_time": (string, HH:MM, "" wenn nicht vorhanden).
        - "currency": (string).
        - "receipt_number": (string, "" wenn nicht vorhanden).
        - "items": Eine Liste von Objekten für jeden Artikel (leere Liste `[]` wenn keine erkannt):
            - "description": Die Beschreibung des Artikels (string).
            - "category": Die Kategorie des Artikels aus der obigen Liste (string). <--- NEU!
            - "quantity": Menge (number, default 1).
            - "unit": Einheit (string, "" wenn nicht vorhanden).
            - "unit_price": Preis pro Einheit (number, `null` wenn nicht vorhanden).
            - "total_price": Gesamtpreis des Postens (number).
            - "vat_rate": MwSt-Satz (number, `null` wenn nicht vorhanden).
        - "subtotal": (number, `null` wenn nicht vorhanden).
        - "tax_details": Liste von Objekten (leere Liste `[]` wenn nicht vorhanden):
            - "vat_percent": (number).
            - "net_amount": (number).
            - "tax_amount": (number).
            - "gross_amount": (number).
        - "total_tax_amount": (number, `null` wenn nicht vorhanden).
        - "total_amount": (number).

        KEINE ANDEREN FELDER HINZUFÜGEN!

        Beispiel für die ZWINGEND einzuhaltende Struktur (mit Kategorie):
        {{
          "merchant_name": "Beispiel Shop", "merchant_address": "Musterweg 1", "vat_id": "",
          "transaction_date": "2024-01-15", "transaction_time": "10:05", "currency": "EUR",
          "receipt_number": "R-1002",
          "items": [
            {{"description": "Bio Tomaten", "category": "Lebensmittel: Obst & Gemüse (speziell)", "quantity": 0.55, "unit": "kg", "unit_price": 3.99, "total_price": 2.20, "vat_rate": 7}},
            {{"description": "Vollmilch 1L", "category": "Lebensmittel: Grundnahrungsmittel", "quantity": 2, "unit": "Stk", "unit_price": 1.19, "total_price": 2.38, "vat_rate": 7}},
            {{"description": "Duschgel Men", "category": "Drogerie: Körperpflege", "quantity": 1, "unit": "", "unit_price": null, "total_price": 1.99, "vat_rate": 19}},
            {{"description": "AA Batterien", "category": "Sonstiges / Unkategorisiert", "quantity": 1, "unit": "Stk", "unit_price": 3.49, "total_price": 3.49, "vat_rate": 19}}
          ],
          "subtotal": 9.07,
          "tax_details": [
            {{"vat_percent": 7, "net_amount": 4.28, "tax_amount": 0.30, "gross_amount": 4.58}},
            {{"vat_percent": 19, "net_amount": 4.61, "tax_amount": 0.88, "gross_amount": 5.49}}
          ],
          "total_tax_amount": 1.18,
          "total_amount": 9.07
        }}

        Hier ist der Kassenzettel/die Rechnung:
        """
        # Send API Request
        response = model.generate_content(
            [prompt, img],
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json"),
            request_options={'timeout': 240} # Timeout ggf. leicht erhöhen wegen komplexerem Task
        )

        # --- JSON Parsing (unverändert, aber jetzt mit Kategorie im Ergebnis) ---
        try:
            response_text = response.text.strip()
            json_start_index = -1; first_brace = response_text.find('{'); first_bracket = response_text.find('[')
            if first_brace != -1 and first_bracket != -1: json_start_index = min(first_brace, first_bracket)
            elif first_brace != -1: json_start_index = first_brace
            elif first_bracket != -1: json_start_index = first_bracket

            if json_start_index != -1:
                start_char = response_text[json_start_index]; end_char = '}' if start_char == '{' else ']'
                json_end_index = response_text.rfind(end_char, json_start_index)
                if json_end_index != -1:
                    potential_json_string = response_text[json_start_index : json_end_index + 1]
                    parsed_json = json.loads(potential_json_string)
                    # Schema-Prüfung beinhaltet jetzt die Kategorie
                    guaranteed_json = ensure_json_schema(parsed_json, filename)
                    return guaranteed_json
                else:
                    st.error(f"Kein JSON-Endzeichen ('{end_char}') für '{filename}' gefunden.")
                    # ... (Fehlerausgabe wie vorher) ...
                    return None
            else:
                st.error(f"Kein JSON-Start ('{{' oder '[') für '{filename}' gefunden.")
                # ... (Fehlerausgabe wie vorher) ...
                return None
        except json.JSONDecodeError as e:
            st.error(f"JSON Parse Fehler für '{filename}': {e}")
            # ... (Fehlerausgabe wie vorher) ...
            return None
        except Exception as inner_e:
             st.error(f"Verarbeitungsfehler für '{filename}': {inner_e}")
             # ... (Fehlerausgabe wie vorher) ...
             return None
    # --- Generelle Fehlerbehandlung (unverändert) ---
    except Exception as e:
        st.error(f"Analysefehler für '{filename}': {type(e).__name__}")
        # ... (Fehlerausgabe wie vorher) ...
        return None

# --- Funktion zum Speichern in Google Sheets (AKTUALISIERT MIT KATEGORIE) ---
def save_to_google_sheet(results_list, sheet_instance, worksheet_instance):
    """Formatiert Ergebnisse inkl. Kategorie, prüft/setzt Header & fügt Zeilen ein."""
    if not results_list: return 0

    # --- HEADER CHECK (unverändert, aber EXPECTED_HEADERS enthält jetzt Kategorie) ---
    header_added_or_verified = False
    try:
        header_row = worksheet_instance.row_values(1)
        if header_row == EXPECTED_HEADERS: header_added_or_verified = True
        else:
            st.warning("Header-Zeile fehlt/falsch. Setze Header...")
            worksheet_instance.insert_row(EXPECTED_HEADERS, 1)
            st.info("Header-Zeile eingefügt/aktualisiert.")
            header_added_or_verified = True
    except gspread.exceptions.APIError as e:
        if 'exceeds grid limits' in str(e).lower() or 'unable to parse range' in str(e).lower():
            st.info("Sheet leer. Füge Header hinzu...")
            try:
                worksheet_instance.insert_row(EXPECTED_HEADERS, 1)
                st.info("Header-Zeile eingefügt.")
                header_added_or_verified = True
            except Exception as header_insert_e:
                 st.error(f"Header setzen fehlgeschlagen: {header_insert_e}"); return 0
        else: st.error(f"Header prüfen fehlgeschlagen: {e}"); return 0
    except Exception as e: st.error(f"Header prüfen fehlgeschlagen: {e}"); return 0
    if not header_added_or_verified: st.error("Header nicht ok."); return 0

    # --- DATENVERARBEITUNG (mit Kategorie) ---
    rows_to_append = []
    timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for result in results_list:
        filename = result["filename"]
        data = result["data"]
        meta_info = { # Meta-Infos bleiben gleich
            "Timestamp Added": timestamp_now, "Receipt Date": data.get("transaction_date", ""),
            "Receipt Time": data.get("transaction_time", ""), "Store Name": data.get("merchant_name", ""),
            "Receipt Number": data.get("receipt_number", ""), "Receipt Total Amount": data.get("total_amount", None),
            "Currency": data.get("currency", ""), "Filename": filename, "Receipt VAT ID": data.get("vat_id", ""),
            "Receipt Address": data.get("merchant_address", ""), "Receipt Subtotal": data.get("subtotal", None),
            "Receipt Total Tax Amount": data.get("total_tax_amount", None),
        }
        items = data.get("items", [])
        if not items: continue
        for item in items:
            # Erstelle Zeile - Reihenfolge muss zu EXPECTED_HEADERS passen!
            row = [
                meta_info["Timestamp Added"], meta_info["Receipt Date"], meta_info["Receipt Time"],
                meta_info["Store Name"], meta_info["Receipt Number"], meta_info["Receipt Total Amount"],
                meta_info["Currency"],
                item.get("category", EXPECTED_ITEM_SCHEMA["category"]), # NEU: Kategorie holen
                item.get("description", ""), item.get("quantity", 1),
                item.get("unit", ""), item.get("unit_price", None), item.get("total_price", None),
                item.get("vat_rate", None), meta_info["Filename"], meta_info["Receipt VAT ID"],
                meta_info["Receipt Address"], meta_info["Receipt Subtotal"], meta_info["Receipt Total Tax Amount"],
            ]
            row = ["" if v is None else v for v in row]
            rows_to_append.append(row)

    # --- DATEN SCHREIBEN (unverändert) ---
    if rows_to_append:
        try:
            worksheet_instance.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            return len(rows_to_append)
        except Exception as e: st.error(f"Fehler beim Schreiben in Sheets: {e}"); return 0
    else: return 0

# --- Streamlit UI Definition (unverändert) ---
col1, col2 = st.columns(2)
with col1: st.header("Option 1: Fotografieren"); img_file_buffer = st.camera_input("Kamera aktivieren", key="camera")
with col2: st.header("Option 2: Hochladen"); uploaded_files = st.file_uploader("Wähle Bilder aus", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="uploader")

# --- Verarbeitung und Anzeige der Eingabebilder (unverändert) ---
images_to_process = []
if img_file_buffer:
    if not hasattr(img_file_buffer, 'name'): img_file_buffer.name = f"Kamerabild_{hash(img_file_buffer)}.jpg"
    images_to_process.append(img_file_buffer)
if uploaded_files: images_to_process.extend(uploaded_files)

if images_to_process:
    with st.expander("Vorschau der ausgewählten Bilder", expanded=False):
        num_cols = min(len(images_to_process), 5); cols = st.columns(num_cols)
        for idx, image_file in enumerate(images_to_process):
            with cols[idx % num_cols]: st.image(image_file, caption=f"{image_file.name}", width=150)
st.divider()

# --- Analyse-Bereich (unverändert) ---
if images_to_process:
    st.header(f"Bereit zur Analyse von {len(images_to_process)} Beleg(en)")
    if st.button(f"✨ Analysiere & Speichere {len(images_to_process)} Beleg(e)!", type="primary", key="analyze_button"):
        st.subheader("⚙️ Verarbeitung läuft..."); analysis_successful = 0; analysis_failed = 0
        all_results_structured = []; progress_bar = st.progress(0); status_text = st.empty()
        result_placeholder = st.container()
        for i, image_file in enumerate(images_to_process):
            status_text.info(f"Verarbeite Bild {i+1}/{len(images_to_process)}: {image_file.name}...")
            image_bytes = image_file.getvalue()
            analysis_result = analyze_receipt_with_gemini(image_bytes, filename=image_file.name)
            with result_placeholder:
                if analysis_result and isinstance(analysis_result, dict):
                     st.success(f"✅ Analyse für {image_file.name} erfolgreich.")
                     analysis_successful += 1
                     all_results_structured.append({"filename": image_file.name,"data": analysis_result})
                else:
                     st.error(f"❌ Analyse für {image_file.name} fehlgeschlagen (siehe Details oben).")
                     analysis_failed += 1
            progress_bar.progress((i + 1) / len(images_to_process))
        status_text.info("Analyse abgeschlossen. Speichere Ergebnisse in Google Sheets...")
        rows_added = 0
        if worksheet and all_results_structured: rows_added = save_to_google_sheet(all_results_structured, spreadsheet, worksheet)
        elif not all_results_structured and analysis_successful > 0: st.warning("Keine Ergebnisse zum Speichern.")
        elif not worksheet: st.error("Keine Worksheet-Verbindung.")
        status_text.empty(); progress_bar.empty()
        st.subheader("🏁 Verarbeitungsübersicht")
        st.success(f"{analysis_successful} Beleg(e) erfolgreich analysiert.")
        if analysis_failed > 0: st.warning(f"{analysis_failed} Beleg(e) nicht analysiert (siehe Fehlerdetails oben).")
        if rows_added > 0: st.success(f"{rows_added} Artikel-Zeilen zu '{WORKSHEET_NAME}' hinzugefügt.")
        elif analysis_successful > 0: st.warning("Keine Zeilen hinzugefügt.")
else: st.info("Bitte mache ein Foto oder lade Bilder hoch.")

# --- Footer ---
st.markdown("---")
st.markdown("Entwickelt mit [Streamlit](https://streamlit.io), [Google Gemini](https://ai.google.dev/) & [gspread](https://docs.gspread.org/).")