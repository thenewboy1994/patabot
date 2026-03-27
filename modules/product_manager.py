"""
Product Manager — مدير المنتجات
================================
Uses single BigBuy API calls to avoid rate limiting.
GET /rest/catalog/products.json (pageSize up to 10000)
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

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:

                # ONE call: get all products (basic info)
                logger.info("📂 Getting product catalog...")
                resp = await client.get(
                    f"{BIGBUY_API_URL}/catalog/products.json",
                    headers=self.headers,
                    params={"pageSize": 200, "page": 1}
                )

                if resp.status_code == 429:
                    logger.warning("⏳ Rate limited. Waiting 30s and retrying...")
                    await asyncio.sleep(30)
                    resp = await client.get(
                        f"{BIGBUY_API_URL}/catalog/products.json",
                        headers=self.headers,
                        params={"pageSize": 100, "page": 1}
                    )

                if resp.status_code != 200:
                    err = f"Products API: {resp.status_code} - {resp.text[:300]}"
                    logger.error(f"❌ {err}")
                    return {"products": self._demo(), "source": "demo", "error": err}

                catalog = resp.json()
                if not isinstance(catalog, list):
                    logger.error(f"❌ Unexpected response type: {type(catalog)}")
                    return {"products": self._demo(), "source": "demo",
                            "error": f"Response is {type(catalog)}, expected list",
                            "sample": str(catalog)[:300]}

                logger.info(f"✅ Got {len(catalog)} products from catalog")

                # Now get prices in batch
                await asyncio.sleep(3)
                logger.info("💰 Getting product prices...")

                prices_resp = await client.get(
                    f"{BIGBUY_API_URL}/catalog/productsprices.json",
                    headers=self.headers,
                    params={"pageSize": 200, "page": 1}
                )

                prices_map = {}
                if prices_resp.status_code == 200:
                    prices_data = prices_resp.json()
                    if isinstance(prices_data, list):
                        for p in prices_data:
                            pid = p.get('id') or p.get('productId')
                            wp = p.get('wholesalePrice', 0)
                            if pid and wp:
                                prices_map[pid] = wp
                        logger.info(f"✅ Got prices for {len(prices_map)} products")
                    else:
                        logger.warning(f"⚠️ Prices response type: {type(prices_data)}")
                elif prices_resp.status_code == 429:
                    logger.warning("⏳ Rate limited on prices. Will use individual pricing.")
                else:
                    logger.warning(f"⚠️ Prices API: {prices_resp.status_code}")

                # Build product list
                all_products = []
                for item in catalog:
                    pid = item.get('id')
                    sku = item.get('sku', '')
                    name = item.get('name', sku)
                    stock = item.get('inShopsQuantity', 0)

                    if not pid:
                        continue

                    # Get price from batch or skip
                    cost = prices_map.get(pid, 0)

                    # If no batch price, try individual (for first 20 only)
                    if not cost and len(all_products) < 20:
                        await asyncio.sleep(2)
                        try:
                            pr = await client.get(
                                f"{BIGBUY_API_URL}/catalog/productprice/{pid}.json",
                                headers=self.headers
                            )
                            if pr.status_code == 200:
                                cost = pr.json().get('wholesalePrice', 0)
                            elif pr.status_code == 429:
                                logger.warning("⏳ Rate limited. Stopping individual prices.")
                                break
                        except:
                            pass

                    if cost and 5 <= cost <= 200 and stock > 0:
                        product = self._build(pid, sku, name, "", cost, stock)
                        all_products.append(product)

                all_products.sort(key=lambda p: p['profit'], reverse=True)
                self.products = all_products[:100]

                logger.info(f"✅ Total profitable products: {len(self.products)}")

                if self.products:
                    return {"products": self.products, "count": len(self.products), "source": "bigbuy"}
                else:
                    return {"products": self._demo(), "source": "demo",
                            "note": f"Catalog has {len(catalog)} items but none matched price/stock criteria",
                            "prices_found": len(prices_map)}

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
        if r: logger.info(f"🗑️ Removed {r} out-of-stock")

    async def get_current_products(self) -> List[Dict]:
        if not self.products: await self.fetch_profitable_products()
        return self.products

    async def get_product_count(self) -> int:
        return len(self.products)

    async def process_order(self, data: Dict) -> Dict:
        order = {
            "id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "customer": data.get("customer", {}),
            "items": data.get("items", []),
            "total": data.get("total", 0),
            "status": "processing",
            "created_at": datetime.now().isoformat()
        }
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
        except Exception as e:
            logger.error(f"❌ Order error: {e}")
        return {}

    async def get_orders(self): return self.orders

    def _demo(self) -> List[Dict]:
        return [
            self._build("d1","DEMO-001","Premium Dog Bed","Cama premium",25.0,150),
            self._build("d2","DEMO-002","Smart Pet Feeder","Comedero WiFi",35.0,80),
            self._build("d3","DEMO-003","LED Night Light","Luz nocturna",8.0,300),
            self._build("d4","DEMO-004","Wireless Charger","Cargador",12.0,200),
            self._build("d5","DEMO-005","Resistance Bands","Bandas",10.0,250),
        ]
