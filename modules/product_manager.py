"""
PataBot — Product Manager Module v3
Fetches products from BigBuy API with real images and multilingual descriptions.
Fixed image parsing to match BigBuy's actual response format.
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

    def _get_margin(self, price: float) -> float:
        if price < 15:
            return 1.50
        elif price <= 50:
            return 1.40
        else:
            return 1.30

    # ─── Safe API Call with Retry ───

    async def _safe_api_call(self, client: httpx.AsyncClient, url: str, params: dict = None, max_retries: int = 3) -> dict:
        """Make an API call with automatic retry on 429."""
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    return {"status": 200, "data": resp.json()}
                elif resp.status_code == 429:
                    wait_time = 15 * (attempt + 1)
                    logger.warning(f"429 on {url}, waiting {wait_time}s (attempt {attempt+1})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return {"status": resp.status_code, "data": None}
            except Exception as e:
                logger.error(f"API error {url}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                return {"status": 0, "data": None}
        return {"status": 429, "data": None}

    # ─── Main Product Fetch ───

    async def fetch_profitable_products(self, max_pages: int = 3, page_size: int = 200) -> dict:
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

                for item in data:
                    wholesale = item.get("wholesalePrice")
                    if wholesale and float(wholesale) > 0:
                        wp = float(wholesale)
                        margin = self._get_margin(wp)
                        selling_price = round(wp * margin, 2)
                        old_price = round(selling_price * 1.23, 2)
                        profit = round(selling_price - wp, 2)

                        all_products.append({
                            "id": item.get("id"),
                            "sku": item.get("sku", ""),
                            "name": item.get("name", f"Product #{item.get('id')}"),
                            "description": "",
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
                        })

                logger.info(f"Page {page}: {len(data)} products fetched")
                if page < max_pages:
                    await asyncio.sleep(5)

        all_products.sort(key=lambda x: x["profit"], reverse=True)
        self.products_cache = all_products[:200]
        self.last_fetch_time = datetime.now().isoformat()
        logger.info(f"Cached {len(self.products_cache)} products")

        if self.products_cache:
            asyncio.create_task(self._enrich_all_products())

        return {
            "products": [self._format_product(p) for p in self.products_cache[:20]],
            "count": len(self.products_cache),
            "errors": fetch_errors,
            "message": f"Fetched {len(self.products_cache)} products. Enrichment started in background."
        }

    # ─── Image Fetching — FIXED for BigBuy format ───

    async def _fetch_product_images(self, client: httpx.AsyncClient, product_id: int) -> list:
        """
        Fetch images for a product.
        BigBuy returns: {"id": 1289533, "images": [{"id": 7739715, "isCover": true, "url": "https://cdn.bigbuy.com/images/...", ...}, ...]}
        """
        url = f"{BIGBUY_BASE}/rest/catalog/productimages/{product_id}.json"
        result = await self._safe_api_call(client, url, max_retries=2)

        if result["status"] != 200 or not result["data"]:
            return []

        data = result["data"]
        image_urls = []

        try:
            # BigBuy format: {"id": X, "images": [{...}, ...]}
            if isinstance(data, dict) and "images" in data:
                for img in data["images"]:
                    if isinstance(img, dict) and img.get("url"):
                        image_urls.append(img["url"])

            # Alternative: direct list of image objects
            elif isinstance(data, list):
                for img in data:
                    if isinstance(img, dict) and img.get("url"):
                        image_urls.append(img["url"])

            # Alternative: dict without "images" key but with url values
            elif isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, str) and val.startswith("http") and (".jpg" in val or ".png" in val or ".webp" in val):
                        image_urls.append(val)

        except Exception as e:
            logger.error(f"Image parse error for {product_id}: {e}")

        # Sort: put cover image first
        if isinstance(data, dict) and "images" in data:
            try:
                cover_imgs = [img["url"] for img in data["images"] if isinstance(img, dict) and img.get("isCover") and img.get("url")]
                other_imgs = [img["url"] for img in data["images"] if isinstance(img, dict) and not img.get("isCover") and img.get("url")]
                if cover_imgs:
                    image_urls = cover_imgs + other_imgs
            except:
                pass

        return image_urls

    # ─── Product Info — FIXED for BigBuy format ───

    async def _fetch_product_info(self, client: httpx.AsyncClient, product_id: int) -> dict:
        """
        Fetch multilingual product info.
        BigBuy returns a list: [{"id": X, "sku": "...", "name": "...", "description": "...", ...}]
        """
        url = f"{BIGBUY_BASE}/rest/catalog/productinformation/{product_id}.json"
        result = await self._safe_api_call(client, url, max_retries=2)

        if result["status"] != 200 or not result["data"]:
            return {}

        data = result["data"]
        descriptions = {}

        try:
            # BigBuy format: list with one item containing name+description
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Check for isoCode or language field
                        lang = item.get("isoCode", item.get("language", "")).lower()
                        name = item.get("name", "")
                        desc = item.get("description", "")
                        if lang and (name or desc):
                            descriptions[lang] = {"name": name, "description": desc}
                        elif name and not lang:
                            # No language specified, assume Spanish
                            descriptions["es"] = {"name": name, "description": desc}

            # Single dict with name and description
            elif isinstance(data, dict):
                name = data.get("name", "")
                desc = data.get("description", "")
                sku = data.get("sku", "")
                if name:
                    descriptions["es"] = {"name": name, "description": desc}

        except Exception as e:
            logger.error(f"Info parse error for {product_id}: {e}")

        return descriptions

    # ─── Background Enrichment ───

    async def _enrich_all_products(self):
        if self.enrichment_running:
            logger.info("Enrichment already running")
            return

        self.enrichment_running = True
        enriched_count = 0
        images_count = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for i, product in enumerate(self.products_cache):
                    if product.get("enriched"):
                        continue

                    pid = product["id"]

                    # Fetch images
                    try:
                        images = await self._fetch_product_images(client, pid)
                        if images:
                            product["images"] = images
                            product["image_url"] = images[0]
                            images_count += 1
                    except Exception as e:
                        logger.debug(f"Image fetch failed for {pid}: {e}")

                    await asyncio.sleep(3)  # 3s delay between requests

                    # Fetch info
                    try:
                        descriptions = await self._fetch_product_info(client, pid)
                        if descriptions:
                            product["descriptions"] = descriptions
                            # Update name from Spanish or English
                            for lang in ["es", "en", "fr", "de"]:
                                if lang in descriptions and descriptions[lang].get("name"):
                                    product["name"] = descriptions[lang]["name"]
                                    break
                    except Exception as e:
                        logger.debug(f"Info fetch failed for {pid}: {e}")

                    product["enriched"] = True
                    enriched_count += 1

                    await asyncio.sleep(3)  # 3s delay

                    if enriched_count % 5 == 0:
                        logger.info(f"Enriched {enriched_count}/{len(self.products_cache)} — {images_count} with images")

            logger.info(f"ENRICHMENT COMPLETE: {enriched_count} enriched, {images_count} with images")

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
        finally:
            self.enrichment_running = False

    # ─── Format for API ───

    def _format_product(self, p: dict) -> dict:
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

    # ─── API Methods ───

    async def get_current_products(self) -> list:
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
        return {"status": "success", "order": order}

    async def update_inventory_and_prices(self):
        logger.info("Updating inventory...")

    async def remove_unavailable_products(self):
        logger.info("Checking availability...")

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
