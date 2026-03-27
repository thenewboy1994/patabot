"""
Product Manager — مدير المنتجات
Uses ONLY batch BigBuy API endpoints to avoid 400/429 errors.
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
        logger.info("📦 Fetching products from BigBuy (batch mode)...")

        if not BIGBUY_API_KEY:
            return {"products": self._demo(), "source": "demo"}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:

                # STEP 1: Get products catalog
                logger.info("📂 Step 1: Getting catalog...")
                r1 = await client.get(
                    f"{BIGBUY_API_URL}/catalog/products.json",
                    headers=self.headers,
                    params={"pageSize": 500, "page": 1}
                )

                if r1.status_code != 200:
                    err = f"Catalog: {r1.status_code} - {r1.text[:200]}"
                    logger.error(f"❌ {err}")
                    return {"products": self._demo(), "source": "demo", "error": err}

                catalog = r1.json()
                if not isinstance(catalog, list):
                    return {"products": self._demo(), "source": "demo",
                            "error": f"Catalog type: {type(catalog).__name__}"}

                logger.info(f"✅ Catalog: {len(catalog)} products")

                # Build catalog map by ID
                catalog_map = {}
                for item in catalog:
                    pid = item.get('id')
                    if pid:
                        catalog_map[pid] = item

                # STEP 2: Get ALL prices in batch
                await asyncio.sleep(3)
                logger.info("💰 Step 2: Getting batch prices...")

                prices_map = {}
                page = 1
                while page <= 3:
                    r2 = await client.get(
                        f"{BIGBUY_API_URL}/catalog/productsprices.json",
                        headers=self.headers,
                        params={"pageSize": 500, "page": page}
                    )

                    if r2.status_code == 200:
                        pdata = r2.json()
                        if isinstance(pdata, list) and pdata:
                            for p in pdata:
                                pid = p.get('id') or p.get('productId')
                                wp = p.get('wholesalePrice', 0)
                                if pid and wp and wp > 0:
                                    prices_map[pid] = wp
                            logger.info(f"  Page {page}: {len(pdata)} prices")
                            page += 1
                            await asyncio.sleep(2)
                        else:
                            break
                    elif r2.status_code == 429:
                        logger.warning("⏳ Rate limited on prices. Waiting 15s...")
                        await asyncio.sleep(15)
                    else:
                        logger.warning(f"⚠️ Prices page {page}: {r2.status_code} - {r2.text[:200]}")
                        break

                logger.info(f"✅ Total prices: {len(prices_map)}")

                # STEP 3: Get stock in batch
                await asyncio.sleep(3)
                logger.info("📊 Step 3: Getting batch stock...")

                stock_map = {}
                r3 = await client.get(
                    f"{BIGBUY_API_URL}/catalog/productsstockbyreference.json",
                    headers=self.headers,
                    params={"pageSize": 500, "page": 1}
                )

                if r3.status_code == 200:
                    sdata = r3.json()
                    if isinstance(sdata, list):
                        for s in sdata:
                            stocks = s.get('stocks', [])
                            pid = s.get('id') or s.get('productId')
                            ref = s.get('reference') or s.get('sku')
                            qty = 0
                            if isinstance(stocks, list):
                                qty = sum(st.get('quantity', 0) for st in stocks)
                            elif 'quantity' in s:
                                qty = s.get('quantity', 0)
                            if pid:
                                stock_map[pid] = qty
                        logger.info(f"✅ Stock data: {len(stock_map)} products")
                else:
                    logger.warning(f"⚠️ Stock: {r3.status_code}")

                # STEP 4: Combine everything
                logger.info("🔧 Step 4: Building product list...")
                all_products = []

                for pid, cost in prices_map.items():
                    if cost < 5 or cost > 200:
                        continue

                    stock = stock_map.get(pid, 0)
                    cat_item = catalog_map.get(pid, {})
                    sku = cat_item.get('sku', '')
                    name = cat_item.get('name', sku or f'Product-{pid}')
                    in_shops = cat_item.get('inShopsQuantity', stock)

                    if in_shops > 0 or stock > 0:
                        product = self._build(pid, sku, name, "", cost, max(stock, in_shops))
                        all_products.append(product)

                all_products.sort(key=lambda p: p['profit'], reverse=True)
                self.products = all_products[:200]

                logger.info(f"✅ TOTAL profitable products: {len(self.products)}")

                if self.products:
                    top3 = [(p['name'][:30], p['cost_price'], p['selling_price']) for p in self.products[:3]]
                    logger.info(f"🏆 Top 3: {top3}")
                    return {"products": self.products, "count": len(self.products), "source": "bigbuy"}
                else:
                    return {"products": self._demo(), "source": "demo",
                            "catalog_count": len(catalog),
                            "prices_count": len(prices_map),
                            "stock_count": len(stock_map),
                            "note": "No products matched all criteria (price 5-200, in stock)"}

        except Exception as e:
            logger.error(f"❌ Fatal: {e}")
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
            self._build("d4","DEMO-004","Wireless Charger","",12.0,200),
            self._build("d5","DEMO-005","Resistance Bands","",10.0,250),
        ]
