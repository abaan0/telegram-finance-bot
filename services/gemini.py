import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()


GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

GEMINI_FALLBACK_MODELS = [
    GEMINI_MODEL,              # Primary
    "gemini-3.7-flash",        # Fallback 1
    "gemini-3.6-flash",        # Fallback 2
    "gemini-3.5-flash",        # Fallback 3
    "gemini-3.1-flash-lite",   # Fallback 4
]


client = genai.Client(
    api_key=GEMINI_API_KEY
)