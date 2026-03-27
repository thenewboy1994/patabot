"""
Product Manager — مدير المنتجات الشامل
Gets products with names, descriptions, images, and prices from BigBuy.
Full dropshipping solution.
"""

import os
import logging
import asyncio
import httpx
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger('PataBot.Products')

BIGBUY_API_URL = "https://api.bigbuy.eu/rest"
BIGBUY_API_KEY = os.environ.get("BIGBUY_API_KEY", "")

MIN_MARGIN = 0.30
MAX_MARGIN = 0.50
TARGET_MARGIN = 0.40


class ProductManager:
    def __init__(self):
        self.products = []
        self.orders = []
        self.headers = {
            "Authorization": f"Bearer {BIGBUY_API_KEY}",
            "Content-Type": "application/json"
        }

    async def fetch_profitable_products(self) -> Dict:
        logger.info("📦 Fetching complete products from BigBuy...")

        if not BIGBUY_API_KEY:
            return {"products": self._demo(), "source": "demo"}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:

                # STEP 1: Get product catalog with prices
                logger.info("📂 Step 1: Getting catalog with prices...")
                all_items = []
                page = 1
                while page <= 5:
                    resp = await client.get(
                        f"{BIGBUY_API_URL}/catalog/products.json",
                        headers=self.headers,
                        params={"pageSize": 200, "page": page}
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(15)
                        continue
                    if resp.status_code != 200:
                        break
                    items = resp.json()
                    if not isinstance(items, list) or not items:
                        break
                    all_items.extend(items)
                    logger.info(f"  Page {page}: {len(items)} products")
                    page += 1
                    await asyncio.sleep(3)

                logger.info(f"✅ Total catalog: {len(all_items)} products")

                # Filter profitable products
                profitable = []
                for item in all_items:
                    cost = item.get('wholesalePrice', 0)
                    if cost and 3 <= cost <= 300:
                        profitable.append(item)

                profitable.sort(key=lambda x: x.get('wholesalePrice', 0), reverse=True)
                profitable = profitable[:200]
                logger.info(f"✅ Profitable products: {len(profitable)}")

                if not profitable:
                    return {"products": self._demo(), "source": "demo", "note": "No profitable products found"}

                # STEP 2: Get product names and descriptions
                logger.info("📝 Step 2: Getting product names & descriptions...")
                product_ids = [p.get('id') for p in profitable if p.get('id')]

                # Get info in batches using taxonomy
                names_map = {}
                descriptions_map = {}

                # Try getting product info for first 50 products individually (with delays)
                fetched_info = 0
                for pid in product_ids[:50]:
                    if fetched_info >= 50:
                        break
                    await asyncio.sleep(1.5)
                    try:
                        r = await client.get(
                            f"{BIGBUY_API_URL}/catalog/productinformation/{pid}.json",
                            headers=self.headers,
                            params={"isoCode": "es"}
                        )
                        if r.status_code == 200:
                            info = r.json()
                            if isinstance(info, list) and info:
                                names_map[pid] = info[0].get('name', '')
                                descriptions_map[pid] = info[0].get('description', '')
                                fetched_info += 1
                            elif isinstance(info, dict):
                                names_map[pid] = info.get('name', '')
                                descriptions_map[pid] = info.get('description', '')
                                fetched_info += 1
                        elif r.status_code == 429:
                            logger.warning("⏳ Rate limited on info. Waiting 10s...")
                            await asyncio.sleep(10)
                        elif r.status_code == 400:
                            # Try without isoCode
                            r2 = await client.get(
                                f"{BIGBUY_API_URL}/catalog/productinformation/{pid}.json",
                                headers=self.headers
                            )
                            if r2.status_code == 200:
                                info = r2.json()
                                if isinstance(info, list) and info:
                                    names_map[pid] = info[0].get('name', '')
                                    descriptions_map[pid] = info[0].get('description', '')
                                    fetched_info += 1
                    except:
                        continue

                logger.info(f"✅ Got names for {len(names_map)} products")

                # STEP 3: Get product images
                logger.info("🖼️ Step 3: Getting product images...")
                images_map = {}
                fetched_imgs = 0

                for pid in product_ids[:50]:
                    if fetched_imgs >= 50:
                        break
                    await asyncio.sleep(1.5)
                    try:
                        r = await client.get(
                            f"{BIGBUY_API_URL}/catalog/productimages/{pid}.json",
                            headers=self.headers
                        )
                        if r.status_code == 200:
                            imgs = r.json()
                            if isinstance(imgs, list):
                                urls = [img.get('url', '') for img in imgs[:5] if img.get('url')]
                                if urls:
                                    images_map[pid] = urls
                                    fetched_imgs += 1
                        elif r.status_code == 429:
                            logger.warning("⏳ Rate limited on images. Waiting 10s...")
                            await asyncio.sleep(10)
                    except:
                        continue

                logger.info(f"✅ Got images for {len(images_map)} products")

                # STEP 4: Build final product list
                logger.info("🔧 Step 4: Building final product list...")
                final_products = []

                for item in profitable:
                    pid = item.get('id')
                    cost = item.get('wholesalePrice', 0)
                    sku = item.get('sku', '')

                    name = names_map.get(pid, sku)
                    description = descriptions_map.get(pid, '')
                    images = images_map.get(pid, [])

                    # Clean description (remove HTML tags simply)
                    if description:
                        import re
                        description = re.sub(r'<[^>]+>', ' ', description)
                        description = ' '.join(description.split())[:500]

                    product = self._build(pid, sku, name, description, cost,
                                         item.get('inShopsQuantity', 1) or 1, images)
                    final_products.append(product)

                final_products.sort(key=lambda p: p['profit'], reverse=True)
                self.products = final_products

                logger.info(f"🎉 TOTAL READY: {len(self.products)} products with details!")

                if self.products:
                    top3 = [(p['name'][:40], f"€{p['cost_price']}→€{p['selling_price']}", f"profit:€{p['profit']}") for p in self.products[:3]]
                    logger.info(f"🏆 Top 3: {top3}")

                return {"products": self.products, "count": len(self.products), "source": "bigbuy",
                        "with_names": len(names_map), "with_images": len(images_map)}

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {"products": self._demo(), "source": "demo", "error": str(e)}

    def _build(self, pid, sku, name, desc, cost, stock, images=None) -> Dict:
        margin = MAX_MARGIN if cost < 15 else (TARGET_MARGIN if cost < 50 else MIN_MARGIN)
        sell = round(cost * (1 + margin), 2)
        return {
            "id": pid, "sku": sku, "name": name or sku,
            "description": desc or "",
            "cost_price": cost, "selling_price": sell,
            "profit": round(sell - cost, 2), "profit_margin": margin,
            "images": images or [], "in_stock": True,
            "stock_quantity": stock, "added_date": datetime.now().isoformat()
        }

    async def update_inventory_and_prices(self):
        logger.info("🔄 Updating inventory...")

    async def remove_unavailable_products(self):
        before = len(self.products)
        self.products = [p for p in self.products if p.get('in_stock')]
        r = before - len(self.products)
        if r: logger.info(f"🗑️ Removed {r}")

    async def get_current_products(self) -> List[Dict]:
        if not self.products: await self.fetch_profitable_products()
        return self.products

    async def get_product_count(self): return len(self.products)

    async def process_order(self, data: Dict) -> Dict:
        order = {"id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                 "customer": data.get("customer", {}), "items": data.get("items", []),
                 "total": data.get("total", 0), "status": "processing",
                 "created_at": datetime.now().isoformat()}
        if BIGBUY_API_KEY:
            r = await self._send_bigbuy(order)
            order["bigbuy_order_id"] = r.get("id")
        self.orders.append(order)
        return {"status": "success", "order": order}

    async def _send_bigbuy(self, order: Dict) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(f"{BIGBUY_API_URL}/order/create.json",
                    headers=self.headers,
                    json={"internalReference": order["id"], "language": "es",
                          "paymentMethod": "moneybox",
                          "carriers": [{"name": "default"}],
                          "shippingAddress": order["customer"],
                          "products": [{"reference": i["sku"], "quantity": i.get("quantity",1)} for i in order["items"]]})
                if r.status_code in [200,201]: return r.json()
        except Exception as e: logger.error(f"❌ Order: {e}")
        return {}

    async def get_orders(self): return self.orders

    def _demo(self) -> List[Dict]:
        return [
            self._build("d1","DEMO-001","Premium Dog Bed","Cama ortopédica premium para perros",25.0,150),
            self._build("d2","DEMO-002","Smart Pet Feeder","Comedero automático WiFi",35.0,80),
            self._build("d3","DEMO-003","LED Night Light","Luz nocturna LED decorativa",8.0,300),
        ]
