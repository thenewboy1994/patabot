"""
PataBot — Product Manager Module
Fetches products from BigBuy API with real images and multilingual descriptions.
Updated: March 2026
"""

import httpx
import asyncio
import os
import logging
from typing import Optional

logger = logging.getLogger("patabot.products")

BIGBUY_API_KEY = os.getenv("BIGBUY_API_KEY", "")
BIGBUY_BASE = "https://api.bigbuy.eu"

HEADERS = {
    "Authorization": f"Bearer {BIGBUY_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# ─── In-memory product store ───
products_cache = []
enrichment_running = False


def get_margin(price: float) -> float:
    """Calculate selling margin based on wholesale price tier."""
    if price < 15:
        return 1.50   # 50% margin
    elif price <= 50:
        return 1.40   # 40% margin
    else:
        return 1.30   # 30% margin


async def fetch_products_from_bigbuy(max_pages: int = 5, page_size: int = 200) -> list:
    """
    Fetch products from BigBuy catalog API.
    Uses wholesalePrice directly from products.json (price endpoints return 400).
    """
    global products_cache
    all_products = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(1, max_pages + 1):
            try:
                url = f"{BIGBUY_BASE}/rest/catalog/products.json"
                params = {"pageSize": page_size, "page": page}
                
                resp = await client.get(url, headers=HEADERS, params=params)
                
                if resp.status_code == 429:
                    logger.warning(f"Rate limited on page {page}, waiting 5s...")
                    await asyncio.sleep(5)
                    resp = await client.get(url, headers=HEADERS, params=params)
                
                if resp.status_code != 200:
                    logger.error(f"BigBuy page {page} returned {resp.status_code}")
                    break

                data = resp.json()
                if not data:
                    break

                for item in data:
                    wholesale = item.get("wholesalePrice")
                    if wholesale and float(wholesale) > 0:
                        wp = float(wholesale)
                        margin = get_margin(wp)
                        selling_price = round(wp * margin, 2)
                        old_price = round(selling_price * 1.23, 2)  # ~23% "discount"
                        profit = round(selling_price - wp, 2)

                        product = {
                            "id": item.get("id"),
                            "sku": item.get("sku", ""),
                            "name": item.get("name", f"Product #{item.get('id')}"),
                            "description": item.get("description", ""),
                            "wholesale_price": wp,
                            "selling_price": selling_price,
                            "old_price": old_price,
                            "profit": profit,
                            "margin_pct": round((margin - 1) * 100),
                            "category": item.get("category", ""),
                            "images": [],          # Will be enriched
                            "image_url": "",        # Primary image
                            "descriptions": {},     # Multilingual — will be enriched
                            "enriched": False
                        }
                        all_products.append(product)

                logger.info(f"Page {page}: fetched {len(data)} products")
                await asyncio.sleep(2.5)  # Respect rate limits

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

    # Sort by profit (highest first) and keep top 200
    all_products.sort(key=lambda x: x["profit"], reverse=True)
    products_cache = all_products[:200]
    
    logger.info(f"Total profitable products cached: {len(products_cache)}")
    
    # Start background enrichment (images + descriptions)
    asyncio.create_task(enrich_all_products())
    
    return products_cache


async def fetch_product_images(client: httpx.AsyncClient, product_id: int) -> list:
    """Fetch images for a single product from BigBuy API."""
    try:
        url = f"{BIGBUY_BASE}/rest/catalog/productimages/{product_id}.json"
        resp = await client.get(url, headers=HEADERS)
        
        if resp.status_code == 200:
            images_data = resp.json()
            image_urls = []
            
            if isinstance(images_data, list):
                for img in images_data:
                    if isinstance(img, dict) and img.get("url"):
                        image_urls.append(img["url"])
                    elif isinstance(img, str) and img.startswith("http"):
                        image_urls.append(img)
            elif isinstance(images_data, dict):
                # Some products return a dict with image URLs
                for key, val in images_data.items():
                    if isinstance(val, str) and val.startswith("http"):
                        image_urls.append(val)
                    elif isinstance(val, list):
                        for v in val:
                            if isinstance(v, dict) and v.get("url"):
                                image_urls.append(v["url"])
                            elif isinstance(v, str) and v.startswith("http"):
                                image_urls.append(v)
            
            return image_urls
        else:
            logger.debug(f"Images for {product_id}: status {resp.status_code}")
            return []
    except Exception as e:
        logger.debug(f"Error fetching images for {product_id}: {e}")
        return []


async def fetch_product_info(client: httpx.AsyncClient, product_id: int) -> dict:
    """Fetch multilingual product information from BigBuy API."""
    try:
        url = f"{BIGBUY_BASE}/rest/catalog/productinformation/{product_id}.json"
        resp = await client.get(url, headers=HEADERS)
        
        if resp.status_code == 200:
            info_data = resp.json()
            descriptions = {}
            
            if isinstance(info_data, list):
                for item in info_data:
                    if isinstance(item, dict):
                        lang = item.get("isoCode", item.get("language", "")).lower()
                        name = item.get("name", "")
                        desc = item.get("description", "")
                        if lang and (name or desc):
                            descriptions[lang] = {
                                "name": name,
                                "description": desc
                            }
            elif isinstance(info_data, dict):
                for lang_code in ["es", "en", "fr", "de", "nl", "it"]:
                    if lang_code in info_data:
                        lang_info = info_data[lang_code]
                        if isinstance(lang_info, dict):
                            descriptions[lang_code] = {
                                "name": lang_info.get("name", ""),
                                "description": lang_info.get("description", "")
                            }
            
            return descriptions
        return {}
    except Exception as e:
        logger.debug(f"Error fetching info for {product_id}: {e}")
        return {}


async def enrich_all_products():
    """Background task: enrich products with images and multilingual descriptions."""
    global products_cache, enrichment_running
    
    if enrichment_running:
        logger.info("Enrichment already running, skipping...")
        return
    
    enrichment_running = True
    enriched_count = 0
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for product in products_cache:
                if product.get("enriched"):
                    continue
                
                product_id = product["id"]
                
                # Fetch images
                images = await fetch_product_images(client, product_id)
                if images:
                    product["images"] = images
                    product["image_url"] = images[0]  # Primary image
                
                await asyncio.sleep(1.5)  # Rate limit respect
                
                # Fetch multilingual info
                descriptions = await fetch_product_info(client, product_id)
                if descriptions:
                    product["descriptions"] = descriptions
                    # Update main name if Spanish version available
                    if "es" in descriptions and descriptions["es"].get("name"):
                        product["name"] = descriptions["es"]["name"]
                    elif "en" in descriptions and descriptions["en"].get("name"):
                        product["name"] = descriptions["en"]["name"]
                
                product["enriched"] = True
                enriched_count += 1
                
                await asyncio.sleep(1.5)  # Rate limit respect
                
                if enriched_count % 10 == 0:
                    logger.info(f"Enriched {enriched_count}/{len(products_cache)} products")
        
        logger.info(f"Enrichment complete: {enriched_count} products enriched")
    
    except Exception as e:
        logger.error(f"Enrichment error: {e}")
    finally:
        enrichment_running = False


def get_products(limit: int = 200) -> list:
    """Return cached products (for API responses)."""
    result = []
    for p in products_cache[:limit]:
        result.append({
            "id": p["id"],
            "sku": p["sku"],
            "name": p["name"],
            "description": p.get("description", ""),
            "selling_price": p["selling_price"],
            "old_price": p["old_price"],
            "profit": p["profit"],
            "margin_pct": p["margin_pct"],
            "image_url": p.get("image_url", ""),
            "images": p.get("images", []),
            "descriptions": p.get("descriptions", {}),
            "enriched": p.get("enriched", False),
            "category": p.get("category", "")
        })
    return result


def get_enrichment_status() -> dict:
    """Return enrichment progress."""
    total = len(products_cache)
    enriched = sum(1 for p in products_cache if p.get("enriched"))
    with_images = sum(1 for p in products_cache if p.get("image_url"))
    
    return {
        "total_products": total,
        "enriched": enriched,
        "with_images": with_images,
        "progress_pct": round((enriched / total * 100) if total > 0 else 0),
        "running": enrichment_running
    }
