# pages/02_Analyse.py

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials # Make sure this is imported
from gspread_dataframe import get_as_dataframe
import plotly.express as px
import datetime
import json # <<< --- REQUIRED for parsing the credential string
import warnings

# --- Configuration ---
# !! Make sure these match your Google Sheet !!
GOOGLE_SHEET_NAME = "Haushaltsbuch" # The overall Google Sheet filename
WORKSHEET_NAME = "Ausgaben"         # The specific worksheet tab name
# !! Make sure these match the column headers in your sheet !!
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
CURRENCY_SYMBOL = "EUR"
# Define how uncategorized items are represented in your sheet
UNCATEGORIZED = ["Sonstiges / Unkategorisiert", "", None]

# --- Page Setup ---
# Keep this commented out if your main app script (Home.py/App.py) sets it.
# st.set_page_config(layout="wide", page_title="Haushaltsbuch Analyse", page_icon="📊")

st.title("📊 Dein Digitales Haushaltsbuch - Analyse")
st.markdown("Analyse deiner Ausgaben basierend auf gescannten Kassenzetteln.")

# --- Authentication & Data Loading (MODIFIED AUTHENTICATION) ---

# Use Streamlit Secrets for credentials (reading the JSON string)
def authenticate_gspread():
    """Authenticates with Google Sheets API using Service Account JSON string from Secrets."""
    try:
        # 1. Access the JSON string from secrets using your preferred key
        creds_string = st.secrets["GOOGLE_SHEETS_CREDENTIALS"]

        # 2. Parse the JSON string into a Python dictionary
        creds_json = json.loads(creds_string)

        # 3. Use the parsed dictionary with from_service_account_info
        creds = Credentials.from_service_account_info(
            creds_json, # Pass the parsed dictionary here
            scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        # Successfully created credentials, now authorize gspread
        return gspread.authorize(creds)

    except KeyError:
        st.error("Secret key 'GOOGLE_SHEETS_CREDENTIALS' not found in `.streamlit/secrets.toml`.")
        st.error("Please ensure secrets.toml contains the key with your service account JSON string.")
        return None
    except json.JSONDecodeError:
        st.error("Failed to parse the JSON string stored in 'GOOGLE_SHEETS_CREDENTIALS' secret.")
        st.error("Please ensure the value is a valid JSON object string (check for typos, quotes, braces, etc.).")
        # st.code(st.secrets["GOOGLE_SHEETS_CREDENTIALS"][:500] + "...") # Uncomment to show part of the string for debug
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during authentication: {e}")
        return None

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(_gc: gspread.Client):
    """Loads data from Google Sheet into a Pandas DataFrame."""
    if _gc is None:
        # Error message handled by caller (authenticate_gspread)
        return pd.DataFrame()
    try:
        spreadsheet = _gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        # Using na_filter=False to prevent empty strings becoming NaN immediately
        df = get_as_dataframe(worksheet, evaluate_formulas=True, header=0, na_filter=False)
        # Quiet success message
        # st.success(f"Daten erfolgreich aus '{GOOGLE_SHEET_NAME}/{WORKSHEET_NAME}' geladen ({len(df)} Zeilen).")
        return df
    except gspread.SpreadsheetNotFound:
        st.error(f"Google Sheet '{GOOGLE_SHEET_NAME}' nicht gefunden. Überprüfe Namen und Freigabe.")
        return pd.DataFrame()
    except gspread.WorksheetNotFound:
        st.error(f"Worksheet '{WORKSHEET_NAME}' im Sheet '{GOOGLE_SHEET_NAME}' nicht gefunden.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten aus Google Sheets: {e}")
        return pd.DataFrame()

def preprocess_data(df):
    """Cleans and preprocesses the DataFrame."""
    if df.empty:
        return df

    # Convert Date/Time Columns (handle errors by coercing to NaT)
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors='coerce')
    df[TIMESTAMP_COLUMN] = pd.to_datetime(df[TIMESTAMP_COLUMN], errors='coerce')

    # --- CRITICAL: Drop rows where the primary date column is invalid ---
    original_rows = len(df)
    df = df.dropna(subset=[DATE_COLUMN])
    if len(df) < original_rows:
        st.warning(f"{original_rows - len(df)} Zeilen wurden entfernt, da '{DATE_COLUMN}' kein gültiges Datum enthielt.")

    # Exit early if no valid date data remains
    if df.empty: return df

    # Extract useful date parts
    df['Year'] = df[DATE_COLUMN].dt.year
    df['Month'] = df[DATE_COLUMN].dt.month
    df['Month_Name'] = df[DATE_COLUMN].dt.strftime('%Y-%m') # For grouping/sorting by month
    df['DayOfWeek'] = df[DATE_COLUMN].dt.day_name()

    # Handle potential errors in Receipt Time parsing
    if 'Receipt Time' in df.columns:
        try:
            df['Hour'] = pd.to_datetime(df['Receipt Time'], format='%H:%M', errors='coerce').dt.hour
        except Exception: # Broad exception if format isn't HH:MM
            df['Hour'] = pd.to_datetime(df['Receipt Time'], errors='coerce').dt.hour
    else:
        df['Hour'] = None # Or some default value if the column doesn't exist

    # Convert Numeric Columns
    numeric_cols = [ITEM_PRICE_COLUMN, ITEM_UNIT_PRICE_COLUMN, RECEIPT_TOTAL_COLUMN, 'Item Quantity', 'Item VAT Rate', 'Receipt Subtotal', 'Receipt Total Tax Amount']
    for col in numeric_cols:
        if col in df.columns:
             # Replace empty strings before numeric conversion
             df[col] = df[col].replace('', None)
             df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            st.warning(f"Erwartete numerische Spalte '{col}' nicht in den Daten gefunden.")


    # Clean Item Category - Replace specific list of values with the standard 'Unkategorisiert'
    if ITEM_CATEGORY_COLUMN in df.columns:
        df[ITEM_CATEGORY_COLUMN] = df[ITEM_CATEGORY_COLUMN].replace(UNCATEGORIZED[1:], UNCATEGORIZED[0]).fillna(UNCATEGORIZED[0])
    else:
         st.error(f"Kategorie Spalte '{ITEM_CATEGORY_COLUMN}' nicht gefunden! Kategorisierung wird nicht funktionieren.")
         return pd.DataFrame() # Return empty if category is essential and missing

    # Normalize Item Description
    if ITEM_DESC_COLUMN in df.columns:
        df[ITEM_DESC_COLUMN] = df[ITEM_DESC_COLUMN].astype(str).str.strip()
    else:
         st.warning(f"Artikelbeschreibung Spalte '{ITEM_DESC_COLUMN}' nicht gefunden.")


    # Ensure correct data types for calculations
    if ITEM_PRICE_COLUMN in df.columns: df[ITEM_PRICE_COLUMN] = df[ITEM_PRICE_COLUMN].astype(float)
    if 'Item Quantity' in df.columns: df['Item Quantity'] = df['Item Quantity'].astype(float)


    return df

