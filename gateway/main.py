from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import requests
import secrets
import os
import json
from pathlib import Path
import time
from dotenv import load_dotenv

# Get environment variables
env_path = Path(__file__).resolve().parent / "credentials.env"
load_dotenv(dotenv_path=env_path)

class QuestionRequest(BaseModel):
    store_id: str
    question: str


app = FastAPI(title="Shopify Gateway API")

# My credentials for the app
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")

AI_SERVICE_URL = "http://localhost:9000/api/v1/ask"

# Storage
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "storage" / "store.json"

def save_dict(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_dict() -> dict:
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

# Load existing tokens
token_data = load_dict()

# Temporary storage for OAuth state values
oauth_states = {}

# OAuth endpoints
@app.get("/auth/install")
def install(shop: str):
    # Generate unique state for CSRF protection
    state = secrets.token_hex(16)
    oauth_states[shop] = state
    # Note down the scopes below for future reference
    scopes = "read_inventory,read_orders,read_products,read_customers,read_locations,read_markets_home,read_markets"
    redirect_uri = "http://localhost:8000/auth/callback"

    install_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&scope={scopes}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )

    return RedirectResponse(install_url)

@app.get("/auth/callback")
def callback(shop: str, code: str, state: str):
    # Validate OAuth state
    if shop not in oauth_states or oauth_states[shop] != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    del oauth_states[shop]  # cleanup

    # Exchange code for access token
    token_url = f"https://{shop}/admin/oauth/access_token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code
    }

    r = requests.post(token_url, json=payload)

    if r.status_code != 200:
        raise HTTPException(400, detail="OAuth token request failed")

    try:
        access_token = r.json()["access_token"]
    except (ValueError, KeyError):
        raise HTTPException(400, detail="Failed to retrieve access token")

    # Store token (and optional timestamp)
    token_data[shop] = access_token
    save_dict(token_data)

    return {"status": "installed"}

# this is the main function, which will be called to ask questions
@app.post("/api/v1/questions")
def ask_question(req: QuestionRequest):
    # Validate input
    if not req.store_id or not req.question:
        raise HTTPException(status_code=401, detail="Question / store_id not found")
    
    # Get the shopify storeid authenticated and get the shopify token
    if req.store_id not in token_data:
        raise HTTPException(status_code=401, detail=f"Please authenticate via this link: http://localhost:8000/auth/install?shop={req.store_id}")

    SHOPIFY_TOKEN = token_data[req.store_id]
    # Prepare payload for AI service
    payload = {
        "store_id": req.store_id,
        "question": req.question,
        "shopify_token": SHOPIFY_TOKEN
    }

    response = requests.post(AI_SERVICE_URL, json=payload, timeout=60)
    # Return AI service response to user
    return response.json()

@app.get("/helloworld")
def helloworld():
    return {"hello world :DD"}
