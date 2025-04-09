# pages/02_Analyse.py
# Version: 1.3 (Robust Authentication)

# --- Core Imports ---
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
import plotly.express as px
import datetime
import json # For parsing credential string
import os  # For os.getenv fallback
import warnings

# --- Configuration ---
# !! Make sure these match your Google Sheet !!
GOOGLE_SHEET_NAME = "Haushaltsbuch" # The overall Google Sheet filename
WORKSHEET_NAME = "Ausgaben"         # The specific worksheet tab name

# !! Make sure these match the EXACT column headers in your sheet !!
# Case-sensitive!
DATE_COLUMN = 'Receipt Date'
TIMESTAMP_COLUMN = 'Timestamp Added'
ITEM_CATEGORY_COLUMN = 'Item Category'
ITEM_DESC_COLUMN = 'Item Description'
ITEM_PRICE_COLUMN = 'Item Total Price'
ITEM_UNIT_PRICE_COLUMN = 'Item Unit Price'
RECEIPT_TOTAL_COLUMN = 'Receipt Total Amount'
STORE_COLUMN = 'Store Name'
RECEIPT_NUM_COLUMN = 'Receipt Number'
FILENAME_COLUMN = 'Filename'
# Other potential columns used in logic
ITEM_QUANTITY_COLUMN = 'Item Quantity'
ITEM_VAT_RATE_COLUMN = 'Item VAT Rate'
RECEIPT_SUBTOTAL_COLUMN = 'Receipt Subtotal'
RECEIPT_TAX_COLUMN = 'Receipt Total Tax Amount'
RECEIPT_ADDRESS_COLUMN = 'Receipt Address'
RECEIPT_VAT_ID_COLUMN = 'Receipt VAT ID'
RECEIPT_TIME_COLUMN = 'Receipt Time'

# --- App Settings ---
CURRENCY_SYMBOL = "EUR"
# Define how uncategorized items are represented in your sheet (for cleaning)
UNCATEGORIZED = ["Sonstiges / Unkategorisiert", "", None]

# --- Page Setup ---
# Keep this commented out if your main app script (app.py/Home.py) sets it.
# st.set_page_config(layout="wide", page_title="Haushaltsbuch Analyse", page_icon="📊")

st.title("📊 Dein Digitales Haushaltsbuch - Analyse")
st.markdown("Analyse deiner Ausgaben basierend auf gescannten Kassenzetteln.")
st.divider()

# --- Authentication & Data Loading ---

def authenticate_gspread():
    """
    Authenticates with Google Sheets API using Service Account JSON string.
    Tries st.secrets first, then falls back to os.getenv.
    Returns an authorized gspread client object or None on failure.
    """
    google_sheets_credentials_info = None
    config_load_success = False
    source_msg = "unknown source" # For logging/display

    # --- 1. Try loading via st.secrets (primary method) ---
    try:
        # Attempt to access the secret key
        creds_string = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]
        source_msg = "st.secrets (local: .streamlit/secrets.toml)"
        # Attempt to parse the JSON string
        google_sheets_credentials_info = json.loads(creds_string)
        # Basic validation
        if not isinstance(google_sheets_credentials_info, dict) or "client_email" not in google_sheets_credentials_info:
            raise ValueError("Invalid structure or missing 'client_email'.")
        # st.info(f"Credentials successfully loaded and parsed via {source_msg}.") # Can be verbose
        config_load_success = True

    except (KeyError, AttributeError, FileNotFoundError):
        # This happens if the key doesn't exist in secrets or secrets file not found
        st.warning(f"GOOGLE_SHEETS_CREDENTIALS key not found via {source_msg}. Trying os.getenv fallback...")
    except json.JSONDecodeError as e_json_secrets:
        st.error(f"Failed to parse JSON from {source_msg}['GOOGLE_SHEETS_CREDENTIALS']: {e_json_secrets}")
        st.error("Check formatting in secrets.toml if running locally.")
        # Stop if parsing fails from primary source
        return None
    except ValueError as e_val_secrets:
         st.error(f"Data validation error in credentials from {source_msg}: {e_val_secrets}")
         # Stop if validation fails from primary source
         return None
    except Exception as e_other_secrets:
        # Catch any other unexpected errors during st.secrets access/parsing
        st.error(f"Unexpected error reading/parsing secrets via {source_msg}: {e_other_secrets}")
        return None


    # --- 2. Fallback to os.getenv (if st.secrets failed or wasn't successful) ---
    if not config_load_success:
        creds_string_env = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        source_msg = "os.getenv (Render Environment Variable)"
        if creds_string_env:
            # st.info(f"Found GOOGLE_SHEETS_CREDENTIALS string via {source_msg}. Attempting parse...") # Can be verbose
            try:
                # Attempt to parse the JSON string from environment variable
                google_sheets_credentials_info = json.loads(creds_string_env)
                # Basic validation
                if not isinstance(google_sheets_credentials_info, dict) or "client_email" not in google_sheets_credentials_info:
                     raise ValueError("Invalid structure or missing 'client_email'.")
                # st.success(f"Credentials successfully loaded and parsed via {source_msg}.") # Can be verbose
                config_load_success = True
            except json.JSONDecodeError as e_json_env:
                st.error(f"Failed to parse JSON from {source_msg}('GOOGLE_SHEETS_CREDENTIALS'): {e_json_env}")
                st.error(f"Received string (start): '{creds_string_env[:70]}...'")
                st.error("Check the Environment Variable value in your deployment settings (e.g., Render).")
                # Stop if parsing env var fails
                return None
            except ValueError as e_val_env:
                 st.error(f"Data validation error in credentials from {source_msg}: {e_val_env}")
                 # Stop if validation fails from env var
                 return None
            except Exception as e_other_env:
                 st.error(f"Unexpected error parsing credentials via {source_msg}: {e_other_env}")
                 return None
        else:
            # Only show the definitive error if BOTH methods failed to find the variable/key
            st.error("GOOGLE_SHEETS_CREDENTIALS could not be found via st.secrets or os.getenv.")
            # Stop if definitely missing
            return None

    # --- 3. Authorize Gspread Client (if credentials loaded successfully) ---
    if config_load_success and google_sheets_credentials_info:
        try:
            st.info(f"Authenticating Google Sheets using credentials parsed via {source_msg} for: {google_sheets_credentials_info.get('client_email', 'N/A')}")
            credentials = Credentials.from_service_account_info(
                google_sheets_credentials_info,
                scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            )
            gc = gspread.authorize(credentials)
            st.success("Google Sheets Client successfully authorized.") # Confirm success
            return gc
        except Exception as auth_e:
            st.error(f"Failed to authorize gspread client with loaded credentials: {auth_e}")
            return None
    else:
        # This path should ideally not be reached due to earlier checks, but as a safeguard:
        st.error("Authentication failed: Could not obtain valid credentials.")
        return None