# --- Main App Logic ---
gc = authenticate_gspread() # Attempt authentication

if gc is None:
    # Error message is displayed within authenticate_gspread if secrets are missing/invalid
    st.stop() # Stop execution if authentication failed
else:
    df_raw = load_data(gc) # Load data only if authentication succeeded

    if not df_raw.empty:
        df = preprocess_data(df_raw.copy()) # Preprocess the data

        if df.empty: # Check if preprocessing resulted in empty dataframe (e.g., no valid dates)
            st.warning("Keine gültigen Daten nach der Vorverarbeitung gefunden. Überprüfe die Daten in der Google Tabelle, insbesondere die Spalte 'Receipt Date'.")
            st.stop()
        else:
            # --- Sidebar Filters ---
            st.sidebar.header("Filter (Analyse)")
            min_date = df[DATE_COLUMN].min().date()
            max_date = df[DATE_COLUMN].max().date()

            default_start = min_date
            default_end = max_date
            if default_start > default_end: default_start = default_end # Avoid invalid default range

            date_range = st.sidebar.date_input(
                "Zeitraum auswählen",
                value=(default_start, default_end),
                min_value=min_date,
                max_value=max_date,
                key="analyse_date_filter" # Unique key for this page's filter
            )

            # --- Apply Date Filter ---
            filtered_df = pd.DataFrame() # Initialize as empty
            start_date = None
            end_date = None
            if len(date_range) == 2:
                try:
                    start_date = pd.Timestamp(date_range[0])
                    end_date = pd.Timestamp(date_range[1])
                    if start_date <= end_date:
                         mask = (df[DATE_COLUMN] >= start_date) & (df[DATE_COLUMN] <= end_date)
                         filtered_df = df.loc[mask].copy() # Create filtered copy
                    else:
                        st.sidebar.warning("Startdatum liegt nach dem Enddatum.")
                        # filtered_df remains empty
                except Exception as e:
                     st.sidebar.error(f"Fehler bei der Datumsfilterung: {e}")
                     # filtered_df remains empty
            else: # Should not happen with default values, but handle defensively
                 st.sidebar.info("Ungültiger Datumsbereich ausgewählt.")
                 # filtered_df remains empty


            # --- Main Content Tabs ---
            tab_overview, tab_categories, tab_items, tab_receipts, tab_time, tab_budget, tab_quality = st.tabs([
                "📈 Übersicht",
                "🛒 Kategorien",
                "🏷️ Artikelpreise",
                "🧾 Belegdetails",
                "⏰ Zeitanalyse",
                "💰 Budget (Demo)",
                "🧹 Datenqualität"
            ])

            # --- Check if filtered data exists before proceeding with tabs ---
            if filtered_df.empty and start_date and end_date and start_date <= end_date:
                 # Only show warning if a valid date range was selected but yielded no data
                 st.warning(f"Keine Daten im ausgewählten Zeitraum ({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}) gefunden.")
            elif not filtered_df.empty:
                # --- 1. Overview Tab ---
                with tab_overview:
                    st.header("Übersicht deiner Ausgaben")
                    # Key Metrics
                    total_spending = filtered_df[ITEM_PRICE_COLUMN].sum()
                    # Use unique receipt identifiers to sum receipt totals only once
                    receipt_id_cols = [DATE_COLUMN, STORE_COLUMN, RECEIPT_NUM_COLUMN, RECEIPT_TOTAL_COLUMN]
                    receipt_id_cols = [col for col in receipt_id_cols if col in filtered_df.columns]
                    receipt_totals = filtered_df.drop_duplicates(subset=receipt_id_cols)
                    receipt_totals_sum = receipt_totals[RECEIPT_TOTAL_COLUMN].sum()

                    st.info(f"Hinweis: Gesamt basiert auf Summe der Artikelpreise ({total_spending:.2f} {CURRENCY_SYMBOL}). Summe der eindeutigen Belegsummen wäre {receipt_totals_sum:.2f} {CURRENCY_SYMBOL}.")

                    num_days = (end_date - start_date).days + 1
                    avg_daily_spending = total_spending / num_days if num_days > 0 else 0
                    num_receipts = receipt_totals.shape[0]
                    avg_receipt_value = receipt_totals_sum / num_receipts if num_receipts > 0 else 0

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Gesamtausgaben (Artikel)", f"{total_spending:.2f} {CURRENCY_SYMBOL}")
                    col2.metric("Ø Ausgaben / Tag", f"{avg_daily_spending:.2f} {CURRENCY_SYMBOL}")
                    col3.metric("Anzahl Belege", f"{num_receipts}")
                    col4.metric("Ø Wert / Beleg", f"{avg_receipt_value:.2f} {CURRENCY_SYMBOL}")

                    st.markdown("---")

                    # Spending Over Time (Line Chart)
                    st.subheader("Ausgaben über Zeit")
                    spending_over_time = filtered_df.groupby(filtered_df[DATE_COLUMN].dt.date)[ITEM_PRICE_COLUMN].sum().reset_index()
                    spending_over_time = spending_over_time.rename(columns={DATE_COLUMN: "Datum", ITEM_PRICE_COLUMN: "Ausgaben"})
                    if not spending_over_time.empty:
                        fig_time = px.line(spending_over_time, x='Datum', y='Ausgaben', title="Tägliche Ausgaben", markers=True)
                        fig_time.update_layout(xaxis_title="Datum", yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})")
                        st.plotly_chart(fig_time, use_container_width=True)

                    # Spending by Category (Pie/Donut Chart or Treemap)
                    st.subheader("Ausgaben nach Kategorie")
                    spending_by_category = filtered_df.groupby(ITEM_CATEGORY_COLUMN)[ITEM_PRICE_COLUMN].sum().reset_index()
                    spending_by_category = spending_by_category[spending_by_category[ITEM_PRICE_COLUMN] > 0] # Exclude zero spending
                    spending_by_category = spending_by_category.sort_values(by=ITEM_PRICE_COLUMN, ascending=False)

                    chart_type = st.selectbox("Kategorie-Charttyp:", ["Donut", "Treemap", "Balken"], key="cat_chart_type")
                    if not spending_by_category.empty:
                        common_chart_args = {"names": ITEM_CATEGORY_COLUMN, "values": ITEM_PRICE_COLUMN, "title": "Ausgabenanteil pro Kategorie"}
                        if chart_type == "Donut":
                            fig_cat = px.pie(**common_chart_args, hole=0.4)
                            fig_cat.update_traces(textposition='outside', textinfo='percent+label')
                        elif chart_type == "Treemap":
                             fig_cat = px.treemap(spending_by_category, path=[ITEM_CATEGORY_COLUMN], values=ITEM_PRICE_COLUMN, title="Ausgabenanteil pro Kategorie (Treemap)")
                             fig_cat.update_traces(textinfo='label+value+percent root')
                        else: # Balken
                             fig_cat = px.bar(spending_by_category, x=ITEM_PRICE_COLUMN, y=ITEM_CATEGORY_COLUMN, orientation='h', title="Gesamtausgaben pro Kategorie")
                             fig_cat.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", yaxis_title="Kategorie")
                        st.plotly_chart(fig_cat, use_container_width=True)

                # --- 2. Category Deep Dive ---
                with tab_categories:
                    st.header("Kategorie-Detailanalyse")
                    available_categories = sorted(filtered_df[ITEM_CATEGORY_COLUMN].unique())
                    if not available_categories:
                        st.warning("Keine Kategorien in den gefilterten Daten gefunden.")
                    else:
                        selected_category = st.selectbox("Wähle eine Kategorie:", available_categories, index = 0)
                        if selected_category:
                            category_df = filtered_df[filtered_df[ITEM_CATEGORY_COLUMN] == selected_category]
                            if not category_df.empty:
                                st.subheader(f"Analyse für: {selected_category}")
                                # Metrics
                                cat_total_spending = category_df[ITEM_PRICE_COLUMN].sum()
                                cat_item_count = category_df.shape[0]
                                cat_total_quantity = category_df['Item Quantity'].sum() if 'Item Quantity' in category_df else "N/A"
                                col1, col2, col3 = st.columns(3)
                                col1.metric("Gesamtausgaben", f"{cat_total_spending:.2f} {CURRENCY_SYMBOL}")
                                col2.metric("Anzahl Artikel", f"{cat_item_count}")
                                col3.metric("Gesamtmenge (falls erfasst)", f"{cat_total_quantity}")
                                st.markdown("---")
                                # Spending Trend
                                st.write("**Ausgabenentwicklung in dieser Kategorie**")
                                cat_spending_over_time = category_df.groupby(category_df[DATE_COLUMN].dt.date)[ITEM_PRICE_COLUMN].sum().reset_index()
                                cat_spending_over_time = cat_spending_over_time.rename(columns={DATE_COLUMN: "Datum", ITEM_PRICE_COLUMN: "Ausgaben"})
                                if not cat_spending_over_time.empty:
                                    fig_cat_time = px.line(cat_spending_over_time, x='Datum', y='Ausgaben', markers=True)
                                    fig_cat_time.update_layout(yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})")
                                    st.plotly_chart(fig_cat_time, use_container_width=True)
                                # Top Items
                                st.write("**Top Artikel in dieser Kategorie (nach Ausgaben)**")
                                top_items = category_df.groupby(ITEM_DESC_COLUMN).agg(
                                     TotalSpending=(ITEM_PRICE_COLUMN, 'sum'),
                                     TimesPurchased=('Item Description', 'size')
                                ).reset_index().sort_values(by='TotalSpending', ascending=False).head(15)
                                if not top_items.empty:
                                     fig_top_items = px.bar(top_items, x='TotalSpending', y=ITEM_DESC_COLUMN, orientation='h',
                                                            title=f"Top 15 Artikel in '{selected_category}'", hover_data=['TimesPurchased'])
                                     fig_top_items.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", yaxis_title="Artikel")
                                     st.plotly_chart(fig_top_items, use_container_width=True)
                                # Table
                                st.write("**Alle Artikel in dieser Kategorie (im Zeitraum)**")
                                display_cols_cat = [DATE_COLUMN, STORE_COLUMN, ITEM_DESC_COLUMN, 'Item Quantity', ITEM_UNIT_PRICE_COLUMN, ITEM_PRICE_COLUMN]
                                display_cols_cat = [col for col in display_cols_cat if col in category_df.columns]
                                st.dataframe(category_df[display_cols_cat].sort_values(by=DATE_COLUMN, ascending=False), use_container_width=True)

                # --- 3. Item Price Tracker ---
                with tab_items:
                    st.header("Artikel-Preis-Tracker")
                    available_items = sorted(filtered_df[ITEM_DESC_COLUMN].astype(str).unique())
                    if not available_items:
                         st.warning("Keine Artikelbeschreibungen gefunden.")
                    else:
                        selected_item = st.selectbox(
                            "Wähle einen Artikel:", available_items, index=0,
                            help="Wähle einen Artikel, um dessen Preisentwicklung zu sehen."
                        )
                        if selected_item:
                            item_df = filtered_df[filtered_df[ITEM_DESC_COLUMN] == selected_item].copy()
                            if not item_df.empty:
                                st.subheader(f"Preisanalyse für: {selected_item}")
                                # Determine price column
                                price_col_to_plot = ITEM_PRICE_COLUMN
                                y_axis_label = f"Gesamtpreis Artikel ({CURRENCY_SYMBOL})"
                                price_info_msg = f"Verwende '{ITEM_PRICE_COLUMN}'."
                                if ITEM_UNIT_PRICE_COLUMN in item_df.columns and item_df[ITEM_UNIT_PRICE_COLUMN].sum() > 0:
                                    tolerance = 0.05
                                    quantity_mask = (item_df['Item Quantity'] != 0)
                                    plausible = pd.Series([False] * len(item_df), index=item_df.index)
                                    if quantity_mask.any(): plausible[quantity_mask] = abs(item_df.loc[quantity_mask, ITEM_PRICE_COLUMN] / item_df.loc[quantity_mask, 'Item Quantity'] - item_df.loc[quantity_mask, ITEM_UNIT_PRICE_COLUMN]) < tolerance
                                    quantity_one_mask = (item_df['Item Quantity'] == 1)
                                    plausible[quantity_one_mask] = plausible[quantity_one_mask] | (abs(item_df.loc[quantity_one_mask, ITEM_PRICE_COLUMN] - item_df.loc[quantity_one_mask, ITEM_UNIT_PRICE_COLUMN]) < tolerance)
                                    if plausible.mean() > 0.6:
                                        price_col_to_plot = ITEM_UNIT_PRICE_COLUMN
                                        y_axis_label = f"Stückpreis ({CURRENCY_SYMBOL})"
                                        price_info_msg = f"Verwende '{ITEM_UNIT_PRICE_COLUMN}' (scheint plausibel)."
                                st.info(price_info_msg)
                                item_df['Datum'] = item_df[DATE_COLUMN].dt.date
                                # Price Over Time Plot
                                st.write("**Preisentwicklung über Zeit**")
                                price_trend_df = item_df[[DATE_COLUMN, price_col_to_plot, STORE_COLUMN]].sort_values(by=DATE_COLUMN)
                                price_trend_df = price_trend_df[price_trend_df[price_col_to_plot] > 0] # Plot only positive prices
                                if not price_trend_df.empty:
                                    fig_price_trend = px.scatter(price_trend_df, x=DATE_COLUMN, y=price_col_to_plot, color=STORE_COLUMN, title=f"Preisverlauf für '{selected_item}'")
                                    fig_price_trend.update_traces(mode='markers+lines')
                                    fig_price_trend.update_layout(xaxis_title="Datum", yaxis_title=y_axis_label, legend_title="Geschäft")
                                    st.plotly_chart(fig_price_trend, use_container_width=True)
                                # Price Variation by Store
                                st.write("**Preisvergleich nach Geschäft (im Zeitraum)**")
                                price_by_store = item_df[item_df[price_col_to_plot] > 0].groupby(STORE_COLUMN)[price_col_to_plot].agg(['mean', 'min', 'max', 'count']).reset_index().sort_values(by='mean')
                                if not price_by_store.empty:
                                     st.dataframe(price_by_store.rename(columns={'mean': f'Ø {y_axis_label}', 'min': f'Min {y_axis_label}', 'max': f'Max {y_axis_label}', 'count': 'Anzahl Käufe'}).round(2), use_container_width=True)

                # --- 4. Receipt Explorer ---
                with tab_receipts:
                    st.header("Belegdetails durchsuchen")
                    # Create unique receipt ID
                    receipt_id_cols = [DATE_COLUMN, 'Receipt Time', STORE_COLUMN, RECEIPT_NUM_COLUMN, FILENAME_COLUMN]
                    receipt_id_cols = [col for col in receipt_id_cols if col in filtered_df.columns]
                    for col in receipt_id_cols: filtered_df[f'{col}_str'] = filtered_df[col].astype(str)
                    id_cols_str = [f'{col}_str' for col in receipt_id_cols]
                    filtered_df['Receipt_ID'] = filtered_df[id_cols_str].agg('_'.join, axis=1)
                    filtered_df = filtered_df.drop(columns=id_cols_str)

                    receipt_summary = filtered_df.drop_duplicates(subset=['Receipt_ID']).sort_values(by=DATE_COLUMN, ascending=False)

                    display_options = []
                    option_map = {}
                    for index, row in receipt_summary.iterrows():
                        date_str = row[DATE_COLUMN].strftime('%Y-%m-%d') if pd.notna(row[DATE_COLUMN]) else '?'
                        store_str = str(row.get(STORE_COLUMN, '?'))
                        total_str = f"{row.get(RECEIPT_TOTAL_COLUMN, 0):.2f} {CURRENCY_SYMBOL}" if pd.notna(row.get(RECEIPT_TOTAL_COLUMN)) else '?'
                        time_str = str(row.get('Receipt Time', ''))
                        display_str = f"{date_str} {time_str} - {store_str} ({total_str})"
                        display_options.append(display_str)
                        option_map[display_str] = row['Receipt_ID']

                    st.write("Wähle einen Beleg aus der Dropdown-Liste:")
                    selected_display_option = st.selectbox("Beleg auswählen:", options=display_options, index=0 if display_options else None)

                    if selected_display_option and selected_display_option in option_map:
                        selected_receipt_id = option_map[selected_display_option]
                        receipt_detail_df = filtered_df[filtered_df['Receipt_ID'] == selected_receipt_id]
                        if not receipt_detail_df.empty:
                            receipt_info = receipt_detail_df.iloc[0]
                            st.subheader(f"Details: {receipt_info.get(STORE_COLUMN,'N/A')} - {receipt_info[DATE_COLUMN].strftime('%Y-%m-%d')}")
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Gesamtsumme (Beleg)", f"{receipt_info.get(RECEIPT_TOTAL_COLUMN, 0):.2f} {CURRENCY_SYMBOL}")
                            col2.metric("Datum", f"{receipt_info[DATE_COLUMN].strftime('%Y-%m-%d')}")
                            col3.metric("Uhrzeit", f"{receipt_info.get('Receipt Time', 'N/A')}")
                            # Items
                            st.write("**Gekaufte Artikel:**")
                            item_display_cols = [ITEM_DESC_COLUMN, 'Item Quantity', ITEM_UNIT_PRICE_COLUMN, ITEM_PRICE_COLUMN, ITEM_CATEGORY_COLUMN]
                            item_display_cols = [col for col in item_display_cols if col in receipt_detail_df.columns]
                            st.dataframe(receipt_detail_df[item_display_cols].reset_index(drop=True), use_container_width=True)
                            # Image
                            filename = receipt_info.get(FILENAME_COLUMN)
                            if filename and isinstance(filename, str) and filename.strip():
                                st.write("**Beleg Bild:**")
                                image_path = f"receipt_images/{filename}" # Adjust path if needed
                                try:
                                    st.image(image_path, caption=f"Beleg: {filename}", use_column_width='auto')
                                except FileNotFoundError:
                                    st.warning(f"Bild '{filename}' nicht in '{image_path}' gefunden.")
                                except Exception as e:
                                    st.error(f"Fehler beim Laden von Bild '{filename}': {e}")

                # --- 5. Time Analysis ---
                with tab_time:
                    st.header("Zeitanalyse der Ausgaben")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Ausgaben nach Wochentag")
                        spending_by_dow = filtered_df.groupby('DayOfWeek')[ITEM_PRICE_COLUMN].sum().reset_index()
                        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        try:
                             spending_by_dow['DayOfWeek'] = pd.Categorical(spending_by_dow['DayOfWeek'], categories=weekday_order, ordered=True)
                             spending_by_dow = spending_by_dow.sort_values('DayOfWeek')
                             fig_dow = px.bar(spending_by_dow, x='DayOfWeek', y=ITEM_PRICE_COLUMN, title="Gesamtausgaben pro Wochentag")
                             fig_dow.update_layout(xaxis_title="Wochentag", yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})")
                             st.plotly_chart(fig_dow, use_container_width=True)
                        except Exception as e:
                             st.warning(f"Wochentags-Chart Fehler: {e}")
                    with col2:
                        st.subheader("Ausgaben nach Tageszeit")
                        spending_by_hour = filtered_df.dropna(subset=['Hour']).copy()
                        if not spending_by_hour.empty and spending_by_hour['Hour'].nunique() > 1:
                             spending_by_hour['Hour'] = spending_by_hour['Hour'].astype(int)
                             spending_by_hour = spending_by_hour.groupby('Hour')[ITEM_PRICE_COLUMN].sum().reset_index()
                             fig_hour = px.bar(spending_by_hour, x='Hour', y=ITEM_PRICE_COLUMN, title="Gesamtausgaben pro Stunde")
                             fig_hour.update_layout(xaxis_title="Stunde (0-23)", yaxis_title=f"Ausgaben ({CURRENCY_SYMBOL})", xaxis = dict(tickmode = 'linear', dtick = 1))
                             st.plotly_chart(fig_hour, use_container_width=True)
                        else:
                             st.info("Keine ausreichenden Stundendaten vorhanden.")

                # --- 6. Budgeting Module (Simple Demo) ---
                with tab_budget:
                    st.header("Budgetübersicht (Demo)")
                    st.info("Feste Demo-Budgets im Code. Analyse basiert auf dem **aktuellen Kalendermonat**.")
                    # Define budgets (Adjust these!)
                    monthly_budgets = {
                        "Lebensmittel: Obst & Gemüse": 100, "Lebensmittel: Milchprodukte & Eier": 50,
                        "Lebensmittel: Fleisch & Wurst": 80, "Lebensmittel: Getränke": 40,
                        "Drogerie & Kosmetik": 60, "Transport": 50, "Sonstiges / Unkategorisiert": 75,
                    }
                    # Use original 'df' for current month analysis, not sidebar filtered 'filtered_df'
                    now = datetime.datetime.now()
                    current_month_start = datetime.datetime(now.year, now.month, 1)
                    current_month_df = df[(df[DATE_COLUMN] >= current_month_start) & (df[DATE_COLUMN] <= pd.Timestamp(now))].copy()

                    if current_month_df.empty:
                        st.warning(f"Keine Ausgaben im aktuellen Monat ({now.strftime('%B %Y')}) gefunden.")
                    else:
                        st.subheader(f"Budget vs. Ausgaben für: {now.strftime('%B %Y')}")
                        spending_this_month = current_month_df.groupby(ITEM_CATEGORY_COLUMN)[ITEM_PRICE_COLUMN].sum()
                        budget_results = []
                        for category, budget in monthly_budgets.items():
                            spent = spending_this_month.get(category, 0)
                            progress = min(spent / budget, 1.0) if budget > 0 else 0
                            remaining = budget - spent
                            budget_results.append({"Kategorie": category, "Budget": budget, "Ausgegeben": spent, "Verbleibend": remaining, "Fortschritt": progress})
                        budget_df = pd.DataFrame(budget_results)
                        for index, row in budget_df.iterrows():
                            st.write(f"**{row['Kategorie']}**")
                            col1, col2 = st.columns([3, 1])
                            with col1: st.progress(row['Fortschritt'])
                            with col2:
                                if row['Ausgegeben'] > row['Budget']: st.error(f"{row['Ausgegeben']:.2f} / {row['Budget']:.2f} ({row['Verbleibend']:.2f})")
                                else: st.info(f"{row['Ausgegeben']:.2f} / {row['Budget']:.2f} ({row['Verbleibend']:.2f})")
                        # Unbudgeted
                        st.markdown("---")
                        st.write("**Ausgaben in nicht budgetierten Kategorien (diesen Monat):**")
                        unbudgeted_spending = spending_this_month[~spending_this_month.index.isin(monthly_budgets.keys())]
                        unbudgeted_spending = unbudgeted_spending[unbudgeted_spending > 0] # Show only non-zero
                        if not unbudgeted_spending.empty:
                             st.dataframe(unbudgeted_spending.reset_index().rename(columns={ITEM_PRICE_COLUMN: f'Ausgaben ({CURRENCY_SYMBOL})'}), use_container_width=True, hide_index=True)
                        else:
                             st.success("Keine Ausgaben in nicht budgetierten Kategorien.")

                # --- 7. Data Quality Check ---
                with tab_quality:
                    st.header("Überprüfung der Datenqualität")
                    st.subheader("Artikel mit generischer Kategorie")
                    st.info(f"Identifiziert Artikel im **ausgewählten Zeitraum**, deren Kategorie als '{UNCATEGORIZED[0]}' erfasst wurde.")
                    uncategorized_items = filtered_df[filtered_df[ITEM_CATEGORY_COLUMN] == UNCATEGORIZED[0]]
                    if not uncategorized_items.empty:
                        st.warning(f"{len(uncategorized_items)} Artikel ohne spezifische Kategorie im Zeitraum gefunden.")
                        display_cols_quality = [DATE_COLUMN, STORE_COLUMN, ITEM_DESC_COLUMN, ITEM_PRICE_COLUMN, ITEM_CATEGORY_COLUMN, FILENAME_COLUMN]
                        display_cols_quality = [col for col in display_cols_quality if col in uncategorized_items.columns]
                        st.dataframe(uncategorized_items[display_cols_quality].sort_values(by=DATE_COLUMN, ascending=False), use_container_width=True)
                        try: # Link to sheet for correction
                             spreadsheet_url = gc.open(GOOGLE_SHEET_NAME).url
                             st.link_button("Google Sheet öffnen zum Korrigieren", spreadsheet_url)
                        except Exception as e:
                             st.warning(f"Link zu Google Sheet konnte nicht erstellt werden: {e}")
                    else:
                        st.success(f"Alle Artikel im ausgewählten Zeitraum scheinen spezifisch kategorisiert zu sein!")


    elif gc is not None: # df_raw is empty but connection worked
        st.warning(f"Die Google Tabelle '{GOOGLE_SHEET_NAME}/{WORKSHEET_NAME}' wurde geöffnet, enthält aber keine Daten oder konnte nicht gelesen werden.")
    # If gc is None, error was handled during authentication attempt

# Add footer or additional info for this specific page in the sidebar
st.sidebar.markdown("---")
st.sidebar.info("Analyse v1.2 (JSON String Auth)")