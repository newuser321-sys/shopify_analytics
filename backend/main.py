import sqlite3
from pathlib import Path
import requests
from datetime import datetime, timedelta
from google import genai
from google.genai import errors
import json
from fastapi import HTTPException
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv

# Get environment variables
env_path = Path(__file__).resolve().parent / "credentials.env"
load_dotenv(dotenv_path=env_path)

# Request model
class AskRequest(BaseModel):
    store_id: str
    question: str
    shopify_token: str

# Run server
app = FastAPI(title="AI Backend Service")

# Database setup
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "shopify.db"
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # shop table
    c.execute("""
        CREATE TABLE IF NOT EXISTS shop (
            shop_id TEXT PRIMARY KEY,
            name TEXT,
            currency TEXT,
            timezone TEXT,
            created_at TEXT
        )
    """)

    # products table
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            title TEXT,
            vendor TEXT,
            product_type TEXT,
            created_at TEXT
        )
    """)

    # variants table
    c.execute("""
        CREATE TABLE IF NOT EXISTS variants (
            variant_id TEXT PRIMARY KEY,
            product_id TEXT,
            sku TEXT,
            price REAL,
            inventory_item_id TEXT,
            FOREIGN KEY(product_id) REFERENCES products(product_id)
        )
    """)

    # inventory table
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
        inventory_item_id TEXT,
        location_id TEXT,
        available INTEGER,
        updated_at TEXT,
        PRIMARY KEY (inventory_item_id, location_id)
        );

    """)

    # orders table
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            created_at TEXT,
            customer_id TEXT
        )
    """)

    # order_items table
    c.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_id TEXT,
            product_id TEXT,
            variant_id TEXT,
            quantity INTEGER,
            price REAL
        )
    """)


    conn.commit()
    conn.close()

init_db()

