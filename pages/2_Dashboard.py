# pages/02_Analyse.py
# Version: 1.4 (Robust Auth + Plotly Pie Fix)

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
        creds_string = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]
        source_msg = "st.secrets (local: .streamlit/secrets.toml)"
        google_sheets_credentials_info = json.loads(creds_string)
        if not isinstance(google_sheets_credentials_info, dict) or "client_email" not in google_sheets_credentials_info:
            raise ValueError("Invalid structure or missing 'client_email'.")
        config_load_success = True
    except (KeyError, AttributeError, FileNotFoundError):
        st.warning(f"GOOGLE_SHEETS_CREDENTIALS key not found via {source_msg}. Trying os.getenv fallback...")
    except json.JSONDecodeError as e_json_secrets:
        st.error(f"Failed to parse JSON from {source_msg}['GOOGLE_SHEETS_CREDENTIALS']: {e_json_secrets}"); return None
    except ValueError as e_val_secrets:
         st.error(f"Data validation error in credentials from {source_msg}: {e_val_secrets}"); return None
    except Exception as e_other_secrets:
        st.error(f"Unexpected error reading/parsing secrets via {source_msg}: {e_other_secrets}"); return None

    # --- 2. Fallback to os.getenv (if st.secrets failed or wasn't successful) ---
    if not config_load_success:
        creds_string_env = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        source_msg = "os.getenv (Render Environment Variable)"
        if creds_string_env:
            try:
                google_sheets_credentials_info = json.loads(creds_string_env)
                if not isinstance(google_sheets_credentials_info, dict) or "client_email" not in google_sheets_credentials_info:
                     raise ValueError("Invalid structure or missing 'client_email'.")
                config_load_success = True
            except json.JSONDecodeError as e_json_env:
                st.error(f"Failed to parse JSON from {source_msg}('GOOGLE_SHEETS_CREDENTIALS'): {e_json_env}"); return None
            except ValueError as e_val_env:
                 st.error(f"Data validation error in credentials from {source_msg}: {e_val_env}"); return None
            except Exception as e_other_env:
                 st.error(f"Unexpected error parsing credentials via {source_msg}: {e_other_env}"); return None
        else:
            st.error("GOOGLE_SHEETS_CREDENTIALS could not be found via st.secrets or os.getenv."); return None

    # --- 3. Authorize Gspread Client (if credentials loaded successfully) ---
    if config_load_success and google_sheets_credentials_info:
        try:
            st.info(f"Authenticating Google Sheets using credentials parsed via {source_msg} for: {google_sheets_credentials_info.get('client_email', 'N/A')}")
            credentials = Credentials.from_service_account_info(
                google_sheets_credentials_info,
                scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            )
            gc = gspread.authorize(credentials)
            st.success("Google Sheets Client successfully authorized.")
            return gc
        except Exception as auth_e:
            st.error(f"Failed to authorize gspread client with loaded credentials: {auth_e}"); return None
    else:
        st.error("Authentication failed: Could not obtain valid credentials."); return None


@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(_gc: gspread.Client):
    """Loads data from the specified Google Sheet and Worksheet."""
    if _gc is None: st.error("Gspread client not available."); return pd.DataFrame()
    try:
        spreadsheet = _gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        st.info(f"Accessing Worksheet: '{WORKSHEET_NAME}' in Sheet: '{GOOGLE_SHEET_NAME}'...")
        df = get_as_dataframe(worksheet, evaluate_formulas=True, header=0, na_filter=False)
        st.success(f"Daten erfolgreich aus '{GOOGLE_SHEET_NAME}/{WORKSHEET_NAME}' geladen ({len(df)} Zeilen).")
        if df.empty: st.warning("Tabelle geladen, aber leer.")
        return df
    except gspread.SpreadsheetNotFound:
        st.error(f"Sheet '{GOOGLE_SHEET_NAME}' nicht gefunden. Teilen prüfen."); return pd.DataFrame()
    except gspread.WorksheetNotFound:
        st.error(f"Worksheet '{WORKSHEET_NAME}' nicht gefunden."); return pd.DataFrame()
    except gspread.exceptions.APIError as api_error:
         st.error(f"Google Sheets API Fehler: {api_error}. API/Berechtigungen prüfen."); return pd.DataFrame()
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}"); return pd.DataFrame()

