"""
PataBot — Product Manager Module v2
Fetches products from BigBuy API with real images and multilingual descriptions.
Handles rate limiting gracefully with retries and delays.
Updated: March 2026
"""

import httpx
import asyncio
import os
import logging
from datetime import datetime

logger = logging.getLogger("patabot.products")

BIGBUY_API_KEY = os.getenv("BIGBUY_API_KEY", "")
BIGBUY_BASE = "https://api.bigbuy.eu"


class ProductManager:
    """Manages products: fetch from BigBuy, enrich with images/descriptions, cache."""

    def __init__(self):
        self.products_cache = []
        self.orders = []
        self.enrichment_running = False
        self.last_fetch_time = None
        self.headers = {
            "Authorization": f"Bearer {BIGBUY_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    # ─── Margin Calculation ───

    def _get_margin(self, price: float) -> float:
        if price < 15:
            return 1.50
        elif price <= 50:
            return 1.40
        else:
            return 1.30

    # ─── Safe API Call with Retry ───

    async def _safe_api_call(self, client: httpx.AsyncClient, url: str, params: dict = None, max_retries: int = 3) -> dict:
        """Make an API call with automatic retry on 429 rate limit."""
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                
                if resp.status_code == 200:
                    return {"status": 200, "data": resp.json()}
                elif resp.status_code == 429:
                    wait_time = 10 * (attempt + 1)  # 10s, 20s, 30s
                    logger.warning(f"Rate limited (429) on {url}, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"API returned {resp.status_code} for {url}")
                    return {"status": resp.status_code, "data": None}
            except Exception as e:
                logger.error(f"API call error for {url}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return {"status": 0, "data": None, "error": str(e)}
        
        return {"status": 429, "data": None, "error": "Max retries exceeded"}

    # ─── Main Product Fetch ───

    async def fetch_profitable_products(self, max_pages: int = 3, page_size: int = 200) -> dict:
        """Fetch products from BigBuy catalog API with wholesalePrice."""
        all_products = []
        fetch_errors = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for page in range(1, max_pages + 1):
                url = f"{BIGBUY_BASE}/rest/catalog/products.json"
                params = {"pageSize": page_size, "page": page}

                result = await self._safe_api_call(client, url, params)

                if result["status"] != 200 or not result["data"]:
                    fetch_errors.append(f"Page {page}: status {result['status']}")
                    break

                data = result["data"]
                if not data:
                    break

                page_count = 0
                for item in data:
                    wholesale = item.get("wholesalePrice")
                    if wholesale and float(wholesale) > 0:
                        wp = float(wholesale)
                        margin = self._get_margin(wp)
                        selling_price = round(wp * margin, 2)
                        old_price = round(selling_price * 1.23, 2)
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
                            "images": [],
                            "image_url": "",
                            "descriptions": {},
                            "enriched": False
                        }
                        all_products.append(product)
                        page_count += 1

                logger.info(f"Page {page}: fetched {page_count} profitable products from {len(data)} total")
                
                # Wait between pages to avoid rate limit
                if page < max_pages:
                    await asyncio.sleep(5)

        # Sort by profit and keep top 200
        all_products.sort(key=lambda x: x["profit"], reverse=True)
        self.products_cache = all_products[:200]
        self.last_fetch_time = datetime.now().isoformat()

        logger.info(f"Total profitable products cached: {len(self.products_cache)}")

        # Start background enrichment automatically
        if self.products_cache:
            asyncio.create_task(self._enrich_all_products())

        return {
            "products": [self._format_product(p) for p in self.products_cache[:20]],
            "count": len(self.products_cache),
            "errors": fetch_errors,
            "message": f"Fetched {len(self.products_cache)} products. Enrichment started in background."
        }

    # ─── Image Fetching ───

    async def _fetch_product_images(self, client: httpx.AsyncClient, product_id: int) -> list:
        """Fetch images for a single product from BigBuy API."""
        url = f"{BIGBUY_BASE}/rest/catalog/productimages/{product_id}.json"
        result = await self._safe_api_call(client, url, max_retries=2)
        
        if result["status"] != 200 or not result["data"]:
            return []
        
        images_data = result["data"]
        image_urls = []

        # BigBuy returns: {"id": X, "images": [{"url": "...", "isCover": true}, ...]}
        if isinstance(images_data, dict):
            # Format: {"id": X, "images": [...]}
            if "images" in images_data:
                for img in images_data["images"]:
                    if isinstance(img, dict) and img.get("url"):
                        image_urls.append(img["url"])
            else:
                # Format: direct dict with url fields
                for key, val in images_data.items():
                    if isinstance(val, str) and val.startswith("http"):
                        image_urls.append(val)
                    elif isinstance(val, list):
                        for v in val:
                            if isinstance(v, dict) and v.get("url"):
                                image_urls.append(v["url"])
        elif isinstance(images_data, list):
            for img in images_data:
                if isinstance(img, dict) and img.get("url"):
                    image_urls.append(img["url"])
                elif isinstance(img, str) and img.startswith("http"):
                    image_urls.append(img)

        return image_urls

    # ─── Multilingual Info ───

    async def _fetch_product_info(self, client: httpx.AsyncClient, product_id: int) -> dict:
        """Fetch multilingual product information from BigBuy API."""
        url = f"{BIGBUY_BASE}/rest/catalog/productinformation/{product_id}.json"
        result = await self._safe_api_call(client, url, max_retries=2)
        
        if result["status"] != 200 or not result["data"]:
            return {}
        
        info_data = result["data"]
        descriptions = {}

        if isinstance(info_data, list):
            for item in info_data:
                if isinstance(item, dict):
                    lang = item.get("isoCode", item.get("language", "")).lower()
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    if lang and (name or desc):
                        descriptions[lang] = {"name": name, "description": desc}
        elif isinstance(info_data, dict):
            # Could be {"id": X, ...} with embedded info
            if "name" in info_data:
                descriptions["es"] = {
                    "name": info_data.get("name", ""),
                    "description": info_data.get("description", "")
                }
            for lang_code in ["es", "en", "fr", "de", "nl", "it"]:
                if lang_code in info_data:
                    lang_info = info_data[lang_code]
                    if isinstance(lang_info, dict):
                        descriptions[lang_code] = {
                            "name": lang_info.get("name", ""),
                            "description": lang_info.get("description", "")
                        }

        return descriptions

    # ─── Background Enrichment ───

    async def _enrich_all_products(self):
        """Background task: enrich products with images and multilingual descriptions."""
        if self.enrichment_running:
            logger.info("Enrichment already running, skipping...")
            return

        self.enrichment_running = True
        enriched_count = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for product in self.products_cache:
                    if product.get("enriched"):
                        continue

                    product_id = product["id"]

                    # Fetch images
                    images = await self._fetch_product_images(client, product_id)
                    if images:
                        product["images"] = images
                        product["image_url"] = images[0]

                    await asyncio.sleep(2)  # Rate limit: 2s between requests

                    # Fetch multilingual info
                    descriptions = await self._fetch_product_info(client, product_id)
                    if descriptions:
                        product["descriptions"] = descriptions
                        if "es" in descriptions and descriptions["es"].get("name"):
                            product["name"] = descriptions["es"]["name"]
                        elif "en" in descriptions and descriptions["en"].get("name"):
                            product["name"] = descriptions["en"]["name"]

                    product["enriched"] = True
                    enriched_count += 1

                    await asyncio.sleep(2)  # Rate limit: 2s between requests

                    if enriched_count % 5 == 0:
                        logger.info(f"Enriched {enriched_count}/{len(self.products_cache)} products ({sum(1 for p in self.products_cache if p.get('image_url'))} with images)")

            logger.info(f"Enrichment complete: {enriched_count} products enriched")

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
        finally:
            self.enrichment_running = False

    # ─── Format Product for API Response ───

    def _format_product(self, p: dict) -> dict:
        """Format a product for API response."""
        return {
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
        }

    # ─── API Methods (called by main.py) ───

    async def get_current_products(self) -> list:
        """Return cached products for API responses."""
        if not self.products_cache:
            await self.fetch_profitable_products(max_pages=2)

        return [self._format_product(p) for p in self.products_cache[:200]]

    async def get_product_count(self) -> int:
        return len(self.products_cache)

    async def get_orders(self) -> list:
        return self.orders

    async def process_order(self, order_data: dict) -> dict:
        order = {
            "id": len(self.orders) + 1,
            "product_id": order_data.get("product_id"),
            "customer": order_data.get("customer", {}),
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        self.orders.append(order)
        logger.info(f"New order #{order['id']} created")
        return {"status": "success", "order": order}

    async def update_inventory_and_prices(self):
        logger.info("Updating inventory and prices...")

    async def remove_unavailable_products(self):
        logger.info("Checking for unavailable products...")

    def get_enrichment_status(self) -> dict:
        total = len(self.products_cache)
        enriched = sum(1 for p in self.products_cache if p.get("enriched"))
        with_images = sum(1 for p in self.products_cache if p.get("image_url"))

        return {
            "total_products": total,
            "enriched": enriched,
            "with_images": with_images,
            "progress_pct": round((enriched / total * 100) if total > 0 else 0),
            "running": self.enrichment_running,
            "last_fetch": self.last_fetch_time
        }
