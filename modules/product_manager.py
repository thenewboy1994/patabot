"""
PataBot — Product Manager v5 FINAL
Images-first strategy with proper retry logic.
Only marks products as enriched when images are actually found.
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

    def _get_margin(self, price):
        if price < 15: return 1.50
        elif price <= 50: return 1.40
        else: return 1.30

    async def _api_get(self, client, url, params=None):
        try:
            resp = await client.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                logger.warning(f"429: {url}")
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
                    await asyncio.sleep(15)
                    data = await self._api_get(client, url, {"pageSize": page_size, "page": page})
                    if not data:
                        errors.append(f"Page {page} failed")
                        break

                for item in data:
                    wp = item.get("wholesalePrice")
                    if wp and float(wp) > 0:
                        wp = float(wp)
                        m = self._get_margin(wp)
                        sp = round(wp * m, 2)
                        all_products.append({
                            "id": item.get("id"), "sku": item.get("sku", ""),
                            "name": item.get("name", f"Product #{item.get('id')}"),
                            "description": "", "wholesale_price": wp,
                            "selling_price": sp, "old_price": round(sp * 1.23, 2),
                            "profit": round(sp - wp, 2), "margin_pct": round((m-1)*100),
                            "category": item.get("category", ""),
                            "images": [], "image_url": "",
                            "descriptions": {}, "has_images": False, "has_names": False
                        })
                logger.info(f"Page {page}: {len(data)} products")
                if page < max_pages:
                    await asyncio.sleep(5)

        all_products.sort(key=lambda x: x["profit"], reverse=True)
        self.products_cache = all_products[:200]
        self.last_fetch_time = datetime.now().isoformat()
        logger.info(f"Cached {len(self.products_cache)} products")

        # Delay enrichment 5 minutes to let rate limit reset
        asyncio.create_task(self._delayed_enrichment(300))

        return {
            "products": [self._fmt(p) for p in self.products_cache[:20]],
            "count": len(self.products_cache), "errors": errors,
            "message": f"Fetched {len(self.products_cache)} products. Image enrichment will start in 5 minutes."
        }

    async def _delayed_enrichment(self, delay_seconds):
        """Wait then start enrichment to avoid rate limiting."""
        logger.info(f"Enrichment scheduled in {delay_seconds}s...")
        await asyncio.sleep(delay_seconds)
        await self._enrich_images_only()

    # ─── Image Enrichment ───

    async def _enrich_images_only(self):
        if self.enrichment_running:
            return
        self.enrichment_running = True
        img_count = 0
        processed = 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for product in self.products_cache:
                    if product.get("has_images"):
                        continue

                    pid = product["id"]
                    url = f"{BIGBUY_BASE}/rest/catalog/productimages/{pid}.json"
                    data = await self._api_get(client, url)

                    if data:
                        urls = self._parse_images(data)
                        if urls:
                            product["images"] = urls
                            product["image_url"] = urls[0]
                            product["has_images"] = True
                            img_count += 1
                    # If 429, don't mark as has_images — will retry next time

                    processed += 1
                    await asyncio.sleep(3)

                    if processed % 10 == 0:
                        logger.info(f"Images: {processed}/{len(self.products_cache)}, {img_count} successful")

            logger.info(f"IMAGE ENRICHMENT: {img_count}/{processed} with images")

            # Now fetch names (slower)
            if img_count > 0:
                await asyncio.sleep(60)
                await self._enrich_names()

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
        finally:
            self.enrichment_running = False

    # ─── Manual Enrich (called from /api/products/enrich) ───

    async def run_enrichment(self):
        """Manually trigger enrichment for products missing images."""
        if not self.products_cache:
            return {"error": "No products cached. Call /api/products/fetch first."}
        if self.enrichment_running:
            return {"status": "Already running", "progress": self.get_enrichment_status()}

        missing = sum(1 for p in self.products_cache if not p.get("has_images"))
        asyncio.create_task(self._enrich_images_only())
        return {
            "status": "Enrichment started",
            "products_missing_images": missing,
            "total": len(self.products_cache)
        }

    def _parse_images(self, data):
        cover = []
        others = []
        try:
            imgs = None
            if isinstance(data, dict) and "images" in data:
                imgs = data["images"]
            elif isinstance(data, list):
                imgs = data
            if imgs:
                for img in imgs:
                    if isinstance(img, dict) and img.get("url"):
                        if img.get("isCover"):
                            cover.append(img["url"])
                        else:
                            others.append(img["url"])
        except:
            pass
        return cover + others

    # ─── Names ───

    async def _enrich_names(self):
        logger.info("Starting names enrichment...")
        count = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for product in self.products_cache:
                    if product.get("has_names"):
                        continue
                    pid = product["id"]
                    url = f"{BIGBUY_BASE}/rest/catalog/productinformation/{pid}.json"
                    data = await self._api_get(client, url)
                    if data:
                        descs = self._parse_info(data)
                        if descs:
                            product["descriptions"] = descs
                            product["has_names"] = True
                            for lang in ["es","en","fr","de"]:
                                if lang in descs and descs[lang].get("name"):
                                    product["name"] = descs[lang]["name"]
                                    break
                            count += 1
                    await asyncio.sleep(5)
                    if count % 10 == 0 and count > 0:
                        logger.info(f"Names: {count} updated")
            logger.info(f"NAMES DONE: {count}")
        except Exception as e:
            logger.error(f"Names error: {e}")

    def _parse_info(self, data):
        descs = {}
        try:
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        lang = item.get("isoCode", item.get("language","")).lower()
                        name = item.get("name","")
                        desc = item.get("description","")
                        if lang and (name or desc):
                            descs[lang] = {"name": name, "description": desc}
                        elif name:
                            descs["es"] = {"name": name, "description": desc}
            elif isinstance(data, dict) and data.get("name"):
                descs["es"] = {"name": data["name"], "description": data.get("description","")}
        except:
            pass
        return descs

    # ─── Format & API ───

    def _fmt(self, p):
        return {
            "id": p["id"], "sku": p["sku"], "name": p["name"],
            "description": p.get("description",""),
            "selling_price": p["selling_price"], "old_price": p["old_price"],
            "profit": p["profit"], "margin_pct": p["margin_pct"],
            "image_url": p.get("image_url",""), "images": p.get("images",[]),
            "descriptions": p.get("descriptions",{}),
            "enriched": p.get("has_images", False), "category": p.get("category","")
        }

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
        with_images = sum(1 for p in self.products_cache if p.get("has_images"))
        with_names = sum(1 for p in self.products_cache if p.get("has_names"))
        return {
            "total_products": total,
            "with_images": with_images,
            "with_names": with_names,
            "progress_pct": round((with_images/total*100) if total > 0 else 0),
            "running": self.enrichment_running,
            "last_fetch": self.last_fetch_time
        }
