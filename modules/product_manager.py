"""
PataBot — Product Manager Module v4
IMAGES FIRST strategy: enrich with images only, skip product info to avoid rate limiting.
Names/descriptions fetched later in a separate pass.
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

    async def _api_get(self, client, url, params=None):
        """Simple API call — returns data or None. No retries (to save rate limit)."""
        try:
            resp = await client.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                logger.warning(f"429 rate limit: {url}")
                return None
            else:
                logger.debug(f"Status {resp.status_code}: {url}")
                return None
        except Exception as e:
            logger.error(f"Error: {url} — {e}")
            return None

    # ─── Fetch Products ───

    async def fetch_profitable_products(self, max_pages=3, page_size=200):
        all_products = []
        errors = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for page in range(1, max_pages + 1):
                url = f"{BIGBUY_BASE}/rest/catalog/products.json"
                data = await self._api_get(client, url, {"pageSize": page_size, "page": page})

                if not data:
                    errors.append(f"Page {page} failed")
                    # Wait and retry once
                    await asyncio.sleep(15)
                    data = await self._api_get(client, url, {"pageSize": page_size, "page": page})
                    if not data:
                        break

                for item in data:
                    wp = item.get("wholesalePrice")
                    if wp and float(wp) > 0:
                        wp = float(wp)
                        m = self._get_margin(wp)
                        sp = round(wp * m, 2)
                        all_products.append({
                            "id": item.get("id"),
                            "sku": item.get("sku", ""),
                            "name": item.get("name", f"Product #{item.get('id')}"),
                            "description": "",
                            "wholesale_price": wp,
                            "selling_price": sp,
                            "old_price": round(sp * 1.23, 2),
                            "profit": round(sp - wp, 2),
                            "margin_pct": round((m - 1) * 100),
                            "category": item.get("category", ""),
                            "images": [],
                            "image_url": "",
                            "descriptions": {},
                            "enriched": False
                        })

                logger.info(f"Page {page}: {len(data)} products")
                if page < max_pages:
                    await asyncio.sleep(5)

        all_products.sort(key=lambda x: x["profit"], reverse=True)
        self.products_cache = all_products[:200]
        self.last_fetch_time = datetime.now().isoformat()
        logger.info(f"Cached {len(self.products_cache)} products")

        # Start IMAGES-ONLY enrichment
        if self.products_cache:
            asyncio.create_task(self._enrich_images_only())

        return {
            "products": [self._fmt(p) for p in self.products_cache[:20]],
            "count": len(self.products_cache),
            "errors": errors,
            "message": f"Fetched {len(self.products_cache)} products. Image enrichment started."
        }

    # ─── IMAGES-ONLY Enrichment (fast, avoids rate limit) ───

    async def _enrich_images_only(self):
        """Fetch ONLY images for each product. One request per product, 3s delay."""
        if self.enrichment_running:
            return
        self.enrichment_running = True
        count = 0
        img_count = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for product in self.products_cache:
                    if product.get("enriched"):
                        continue

                    pid = product["id"]
                    url = f"{BIGBUY_BASE}/rest/catalog/productimages/{pid}.json"
                    data = await self._api_get(client, url)

                    if data:
                        urls = self._parse_images(data)
                        if urls:
                            product["images"] = urls
                            product["image_url"] = urls[0]
                            img_count += 1

                    product["enriched"] = True
                    count += 1

                    # 3 second delay to respect rate limit
                    await asyncio.sleep(3)

                    if count % 10 == 0:
                        logger.info(f"Images: {count}/{len(self.products_cache)} done, {img_count} with images")

            logger.info(f"IMAGE ENRICHMENT DONE: {count} processed, {img_count} with images")

            # After images are done, fetch names in a separate slower pass
            await asyncio.sleep(30)  # Wait 30s before starting names
            await self._enrich_names()

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
        finally:
            self.enrichment_running = False

    def _parse_images(self, data) -> list:
        """Parse BigBuy image response. Format: {"id": X, "images": [{"url": "...", "isCover": true}]}"""
        urls = []
        cover = []
        others = []

        try:
            images_list = None

            if isinstance(data, dict) and "images" in data:
                images_list = data["images"]
            elif isinstance(data, list):
                images_list = data

            if images_list:
                for img in images_list:
                    if isinstance(img, dict) and img.get("url"):
                        u = img["url"]
                        if img.get("isCover"):
                            cover.append(u)
                        else:
                            others.append(u)

            urls = cover + others
        except:
            pass

        return urls

    # ─── Names Enrichment (separate slower pass) ───

    async def _enrich_names(self):
        """Fetch product names/descriptions — slower pass with 5s delays."""
        logger.info("Starting names enrichment (slow pass)...")
        count = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for product in self.products_cache:
                    if product.get("descriptions"):
                        continue  # Already has names

                    pid = product["id"]
                    url = f"{BIGBUY_BASE}/rest/catalog/productinformation/{pid}.json"
                    data = await self._api_get(client, url)

                    if data:
                        descs = self._parse_info(data)
                        if descs:
                            product["descriptions"] = descs
                            for lang in ["es", "en", "fr", "de"]:
                                if lang in descs and descs[lang].get("name"):
                                    product["name"] = descs[lang]["name"]
                                    break
                            count += 1

                    # 5 second delay — very conservative
                    await asyncio.sleep(5)

                    if count % 10 == 0 and count > 0:
                        logger.info(f"Names: {count} products updated")

            logger.info(f"NAMES ENRICHMENT DONE: {count} names updated")
        except Exception as e:
            logger.error(f"Names enrichment error: {e}")

    def _parse_info(self, data) -> dict:
        """Parse BigBuy product info response."""
        descs = {}
        try:
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        lang = item.get("isoCode", item.get("language", "")).lower()
                        name = item.get("name", "")
                        desc = item.get("description", "")
                        if lang and (name or desc):
                            descs[lang] = {"name": name, "description": desc}
                        elif name:
                            descs["es"] = {"name": name, "description": desc}
            elif isinstance(data, dict) and data.get("name"):
                descs["es"] = {"name": data["name"], "description": data.get("description", "")}
        except:
            pass
        return descs

    # ─── Format ───

    def _fmt(self, p):
        return {
            "id": p["id"], "sku": p["sku"], "name": p["name"],
            "description": p.get("description", ""),
            "selling_price": p["selling_price"], "old_price": p["old_price"],
            "profit": p["profit"], "margin_pct": p["margin_pct"],
            "image_url": p.get("image_url", ""), "images": p.get("images", []),
            "descriptions": p.get("descriptions", {}),
            "enriched": p.get("enriched", False), "category": p.get("category", "")
        }

    # ─── API Methods ───

    async def get_current_products(self):
        if not self.products_cache:
            await self.fetch_profitable_products(max_pages=2)
        return [self._fmt(p) for p in self.products_cache[:200]]

    async def get_product_count(self):
        return len(self.products_cache)

    async def get_orders(self):
        return self.orders

    async def process_order(self, data):
        order = {"id": len(self.orders)+1, "product_id": data.get("product_id"),
                 "customer": data.get("customer",{}), "status": "pending",
                 "created_at": datetime.now().isoformat()}
        self.orders.append(order)
        return {"status": "success", "order": order}

    async def update_inventory_and_prices(self):
        pass

    async def remove_unavailable_products(self):
        pass

    def get_enrichment_status(self):
        total = len(self.products_cache)
        enriched = sum(1 for p in self.products_cache if p.get("enriched"))
        with_images = sum(1 for p in self.products_cache if p.get("image_url"))
        with_names = sum(1 for p in self.products_cache if p.get("descriptions"))
        return {
            "total_products": total, "enriched": enriched,
            "with_images": with_images, "with_names": with_names,
            "progress_pct": round((enriched/total*100) if total > 0 else 0),
            "running": self.enrichment_running, "last_fetch": self.last_fetch_time
        }