def preprocess_data(df_input):
    """Cleans and preprocesses the raw DataFrame."""
    if df_input.empty: st.warning("Preprocessing skipped: Input leer."); return df_input
    df = df_input.copy()
    st.info("Starte Datenvorverarbeitung...")
    initial_rows = len(df)

    essential_cols = [DATE_COLUMN, ITEM_CATEGORY_COLUMN, ITEM_PRICE_COLUMN, ITEM_DESC_COLUMN]
    missing_essential = [col for col in essential_cols if col not in df.columns]
    if missing_essential:
        st.error(f"Essentielle Spalten fehlen: {', '.join(missing_essential)}. Abbruch."); return pd.DataFrame()

    # --- Date Conversion (crucial!) ---
    # Using errors='coerce' will turn unparseable dates into NaT (Not a Time)
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors='coerce')
    df.dropna(subset=[DATE_COLUMN], inplace=True) # Drop rows where date conversion failed
    rows_after_date_dropna = len(df)
    if rows_after_date_dropna < initial_rows:
        st.warning(f"{initial_rows - rows_after_date_dropna} Zeilen entfernt (ungültiges Datum in '{DATE_COLUMN}'). Bitte Format in Google Sheet prüfen (z.B. YYYY-MM-DD).")
    if df.empty: st.error("Keine Zeilen mit gültigem Datum vorhanden. Abbruch."); return df

    # --- Optional Timestamp/Time Conversion ---
    if TIMESTAMP_COLUMN in df.columns: df[TIMESTAMP_COLUMN] = pd.to_datetime(df[TIMESTAMP_COLUMN], errors='coerce')
    if RECEIPT_TIME_COLUMN in df.columns:
        df['Hour'] = pd.to_datetime(df[RECEIPT_TIME_COLUMN], format='%H:%M', errors='coerce').dt.hour
        if df['Hour'].isnull().any(): # Fallback parsing
             mask_nan_hour = df['Hour'].isnull()
             df.loc[mask_nan_hour, 'Hour'] = pd.to_datetime(df.loc[mask_nan_hour, RECEIPT_TIME_COLUMN], errors='coerce').dt.hour
    else: df['Hour'] = None

    # --- Date Part Extraction ---
    df['Year'] = df[DATE_COLUMN].dt.year
    df['Month'] = df[DATE_COLUMN].dt.month
    df['Month_Name'] = df[DATE_COLUMN].dt.strftime('%Y-%m')
    df['DayOfWeek'] = df[DATE_COLUMN].dt.day_name()

    # --- Numeric Conversion ---
    numeric_cols = [ ITEM_PRICE_COLUMN, ITEM_UNIT_PRICE_COLUMN, RECEIPT_TOTAL_COLUMN, ITEM_QUANTITY_COLUMN, ITEM_VAT_RATE_COLUMN, RECEIPT_SUBTOTAL_COLUMN, RECEIPT_TAX_COLUMN ]
    for col in numeric_cols:
        if col in df.columns:
             df[col] = df[col].replace(['', None], pd.NA)
             df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(float)
        # else: # Optionally create missing numeric columns with 0
             # df[col] = 0

    # --- String Cleaning ---
    df[ITEM_CATEGORY_COLUMN] = df[ITEM_CATEGORY_COLUMN].replace(UNCATEGORIZED[1:], UNCATEGORIZED[0]).fillna(UNCATEGORIZED[0]).astype(str)
    df[ITEM_DESC_COLUMN] = df[ITEM_DESC_COLUMN].astype(str).str.strip()

    st.success(f"Datenvorverarbeitung abgeschlossen. {len(df)} gültige Zeilen verbleiben.")
    return df


# ==============================================================================
# --- Main Application Logic Starts Here ---
# ==============================================================================

gc = authenticate_gspread() # 1. Authenticate

