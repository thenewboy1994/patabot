"""
Product Manager — Fast version
Step 1 (instant): Get catalog with prices
Step 2 (background): Enrich with names, descriptions, images gradually
"""

import os
import re
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
        self.enriching = False
        self.headers = {
            "Authorization": f"Bearer {BIGBUY_API_KEY}",
            "Content-Type": "application/json"
        }

    async def fetch_profitable_products(self) -> Dict:
        """Fast fetch - catalog + prices only (< 30 seconds)"""
        logger.info("📦 Fast fetch from BigBuy...")

        if not BIGBUY_API_KEY:
            return {"products": self._demo(), "source": "demo"}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                all_items = []
                page = 1
                while page <= 3:
                    resp = await client.get(
                        f"{BIGBUY_API_URL}/catalog/products.json",
                        headers=self.headers,
                        params={"pageSize": 200, "page": page}
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(10)
                        continue
                    if resp.status_code != 200:
                        break
                    items = resp.json()
                    if not isinstance(items, list) or not items:
                        break
                    all_items.extend(items)
                    page += 1
                    await asyncio.sleep(2)

                logger.info(f"✅ Catalog: {len(all_items)} products")

                final = []
                for item in all_items:
                    cost = item.get('wholesalePrice', 0)
                    if not cost or cost < 3 or cost > 300:
                        continue
                    final.append(self._build(
                        item.get('id'), item.get('sku', ''),
                        item.get('sku', ''), "", cost,
                        item.get('inShopsQuantity', 1) or 1, []
                    ))

                final.sort(key=lambda p: p['profit'], reverse=True)
                self.products = final[:200]
                logger.info(f"✅ Ready: {len(self.products)} profitable products")

                # Start background enrichment (don't wait for it)
                if self.products and not self.enriching:
                    asyncio.create_task(self._enrich_products())

                return {"products": self.products, "count": len(self.products),
                        "source": "bigbuy", "status": "names and images loading in background"}

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {"products": self._demo(), "source": "demo", "error": str(e)}

    async def _enrich_products(self):
        """Background task: add names, descriptions, images"""
        if self.enriching:
            return
        self.enriching = True
        logger.info("🎨 Starting background enrichment...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            enriched = 0
            for product in self.products[:100]:
                pid = product['id']
                if str(pid).startswith('d'):
                    continue

                # Get name and description
                await asyncio.sleep(2)
                try:
                    r = await client.get(
                        f"{BIGBUY_API_URL}/catalog/productinformation/{pid}.json",
                        headers=self.headers,
                        params={"isoCode": "es"}
                    )
                    if r.status_code == 200:
                        info = r.json()
                        if isinstance(info, list) and info:
                            product['name'] = info[0].get('name', product['sku'])
                            desc = info[0].get('description', '')
                            if desc:
                                product['description'] = re.sub(r'<[^>]+>', ' ', desc)[:500]
                        elif isinstance(info, dict):
                            product['name'] = info.get('name', product['sku'])
                            desc = info.get('description', '')
                            if desc:
                                product['description'] = re.sub(r'<[^>]+>', ' ', desc)[:500]
                    elif r.status_code == 429:
                        await asyncio.sleep(15)
                except:
                    pass

                # Get images
                await asyncio.sleep(2)
                try:
                    r = await client.get(
                        f"{BIGBUY_API_URL}/catalog/productimages/{pid}.json",
                        headers=self.headers
                    )
                    if r.status_code == 200:
                        imgs = r.json()
                        if isinstance(imgs, list):
                            product['images'] = [i.get('url','') for i in imgs[:5] if i.get('url')]
                    elif r.status_code == 429:
                        await asyncio.sleep(15)
                except:
                    pass

                enriched += 1
                if enriched % 10 == 0:
                    logger.info(f"🎨 Enriched {enriched} products...")

        self.enriching = False
        logger.info(f"✅ Enrichment complete: {enriched} products updated")

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
            self._build("d1","DEMO-001","Premium Dog Bed","Cama premium",25.0,150),
            self._build("d2","DEMO-002","Smart Pet Feeder","Comedero WiFi",35.0,80),
            self._build("d3","DEMO-003","LED Night Light","Luz LED",8.0,300),
        ]
