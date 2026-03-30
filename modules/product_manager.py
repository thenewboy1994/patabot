"""
PataBot — Product Manager v6 FINAL
- JSON persistence (survives restarts)
- Fetches up to 1000 products from BigBuy
- Catalog API with pagination, search, filter, sort
- Reliable image/name enrichment (each product matches its own images)
"""

import httpx
import asyncio
import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("patabot.products")

BIGBUY_API_KEY = os.getenv("BIGBUY_API_KEY", "")
BIGBUY_BASE = "https://api.bigbuy.eu"
CACHE_FILE = Path("products_cache.json")


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
        self._load_from_file()

    # ─── Persistence ───

    def _load_from_file(self):
        """Load products from JSON cache file (survives process restarts)."""
        try:
            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                self.products_cache = data.get("products", [])
                self.last_fetch_time = data.get("last_fetch_time")
                logger.info(f"Loaded {len(self.products_cache)} products from cache file")
        except Exception as e:
            logger.error(f"Cache load error: {e}")

    def _save_to_file(self):
        """Save products to JSON cache file."""
        try:
            data = {
                "products": self.products_cache,
                "last_fetch_time": self.last_fetch_time,
                "saved_at": datetime.now().isoformat()
            }
            CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            logger.info(f"Saved {len(self.products_cache)} products to cache file")
        except Exception as e:
            logger.error(f"Cache save error: {e}")

    # ─── Helpers ───

    def _get_margin(self, price):
        if price < 15:
            return 1.50
        elif price <= 50:
            return 1.40
        else:
            return 1.30

    async def _api_get(self, client, url, params=None):
        try:
            resp = await client.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                logger.warning(f"429 Rate Limited: {url} — waiting 30s")
                await asyncio.sleep(30)
                resp2 = await client.get(url, headers=self.headers, params=params)
                if resp2.status_code == 200:
                    return resp2.json()
            return None
        except Exception as e:
            logger.error(f"API error: {url} — {e}")
            return None

    # ─── Fetch Products from BigBuy ───

    async def fetch_profitable_products(self, max_pages=10, page_size=200):
        """Fetch products from BigBuy. max_pages=5, page_size=200 = up to 1000 products."""
        all_products = []
        errors = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for page in range(1, max_pages + 1):
                url = f"{BIGBUY_BASE}/rest/catalog/products.json"
                data = await self._api_get(client, url, {"pageSize": page_size, "page": page})
                if not data:
                    errors.append(f"Page {page} failed")
                    break

                for item in data:
                    wp = item.get("wholesalePrice")
                    if not wp or float(wp) <= 0:
                        continue
                    wp = float(wp)

                    # ── Dropshipping price filter ──
                    # Only products €2–€80 wholesale are good for this store.
                    # Avoids electronics, appliances, luxury items (>€80).
                    # Avoids items too cheap to be worth selling (<€2).
                    if wp < 2.0 or wp > 80.0:
                        continue

                    m = self._get_margin(wp)
                    sp = round(wp * m, 2)
                    pid = item.get("id")

                    # Preserve existing enrichment data if product already in cache
                    existing = next((p for p in self.products_cache if p["id"] == pid), None)
                    if existing:
                        existing["wholesale_price"] = wp
                        existing["selling_price"] = sp
                        existing["old_price"] = round(sp * 1.23, 2)
                        existing["profit"] = round(sp - wp, 2)
                        all_products.append(existing)
                    else:
                        all_products.append({
                            "id": pid,
                            "sku": item.get("sku", ""),
                            "name": item.get("name", f"Producto #{pid}"),
                            "description": "",
                            "wholesale_price": wp,
                            "selling_price": sp,
                            "old_price": round(sp * 1.23, 2),
                            "profit": round(sp - wp, 2),
                            "margin_pct": round((m - 1) * 100),
                            "category": str(item.get("category", "")),
                            "images": [],
                            "image_url": "",
                            "descriptions": {},
                            "has_images": False,
                            "has_names": False
                        })

                logger.info(f"Page {page}: {len(data)} products fetched")
                if len(data) < page_size:
                    break  # Last page
                if page < max_pages:
                    await asyncio.sleep(3)

        # Sort by margin % first (best deal for customer), then by selling price
        # This puts affordable high-margin products first — ideal for dropshipping
        all_products.sort(key=lambda x: (x["margin_pct"], -x["selling_price"]), reverse=True)
        self.products_cache = all_products[:2000]  # Keep up to 2000 products
        self.last_fetch_time = datetime.now().isoformat()
        self._save_to_file()
        logger.info(f"Cached {len(self.products_cache)} products total")

        # Start enrichment after 5 minute delay (let rate limit reset)
        asyncio.create_task(self._delayed_enrichment(300))

        return {
            "status": "success",
            "count": len(self.products_cache),
            "errors": errors,
            "message": f"Fetched {len(self.products_cache)} products. Image enrichment starts in 5 minutes."
        }

    # ─── Enrichment ───

    async def _delayed_enrichment(self, delay_seconds):
        logger.info(f"Enrichment scheduled in {delay_seconds}s...")
        await asyncio.sleep(delay_seconds)
        await self._enrich_products()

    async def _enrich_products(self):
        """Enrich products with real images and names from BigBuy API.
        Each product ID fetches its OWN images — no mixing."""
        if self.enrichment_running:
            logger.info("Enrichment already running, skipping")
            return
        self.enrichment_running = True
        img_count = 0
        name_count = 0

        try:
            # Enrich all products that still need images (up to 1000)
            to_enrich = [p for p in self.products_cache[:1000] if not p.get("has_images")]
            logger.info(f"Enriching {len(to_enrich)} products...")

            async with httpx.AsyncClient(timeout=30.0) as client:
                for i, product in enumerate(to_enrich):
                    pid = product["id"]  # Use THIS product's ID for its images

                    # Fetch THIS product's images
                    img_data = await self._api_get(
                        client,
                        f"{BIGBUY_BASE}/rest/catalog/productimages/{pid}.json"
                    )
                    if img_data:
                        urls = self._parse_images(img_data)
                        if urls:
                            product["images"] = urls
                            product["image_url"] = urls[0]  # Cover image first
                            product["has_images"] = True
                            img_count += 1

                    await asyncio.sleep(2)

                    # Fetch THIS product's name and description
                    if not product.get("has_names"):
                        info_data = await self._api_get(
                            client,
                            f"{BIGBUY_BASE}/rest/catalog/productinformation/{pid}.json"
                        )
                        if info_data:
                            descs = self._parse_info(info_data)
                            if descs:
                                product["descriptions"] = descs
                                product["has_names"] = True
                                for lang in ["es", "en", "fr", "de"]:
                                    if lang in descs and descs[lang].get("name"):
                                        product["name"] = descs[lang]["name"]
                                        if descs[lang].get("description"):
                                            product["description"] = descs[lang]["description"][:500]
                                        break
                                name_count += 1
                        await asyncio.sleep(3)

                    if (i + 1) % 20 == 0:
                        logger.info(f"Enrichment: {i+1}/{len(to_enrich)} | Images: {img_count} | Names: {name_count}")
                        self._save_to_file()  # Save progress every 20 products

            logger.info(f"ENRICHMENT COMPLETE: {img_count} images, {name_count} names")
            self._save_to_file()

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
            self._save_to_file()  # Save whatever we got
        finally:
            self.enrichment_running = False

    async def run_enrichment(self):
        """Manually trigger enrichment via API."""
        if not self.products_cache:
            return {"error": "No products cached. Call /api/products/fetch first."}
        if self.enrichment_running:
            return {"status": "Already running", "progress": self.get_enrichment_status()}
        missing_images = sum(1 for p in self.products_cache if not p.get("has_images"))
        asyncio.create_task(self._enrich_products())
        return {
            "status": "Enrichment started",
            "products_missing_images": missing_images,
            "total": len(self.products_cache)
        }

    # ─── Image & Name Parsers ───

    def _parse_images(self, data):
        """Parse BigBuy productimages response. Returns URLs, cover image first."""
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
        except Exception:
            pass
        return cover + others

    def _parse_info(self, data):
        """Parse BigBuy productinformation response. Returns {lang_code: {name, description}}."""
        descs = {}
        try:
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        lang = item.get("isoCode", item.get("language", "")).lower()[:2]
                        name = item.get("name", "").strip()
                        desc = item.get("description", "").strip()
                        if lang and (name or desc):
                            descs[lang] = {"name": name, "description": desc}
            elif isinstance(data, dict) and data.get("name"):
                descs["es"] = {"name": data["name"], "description": data.get("description", "")}
        except Exception:
            pass
        return descs

    # ─── Catalog API ───

    async def get_catalog(self, page=1, limit=48, category="", search="", sort="profit", min_price=0, max_price=99999):
        """Paginated catalog with filtering and sorting."""
        products = [self._fmt(p) for p in self.products_cache]

        # Apply filters
        if category and category != "all":
            products = [p for p in products if p.get("category") == category]

        if search:
            s = search.lower()
            products = [p for p in products if
                        s in p["name"].lower() or
                        s in p.get("description", "").lower()]

        products = [p for p in products if min_price <= p["selling_price"] <= max_price]

        # Apply sort
        if sort == "price_asc":
            products.sort(key=lambda x: x["selling_price"])
        elif sort == "price_desc":
            products.sort(key=lambda x: x["selling_price"], reverse=True)
        elif sort == "newest":
            products.sort(key=lambda x: x["id"], reverse=True)
        else:  # profit (default — most profitable first)
            products.sort(key=lambda x: x["profit"], reverse=True)

        total = len(products)
        start = (page - 1) * limit
        end = start + limit
        pages = max(1, (total + limit - 1) // limit)

        return {
            "products": products[start:end],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": pages
        }

    async def get_categories(self):
        """Get all categories with product counts."""
        cats = {}
        for p in self.products_cache:
            cat = p.get("category", "")
            if cat:
                cats[cat] = cats.get(cat, 0) + 1
        return [{"id": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:50]]

    async def get_product_by_id(self, product_id):
        """Get a single product by ID."""
        for p in self.products_cache:
            if p["id"] == product_id:
                return self._fmt(p)
        return None

    # ─── Formatting ───

    def _fmt(self, p):
        return {
            "id": p["id"],
            "sku": p.get("sku", ""),
            "name": p["name"],
            "description": p.get("description", ""),
            "selling_price": p["selling_price"],
            "old_price": p["old_price"],
            "profit": p["profit"],
            "margin_pct": p.get("margin_pct", 30),
            "image_url": p.get("image_url", ""),
            "images": p.get("images", []),
            "descriptions": p.get("descriptions", {}),
            "enriched": p.get("has_images", False),
            "category": p.get("category", ""),
        }

    # ─── Standard Endpoints ───

    async def get_current_products(self):
        if not self.products_cache:
            await self.fetch_profitable_products(max_pages=3)
        return [self._fmt(p) for p in self.products_cache[:200]]

    async def get_product_count(self):
        return len(self.products_cache)

    async def get_orders(self):
        return self.orders

    async def process_order(self, data):
        order = {
            "id": len(self.orders) + 1,
            "product_id": data.get("product_id"),
            "customer": data.get("customer", {}),
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
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
            "progress_pct": round((with_images / total * 100) if total > 0 else 0),
            "running": self.enrichment_running,
            "last_fetch": self.last_fetch_time
        }
