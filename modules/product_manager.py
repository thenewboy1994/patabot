"""
Product Manager — مدير المنتجات
================================
- جلب المنتجات من BigBuy API
- حساب هوامش الربح (30-50%)
- معالجة الطلبات
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

MIN_PROFIT_MARGIN = 0.30
MAX_PROFIT_MARGIN = 0.50
TARGET_PROFIT_MARGIN = 0.40


class ProductManager:
    def __init__(self):
        self.products = []
        self.orders = []
        self.headers = {
            "Authorization": f"Bearer {BIGBUY_API_KEY}",
            "Content-Type": "application/json"
        }

    async def fetch_profitable_products(self) -> Dict:
        """جلب المنتجات المربحة من BigBuy — طريقة بسيطة وآمنة"""
        logger.info("📦 Fetching profitable products from BigBuy...")

        if not BIGBUY_API_KEY:
            logger.warning("⚠️ No API key. Demo mode.")
            return {"products": self._get_demo_products(), "source": "demo"}

        all_products = []

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:

                # Step 1: Get taxonomies list
                logger.info("📂 Step 1: Getting taxonomies...")
                tax_resp = await client.get(
                    f"{BIGBUY_API_URL}/catalog/taxonomies.json",
                    headers=self.headers
                )

                if tax_resp.status_code != 200:
                    error_msg = f"Taxonomies: {tax_resp.status_code} - {tax_resp.text[:200]}"
                    logger.error(f"❌ {error_msg}")
                    return {"products": self._get_demo_products(), "source": "demo", "error": error_msg}

                taxonomies = tax_resp.json()
                logger.info(f"✅ Got {len(taxonomies)} taxonomies")

                # Step 2: Pick leaf taxonomies (those that ARE NOT parents)
                all_tax_ids = set(t.get('id') for t in taxonomies if t.get('id'))
                parent_ids = set(t.get('parentTaxonomy') for t in taxonomies if t.get('parentTaxonomy'))
                leaf_ids = list(all_tax_ids - parent_ids)[:10]  # First 10 leaf categories

                logger.info(f"📂 Step 2: Using {len(leaf_ids)} leaf taxonomies: {leaf_ids[:5]}...")

                # Step 3: Get products for each leaf taxonomy (with delay to avoid rate limit)
                for i, tax_id in enumerate(leaf_ids):
                    logger.info(f"📦 Fetching taxonomy {tax_id} ({i+1}/{len(leaf_ids)})...")

                    # Wait 2 seconds between requests to avoid 429
                    if i > 0:
                        await asyncio.sleep(2)

                    try:
                        resp = await client.get(
                            f"{BIGBUY_API_URL}/catalog/productsinformation.json",
                            headers=self.headers,
                            params={
                                "isoCode": "es",
                                "parentTaxonomy": tax_id,
                                "pageSize": 10,
                                "page": 1
                            }
                        )

                        if resp.status_code == 200:
                            products_info = resp.json()
                            if isinstance(products_info, list):
                                logger.info(f"  ✅ Got {len(products_info)} products from taxonomy {tax_id}")

                                for pinfo in products_info:
                                    pid = pinfo.get('id')
                                    if not pid:
                                        continue

                                    # Wait before price request
                                    await asyncio.sleep(1)

                                    try:
                                        pr = await client.get(
                                            f"{BIGBUY_API_URL}/catalog/productprice/{pid}.json",
                                            headers=self.headers
                                        )
                                        if pr.status_code == 200:
                                            price_data = pr.json()
                                            cost = price_data.get('wholesalePrice', 0)
                                            if cost and 5 <= cost <= 200:
                                                product = self._build_product(
                                                    pid,
                                                    pinfo.get('sku', ''),
                                                    pinfo.get('name', 'Product'),
                                                    pinfo.get('description', ''),
                                                    cost, [], 10
                                                )
                                                all_products.append(product)
                                                logger.info(f"  💰 Added: {pinfo.get('name','')} — €{cost} → €{product['selling_price']}")
                                        elif pr.status_code == 429:
                                            logger.warning("⏳ Rate limited on price. Waiting 5s...")
                                            await asyncio.sleep(5)
                                    except Exception as e:
                                        logger.debug(f"  Price error {pid}: {e}")

                        elif resp.status_code == 404:
                            logger.info(f"  ⚠️ Taxonomy {tax_id}: no products (404)")
                        elif resp.status_code == 429:
                            logger.warning("⏳ Rate limited. Waiting 10s...")
                            await asyncio.sleep(10)
                        else:
                            logger.warning(f"  ⚠️ Taxonomy {tax_id}: {resp.status_code}")

                    except Exception as e:
                        logger.warning(f"  ❌ Error taxonomy {tax_id}: {e}")

                # Sort by profit
                all_products.sort(key=lambda p: p['profit'], reverse=True)
                self.products = all_products[:100]

                logger.info(f"✅ Total profitable products found: {len(self.products)}")

                if not self.products:
                    logger.info("📋 No products found from API. Returning demo products.")
                    return {"products": self._get_demo_products(), "source": "demo",
                            "note": "API connected but no products matched criteria. Check taxonomy IDs."}

                return {"products": self.products, "count": len(self.products), "source": "bigbuy"}

        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            return {"products": self._get_demo_products(), "source": "demo", "error": str(e)}

    def _build_product(self, product_id, sku, name, description, cost, images, stock) -> Dict:
        if cost < 15:
            margin = MAX_PROFIT_MARGIN
        elif cost < 50:
            margin = TARGET_PROFIT_MARGIN
        else:
            margin = MIN_PROFIT_MARGIN

        selling_price = round(cost * (1 + margin), 2)
        profit = round(selling_price - cost, 2)

        return {
            "id": product_id, "sku": sku, "name": name,
            "description": description[:500] if description else "",
            "cost_price": cost, "selling_price": selling_price,
            "profit": profit, "profit_margin": margin,
            "images": images, "in_stock": stock > 0,
            "stock_quantity": stock, "added_date": datetime.now().isoformat()
        }

    async def update_inventory_and_prices(self):
        logger.info("🔄 Updating inventory...")

    async def remove_unavailable_products(self):
        before = len(self.products)
        self.products = [p for p in self.products if p.get('in_stock', False)]
        removed = before - len(self.products)
        if removed > 0:
            logger.info(f"🗑️ Removed {removed} out-of-stock products")

    async def get_current_products(self) -> List[Dict]:
        if not self.products:
            await self.fetch_profitable_products()
        return self.products

    async def get_product_count(self) -> int:
        return len(self.products)

    async def process_order(self, order_data: Dict) -> Dict:
        order = {
            "id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "customer": order_data.get("customer", {}),
            "items": order_data.get("items", []),
            "total": order_data.get("total", 0),
            "status": "processing",
            "created_at": datetime.now().isoformat()
        }
        if BIGBUY_API_KEY:
            result = await self._send_to_bigbuy(order)
            order["bigbuy_order_id"] = result.get("id")
        self.orders.append(order)
        return {"status": "success", "order": order}

    async def _send_to_bigbuy(self, order: Dict) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{BIGBUY_API_URL}/order/create.json",
                    headers=self.headers,
                    json={
                        "internalReference": order["id"],
                        "language": "es",
                        "paymentMethod": "moneybox",
                        "carriers": [{"name": "default"}],
                        "shippingAddress": order["customer"],
                        "products": [
                            {"reference": i["sku"], "quantity": i.get("quantity", 1)}
                            for i in order["items"]
                        ]
                    }
                )
                if resp.status_code in [200, 201]:
                    return resp.json()
        except Exception as e:
            logger.error(f"❌ BigBuy order error: {e}")
        return {}

    async def get_orders(self) -> List[Dict]:
        return self.orders

    def _get_demo_products(self) -> List[Dict]:
        return [
            self._build_product("demo-001", "DEMO-001", "Premium Dog Bed", "Cama premium para perros", 25.00, [], 150),
            self._build_product("demo-002", "DEMO-002", "Smart Pet Feeder", "Comedero automático WiFi", 35.00, [], 80),
            self._build_product("demo-003", "DEMO-003", "LED Night Light", "Luz nocturna LED", 8.00, [], 300),
            self._build_product("demo-004", "DEMO-004", "Wireless Charger", "Cargador inalámbrico", 12.00, [], 200),
            self._build_product("demo-005", "DEMO-005", "Resistance Bands", "Bandas de resistencia", 10.00, [], 250),
        ]
