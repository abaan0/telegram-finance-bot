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


client = genai.Client(
    api_key=GEMINI_API_KEY
)
