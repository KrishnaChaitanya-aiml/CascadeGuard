import os
import httpx
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("FEATHERLESS_API_KEY")
if not api_key:
    raise SystemExit("FEATHERLESS_API_KEY is not configured")

response = httpx.get(
    "https://api.featherless.ai/account/concurrency",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=20,
)
print("Status:", response.status_code)
print(response.text)