# Extra sql helper for inventory 
def run_ddl(sql: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(sql)
    conn.commit()
    conn.close()

helper = """CREATE VIEW IF NOT EXISTS inventory_totals AS
    SELECT
    v.product_id,
    v.variant_id,
    SUM(i.available) AS total_available
    FROM inventory i
    JOIN variants v ON i.inventory_item_id = v.inventory_item_id
    GROUP BY v.product_id, v.variant_id;
"""
run_ddl(helper)

# Cache DB
LAST_SYNC = {}

def should_sync(store_id, minutes=5):
    last = LAST_SYNC.get(store_id)
    if not last:
        return True
    return datetime.utcnow() - last > timedelta(minutes=minutes)

# Static variables

db_schema = """
    Tables:

    shop(
        shop_id TEXT PRIMARY KEY,
        name TEXT,
        currency TEXT,
        timezone TEXT,
        created_at TEXT
    )

    orders(
        order_id TEXT PRIMARY KEY,
        created_at TEXT,
        customer_id TEXT
    )

    order_items(
        order_id TEXT,
        product_id TEXT,
        variant_id TEXT,
        quantity INTEGER,
        price REAL
    )

    products(
        product_id TEXT PRIMARY KEY,
        title TEXT,
        vendor TEXT,
        created_at TEXT
    )

    variants(
        variant_id TEXT PRIMARY KEY,
        product_id TEXT,
        sku TEXT,
        price REAL,
        inventory_item_id TEXT
    )

    inventory(
    inventory_item_id TEXT,
    location_id TEXT,
    available INTEGER,
    updated_at TEXT,
    PRIMARY KEY (inventory_item_id, location_id)
    )
"""

# Orders query (fetch line items and customer)
ORDERS_QUERY = """
    query Orders($first: Int!, $after: String, $query: String) {
    orders(first: $first, after: $after, query: $query) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        createdAt
        customer {
          id
        }
        lineItems(first: 50) {
          edges {
            node {
              id
              quantity
              originalUnitPriceSet {
                shopMoney {
                  amount
                }
              }
              product {
                id
              }
              variant {
                id
                inventoryItem {
                  id
                }
              }
            }
          }
        }
      }
    }
    }
    }
    """

# Products query (includes variants and inventory levels)
PRODUCTS_QUERY = """
    query Products($first: Int!, $after: String) {
    products(first: $first, after: $after) {
        pageInfo {
        hasNextPage
        endCursor
        }
        edges {
        node {
            id
            title
            vendor
            productType
            createdAt
            variants(first: 50) {
            edges {
                node {
                id
                sku
                price
                inventoryItem {
                    id
                    inventoryLevels(first: 10) {
                    edges {
                        node {
                        updatedAt
                        location {
                            id
                            name
                        }
                        quantities(names: ["available"]) {
                            name
                            quantity
                        }
                        }
                    }
                    }
                }
                }
            }
            }
        }
        }
    }
    }
    """

# Shop query (single object)
SHOP_QUERY = """
    query Shop {
    shop {
        id
        name
        currencyCode
        timezone
        createdAt
    }
    }

    """


# Fetch data from shopify
def fetch_shopify_graphql(store_id: str, token: str, query: str, variables: dict = None):
    url = f"https://{store_id}/admin/api/2024-01/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    r = requests.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail=f"Shopify GraphQL API error: {r.text}")
    return r.json()

def fetch_all_graphql(store_id: str, token: str, query: str, variables: dict = None, data_path: list = None):
    combined = []
    after = None

    while True:
        vars_copy = variables.copy() if variables else {}
        if after:
            vars_copy["after"] = after

        response = fetch_shopify_graphql(store_id, token, query, vars_copy)

        if "errors" in response:
            print("GraphQL errors:", response["errors"])
            break

        data = response.get("data", {})
        if data_path:
            for key in data_path:
                if key not in data:
                    print(f"Key missing in response: {key}")
                    data = {}
                    break
                data = data.get(key, {})

        edges = data.get("edges", [])
        combined.extend(edges)

        page_info = data.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            after = page_info.get("endCursor")
        else:
            break

    return {"edges": combined}

def build_time_filter(days: int):
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    return {"created_at_min": since}

def ingest_shopify_data(store_id: str, token: str, createdAtMin=None):
    raw_data = {}

    # Orders
    variables = {"first": 50}
    if createdAtMin:
        variables["query"] = f"created_at:>={createdAtMin}"
    raw_data["orders"] = fetch_all_graphql(
        store_id, token, ORDERS_QUERY, variables, data_path=["orders"]
    )

    # Products (variants include inventoryItem.id)
    raw_data["products"] = fetch_all_graphql(
        store_id, token, PRODUCTS_QUERY, {"first": 50}, data_path=["products"]
    )

    # Shop (single object, no pagination)
    raw_shop = fetch_shopify_graphql(store_id, token, SHOP_QUERY)
    raw_data["shop"] = raw_shop.get("data", {})

    return raw_data

# Normalize the raw data

def strip_gid(gid: str | None):
    if not gid:
        return None
    return gid.split("/")[-1]


def normalize_shop(raw_shop):
    s = raw_shop.get("shop", {})
    if not s:
        return None

    return {
        "shop_id": strip_gid(s.get("id")),
        "name": s.get("name"),
        "currency": s.get("currencyCode"),
        "timezone": s.get("timezone"),
        "created_at": s.get("createdAt"),
    }


def normalize_orders(raw_orders):
    orders = []
    order_items = []

    for edge in raw_orders.get("edges", []):
        o = edge.get("node")
        if not o:
            continue

        order_id = strip_gid(o.get("id"))
        orders.append({
            "order_id": order_id,
            "created_at": o.get("createdAt"),
            "customer_id": strip_gid(o.get("customer", {}).get("id")) if o.get("customer") else None
        })

        for li_edge in o.get("lineItems", {}).get("edges", []):
            li = li_edge.get("node")
            if not li:
                continue

            price = float(li.get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount", 0))

            order_items.append({
                "order_id": order_id,
                "product_id": strip_gid(li.get("product", {}).get("id")) if li.get("product") else None,
                "variant_id": strip_gid(li.get("variant", {}).get("id")) if li.get("variant") else None,
                "quantity": int(li.get("quantity", 0)),
                "price": price
            })

    return {"orders": orders, "order_items": order_items}


def normalize_products(raw_products):
    products = []
    variants = []
    inventory = []

    for edge in raw_products.get("edges", []):
        p = edge.get("node")
        if not p:
            continue

        product_id = strip_gid(p.get("id"))

        # Product
        products.append({
            "product_id": product_id,
            "title": p.get("title"),
            "vendor": p.get("vendor"),
            "product_type": p.get("productType"),
            "created_at": p.get("createdAt")
        })

        # Variants + Inventory
        for v_edge in p.get("variants", {}).get("edges", []):
            v = v_edge.get("node")
            if not v:
                continue

            inventory_item = v.get("inventoryItem") or {}
            inventory_item_id = strip_gid(inventory_item.get("id"))
            if not inventory_item_id:
                continue
            # Variant
            variants.append({
                "variant_id": strip_gid(v.get("id")),
                "product_id": product_id,
                "sku": v.get("sku"),  # may be None
                "price": float(v.get("price", 0)),
                "inventory_item_id": inventory_item_id
            })
            

            # Inventory per location
            for il_edge in inventory_item.get("inventoryLevels", {}).get("edges", []):
                il = il_edge.get("node", {})

                location = il.get("location", {})
                location_id = strip_gid(location.get("id"))

                qty_list = il.get("quantities", [])
                available_qty = 0

                for q in qty_list:
                    if q.get("name") == "available":
                        available_qty = int(q.get("quantity", 0))

                inventory.append({
                    "inventory_item_id": inventory_item_id,
                    "location_id": location_id,
                    "available": available_qty,
                    "updated_at": il.get("updatedAt")
                })




    return {"products": products, "variants": variants, "inventory": inventory}

# Insert / Upsert Functions for Database

def insert_shop(shop):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO shop(shop_id, name, currency, timezone, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(shop_id) DO UPDATE SET
            name=excluded.name,
            currency=excluded.currency,
            timezone=excluded.timezone,
            created_at=excluded.created_at
    """, (shop["shop_id"], shop["name"], shop["currency"], shop["timezone"], shop["created_at"]))
    conn.commit()
    conn.close()


def insert_orders(orders):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for o in orders:
        c.execute("""
            INSERT INTO orders(order_id, created_at, customer_id)
            VALUES (?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                created_at=excluded.created_at,
                customer_id=excluded.customer_id
        """, (o["order_id"], o["created_at"], o["customer_id"]))
    conn.commit()
    conn.close()


def insert_order_items(items):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for i in items:
        c.execute("""
            INSERT OR REPLACE INTO order_items(order_id, product_id, variant_id, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        """, (i["order_id"], i["product_id"], i["variant_id"], i["quantity"], i["price"]))
    conn.commit()
    conn.close()


def insert_products(products):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for p in products:
        c.execute("""
            INSERT INTO products(product_id, title, vendor, product_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                title=excluded.title,
                vendor=excluded.vendor,
                product_type=excluded.product_type,
                created_at=excluded.created_at
        """, (p["product_id"], p["title"], p["vendor"], p["product_type"], p["created_at"]))
    conn.commit()
    conn.close()


def insert_variants(variants):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for v in variants:
        c.execute("""
            INSERT INTO variants(variant_id, product_id, sku, price, inventory_item_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(variant_id) DO UPDATE SET
                product_id=excluded.product_id,
                sku=excluded.sku,
                price=excluded.price,
                inventory_item_id=excluded.inventory_item_id
        """, (v["variant_id"], v["product_id"], v["sku"], v["price"], v["inventory_item_id"]))
    conn.commit()
    conn.close()


def insert_inventory(items):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for i in items:
        c.execute("""
            INSERT INTO inventory(inventory_item_id, location_id, available, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(inventory_item_id, location_id) DO UPDATE SET
                available=excluded.available,
                updated_at=excluded.updated_at
        """, (i["inventory_item_id"], i["location_id"], i["available"], i["updated_at"]))
    conn.commit()
    conn.close()

# Master normalize_all_raw_data
def normalize_all_raw_data(raw_data: dict):
    # Orders
    if "orders" in raw_data:
        normalized_orders = normalize_orders(raw_data["orders"])
        insert_orders(normalized_orders["orders"])
        insert_order_items(normalized_orders["order_items"])

    # Products + Variants + Inventory
    if "products" in raw_data:
        normalized_products = normalize_products(raw_data["products"])
        insert_products(normalized_products["products"])
        insert_variants(normalized_products["variants"])
        insert_inventory(normalized_products["inventory"])
       

    # Shop
    if "shop" in raw_data:
        shop = normalize_shop(raw_data["shop"])
        if shop:
            insert_shop(shop)

# Validate llm's sql query response      
def is_safe_sql(sql: str) -> bool:
    sql = sql.strip().lower()

    if not sql.startswith("select"):
        return False

    forbidden = ["insert", "update", "delete", "drop", "alter", "pragma"]
    for k in forbidden:
        if re.search(rf"\b{k}\b", sql):
            return False

    return True

# Run query if it passes the check
def run_sql(sql: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(sql)
    rows = c.fetchall()

    conn.close()
    return [dict(r) for r in rows]

# Google LLM
API_KEY = os.getenv("GOOGLE_API_KEY")

try:
    client = genai.Client(api_key=API_KEY)
except:
    raise HTTPException(500, detail=f"Error from llm client: {API_KEY}")
def ask_google_llm(prompt: str) -> str:
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )    
    except errors.ClientError as e:
        raise HTTPException(500, detail="LLM quota exceeded. Please retry shortly.")

    return response.text
    
# Main code
@app.post("/api/v1/ask")
def ask(req: AskRequest):
    if not req.store_id or not req.question or not req.shopify_token:
        raise HTTPException(status_code=400, detail="Missing fields")

    # Initialize all variables
    store_id = req.store_id
    token = req.shopify_token
    question = req.question
    
    prompt1 = f"""
        You are an analytics assistant. You must refer to the database schema below and adhere to the rules based on the given question.
        {db_schema}
        Rules:
        - Generate ONLY valid SQLite SQL
        - SELECT queries only
        - Use only the tables and columns provided
        - Do NOT explain the query
        - Do NOT include markdown
        - Do NOT include comments
        - If the question cannot be answered, return: INVALID
        - use 'inventory_totals' to access inventory levels
        - if you are asked about product types, refer to product.title

        {question}
        """
    # Start collecting user's data
    if should_sync(store_id):
        raw_data = ingest_shopify_data(store_id, token)
        normalize_all_raw_data(raw_data)
        LAST_SYNC[store_id] = datetime.utcnow()

    # Send first prompt to llm. This returns a sql statement to query local db
    sql = ask_google_llm(prompt1).strip()

    # Validate the sql statement
    if sql == "INVALID":
        print("Question cannot be answered")
        return

    if not is_safe_sql(sql):
        raise ValueError("Unsafe SQL")

    # Execute the sql statement
    rows = run_sql(sql)

    if not rows:
        return {"answer": "Data is unavailable for this question."}

    # Second prompt to get plain English answer based on the sql query output
    prompt2 = f"""
        You are an analytics assistant.

        User question:
        {question}

        SQL that was executed:
        {sql}

        Query result (JSON):
        {json.dumps(rows, indent=2)}

        Rules:
        - Use ONLY the data in the result.
        - Do NOT invent numbers.
        - Respond in plain English. The answer must be simple and to the point.
        """
    # Ask llm to construct final answer
    answer = ask_google_llm(prompt2)

    return answer

@app.get("/helloworld")
def helloworld():
    return {"hello world :DD"}