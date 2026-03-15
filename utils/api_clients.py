"""Centralised API client initialisation.

All pipeline modules import clients from here. Keys are loaded from
st.secrets (production / Streamlit Cloud) with a .env fallback for local dev.
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_secret(name: str) -> str:
    """Return a secret from st.secrets or the environment."""
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        value = os.getenv(name, "")
        if not value:
            st.warning(f"Missing secret: {name}. Some features may not work.")
        return value


# --- Anthropic (Claude) ---
import anthropic  # noqa: E402

claude = anthropic.Anthropic(api_key=_get_secret("ANTHROPIC_API_KEY"))

# --- OpenAI (DALL-E) ---
import openai  # noqa: E402

openai_client = openai.OpenAI(api_key=_get_secret("OPENAI_API_KEY"))

# --- ElevenLabs ---
import elevenlabs  # noqa: E402

elevenlabs_client = elevenlabs.ElevenLabs(api_key=_get_secret("ELEVENLABS_API_KEY"))
ELEVENLABS_VOICE_ID = _get_secret("ELEVENLABS_VOICE_ID")

# --- Pexels (REST, no SDK) ---
import requests  # noqa: E402


pexels = requests.Session()


def _ensure_pexels_auth():
    """Set the Pexels Authorization header if not already set.

    Called before every Pexels request to handle the case where the
    module was imported before st.secrets was ready.
    """
    if not pexels.headers.get("Authorization"):
        key = _get_secret("PEXELS_API_KEY")
        if key:
            pexels.headers["Authorization"] = key

# --- Marketaux (REST) ---
MARKETAUX_API_KEY = _get_secret("MARKETAUX_API_KEY")

# --- Finnhub (REST) ---
FINNHUB_API_KEY = _get_secret("FINNHUB_API_KEY")
