# app.py
import streamlit as st
import base64
import os # Required for path manipulation and file reading

# --- Function to encode image to Data URI ---
def img_to_data_uri(filepath):
    """Reads an image file and returns a Data URI string."""
    try:
        # Ensure the path is correct, especially when run in different environments
        abs_filepath = os.path.abspath(filepath)
        with open(abs_filepath, "rb") as f:
            img_bytes = f.read()
        encoded = base64.b64encode(img_bytes).decode()
        # Determine MIME type based on file extension (primarily for PNG here)
        ext = os.path.splitext(filepath)[1].lower()
        mime_type = "image/png" if ext == ".png" else "application/octet-stream"
        return f"data:{mime_type};base64,{encoded}"
    except FileNotFoundError:
        # Don't display an error here directly, handle it later
        # st.error(f"Icon file not found at: {filepath}")
        print(f"Warning: Icon file not found at: {filepath}") # Log warning for debugging
        return None
    except Exception as e:
        # st.error(f"Error encoding file {filepath}: {e}")
        print(f"Warning: Error encoding file {filepath}: {e}") # Log warning
        return None

# --- Configuration for Icons ---
# Get the absolute path to the directory containing this script
app_dir = os.path.dirname(os.path.abspath(__file__))
# Define the path to your Apple Touch icon file (MUST BE IN THE SAME DIRECTORY)
touch_icon_path = os.path.join(app_dir, "apple-touch-icon.png")

# Encode the Apple Touch icon
touch_icon_data_uri = img_to_data_uri(touch_icon_path)

# --- Basic Page Configuration ---
# MUST BE THE FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="Multi-App Dashboard",
    # Use encoded touch icon for browser tab if available, otherwise fallback to emoji
    page_icon=touch_icon_data_uri if touch_icon_data_uri else "🚀",
    layout="wide",
    initial_sidebar_state="expanded" # Keep sidebar open initially
)

# --- Inject Apple Touch Icon Link Tag ---
# Place this right after st.set_page_config
if touch_icon_data_uri:
    st.markdown(
        f"""
        <head>
            <link rel="apple-touch-icon" sizes="180x180" href="{touch_icon_data_uri}">
        </head>
        """,
        unsafe_allow_html=True
    )
else:
    # Optional: Display a warning in the app if the icon wasn't found/encoded
    # You might comment this out in production if you prefer not to show it to users
    st.warning("Apple Touch Icon konnte nicht geladen werden. Standard-Symbol wird verwendet.", icon="⚠️")


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

# --- Rest of your potential app logic (if any in the main app.py) ---