"""
PataBot — Product Manager Module
Fetches products from BigBuy API with real images and multilingual descriptions.
Updated: March 2026
"""

import httpx
import asyncio
import os
import logging

logger = logging.getLogger("patabot.products")

BIGBUY_API_KEY = os.getenv("BIGBUY_API_KEY", "")
BIGBUY_BASE = "https://api.bigbuy.eu"


class ProductManager:
    """Manages products: fetch from BigBuy, enrich with images/descriptions, cache."""

    def __init__(self):
        self.products_cache = []
        self.orders = []
        self.enrichment_running = False
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

    # ─── Main Product Fetch ───

    async def fetch_profitable_products(self, max_pages: int = 5, page_size: int = 200) -> dict:
        """Fetch products from BigBuy catalog API with wholesalePrice."""
        all_products = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, max_pages + 1):
                try:
                    url = f"{BIGBUY_BASE}/rest/catalog/products.json"
                    params = {"pageSize": page_size, "page": page}

                    resp = await client.get(url, headers=self.headers, params=params)

                    if resp.status_code == 429:
                        logger.warning(f"Rate limited on page {page}, waiting 5s...")
                        await asyncio.sleep(5)
                        resp = await client.get(url, headers=self.headers, params=params)

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

                    logger.info(f"Page {page}: fetched {len(data)} products")
                    await asyncio.sleep(2.5)

                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}")
                    break

        # Sort by profit and keep top 200
        all_products.sort(key=lambda x: x["profit"], reverse=True)
        self.products_cache = all_products[:200]

        logger.info(f"Total profitable products cached: {len(self.products_cache)}")

        # Start background enrichment
        asyncio.create_task(self._enrich_all_products())

        return {"products": self.products_cache, "count": len(self.products_cache)}

    # ─── Image Enrichment ───

    async def _fetch_product_images(self, client: httpx.AsyncClient, product_id: int) -> list:
        """Fetch images for a single product from BigBuy API."""
        try:
            url = f"{BIGBUY_BASE}/rest/catalog/productimages/{product_id}.json"
            resp = await client.get(url, headers=self.headers)

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
            return []
        except Exception as e:
            logger.debug(f"Error fetching images for {product_id}: {e}")
            return []

    # ─── Multilingual Info ───

    async def _fetch_product_info(self, client: httpx.AsyncClient, product_id: int) -> dict:
        """Fetch multilingual product information from BigBuy API."""
        try:
            url = f"{BIGBUY_BASE}/rest/catalog/productinformation/{product_id}.json"
            resp = await client.get(url, headers=self.headers)

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
                                descriptions[lang] = {"name": name, "description": desc}
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

                    await asyncio.sleep(1.5)

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

                    await asyncio.sleep(1.5)

                    if enriched_count % 10 == 0:
                        logger.info(f"Enriched {enriched_count}/{len(self.products_cache)} products")

            logger.info(f"Enrichment complete: {enriched_count} products enriched")

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
        finally:
            self.enrichment_running = False

    # ─── API Methods (called by main.py) ───

    async def get_current_products(self) -> list:
        """Return cached products for API responses."""
        if not self.products_cache:
            await self.fetch_profitable_products()

        result = []
        for p in self.products_cache[:200]:
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

    async def get_product_count(self) -> int:
        """Return number of cached products."""
        return len(self.products_cache)

    async def get_orders(self) -> list:
        """Return current orders."""
        return self.orders

    async def process_order(self, order_data: dict) -> dict:
        """Process a new order — send to BigBuy."""
        order = {
            "id": len(self.orders) + 1,
            "product_id": order_data.get("product_id"),
            "customer": order_data.get("customer", {}),
            "status": "pending",
            "created_at": __import__("datetime").datetime.now().isoformat()
        }
        self.orders.append(order)
        logger.info(f"New order #{order['id']} created")
        return {"status": "success", "order": order}

    async def update_inventory_and_prices(self):
        """Update inventory and prices from BigBuy."""
        logger.info("Updating inventory and prices...")

    async def remove_unavailable_products(self):
        """Remove products that are no longer available."""
        logger.info("Checking for unavailable products...")

    def get_enrichment_status(self) -> dict:
        """Return enrichment progress."""
        total = len(self.products_cache)
        enriched = sum(1 for p in self.products_cache if p.get("enriched"))
        with_images = sum(1 for p in self.products_cache if p.get("image_url"))

        return {
            "total_products": total,
            "enriched": enriched,
            "with_images": with_images,
            "progress_pct": round((enriched / total * 100) if total > 0 else 0),
            "running": self.enrichment_running
        }
