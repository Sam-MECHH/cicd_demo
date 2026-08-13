import os
import time
import requests
from typing import Dict, Any, List, Optional

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
SOURCE_URL = os.environ.get("SOURCE_URL", "https://dummyjson.com/products")
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "100"))

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # stable enough for basic CRUD

# ---- Helpers ----------------------------------------------------------------

def notion_headers() -> Dict[str, str]:
    if not NOTION_TOKEN:
        raise RuntimeError("Missing NOTION_TOKEN (set it as a GitHub Secret).")
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

def fetch_products() -> List[Dict[str, Any]]:
    """Fetch all products from dummyjson with pagination."""
    products: List[Dict[str, Any]] = []
    skip = 0
    while True:
        url = f"{SOURCE_URL}?limit={PAGE_SIZE}&skip={skip}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("products", [])
        if not batch:
            break
        products.extend(batch)
        skip += PAGE_SIZE
        if len(batch) < PAGE_SIZE:
            break
    return products

def query_database_by_product_id(product_id: int) -> Optional[str]:
    """Return Notion page_id if a row with Product ID == product_id exists."""
    url = f"{NOTION_API}/databases/{NOTION_DATABASE_ID}/query"
    body = {
        "filter": {
            "property": "Product ID",
            "number": { "equals": product_id }
        },
        "page_size": 1
    }
    r = requests.post(url, headers=notion_headers(), json=body, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    if results:
        return results[0]["id"]
    return None

def product_to_properties(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map dummyjson product -> Notion properties.
    Expected Notion database properties (see notion_mapping.md):
      - Name (Title)
      - Product ID (Number)
      - Price (Number)
      - Stock (Number)
      - Rating (Number)
      - Category (Select)
      - Brand (Rich text)
      - Thumbnail (URL)
    """
    name = p.get("title") or f"Product {p.get('id')}"
    return {
        "Name": {"title": [{"text": {"content": name}}]},
        "Product ID": {"number": int(p["id"])},
        "Price": {"number": float(p.get("price", 0))},
        "Stock": {"number": float(p.get("stock", 0))},
        "Rating": {"number": float(p.get("rating", 0))},
        "Category": {"select": {"name": p.get("category", "unknown")}},
        "Brand": {"rich_text": [{"text": {"content": p.get("brand", "")}}]},
        "Thumbnail": {"url": p.get("thumbnail", "")},
    }

def create_page_in_database(p: Dict[str, Any]) -> str:
    url = f"{NOTION_API}/pages"
    body = {
        "parent": { "database_id": NOTION_DATABASE_ID },
        "properties": product_to_properties(p)
    }
    r = requests.post(url, headers=notion_headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()["id"]

def update_page(page_id: str, p: Dict[str, Any]) -> None:
    url = f"{NOTION_API}/pages/{page_id}"
    body = {
        "properties": product_to_properties(p)
    }
    r = requests.patch(url, headers=notion_headers(), json=body, timeout=30)
    r.raise_for_status()

# ---- Main -------------------------------------------------------------------

def main() -> None:
    if not NOTION_DATABASE_ID:
        raise RuntimeError("Missing NOTION_DATABASE_ID (set it as a GitHub Secret).")

    print("🔗 Fetching products from dummyjson…")
    products = fetch_products()
    print(f"📦 Retrieved {len(products)} products")

    created, updated = 0, 0
    for p in products:
        page_id = query_database_by_product_id(int(p["id"]))
        if page_id:
            update_page(page_id, p)
            updated += 1
        else:
            create_page_in_database(p)
            created += 1
        # Be a good API citizen with a tiny delay to avoid rate limits
        time.sleep(0.15)

    print(f"✅ Done. Created: {created} | Updated: {updated}")

if __name__ == "__main__":
    main()
