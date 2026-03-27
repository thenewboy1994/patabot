"""
Product Manager — مدير المنتجات
Gets products from BigBuy - prices included in product data.
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
        skipped_reasons = {"no_price": 0, "price_low": 0, "price_high": 0, "not_active": 0, "accepted": 0}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                page = 1

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

                    logger.info(f"  Got {len(items)} products")

                    # Log first product structure for debugging
                    if page == 1 and items:
                        first = items[0]
                        logger.info(f"  📋 Sample product keys: {list(first.keys())}")
                        logger.info(f"  📋 Sample: wholesalePrice={first.get('wholesalePrice')}, "
                                   f"retailPrice={first.get('retailPrice')}, "
                                   f"inShopsPrice={first.get('inShopsPrice')}, "
                                   f"active={first.get('active')}, "
                                   f"inShopsQuantity={first.get('inShopsQuantity')}")

                    for item in items:
                        # Get cost price - try multiple fields
                        cost = item.get('wholesalePrice', 0) or item.get('retailPrice', 0) or 0

                        if not cost or cost <= 0:
                            skipped_reasons["no_price"] += 1
                            continue
                        if cost < 3:
                            skipped_reasons["price_low"] += 1
                            continue
                        if cost > 300:
                            skipped_reasons["price_high"] += 1
                            continue

                        # Accept product even if stock is 0 or missing
                        # BigBuy handles stock - we just list products
                        stock = item.get('inShopsQuantity', 1) or 1

                        product = self._build(
                            item.get('id'),
                            item.get('sku', ''),
                            item.get('sku', f"Product-{item.get('id')}"),
                            "",
                            cost,
                            stock
                        )
                        all_products.append(product)
                        skipped_reasons["accepted"] += 1

                    page += 1
                    await asyncio.sleep(3)

                all_products.sort(key=lambda p: p['profit'], reverse=True)
                self.products = all_products[:500]

                logger.info(f"✅ Stats: {skipped_reasons}")
                logger.info(f"✅ Total profitable: {len(self.products)}")

                if self.products:
                    top5 = [(p['sku'], f"cost:{p['cost_price']}", f"sell:{p['selling_price']}", f"profit:{p['profit']}") for p in self.products[:5]]
                    logger.info(f"🏆 Top 5: {top5}")
                    return {"products": self.products, "count": len(self.products), "source": "bigbuy",
                            "stats": skipped_reasons}
                else:
                    return {"products": self._demo(), "source": "demo",
                            "stats": skipped_reasons,
                            "note": "No products matched. Check stats for reasons."}

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
            "images": [], "in_stock": True,
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
