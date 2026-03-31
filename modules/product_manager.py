"""
PataBot — Product Manager v7.0
- Fixed _parse_info() with proper language code normalization
- Fixed _enrich_products() to re-fetch descriptions for single-language products
- Added run_re_enrich_descriptions() to force re-fetch multilingual descriptions
- Added detailed logging to diagnose BigBuy language data
- All other features from v6.1 preserved
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

# Map of full language names → 2-letter ISO code
_LANG_NAME_MAP = {
    'español': 'es', 'spanish': 'es', 'espanol': 'es', 'castellano': 'es',
    'english': 'en', 'inglés': 'en', 'ingles': 'en', 'anglais': 'en',
    'français': 'fr', 'french': 'fr', 'frances': 'fr', 'francais': 'fr',
    'deutsch': 'de', 'german': 'de', 'alemán': 'de', 'aleman': 'de',
    'nederlands': 'nl', 'dutch': 'nl', 'holandés': 'nl', 'holandes': 'nl',
    'italiano': 'it', 'italian': 'it',
    'português': 'pt', 'portuguese': 'pt', 'portugues': 'pt',
    'polski': 'pl', 'polish': 'pl', 'polaco': 'pl',
    'català': 'ca', 'catalan': 'ca', 'catalán': 'ca',
    'русский': 'ru', 'russian': 'ru',
    'العربية': 'ar', 'arabic': 'ar',
    'svenska': 'sv', 'swedish': 'sv',
    'dansk': 'da', 'danish': 'da',
    'norsk': 'no', 'norwegian': 'no',
    'suomi': 'fi', 'finnish': 'fi',
}


class ProductManager:

    def __init__(self):
        self.products_cache = []
        self.orders = []
        self.enrichment_running = False
        self.last_fetch_time = None
        self.category_names = {}
        self.headers = {
            "Authorization": f"Bearer {BIGBUY_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self._load_from_file()

    # ─── Persistence ───

    def _load_from_file(self):
        try:
            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                self.products_cache = data.get("products", [])
                self.last_fetch_time = data.get("last_fetch_time")
                self.category_names = data.get("category_names", {})
                logger.info(f"Loaded {len(self.products_cache)} products from cache file")
        except Exception as e:
            logger.error(f"Cache load error: {e}")

    def _save_to_file(self):
        try:
            data = {
                "products": self.products_cache,
                "last_fetch_time": self.last_fetch_time,
                "category_names": self.category_names,
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

    async def _api_get(self, client, url, params=None, retries=3):
        for attempt in range(retries):
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    wait = 900 if attempt == 0 else 300
                    logger.warning(f"429 Rate Limited (attempt {attempt+1}/{retries}) — waiting {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.warning(f"HTTP {resp.status_code}: {url}")
                return None
            except Exception as e:
                logger.error(f"API error: {url} — {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(10)
        return None

    # ─── Language Code Normalization ───

    @staticmethod
    def _normalize_lang(raw):
        """Normalize any language identifier to 2-letter ISO code."""
        if not raw:
            return ''
        s = str(raw).strip()
        lower = s.lower()

        # Direct match in map
        if lower in _LANG_NAME_MAP:
            return _LANG_NAME_MAP[lower]

        # ISO locale like "es-ES", "en-GB", "nl_NL", "fr_FR"
        if len(s) >= 4 and s[2] in '-_':
            return s[:2].lower()

        # Plain 2-letter ISO code
        if len(s) == 2:
            return lower

        # Try removing accents for names like "Català" → "catala"
        try:
            import unicodedata
            normalized = unicodedata.normalize('NFD', lower)
            no_accent = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
            if no_accent in _LANG_NAME_MAP:
                return _LANG_NAME_MAP[no_accent]
        except Exception:
            pass

        # Fallback: first 2 chars
        return lower[:2] if len(lower) >= 2 else lower

    # ─── Taxonomy Names ───

    async def _fetch_taxonomy_names(self, client):
        data = await self._api_get(client, f"{BIGBUY_BASE}/rest/catalog/taxonomies.json")
        if data and isinstance(data, list) and len(data) > 0:
            for item in data:
                tid = str(item.get("id", ""))
                name = item.get("name", "").strip()
                if tid and name:
                    self.category_names[tid] = name
            logger.info(f"Loaded {len(self.category_names)} taxonomy names from BigBuy")
        else:
            data2 = await self._api_get(client, f"{BIGBUY_BASE}/rest/catalog/categories.json",
                                        params={"pageSize": 200})
            if data2 and isinstance(data2, list):
                for item in data2:
                    cid = str(item.get("id", ""))
                    name = item.get("name", "").strip()
                    if cid and name:
                        self.category_names[cid] = name
                logger.info(f"Loaded {len(self.category_names)} category names from BigBuy")

    # ─── Fetch Products from BigBuy ───

    async def fetch_profitable_products(self, max_pages=10, page_size=200):
        all_products = []
        errors = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            if not self.category_names:
                await self._fetch_taxonomy_names(client)
                await asyncio.sleep(2)

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

                    if wp < 2.0 or wp > 80.0:
                        continue

                    m = self._get_margin(wp)
                    sp = round(wp * m, 2)
                    pid = item.get("id")

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
                    break
                if page < max_pages:
                    await asyncio.sleep(3)

        all_products.sort(key=lambda x: (x["margin_pct"], -x["selling_price"]), reverse=True)
        self.products_cache = all_products[:2000]
        self.last_fetch_time = datetime.now().isoformat()
        self._save_to_file()
        logger.info(f"Cached {len(self.products_cache)} products total")

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
        if self.enrichment_running:
            logger.info("Enrichment already running, skipping")
            return
        self.enrichment_running = True
        img_count = 0
        name_count = 0

        try:
            # PASS 1: Products without images (fetch images + descriptions)
            need_images = [p for p in self.products_cache[:1000] if not p.get("has_images")]

            # PASS 2: Products WITH images but missing multilingual descriptions
            # (only Spanish or no descriptions at all)
            need_descriptions = [
                p for p in self.products_cache[:1000]
                if p.get("has_images") and (
                    not p.get("has_names") or
                    len(p.get("descriptions", {})) <= 1
                )
            ]

            logger.info(
                f"Enrichment: {len(need_images)} need images, "
                f"{len(need_descriptions)} need multilingual descriptions"
            )

            async with httpx.AsyncClient(timeout=30.0) as client:

                # PASS 1 — Fetch images + descriptions for products without images
                for i, product in enumerate(need_images):
                    pid = product["id"]

                    img_data = await self._api_get(
                        client, f"{BIGBUY_BASE}/rest/catalog/productimages/{pid}.json"
                    )
                    if img_data:
                        urls = self._parse_images(img_data)
                        if urls:
                            product["images"] = urls
                            product["image_url"] = urls[0]
                            product["has_images"] = True
                            img_count += 1

                    await asyncio.sleep(2)

                    if not product.get("has_names"):
                        fetched = await self._fetch_product_info(client, product)
                        if fetched:
                            name_count += 1
                        await asyncio.sleep(3)

                    if (i + 1) % 20 == 0:
                        logger.info(
                            f"Pass1: {i+1}/{len(need_images)} | "
                            f"Images: {img_count} | Names: {name_count}"
                        )
                        self._save_to_file()

                # PASS 2 — Fetch multilingual descriptions for single-language products
                for i, product in enumerate(need_descriptions):
                    fetched = await self._fetch_product_info(client, product, force=True)
                    if fetched:
                        name_count += 1
                    await asyncio.sleep(3)

                    if (i + 1) % 20 == 0:
                        logger.info(
                            f"Pass2: {i+1}/{len(need_descriptions)} | Names: {name_count}"
                        )
                        self._save_to_file()

            logger.info(f"ENRICHMENT COMPLETE: {img_count} images, {name_count} descriptions")
            self._save_to_file()

        except Exception as e:
            logger.error(f"Enrichment error: {e}")
            self._save_to_file()
        finally:
            self.enrichment_running = False

    async def _fetch_product_info(self, client, product, force=False):
        """Fetch multilingual product info from BigBuy for a single product."""
        pid = product["id"]
        if product.get("has_names") and not force:
            return False

        info_data = await self._api_get(
            client, f"{BIGBUY_BASE}/rest/catalog/productinformation/{pid}.json"
        )
        if not info_data:
            return False

        # Log what BigBuy returns so we can diagnose language availability
        if isinstance(info_data, list):
            raw_langs = [
                item.get("isoCode", item.get("language", "?"))
                for item in info_data if isinstance(item, dict)
            ]
            logger.info(f"Product {pid} — BigBuy returned {len(info_data)} languages: {raw_langs}")
        else:
            logger.info(f"Product {pid} — BigBuy returned dict (single lang)")

        descs = self._parse_info(info_data)
        logger.info(f"Product {pid} — parsed languages: {list(descs.keys())}")

        if descs:
            product["descriptions"] = descs
            product["has_names"] = True
            # Set best available name + description on the product
            for lang in ["es", "en", "fr", "de", "it", "nl", "pt"]:
                if lang in descs and descs[lang].get("name"):
                    product["name"] = descs[lang]["name"]
                    if descs[lang].get("description"):
                        product["description"] = descs[lang]["description"][:500]
                    break
            return True
        return False

    async def run_enrichment(self):
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

    async def run_re_enrich_descriptions(self):
        """Force re-fetch descriptions for products that only have 1 language (usually Spanish only)."""
        if not self.products_cache:
            return {"error": "No products cached. Call /api/products/fetch first."}
        if self.enrichment_running:
            return {"status": "Enrichment already running", "progress": self.get_enrichment_status()}

        # Reset has_names for products with <= 1 language so enrichment will re-fetch them
        reset_count = 0
        for p in self.products_cache:
            if len(p.get("descriptions", {})) <= 1:
                p["has_names"] = False
                reset_count += 1

        logger.info(f"Re-enrich descriptions: reset {reset_count} products")
        asyncio.create_task(self._enrich_products())
        return {
            "status": "Re-enrichment started",
            "products_reset": reset_count,
            "total": len(self.products_cache),
            "message": f"Re-fetching descriptions for {reset_count} products. Check /api/products/enrichment-status."
        }

    # ─── Image & Name Parsers ───

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
        except Exception:
            pass
        return cover + others

    def _parse_info(self, data):
        """Parse BigBuy productinformation response into {lang: {name, description}} dict."""
        descs = {}
        try:
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    # BigBuy uses "isoCode" or "language" field
                    raw_lang = item.get("isoCode", item.get("language", item.get("lang", "")))
                    lang = self._normalize_lang(raw_lang)
                    name = item.get("name", "").strip()
                    desc = item.get("description", "").strip()
                    # Only store if we have valid 2-letter lang code and at least name or description
                    if lang and len(lang) == 2 and (name or desc):
                        descs[lang] = {"name": name, "description": desc}

            elif isinstance(data, dict):
                # Check if it's structured as {lang_code: {name, description}, ...}
                for key, val in data.items():
                    if isinstance(val, dict) and len(str(key)) == 2:
                        lang = str(key).lower()
                        name = val.get("name", "").strip()
                        desc = val.get("description", "").strip()
                        if name or desc:
                            descs[lang] = {"name": name, "description": desc}

                # If no language keys found, treat as single Spanish dict
                if not descs and data.get("name"):
                    descs["es"] = {
                        "name": data["name"],
                        "description": data.get("description", "")
                    }

        except Exception as e:
            logger.debug(f"_parse_info error: {e}")
        return descs

    # ─── Catalog API ───

    async def get_catalog(self, page=1, limit=48, category="", search="", sort="profit", min_price=0, max_price=99999):
        # Only show products with images — visitors never see incomplete products
        products = [self._fmt(p) for p in self.products_cache if p.get("has_images")]

        if category and category != "all":
            products = [p for p in products if p.get("category") == category]

        if search:
            s = search.lower()
            products = [p for p in products if
                        s in p["name"].lower() or
                        s in p.get("description", "").lower()]

        products = [p for p in products if min_price <= p["selling_price"] <= max_price]

        if sort == "price_asc":
            products.sort(key=lambda x: x["selling_price"])
        elif sort == "price_desc":
            products.sort(key=lambda x: x["selling_price"], reverse=True)
        elif sort == "newest":
            products.sort(key=lambda x: x["id"], reverse=True)
        else:
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
        cats = {}
        for p in self.products_cache:
            cat = p.get("category", "")
            if cat:
                cats[cat] = cats.get(cat, 0) + 1
        return [
            {
                "id": k,
                "name": self.category_names.get(k, ""),
                "count": v
            }
            for k, v in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:50]
        ]

    async def get_product_by_id(self, product_id):
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
        # Only return enriched products (with images) to the homepage
        enriched = [self._fmt(p) for p in self.products_cache if p.get("has_images")]
        return enriched[:200]

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
        multilingual = sum(1 for p in self.products_cache if len(p.get("descriptions", {})) > 1)
        return {
            "total_products": total,
            "with_images": with_images,
            "with_names": with_names,
            "multilingual_descriptions": multilingual,
            "progress_pct": round((with_images / total * 100) if total > 0 else 0),
            "running": self.enrichment_running,
            "last_fetch": self.last_fetch_time
        }