if gc: # 2. Proceed only if authenticated
    df_raw = load_data(gc) # 3. Load data

    if not df_raw.empty: # 4. Proceed only if data loaded
        df_processed = preprocess_data(df_raw) # 5. Preprocess

        if not df_processed.empty: # 6. Proceed only if data after preprocessing
            # --- UI Rendering Starts Here ---
            st.sidebar.header("Filter (Analyse)")
            try:
                min_date, max_date = df_processed[DATE_COLUMN].min().date(), df_processed[DATE_COLUMN].max().date()
                default_start, default_end = min_date, max_date
                if default_start > default_end: default_start = default_end
                date_range_selected = st.sidebar.date_input(
                    "Zeitraum auswählen:", value=(default_start, default_end),
                    min_value=min_date, max_value=max_date, key="analyse_date_filter"
                )
            except Exception as e_date_select:
                 st.sidebar.error(f"Fehler Datumsfilter: {e_date_select}"); st.stop()

            # --- Apply Date Filter ---
            df_filtered = pd.DataFrame()
            start_date_ts, end_date_ts = None, None
            if len(date_range_selected) == 2:
                start_date_ts, end_date_ts = pd.Timestamp(date_range_selected[0]), pd.Timestamp(date_range_selected[1])
                if start_date_ts <= end_date_ts:
                    date_mask = (df_processed[DATE_COLUMN] >= start_date_ts) & (df_processed[DATE_COLUMN] <= end_date_ts)
                    df_filtered = df_processed.loc[date_mask].copy()
                else: st.sidebar.warning("Startdatum liegt nach Enddatum.")

            # --- Main Content Area with Tabs ---
            tab_overview, tab_categories, tab_items, tab_receipts, tab_time, tab_budget, tab_quality = st.tabs([
                "📈 Übersicht", "🛒 Kategorien", "🏷️ Artikelpreise", "🧾 Belegdetails",
                "⏰ Zeitanalyse", "💰 Budget (Demo)", "🧹 Datenqualität"
            ])

            if df_filtered.empty and start_date_ts and end_date_ts and start_date_ts <= end_date_ts:
                 st.warning(f"Keine Daten im Zeitraum ({start_date_ts.strftime('%d.%m.%Y')} - {end_date_ts.strftime('%d.%m.%Y')}).")
            elif not df_filtered.empty:

                # --- 1. Overview Tab ---
                with tab_overview:
                    st.header("Übersicht deiner Ausgaben")
                    # Metrics Calculation
                    total_spending_items = df_filtered[ITEM_PRICE_COLUMN].sum()
                    receipt_id_cols = [DATE_COLUMN, STORE_COLUMN, RECEIPT_NUM_COLUMN, RECEIPT_TOTAL_COLUMN]
                    receipt_id_cols = [col for col in receipt_id_cols if col in df_filtered.columns]
                    receipt_totals = df_filtered.drop_duplicates(subset=receipt_id_cols)
                    total_spending_receipts = receipt_totals[RECEIPT_TOTAL_COLUMN].sum()
                    num_days = (end_date_ts - start_date_ts).days + 1
                    avg_daily_spending = total_spending_items / num_days if num_days > 0 else 0
                    num_receipts = len(receipt_totals)
                    avg_receipt_value = total_spending_receipts / num_receipts if num_receipts > 0 else 0
                    st.info(f"Gesamt (Artikel): {total_spending_items:.2f} {CURRENCY_SYMBOL}. | Gesamt (Belege): {total_spending_receipts:.2f} {CURRENCY_SYMBOL}.")
                    # Display Metrics
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Gesamt (Artikel)", f"{total_spending_items:.2f} {CURRENCY_SYMBOL}")
                    mc2.metric("Ø / Tag", f"{avg_daily_spending:.2f} {CURRENCY_SYMBOL}")
                    mc3.metric("Belege", f"{num_receipts}")
                    mc4.metric("Ø / Beleg", f"{avg_receipt_value:.2f} {CURRENCY_SYMBOL}")
                    st.markdown("---")
                    # Spending Over Time Chart
                    st.subheader("Ausgaben über Zeit")
                    spending_ts = df_filtered.groupby(df_filtered[DATE_COLUMN].dt.date)[ITEM_PRICE_COLUMN].sum().reset_index()
                    spending_ts = spending_ts.rename(columns={DATE_COLUMN: "Datum", ITEM_PRICE_COLUMN: "Ausgaben"})
                    if not spending_ts.empty:
                        fig_time = px.line(spending_ts, x='Datum', y='Ausgaben', title="Tägliche Ausgaben", markers=True)
                        st.plotly_chart(fig_time, use_container_width=True)
                    # Spending by Category Chart
                    st.subheader("Ausgaben nach Kategorie")
                    spending_cat = df_filtered.groupby(ITEM_CATEGORY_COLUMN)[ITEM_PRICE_COLUMN].sum().reset_index()
                    spending_cat = spending_cat[spending_cat[ITEM_PRICE_COLUMN] > 0].sort_values(by=ITEM_PRICE_COLUMN, ascending=False)
                    chart_type_cat = st.selectbox("Charttyp:", ["Donut", "Treemap", "Balken"], key="cat_chart_type_select")
                    if not spending_cat.empty:
                        chart_args_cat = {"names": ITEM_CATEGORY_COLUMN, "values": ITEM_PRICE_COLUMN, "title": "Ausgabenanteil"}
                        if chart_type_cat == "Donut":
                            # *** THE FIX IS HERE: Pass spending_cat as first argument ***
                            fig_cat = px.pie(spending_cat, **chart_args_cat, hole=0.4)
                            fig_cat.update_traces(textposition='outside', textinfo='percent+label')
                        elif chart_type_cat == "Treemap":
                            fig_cat = px.treemap(spending_cat, path=[ITEM_CATEGORY_COLUMN], **chart_args_cat)
                            fig_cat.update_traces(textinfo='label+value+percent root')
                        else: # Bar Chart
                            fig_cat = px.bar(spending_cat, x=ITEM_PRICE_COLUMN, y=ITEM_CATEGORY_COLUMN, orientation='h', title="Gesamtausgaben")
                            fig_cat.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", yaxis_title="Kategorie")
                        st.plotly_chart(fig_cat, use_container_width=True)
                    else: st.info("Keine Kategoriedaten im Zeitraum.")

                # --- 2. Category Deep Dive ---
                with tab_categories:
                    st.header("Kategorie-Detailanalyse")
                    available_cats = sorted(df_filtered[ITEM_CATEGORY_COLUMN].unique())
                    if available_cats:
                        selected_cat = st.selectbox("Wähle Kategorie:", available_cats, key="cat_select")
                        if selected_cat:
                            cat_df = df_filtered[df_filtered[ITEM_CATEGORY_COLUMN] == selected_cat]
                            if not cat_df.empty:
                                st.subheader(f"Analyse: {selected_cat}")
                                # Metrics
                                c_tot = cat_df[ITEM_PRICE_COLUMN].sum()
                                c_items = len(cat_df)
                                c_qty = cat_df[ITEM_QUANTITY_COLUMN].sum() if ITEM_QUANTITY_COLUMN in cat_df else "N/A"
                                c_m1, c_m2, c_m3 = st.columns(3)
                                c_m1.metric("Gesamt", f"{c_tot:.2f} {CURRENCY_SYMBOL}")
                                c_m2.metric("Artikel", c_items)
                                c_m3.metric("Menge", c_qty)
                                st.markdown("---")
                                # Trend
                                st.write("**Trend**")
                                cat_tr = cat_df.groupby(cat_df[DATE_COLUMN].dt.date)[ITEM_PRICE_COLUMN].sum().reset_index().rename(columns={DATE_COLUMN: "D", ITEM_PRICE_COLUMN: "A"})
                                if not cat_tr.empty:
                                    fig_c_tr = px.line(cat_tr, x='D', y='A', markers=True)
                                    st.plotly_chart(fig_c_tr, use_container_width=True)
                                # Top Items
                                st.write("**Top Artikel**")
                                cat_top = cat_df.groupby(ITEM_DESC_COLUMN).agg(Summe=(ITEM_PRICE_COLUMN, 'sum'),Anzahl=(ITEM_DESC_COLUMN, 'size')).reset_index().sort_values(by='Summe', ascending=False).head(15)
                                if not cat_top.empty:
                                     fig_c_top = px.bar(cat_top, x='Summe', y=ITEM_DESC_COLUMN, orientation='h', hover_data=['Anzahl'])
                                     fig_c_top.update_layout(yaxis={'categoryorder':'total ascending'})
                                     st.plotly_chart(fig_c_top, use_container_width=True)
                                # Table
                                st.write("**Alle Artikel**")
                                cat_tbl_cols = [DATE_COLUMN, STORE_COLUMN, ITEM_DESC_COLUMN, ITEM_QUANTITY_COLUMN, ITEM_UNIT_PRICE_COLUMN, ITEM_PRICE_COLUMN]
                                cat_tbl_cols = [c for c in cat_tbl_cols if c in cat_df.columns]
                                st.dataframe(cat_df[cat_tbl_cols].sort_values(by=DATE_COLUMN, ascending=False), use_container_width=True)

                # --- 3. Item Price Tracker ---
                with tab_items:
                    st.header("Artikel-Preis-Tracker")
                    available_items = sorted(df_filtered[ITEM_DESC_COLUMN].astype(str).unique())
                    if available_items:
                        selected_item = st.selectbox("Wähle Artikel:", available_items, key="item_select")
                        if selected_item:
                            item_df = df_filtered[df_filtered[ITEM_DESC_COLUMN] == selected_item].copy()
                            if not item_df.empty:
                                st.subheader(f"Preisanalyse: {selected_item}")
                                # Determine price column (simplified)
                                price_col = ITEM_UNIT_PRICE_COLUMN if ITEM_UNIT_PRICE_COLUMN in item_df.columns and item_df[ITEM_UNIT_PRICE_COLUMN].gt(0).any() else ITEM_PRICE_COLUMN
                                price_lbl = "Stückpreis" if price_col == ITEM_UNIT_PRICE_COLUMN else "Gesamtpreis"
                                st.info(f"Verwende: {price_col}")
                                # Trend Plot
                                st.write("**Preisverlauf**")
                                item_trend = item_df[[DATE_COLUMN, price_col, STORE_COLUMN]].sort_values(DATE_COLUMN)
                                item_trend = item_trend[item_trend[price_col] > 0]
                                if not item_trend.empty:
                                    fig_i_trend = px.scatter(item_trend, x=DATE_COLUMN, y=price_col, color=STORE_COLUMN)
                                    fig_i_trend.update_traces(mode='markers+lines')
                                    fig_i_trend.update_layout(yaxis_title=f"{price_lbl} ({CURRENCY_SYMBOL})")
                                    st.plotly_chart(fig_i_trend, use_container_width=True)
                                # Store Comparison Table
                                st.write("**Preisvergleich Geschäfte**")
                                item_store = item_df[item_df[price_col] > 0].groupby(STORE_COLUMN)[price_col].agg(['mean', 'min', 'max', 'count']).reset_index().sort_values('mean')
                                if not item_store.empty:
                                     st.dataframe(item_store.rename(columns={'mean': f'Ø {price_lbl}', 'min': f'Min {price_lbl}', 'max': f'Max {price_lbl}', 'count': 'Käufe'}).round(2), use_container_width=True, hide_index=True)

                # --- 4. Receipt Explorer ---
                with tab_receipts:
                    st.header("Belegdetails durchsuchen")
                    try:
                        # Create unique ID
                        rec_id_cols = [DATE_COLUMN, RECEIPT_TIME_COLUMN, STORE_COLUMN, RECEIPT_NUM_COLUMN, FILENAME_COLUMN, RECEIPT_TOTAL_COLUMN]
                        rec_id_cols = [c for c in rec_id_cols if c in df_filtered.columns]
                        df_rec_copy = df_filtered.copy()
                        for c in rec_id_cols: df_rec_copy[f'{c}_str'] = df_rec_copy[c].astype(str)
                        id_cols_str = [f'{c}_str' for c in rec_id_cols]
                        df_rec_copy['Receipt_Unique_ID'] = df_rec_copy[id_cols_str].agg('_'.join, axis=1)
                        # Summary & Selectbox
                        rec_summary = df_rec_copy.drop_duplicates(subset=['Receipt_Unique_ID']).sort_values(DATE_COLUMN, ascending=False)
                        disp_opts, opt_map = [], {}
                        for idx, r in rec_summary.iterrows():
                            d, s, t = r[DATE_COLUMN].strftime('%Y-%m-%d'), str(r.get(STORE_COLUMN,'?')), f"{r.get(RECEIPT_TOTAL_COLUMN,0):.2f}{CURRENCY_SYMBOL}"
                            tm = str(r.get(RECEIPT_TIME_COLUMN,''))
                            disp_str = f"{d} {tm} - {s} ({t})"
                            disp_opts.append(disp_str); opt_map[disp_str] = r['Receipt_Unique_ID']
                        selected_disp_rec = st.selectbox("Wähle Beleg:", disp_opts, index=0 if disp_opts else None, key="rec_select")
                        # Display Details
                        if selected_disp_rec and selected_disp_rec in opt_map:
                            rec_id = opt_map[selected_disp_rec]
                            rec_detail_df = df_rec_copy[df_rec_copy['Receipt_Unique_ID'] == rec_id]
                            if not rec_detail_df.empty:
                                info = rec_detail_df.iloc[0]
                                st.subheader(f"Details: {info.get(STORE_COLUMN,'?')} - {info[DATE_COLUMN].strftime('%Y-%m-%d')}")
                                r_m1, r_m2, r_m3 = st.columns(3)
                                r_m1.metric("Gesamt", f"{info.get(RECEIPT_TOTAL_COLUMN, 0):.2f} {CURRENCY_SYMBOL}")
                                r_m2.metric("Datum", info[DATE_COLUMN].strftime('%Y-%m-%d'))
                                r_m3.metric("Uhrzeit", f"{info.get(RECEIPT_TIME_COLUMN, 'N/A')}")
                                st.write("**Artikel:**")
                                item_cols = [ITEM_DESC_COLUMN, ITEM_QUANTITY_COLUMN, ITEM_UNIT_PRICE_COLUMN, ITEM_PRICE_COLUMN, ITEM_CATEGORY_COLUMN]
                                item_cols = [c for c in item_cols if c in rec_detail_df.columns]
                                st.dataframe(rec_detail_df[item_cols].reset_index(drop=True), use_container_width=True)
                                # Image Display
                                fname = info.get(FILENAME_COLUMN)
                                if fname and isinstance(fname, str) and fname.strip():
                                     st.write("**Bild:**")
                                     img_path = f"receipt_images/{fname}" # Adjust path if needed!
                                     try: st.image(img_path, caption=fname, use_column_width='auto')
                                     except: st.warning(f"Bild '{fname}' nicht gefunden.")
                    except Exception as e_rec_exp: st.error(f"Fehler Belegdetails: {e_rec_exp}")

                # --- 5. Time Analysis ---
                with tab_time:
                    st.header("Zeitanalyse")
                    t_c1, t_c2 = st.columns(2)
                    with t_c1:
                        st.subheader("Nach Wochentag")
                        try:
                            t_dow = df_filtered.groupby('DayOfWeek')[ITEM_PRICE_COLUMN].sum().reset_index()
                            wk_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                            t_dow['DayOfWeek'] = pd.Categorical(t_dow['DayOfWeek'], categories=wk_order, ordered=True)
                            fig_t_dow = px.bar(t_dow.sort_values('DayOfWeek'), x='DayOfWeek', y=ITEM_PRICE_COLUMN)
                            st.plotly_chart(fig_t_dow, use_container_width=True)
                        except Exception as e_t_dow: st.warning(f"Wochentag Fehler: {e_t_dow}")
                    with t_c2:
                        st.subheader("Nach Tageszeit")
                        t_hr = df_filtered.dropna(subset=['Hour']).copy()
                        if not t_hr.empty and t_hr['Hour'].nunique() > 1:
                            try:
                                t_hr['Hour'] = t_hr['Hour'].astype(int)
                                t_hr_grp = t_hr.groupby('Hour')[ITEM_PRICE_COLUMN].sum().reset_index()
                                fig_t_hr = px.bar(t_hr_grp, x='Hour', y=ITEM_PRICE_COLUMN)
                                fig_t_hr.update_layout(xaxis=dict(tickmode='linear'))
                                st.plotly_chart(fig_t_hr, use_container_width=True)
                            except Exception as e_t_hr: st.warning(f"Stunden Fehler: {e_t_hr}")
                        else: st.info("Nicht genug Stundendaten.")

                # --- 6. Budgeting Module ---
                with tab_budget:
                    st.header("Budgetübersicht (Demo)")
                    st.info("Feste Demo-Budgets. Analyse basiert auf **aktuellem Kalendermonat**.")
                    budgets = { # Example Budgets
                        "Lebensmittel: Milchprodukte & Eier": 50, "Außer Haus: Restaurant / Imbiss": 100,
                        "Transport: Tanken / Kraftstoff": 150, "Sonstiges / Unkategorisiert": 75,
                    }
                    now = datetime.datetime.now()
                    cm_start = datetime.datetime(now.year, now.month, 1)
                    cm_df = df_processed[(df_processed[DATE_COLUMN] >= pd.Timestamp(cm_start)) & (df_processed[DATE_COLUMN] <= pd.Timestamp(now))]

                    if cm_df.empty:
                        st.warning(f"Keine Ausgaben im Monat ({now.strftime('%B %Y')}).")
                    else:
                        st.subheader(f"Budget vs. Ausgaben: {now.strftime('%B %Y')}")
                        cm_spend = cm_df.groupby(ITEM_CATEGORY_COLUMN)[ITEM_PRICE_COLUMN].sum()
                        results = []
                        for cat, bud in budgets.items():
                            spent = cm_spend.get(cat, 0); rem = bud - spent
                            prog = min(spent / bud, 1.0) if bud > 0 else 0
                            results.append({"Kategorie": cat, "Budget": bud, "Ausgegeben": spent, "Verbleibend": rem, "Fortschritt": prog})
                        bud_df = pd.DataFrame(results)
                        for idx, r in bud_df.iterrows():
                            st.write(f"**{r['Kategorie']}**")
                            prog_c1, txt_c2 = st.columns([3,1])
                            with prog_c1: st.progress(r['Fortschritt'])
                            with txt_c2:
                                status = st.error if r['Ausgegeben'] > r['Budget'] else st.info
                                status(f"{r['Ausgegeben']:.2f}/{r['Budget']:.2f} ({r['Verbleibend']:.2f})")
                        # Unbudgeted
                        st.markdown("---"); st.write("**Nicht budgetierte Ausgaben (Monat):**")
                        unbud = cm_spend[~cm_spend.index.isin(budgets.keys())]; unbud = unbud[unbud > 0]
                        if not unbud.empty: st.dataframe(unbud.reset_index().rename(columns={ITEM_PRICE_COLUMN: 'Ausgaben'}), use_container_width=True, hide_index=True)
                        else: st.success("Keine.")

                # --- 7. Data Quality Check ---
                with tab_quality:
                    st.header("Datenqualität")
                    st.subheader(f"Generische Kategorie ('{UNCATEGORIZED[0]}')")
                    st.info("Artikel im **ausgewählten Zeitraum**. Korrektur im Google Sheet empfohlen.")
                    uncat = df_filtered[df_filtered[ITEM_CATEGORY_COLUMN] == UNCATEGORIZED[0]]
                    if not uncat.empty:
                        st.warning(f"{len(uncat)} Artikel gefunden.")
                        qual_cols = [DATE_COLUMN, STORE_COLUMN, ITEM_DESC_COLUMN, ITEM_PRICE_COLUMN, ITEM_CATEGORY_COLUMN, FILENAME_COLUMN]
                        qual_cols = [c for c in qual_cols if c in uncat.columns]
                        st.dataframe(uncat[qual_cols].sort_values(DATE_COLUMN, ascending=False), use_container_width=True, hide_index=True)
                        try:
                             ss_url = gc.open(GOOGLE_SHEET_NAME).url
                             st.link_button("Google Sheet öffnen", ss_url, type="primary")
                        except Exception as e_link_qual: st.warning(f"Link Fehler: {e_link_qual}")
                    else: st.success("Keine generisch kategorisierten Artikel.")

            # --- End of Tab Rendering Block ---

        # --- End of Block (if df_processed has data) ---

    # --- If initial data loading failed or returned empty ---
    elif gc is not None:
        st.warning(f"Keine Daten aus '{GOOGLE_SHEET_NAME}/{WORKSHEET_NAME}' geladen oder Tabelle leer.")
# --- End of Block (if gc is valid) ---

else: # If Authentication Failed
     st.error("Authentifizierung fehlgeschlagen. Dashboard nicht verfügbar.")
     st.info("Prüfe Secrets/Umgebungsvariablen und Sheet-Freigabe.")

# --- Sidebar Footer ---
st.sidebar.markdown("---")
st.sidebar.info("Analyse v1.4 (Robust Auth + Pie Fix)")