@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(_gc: gspread.Client):
    """Loads data from the specified Google Sheet and Worksheet."""
    if _gc is None:
        st.error("Gspread client not available for loading data.")
        return pd.DataFrame() # Return empty if client isn't valid
    try:
        spreadsheet = _gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        st.info(f"Accessing Worksheet: '{WORKSHEET_NAME}' in Sheet: '{GOOGLE_SHEET_NAME}'...")
        # Use na_filter=False to prevent empty strings becoming NaN initially
        # header=0 assumes first row is the header
        df = get_as_dataframe(worksheet, evaluate_formulas=True, header=0, na_filter=False)
        st.success(f"Daten erfolgreich aus '{GOOGLE_SHEET_NAME}/{WORKSHEET_NAME}' geladen ({len(df)} Zeilen).")
        if df.empty:
            st.warning("Die Tabelle wurde geladen, enthält aber keine Datenzeilen.")
        return df
    except gspread.SpreadsheetNotFound:
        st.error(f"Google Sheet '{GOOGLE_SHEET_NAME}' nicht gefunden.")
        st.error("Mögliche Ursachen: Falscher Name, Sheet nicht für Service Account E-Mail geteilt (Editor-Rechte benötigt).")
        return pd.DataFrame()
    except gspread.WorksheetNotFound:
        st.error(f"Worksheet '{WORKSHEET_NAME}' im Sheet '{GOOGLE_SHEET_NAME}' nicht gefunden.")
        return pd.DataFrame()
    except gspread.exceptions.APIError as api_error:
         st.error(f"Google Sheets API Fehler beim Laden: {api_error}")
         st.error("Stelle sicher, dass die Google Sheets API im Google Cloud Projekt aktiviert ist und das Service Account Berechtigungen hat.")
         return pd.DataFrame()
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler beim Laden der Daten aus Google Sheets ist aufgetreten: {e}")
        return pd.DataFrame()

