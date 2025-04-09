# pages/0_🏠_Home.py
import streamlit as st

# --- Page Specific Configuration ---
# Set the title and icon for *this specific page*
# This overrides the default set in app.py when this page is active
st.set_page_config(
    page_title="Dashboard Home",
    page_icon="🏠"
)

# --- Page Title ---
st.title("🚀 Willkommen beim Multi-App Dashboard")
st.caption("Deine zentrale Anlaufstelle für verschiedene Analyse-Tools")

st.divider() # Visual separator

# --- Introduction Section ---
st.markdown(
    """
    Hallo! 👋 Dieses Dashboard bündelt mehrere nützliche Streamlit-Anwendungen an einem Ort.
    Nutze die **Navigation in der Seitenleiste** links, um zwischen den verfügbaren Apps zu wechseln.
    """
)

st.info("ℹ️ Jede Anwendung läuft unabhängig und verwendet die zentral konfigurierten Zugangsdaten (z.B. API-Keys) aus den Streamlit Secrets.", icon="ℹ️")

st.divider() # Visual separator

# --- App Showcase Section ---
st.header("Verfügbare Anwendungen", divider='rainbow')

# Create columns for app cards
col1, col2 = st.columns(2) # Adjust number of columns as needed

with col1:
    with st.container(border=True):
        st.subheader("🧾 Beleg Scanner")
        st.markdown(
            """
            *   **Zweck:** Analysiert Kassenbons (via Foto/Upload).
            *   **Features:** Extrahiert Händler, Datum, Artikel, Preise & Steuern.
            *   **Besonderheit:** Automatische Kategorisierung jedes Artikels.
            *   **Export:** Speichert die Daten strukturiert in Google Sheets.
            """
        )
        st.success("Ideal zur Ausgabenverfolgung!", icon="✅")

with col2:
    with st.container(border=True):
        st.subheader("📊 Weitere App (Platzhalter)") # Example for next app
        st.markdown(
            """
            *   **Zweck:** Beschreibung der nächsten App.
            *   **Features:** Feature 1, Feature 2, ...
            *   **Besonderheit:** Was macht diese App besonders?
            *   **Technologie:** Verwendete Bibliotheken/APIs.
            """
        )
        st.warning("Diese App wird bald hinzugefügt!", icon="⏳")

# Add more columns/containers for more apps...
# Example: If you had a third app
# col3 = st.columns(1) # Or add to the grid above
# with col3: # or col1, col2 depending on layout
#    with st.container(border=True):
#        st.subheader("💬 Nächste App")
#        st.markdown("Beschreibung...")


st.divider()

# --- Footer ---
st.markdown(
    """
    ---
    *Entwickelt mit [Streamlit](https://streamlit.io). Icons von Streamlit/Emoji.*
    """
)