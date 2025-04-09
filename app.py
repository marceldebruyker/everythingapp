# app.py
import streamlit as st

# --- Basic Page Configuration for the Main App ---
st.set_page_config(
    page_title="Multi-App Dashboard",
    page_icon="🚀",  # Icon for the main app/browser tab
    layout="wide",
    initial_sidebar_state="expanded" # Keep sidebar open initially
)

# --- Main Landing Page Content ---
st.title("🚀 Willkommen beim Multi-App Dashboard")

st.sidebar.success("Wähle eine App oben aus.") # Message in the sidebar

st.markdown(
    """
    Dies ist eine Sammlung verschiedener Streamlit-Anwendungen.
    Wähle eine Anwendung aus der Seitenleiste aus, um zu starten.

    **Verfügbare Apps:**
    *   **Beleg Scanner:** Analysiert Kassenbons und speichert die Daten strukturiert in Google Sheets.
    *   *(Weitere Apps werden hier angezeigt, wenn sie im `pages` Ordner hinzugefügt werden)*

    ---
    **Hinweis:** Jede App greift auf die zentralen Streamlit Secrets
    (`.streamlit/secrets.toml`) für API-Schlüssel und Zugangsdaten zu.
    Stelle sicher, dass diese korrekt konfiguriert sind.
    """
)

# You can add more general information or links here if needed
st.markdown("---")
st.info("Navigiere über die Seitenleiste, um die gewünschte Anwendung zu nutzen.")