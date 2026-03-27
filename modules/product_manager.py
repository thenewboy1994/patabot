"""
Product Manager — مدير المنتجات
Gets products from BigBuy with prices included in product data.
No separate price endpoint needed!
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
        logger.info("📦 Fetching products from BigBuy...")

        if not BIGBUY_API_KEY:
            return {"products": self._demo(), "source": "demo"}

        all_products = []

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                page = 1
                total_fetched = 0

                while page <= 5:
                    logger.info(f"📂 Fetching page {page}...")
                    resp = await client.get(
                        f"{BIGBUY_API_URL}/catalog/products.json",
                        headers=self.headers,
                        params={"pageSize": 200, "page": page}
                    )

                    if resp.status_code == 429:
                        logger.warning("⏳ Rate limited. Waiting 15s...")
                        await asyncio.sleep(15)
                        continue

                    if resp.status_code != 200:
                        logger.error(f"❌ Page {page}: {resp.status_code}")
                        break

                    items = resp.json()
                    if not isinstance(items, list) or not items:
                        break

                    total_fetched += len(items)
                    logger.info(f"  Got {len(items)} products")

                    for item in items:
                        cost = item.get('wholesalePrice', 0)
                        stock = item.get('inShopsQuantity', 0)
                        active = item.get('active', 0)

                        if not cost or cost < 5 or cost > 200:
                            continue
                        if stock <= 0:
                            continue
                        if not active:
                            continue

                        product = self._build(
                            item.get('id'),
                            item.get('sku', ''),
                            item.get('sku', f"Product-{item.get('id')}"),
                            "",
                            cost,
                            stock
                        )
                        all_products.append(product)

                    page += 1
                    await asyncio.sleep(3)

                all_products.sort(key=lambda p: p['profit'], reverse=True)
                self.products = all_products[:200]

                logger.info(f"✅ Total fetched: {total_fetched}, Profitable: {len(self.products)}")

                if self.products:
                    top3 = [(p['sku'], p['cost_price'], p['selling_price'], p['profit']) for p in self.products[:3]]
                    logger.info(f"🏆 Top 3: {top3}")
                    return {"products": self.products, "count": len(self.products), "source": "bigbuy"}
                else:
                    return {"products": self._demo(), "source": "demo",
                            "total_fetched": total_fetched,
                            "note": "Products fetched but none matched criteria"}

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {"products": self._demo(), "source": "demo", "error": str(e)}

    def _build(self, pid, sku, name, desc, cost, stock) -> Dict:
        margin = MAX_MARGIN if cost < 15 else (TARGET_MARGIN if cost < 50 else MIN_MARGIN)
        sell = round(cost * (1 + margin), 2)
        return {
            "id": pid, "sku": sku, "name": name,
            "description": desc[:500] if desc else "",
            "cost_price": cost, "selling_price": sell,
            "profit": round(sell - cost, 2), "profit_margin": margin,
            "images": [], "in_stock": stock > 0,
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
            self._build("d1","DEMO-001","Premium Dog Bed","",25.0,150),
            self._build("d2","DEMO-002","Smart Pet Feeder","",35.0,80),
            self._build("d3","DEMO-003","LED Night Light","",8.0,300),
        ]
