import os
from dotenv import load_dotenv

load_dotenv()

FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY")
FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen3-32B")
FEATHERLESS_URL = "https://api.featherless.ai/v1/chat/completions"

NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "CascadeGuard/1.0 (hackathon-project; contact-required-by-policy)",
)

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY")
RELIEFWEB_APPNAME = os.getenv("RELIEFWEB_APPNAME")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "45"))
OVERPASS_TIMEOUT = float(os.getenv("OVERPASS_TIMEOUT", "55"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))
MAX_ZONES = int(os.getenv("MAX_ZONES", "8"))
