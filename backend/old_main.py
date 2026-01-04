from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from google import genai

# Initialize client with API key (auto‑uses env var if set)
client = genai.Client(api_key=API_KEY)

def ask_google_llm(prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.5-flash",   # a free / standard model name
        contents=prompt
    )
    return response.text

app = FastAPI(title="AI Backend Service")

# Request model
class AskRequest(BaseModel):
    store_id: str
    question: str
    shopify_token: str

# Shopify helper
def fetch_shopify_data(store_id: str, token: str):
    url = f"https://{store_id}/admin/api/2024-01/shop.json"
    headers = {
        "X-Shopify-Access-Token": token
    }

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Shopify token")

    return r.json()

# AI endpoint
@app.post("/api/v1/ask")
def ask(req: AskRequest):
    if not req.store_id or not req.question or not req.shopify_token:
        raise HTTPException(status_code=400, detail="Missing fields")

    # Fetch Shopify data (example)
    shop_data = fetch_shopify_data(req.store_id, req.shopify_token)

    # Build AI prompt (stub)
    prompt = f"""
    You are a data planner for a Shopify analytics system.

    Given a user question, return ONLY a JSON object listing:
    - required_metrics
    - time_range (if applicable)
    - aggregation (sum, count, avg, etc)

    Following is the question. Do not answer the question. Return the required JSON object.
    {req.question}
    """

    

    # AI logic placeholder
    answer = {
        "answer": "AI response goes here",
        "store": req.store_id
    }

    return answer

print(run_sql("""SELECT
            p.title,
            v.sku,
            i.available
            FROM inventory i
            JOIN variants v ON v.inventory_item_id = i.inventory_item_id
            JOIN products p ON p.product_id = v.product_id
            WHERE p.title LIKE '%shirt%';

        """))
    return