def preprocess_data(df_input):
    """Cleans and preprocesses the raw DataFrame."""
    if df_input.empty:
        st.warning("Preprocessing skipped: Input DataFrame is empty.")
        return df_input

    df = df_input.copy() # Work on a copy to avoid modifying the cached original

    st.info("Starte Datenvorverarbeitung...")
    initial_rows = len(df)

    # --- Column Existence Check (Essential Columns) ---
    essential_cols = [DATE_COLUMN, ITEM_CATEGORY_COLUMN, ITEM_PRICE_COLUMN, ITEM_DESC_COLUMN]
    missing_essential = [col for col in essential_cols if col not in df.columns]
    if missing_essential:
        st.error(f"Essentielle Spalten fehlen in der Tabelle: {', '.join(missing_essential)}. Abbruch der Vorverarbeitung.")
        return pd.DataFrame() # Return empty if essential columns are missing

    # --- Date Conversion & Validation ---
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors='coerce')
    df.dropna(subset=[DATE_COLUMN], inplace=True) # Drop rows where date conversion failed
    rows_after_date_dropna = len(df)
    if rows_after_date_dropna < initial_rows:
        st.warning(f"{initial_rows - rows_after_date_dropna} Zeilen entfernt (ungültiges Datum in '{DATE_COLUMN}').")
    if df.empty:
        st.error("Keine Zeilen mit gültigem Datum vorhanden. Abbruch.")
        return df

    # --- Other Timestamp Conversion (Optional) ---
    if TIMESTAMP_COLUMN in df.columns:
        df[TIMESTAMP_COLUMN] = pd.to_datetime(df[TIMESTAMP_COLUMN], errors='coerce')
    else:
        st.info(f"Optional: Spalte '{TIMESTAMP_COLUMN}' nicht gefunden.")

    # --- Extract Date Parts ---
    df['Year'] = df[DATE_COLUMN].dt.year
    df['Month'] = df[DATE_COLUMN].dt.month
    df['Month_Name'] = df[DATE_COLUMN].dt.strftime('%Y-%m')
    df['DayOfWeek'] = df[DATE_COLUMN].dt.day_name()

    # --- Time Conversion (Optional) ---
    if RECEIPT_TIME_COLUMN in df.columns:
        # Try specific format first, fallback to general parsing
        df['Hour'] = pd.to_datetime(df[RECEIPT_TIME_COLUMN], format='%H:%M', errors='coerce').dt.hour
        # Fill NaNs from first attempt using general parsing for other formats (like HH:MM:SS)
        if df['Hour'].isnull().any():
             mask_nan_hour = df['Hour'].isnull()
             df.loc[mask_nan_hour, 'Hour'] = pd.to_datetime(df.loc[mask_nan_hour, RECEIPT_TIME_COLUMN], errors='coerce').dt.hour
    else:
        st.info(f"Optional: Spalte '{RECEIPT_TIME_COLUMN}' nicht gefunden, Stundenanalyse nicht möglich.")
        df['Hour'] = None # Assign None if column missing

    # --- Numeric Conversion (Iterate through expected numeric columns) ---
    numeric_cols = [
        ITEM_PRICE_COLUMN, ITEM_UNIT_PRICE_COLUMN, RECEIPT_TOTAL_COLUMN,
        ITEM_QUANTITY_COLUMN, ITEM_VAT_RATE_COLUMN, RECEIPT_SUBTOTAL_COLUMN, RECEIPT_TAX_COLUMN
    ]
    for col in numeric_cols:
        if col in df.columns:
             # Replace empty strings and None with pd.NA before numeric conversion
             df[col] = df[col].replace(['', None], pd.NA)
             # Convert to numeric, coercing errors to NaN, then fill NaN with 0
             df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(float) # Ensure float type
        else:
             st.info(f"Optional: Numerische Spalte '{col}' nicht gefunden, wird mit 0 angenommen wenn nötig.")
             # If a numeric column is expected but missing, create it and fill with 0
             # df[col] = 0 # Decide if creating missing columns is desired

    # --- String Cleaning: Category ---
    # Replace specified uncategorized values and fill remaining NaNs
    df[ITEM_CATEGORY_COLUMN] = df[ITEM_CATEGORY_COLUMN].replace(UNCATEGORIZED[1:], UNCATEGORIZED[0]).fillna(UNCATEGORIZED[0]).astype(str)

    # --- String Cleaning: Item Description ---
    df[ITEM_DESC_COLUMN] = df[ITEM_DESC_COLUMN].astype(str).str.strip()

    # --- Final Type Checks (Example) ---
    # These were already handled during numeric conversion, but good practice
    # df[ITEM_PRICE_COLUMN] = df[ITEM_PRICE_COLUMN].astype(float)
    # if ITEM_QUANTITY_COLUMN in df.columns: df[ITEM_QUANTITY_COLUMN] = df[ITEM_QUANTITY_COLUMN].astype(float)

    st.success(f"Datenvorverarbeitung abgeschlossen. {len(df)} gültige Zeilen verbleiben.")
    return df


# ==============================================================================
# --- Main Application Logic Starts Here ---
# ==============================================================================

# 1. Authenticate with Google Sheets
gc = authenticate_gspread()

# 2. Proceed only if authentication is successful
if gc:
    # 3. Load data from the sheet
    df_raw = load_data(gc)

    # 4. Proceed only if data loading is successful and returns data
    if not df_raw.empty:
        # 5. Preprocess the raw data
        df_processed = preprocess_data(df_raw)

        # 6. Proceed only if preprocessing is successful and returns data
        if not df_processed.empty:
            # ==================================================================
            # --- UI Rendering Starts Here (Data is Ready) ---
            # ==================================================================

            # --- Sidebar Filters ---
            st.sidebar.header("Filter (Analyse)")
            try:
                # Determine min/max dates from the processed data
                min_date = df_processed[DATE_COLUMN].min().date()
                max_date = df_processed[DATE_COLUMN].max().date()
                # Set default range, ensuring start <= end
                default_start = min_date
                default_end = max_date
                if default_start > default_end: default_start = default_end

                # Create the date input widget
                date_range_selected = st.sidebar.date_input(
                    "Zeitraum auswählen:",
                    value=(default_start, default_end),
                    min_value=min_date,
                    max_value=max_date,
                    key="analyse_date_filter" # Unique key for this widget
                )
            except Exception as e_date_select:
                 st.sidebar.error(f"Fehler beim Setup des Datumsfilters: {e_date_select}")
                 st.error("Datumsfilter konnte nicht erstellt werden.")
                 st.stop() # Stop if filter setup fails

            # --- Apply Date Filter to create filtered_df ---
            df_filtered = pd.DataFrame() # Initialize empty
            start_date_ts, end_date_ts = None, None # Keep track of timestamps for messages
            if len(date_range_selected) == 2:
                start_date_ts = pd.Timestamp(date_range_selected[0])
                end_date_ts = pd.Timestamp(date_range_selected[1])
                if start_date_ts <= end_date_ts:
                    # Apply the date filter using .loc for efficiency and clarity
                    date_mask = (df_processed[DATE_COLUMN] >= start_date_ts) & (df_processed[DATE_COLUMN] <= end_date_ts)
                    df_filtered = df_processed.loc[date_mask].copy() # Use .loc and make a copy
                else:
                    st.sidebar.warning("Startdatum liegt nach dem Enddatum. Kein Zeitraum gefiltert.")
            # --- End Date Filter Application ---


            # --- Main Content Area with Tabs ---
            tab_overview, tab_categories, tab_items, tab_receipts, tab_time, tab_budget, tab_quality = st.tabs([
                "📈 Übersicht", "🛒 Kategorien", "🏷️ Artikelpreise", "🧾 Belegdetails",
                "⏰ Zeitanalyse", "💰 Budget (Demo)", "🧹 Datenqualität"
            ])

            # --- Display Warning if Filtered Data is Empty (but range was valid) ---
            if df_filtered.empty and start_date_ts and end_date_ts and start_date_ts <= end_date_ts:
                 st.warning(f"Keine Daten im ausgewählten Zeitraum ({start_date_ts.strftime('%d.%m.%Y')} - {end_date_ts.strftime('%d.%m.%Y')}) gefunden.")
            # --- Proceed to Render Tabs ONLY if df_filtered has data ---
            elif not df_filtered.empty:

                # --- 1. Overview Tab ---
                with tab_overview:
                    st.header("Übersicht deiner Ausgaben")
                    # --- Calculate Metrics ---
                    total_spending_items = df_filtered[ITEM_PRICE_COLUMN].sum()
                    # Get unique receipt totals sum
                    receipt_id_cols = [DATE_COLUMN, STORE_COLUMN, RECEIPT_NUM_COLUMN, RECEIPT_TOTAL_COLUMN]
                    receipt_id_cols = [col for col in receipt_id_cols if col in df_filtered.columns] # Check existence
                    receipt_totals = df_filtered.drop_duplicates(subset=receipt_id_cols)
                    total_spending_receipts = receipt_totals[RECEIPT_TOTAL_COLUMN].sum()
                    # Time period calculation
                    num_days = (end_date_ts - start_date_ts).days + 1 # Inclusive
                    avg_daily_spending = total_spending_items / num_days if num_days > 0 else 0
                    num_receipts = len(receipt_totals)
                    avg_receipt_value = total_spending_receipts / num_receipts if num_receipts > 0 else 0

                    st.info(f"Gesamt (Summe Artikel): {total_spending_items:.2f} {CURRENCY_SYMBOL}. | Gesamt (Summe Belege): {total_spending_receipts:.2f} {CURRENCY_SYMBOL}.")

                    # --- Display Metrics ---
                    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                    metric_col1.metric("Gesamtausgaben (Artikel)", f"{total_spending_items:.2f} {CURRENCY_SYMBOL}")
                    metric_col2.metric("Ø Ausgaben / Tag", f"{avg_daily_spending:.2f} {CURRENCY_SYMBOL}")
                    metric_col3.metric("Anzahl Belege", f"{num_receipts}")
                    metric_col4.metric("Ø Wert / Beleg", f"{avg_receipt_value:.2f} {CURRENCY_SYMBOL}")
                    st.markdown("---")

                    # --- Spending Over Time Chart ---
                    st.subheader("Ausgaben über Zeit")
                    # Group by date (day level) and sum item prices
                    spending_ts = df_filtered.groupby(df_filtered[DATE_COLUMN].dt.date)[ITEM_PRICE_COLUMN].sum().reset_index()
                    spending_ts = spending_ts.rename(columns={DATE_COLUMN: "Datum", ITEM_PRICE_COLUMN: "Ausgaben"})
                    if not spending_ts.empty:
                        fig_time = px.line(spending_ts, x='Datum', y='Ausgaben', title="Tägliche Ausgaben", markers=True)
                        fig_time.update_layout(xaxis_title="Datum", yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})")
                        st.plotly_chart(fig_time, use_container_width=True)
                    else: st.info("Keine Zeitreihendaten im Zeitraum.")

                    # --- Spending by Category Chart ---
                    st.subheader("Ausgaben nach Kategorie")
                    spending_cat = df_filtered.groupby(ITEM_CATEGORY_COLUMN)[ITEM_PRICE_COLUMN].sum().reset_index()
                    # Filter out zero spending categories and sort
                    spending_cat = spending_cat[spending_cat[ITEM_PRICE_COLUMN] > 0].sort_values(by=ITEM_PRICE_COLUMN, ascending=False)

                    chart_type_cat = st.selectbox("Kategorie-Charttyp:", ["Donut", "Treemap", "Balken"], key="cat_chart_type_select")
                    if not spending_cat.empty:
                        chart_args_cat = {"names": ITEM_CATEGORY_COLUMN, "values": ITEM_PRICE_COLUMN, "title": "Ausgabenanteil pro Kategorie"}
                        if chart_type_cat == "Donut":
                            fig_cat = px.pie(**chart_args_cat, hole=0.4)
                            fig_cat.update_traces(textposition='outside', textinfo='percent+label')
                        elif chart_type_cat == "Treemap":
                            fig_cat = px.treemap(spending_cat, path=[ITEM_CATEGORY_COLUMN], **chart_args_cat) # Use path for treemap
                            fig_cat.update_traces(textinfo='label+value+percent root')
                        else: # Bar Chart
                            fig_cat = px.bar(spending_cat, x=ITEM_PRICE_COLUMN, y=ITEM_CATEGORY_COLUMN, orientation='h', **chart_args_cat)
                            fig_cat.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", yaxis_title="Kategorie")
                        st.plotly_chart(fig_cat, use_container_width=True)
                    else: st.info("Keine Kategoriedaten im Zeitraum.")


                # --- 2. Category Deep Dive ---
                with tab_categories:
                    st.header("Kategorie-Detailanalyse")
                    available_categories_list = sorted(df_filtered[ITEM_CATEGORY_COLUMN].unique())
                    if not available_categories_list:
                        st.warning("Keine Kategorien in den gefilterten Daten gefunden.")
                    else:
                        selected_category_dd = st.selectbox("Wähle eine Kategorie:", available_categories_list, key="cat_select")
                        if selected_category_dd:
                            # Filter data for the selected category
                            category_df_filtered = df_filtered[df_filtered[ITEM_CATEGORY_COLUMN] == selected_category_dd]
                            if not category_df_filtered.empty:
                                st.subheader(f"Analyse für: {selected_category_dd}")
                                # Metrics for selected category
                                cat_total = category_df_filtered[ITEM_PRICE_COLUMN].sum()
                                cat_items_count = len(category_df_filtered)
                                cat_quantity_sum = category_df_filtered[ITEM_QUANTITY_COLUMN].sum() if ITEM_QUANTITY_COLUMN in category_df_filtered else "N/A"
                                cat_m1, cat_m2, cat_m3 = st.columns(3)
                                cat_m1.metric("Gesamtausgaben", f"{cat_total:.2f} {CURRENCY_SYMBOL}")
                                cat_m2.metric("Anzahl Artikel", f"{cat_items_count}")
                                cat_m3.metric("Gesamtmenge", f"{cat_quantity_sum}")
                                st.markdown("---")
                                # Trend within category
                                st.write("**Ausgabenentwicklung in dieser Kategorie**")
                                cat_trend = category_df_filtered.groupby(category_df_filtered[DATE_COLUMN].dt.date)[ITEM_PRICE_COLUMN].sum().reset_index()
                                cat_trend = cat_trend.rename(columns={DATE_COLUMN: "Datum", ITEM_PRICE_COLUMN: "Ausgaben"})
                                if not cat_trend.empty:
                                    fig_cat_trend = px.line(cat_trend, x='Datum', y='Ausgaben', markers=True)
                                    fig_cat_trend.update_layout(yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})")
                                    st.plotly_chart(fig_cat_trend, use_container_width=True)
                                else: st.info("Keine Trenddaten für diese Kategorie im Zeitraum.")
                                # Top Items in Category
                                st.write("**Top Artikel in dieser Kategorie (nach Ausgaben)**")
                                cat_top_items = category_df_filtered.groupby(ITEM_DESC_COLUMN).agg(
                                     TotalSpending=(ITEM_PRICE_COLUMN, 'sum'),
                                     TimesPurchased=('Item Description', 'size') # Count occurrences
                                ).reset_index().sort_values(by='TotalSpending', ascending=False).head(15)
                                if not cat_top_items.empty:
                                     fig_cat_top = px.bar(cat_top_items, x='TotalSpending', y=ITEM_DESC_COLUMN, orientation='h',
                                                            title=f"Top 15 Artikel in '{selected_category_dd}'", hover_data=['TimesPurchased'])
                                     fig_cat_top.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", yaxis_title="Artikel")
                                     st.plotly_chart(fig_cat_top, use_container_width=True)
                                else: st.info("Keine Artikel in dieser Kategorie im Zeitraum.")
                                # Table of items in category
                                st.write("**Alle Artikel dieser Kategorie im Zeitraum**")
                                cat_table_cols = [DATE_COLUMN, STORE_COLUMN, ITEM_DESC_COLUMN, ITEM_QUANTITY_COLUMN, ITEM_UNIT_PRICE_COLUMN, ITEM_PRICE_COLUMN]
                                cat_table_cols = [col for col in cat_table_cols if col in category_df_filtered.columns] # Ensure columns exist
                                st.dataframe(category_df_filtered[cat_table_cols].sort_values(by=DATE_COLUMN, ascending=False), use_container_width=True)


                # --- 3. Item Price Tracker ---
                with tab_items:
                    st.header("Artikel-Preis-Tracker")
                    available_items_list = sorted(df_filtered[ITEM_DESC_COLUMN].astype(str).unique())
                    if not available_items_list:
                         st.warning("Keine Artikelbeschreibungen in den gefilterten Daten gefunden.")
                    else:
                        selected_item_pt = st.selectbox(
                            "Wähle einen Artikel:", available_items_list, index=0, key="item_select",
                            help="Wähle einen Artikel, um dessen Preisentwicklung zu sehen. Funktioniert am besten mit exakt gleichen Artikelnamen."
                        )
                        if selected_item_pt:
                            item_df_filtered = df_filtered[df_filtered[ITEM_DESC_COLUMN] == selected_item_pt].copy() # Use copy
                            if not item_df_filtered.empty:
                                st.subheader(f"Preisanalyse für: {selected_item_pt}")
                                # Determine price column logic (Unit vs Total)
                                price_col_plot = ITEM_PRICE_COLUMN # Default
                                price_col_label = f"Gesamtpreis ({CURRENCY_SYMBOL})"
                                price_info = f"Verwende '{ITEM_PRICE_COLUMN}'."
                                if ITEM_UNIT_PRICE_COLUMN in item_df_filtered.columns and item_df_filtered[ITEM_UNIT_PRICE_COLUMN].sum() > 0:
                                    # Add plausibility check here if needed (comparing unit_price vs total_price/quantity)
                                    # For simplicity now, just use unit price if it exists and has values > 0 often
                                    if item_df_filtered[ITEM_UNIT_PRICE_COLUMN].gt(0).mean() > 0.5: # If >50% have unit price > 0
                                         price_col_plot = ITEM_UNIT_PRICE_COLUMN
                                         price_col_label = f"Stückpreis ({CURRENCY_SYMBOL})"
                                         price_info = f"Verwende '{ITEM_UNIT_PRICE_COLUMN}'."
                                st.info(price_info)
                                item_df_filtered['Datum'] = item_df_filtered[DATE_COLUMN].dt.date # Group by day for plot

                                # Price Over Time Plot
                                st.write("**Preisentwicklung über Zeit**")
                                item_price_trend = item_df_filtered[[DATE_COLUMN, price_col_plot, STORE_COLUMN]].sort_values(by=DATE_COLUMN)
                                item_price_trend = item_price_trend[item_price_trend[price_col_plot] > 0] # Plot only positive prices
                                if not item_price_trend.empty:
                                    fig_item_trend = px.scatter(item_price_trend, x=DATE_COLUMN, y=price_col_plot, color=STORE_COLUMN, title=f"Preisverlauf für '{selected_item_pt}'")
                                    fig_item_trend.update_traces(mode='markers+lines') # Connect points per store
                                    fig_item_trend.update_layout(xaxis_title="Datum", yaxis_title=price_col_label, legend_title="Geschäft")
                                    st.plotly_chart(fig_item_trend, use_container_width=True)
                                else: st.info("Keine (positiven) Preisdaten zum Plotten.")

                                # Price Variation by Store
                                st.write("**Preisvergleich nach Geschäft im Zeitraum**")
                                item_price_by_store = item_df_filtered[item_df_filtered[price_col_plot] > 0].groupby(STORE_COLUMN)[price_col_plot].agg(['mean', 'min', 'max', 'count']).reset_index().sort_values(by='mean')
                                if not item_price_by_store.empty:
                                     st.dataframe(item_price_by_store.rename(columns={
                                         'mean': f'Ø {price_col_label}', 'min': f'Min {price_col_label}', 'max': f'Max {price_col_label}', 'count': 'Anzahl Käufe'
                                         }).round(2), # Round numeric values for display
                                         use_container_width=True, hide_index=True
                                     )
                                else: st.info("Keine Preisvergleichsdaten vorhanden.")


                # --- 4. Receipt Explorer ---
                with tab_receipts:
                    st.header("Belegdetails durchsuchen")
                    try:
                         # Create a unique identifier for each receipt robustly
                         receipt_id_cols = [DATE_COLUMN, RECEIPT_TIME_COLUMN, STORE_COLUMN, RECEIPT_NUM_COLUMN, FILENAME_COLUMN, RECEIPT_TOTAL_COLUMN]
                         receipt_id_cols = [col for col in receipt_id_cols if col in df_filtered.columns] # Ensure cols exist
                         # Convert relevant columns to string before concatenation
                         df_filtered_copy = df_filtered.copy() # Work on a temporary copy for ID generation
                         for col in receipt_id_cols:
                              df_filtered_copy[f'{col}_str'] = df_filtered_copy[col].astype(str)
                         id_cols_str = [f'{col}_str' for col in receipt_id_cols]
                         df_filtered_copy['Receipt_Unique_ID'] = df_filtered_copy[id_cols_str].agg('_'.join, axis=1)

                         # Prepare a summary view for selection (one row per receipt)
                         receipt_summary_df = df_filtered_copy.drop_duplicates(subset=['Receipt_Unique_ID']).sort_values(by=DATE_COLUMN, ascending=False)

                         # Create display options for the selectbox
                         receipt_options_ids = receipt_summary_df['Receipt_Unique_ID'].tolist()
                         display_options_list = []
                         option_id_map = {}
                         for index, row in receipt_summary_df.iterrows():
                             date_str = row[DATE_COLUMN].strftime('%Y-%m-%d') if pd.notna(row[DATE_COLUMN]) else '?'
                             store_str = str(row.get(STORE_COLUMN, '?'))
                             total_str = f"{row.get(RECEIPT_TOTAL_COLUMN, 0):.2f} {CURRENCY_SYMBOL}" if pd.notna(row.get(RECEIPT_TOTAL_COLUMN)) else '?'
                             time_str = str(row.get(RECEIPT_TIME_COLUMN, ''))
                             display_str = f"{date_str} {time_str} - {store_str} ({total_str})"
                             display_options_list.append(display_str)
                             option_id_map[display_str] = row['Receipt_Unique_ID'] # Map display string back to ID

                         st.write("Wähle einen Beleg aus der Dropdown-Liste:")
                         selected_display_option_re = st.selectbox("Beleg auswählen:", options=display_options_list, index=0 if display_options_list else None, key="receipt_select")

                         if selected_display_option_re and selected_display_option_re in option_id_map:
                             selected_receipt_unique_id = option_id_map[selected_display_option_re]
                             # Filter the copy again to get all items for this receipt ID
                             receipt_detail_display_df = df_filtered_copy[df_filtered_copy['Receipt_Unique_ID'] == selected_receipt_unique_id]

                             if not receipt_detail_display_df.empty:
                                 # Display receipt header info (take from the first row)
                                 receipt_info_row = receipt_detail_display_df.iloc[0]
                                 st.subheader(f"Details: {receipt_info_row.get(STORE_COLUMN,'N/A')} - {receipt_info_row[DATE_COLUMN].strftime('%Y-%m-%d')}")
                                 rec_m1, rec_m2, rec_m3 = st.columns(3)
                                 rec_m1.metric("Gesamtsumme (Beleg)", f"{receipt_info_row.get(RECEIPT_TOTAL_COLUMN, 0):.2f} {CURRENCY_SYMBOL}")
                                 rec_m2.metric("Datum", f"{receipt_info_row[DATE_COLUMN].strftime('%Y-%m-%d')}")
                                 rec_m3.metric("Uhrzeit", f"{receipt_info_row.get(RECEIPT_TIME_COLUMN, 'N/A')}")

                                 # Display items on the receipt
                                 st.write("**Gekaufte Artikel:**")
                                 receipt_item_cols = [ITEM_DESC_COLUMN, ITEM_QUANTITY_COLUMN, ITEM_UNIT_PRICE_COLUMN, ITEM_PRICE_COLUMN, ITEM_CATEGORY_COLUMN]
                                 receipt_item_cols = [col for col in receipt_item_cols if col in receipt_detail_display_df.columns]
                                 st.dataframe(receipt_detail_display_df[receipt_item_cols].reset_index(drop=True), use_container_width=True)

                                 # Optional: Display Receipt Image (if Filename is present and image accessible)
                                 receipt_filename = receipt_info_row.get(FILENAME_COLUMN)
                                 if receipt_filename and isinstance(receipt_filename, str) and receipt_filename.strip():
                                     st.write("**Beleg Bild (falls verfügbar):**")
                                     # !! ADJUST PATH LOGIC AS NEEDED !!
                                     # Assumes images are in a subdir 'receipt_images' relative to where streamlit runs
                                     # Or use a URL if stored online
                                     image_display_path = f"receipt_images/{receipt_filename}"
                                     try:
                                         st.image(image_display_path, caption=f"Beleg: {receipt_filename}", use_column_width='auto')
                                     except FileNotFoundError:
                                         st.warning(f"Bilddatei '{receipt_filename}' nicht im erwarteten Pfad '{image_display_path}' gefunden.")
                                     except Exception as e_img:
                                         st.error(f"Fehler beim Laden des Bildes '{receipt_filename}': {e_img}")
                                 else:
                                      st.info("Kein Dateiname für Bildanzeige in Daten gefunden.")

                    except Exception as e_receipt_explorer:
                         st.error(f"Fehler im Receipt Explorer Tab: {e_receipt_explorer}")


                # --- 5. Time Analysis ---
                with tab_time:
                    st.header("Zeitanalyse der Ausgaben")
                    time_c1, time_c2 = st.columns(2)
                    with time_c1:
                        st.subheader("Ausgaben nach Wochentag")
                        try:
                            spending_dow = df_filtered.groupby('DayOfWeek')[ITEM_PRICE_COLUMN].sum().reset_index()
                            weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                            spending_dow['DayOfWeek'] = pd.Categorical(spending_dow['DayOfWeek'], categories=weekday_order, ordered=True)
                            spending_dow = spending_dow.sort_values('DayOfWeek')
                            fig_dow = px.bar(spending_dow, x='DayOfWeek', y=ITEM_PRICE_COLUMN, title="Gesamtausgaben pro Wochentag")
                            fig_dow.update_layout(xaxis_title="Wochentag", yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})")
                            st.plotly_chart(fig_dow, use_container_width=True)
                        except Exception as e_dow: st.warning(f"Wochentags-Chart Fehler: {e_dow}")
                    with time_c2:
                        st.subheader("Ausgaben nach Tageszeit")
                        spending_hour = df_filtered.dropna(subset=['Hour']).copy() # Ensure 'Hour' column exists and has values
                        if not spending_hour.empty and spending_hour['Hour'].nunique() > 1:
                            try:
                                 spending_hour['Hour'] = spending_hour['Hour'].astype(int)
                                 spending_hour_grouped = spending_hour.groupby('Hour')[ITEM_PRICE_COLUMN].sum().reset_index()
                                 fig_hour = px.bar(spending_hour_grouped, x='Hour', y=ITEM_PRICE_COLUMN, title="Gesamtausgaben pro Stunde")
                                 fig_hour.update_layout(xaxis_title="Stunde des Tages (0-23)", yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", xaxis = dict(tickmode = 'linear', dtick = 1))
                                 st.plotly_chart(fig_hour, use_container_width=True)
                            except Exception as e_hour: st.warning(f"Stunden-Chart Fehler: {e_hour}")
                        else: st.info("Keine ausreichenden Daten für Stundenanalyse vorhanden.")


                # --- 6. Budgeting Module (Simple Demo) ---
                with tab_budget:
                    st.header("Budgetübersicht (Demo)")
                    st.info("Feste Demo-Budgets im Code. Analyse basiert auf dem **aktuellen Kalendermonat** (unabhängig vom Seitenleistenfilter).")
                    # Define budgets (Adjust these!)
                    # Example: Load from a simple dict, could be external file/sheet later
                    monthly_budgets_dict = {
                        "Lebensmittel: Milchprodukte & Eier": 50, "Lebensmittel: Backwaren": 30,
                        "Lebensmittel: Fleisch & Wurst": 80, "Lebensmittel: Obst (frisch)": 40,
                        "Lebensmittel: Gemüse (frisch)": 40, "Lebensmittel: Getränke: Kaffee, Tee & Kakao": 20,
                        "Drogerie: Körperpflege": 40, "Haushalt: Reinigungsmittel": 25,
                        "Außer Haus: Restaurant / Imbiss": 100, "Transport: Tanken / Kraftstoff": 150,
                        "Sonstiges / Unkategorisiert": 75,
                        # Add more categories as needed
                    }
                    # Use original *processed* df for current month analysis
                    now_dt = datetime.datetime.now()
                    current_month_start_dt = datetime.datetime(now_dt.year, now_dt.month, 1)
                    # Filter the main processed DataFrame for the current calendar month
                    current_month_data_df = df_processed[
                        (df_processed[DATE_COLUMN] >= pd.Timestamp(current_month_start_dt)) &
                        (df_processed[DATE_COLUMN] <= pd.Timestamp(now_dt))
                    ].copy()

                    if current_month_data_df.empty:
                        st.warning(f"Keine Ausgaben im aktuellen Monat ({now_dt.strftime('%B %Y')}) in den Daten gefunden.")
                    else:
                        st.subheader(f"Budget vs. Ausgaben für: {now_dt.strftime('%B %Y')}")
                        spending_this_actual_month = current_month_data_df.groupby(ITEM_CATEGORY_COLUMN)[ITEM_PRICE_COLUMN].sum()
                        budget_display_results = []
                        for category, budget_amount in monthly_budgets_dict.items():
                            spent_amount = spending_this_actual_month.get(category, 0) # Get spending, default to 0
                            progress_value = min(spent_amount / budget_amount, 1.0) if budget_amount > 0 else 0
                            remaining_amount = budget_amount - spent_amount
                            budget_display_results.append({
                                "Kategorie": category, "Budget": budget_amount, "Ausgegeben": spent_amount,
                                "Verbleibend": remaining_amount, "Fortschritt": progress_value
                            })
                        budget_display_df = pd.DataFrame(budget_display_results)

                        # Display budget progress bars and text
                        for index, row_data in budget_display_df.iterrows():
                            st.write(f"**{row_data['Kategorie']}**")
                            b_col1, b_col2 = st.columns([3, 1]) # Progress bar column wider
                            with b_col1:
                                st.progress(row_data['Fortschritt'])
                            with b_col2:
                                # Display spent/budget and remaining, color code if over budget
                                if row_data['Ausgegeben'] > row_data['Budget']:
                                    st.error(f"{row_data['Ausgegeben']:.2f} / {row_data['Budget']:.2f} {CURRENCY_SYMBOL} ({row_data['Verbleibend']:.2f})")
                                else:
                                    st.info(f"{row_data['Ausgegeben']:.2f} / {row_data['Budget']:.2f} {CURRENCY_SYMBOL} ({row_data['Verbleibend']:.2f})")

                        # Show spending for categories without a defined budget this month
                        st.markdown("---")
                        st.write("**Ausgaben in nicht budgetierten Kategorien (diesen Monat):**")
                        unbudgeted_spending_series = spending_this_actual_month[~spending_this_actual_month.index.isin(monthly_budgets_dict.keys())]
                        unbudgeted_spending_series = unbudgeted_spending_series[unbudgeted_spending_series > 0] # Show only categories with spending > 0
                        if not unbudgeted_spending_series.empty:
                             st.dataframe(
                                 unbudgeted_spending_series.reset_index().rename(columns={'index': ITEM_CATEGORY_COLUMN, ITEM_PRICE_COLUMN: f'Ausgaben ({CURRENCY_SYMBOL})'}),
                                 use_container_width=True, hide_index=True
                             )
                        else:
                             st.success("Keine Ausgaben in nicht budgetierten Kategorien diesen Monat.")


                # --- 7. Data Quality Check ---
                with tab_quality:
                    st.header("Überprüfung der Datenqualität")
                    st.subheader(f"Artikel mit generischer Kategorie ('{UNCATEGORIZED[0]}')")
                    st.info(f"Identifiziert Artikel im **ausgewählten Zeitraum**, deren Kategorie generisch ist. Korrigiere diese direkt in der Google Tabelle für bessere Analysen.")

                    # Check in the date-filtered data
                    uncategorized_items_df = df_filtered[df_filtered[ITEM_CATEGORY_COLUMN] == UNCATEGORIZED[0]]

                    if not uncategorized_items_df.empty:
                        st.warning(f"{len(uncategorized_items_df)} Artikel als '{UNCATEGORIZED[0]}' im Zeitraum gefunden.")
                        # Define columns to display for quality check
                        quality_display_cols = [
                            DATE_COLUMN, STORE_COLUMN, ITEM_DESC_COLUMN, ITEM_PRICE_COLUMN,
                            ITEM_CATEGORY_COLUMN, FILENAME_COLUMN
                        ]
                        quality_display_cols = [col for col in quality_display_cols if col in uncategorized_items_df.columns] # Ensure columns exist
                        st.dataframe(
                            uncategorized_items_df[quality_display_cols].sort_values(by=DATE_COLUMN, ascending=False),
                            use_container_width=True, hide_index=True
                        )
                        # Add button to link to the Google Sheet
                        try:
                             spreadsheet_url = gc.open(GOOGLE_SHEET_NAME).url
                             st.link_button("Google Sheet öffnen zum Korrigieren", spreadsheet_url, type="primary")
                        except Exception as e_link:
                             st.warning(f"Link zu Google Sheet konnte nicht erstellt werden: {e_link}")
                    else:
                        st.success(f"Alle Artikel im ausgewählten Zeitraum scheinen spezifisch kategorisiert zu sein (nicht '{UNCATEGORIZED[0]}').")


            # --- End of Tab Rendering Block (if df_filtered has data) ---

        # --- End of Block (if df_processed has data) ---

    # --- If initial data loading failed or returned empty ---
    elif gc is not None: # Check gc again to ensure auth didn't fail silently
        st.warning(f"Konnte keine Daten aus Google Tabelle '{GOOGLE_SHEET_NAME}/{WORKSHEET_NAME}' laden oder die Tabelle ist leer.")
# --- End of Block (if gc is valid) ---

# --- If Authentication Failed ---
else:
     st.error("Authentifizierung fehlgeschlagen. Dashboard kann nicht angezeigt werden.")
     st.info("Überprüfe die 'GOOGLE_SHEETS_CREDENTIALS' in den Secrets/Umgebungsvariablen und die Freigabe des Google Sheets für das Service Account.")

# --- Sidebar Footer ---
st.sidebar.markdown("---")
st.sidebar.info("Analyse v1.3 (Robust Auth)")