"""
Product Manager — مدير المنتجات
================================
- جلب المنتجات من BigBuy API (باستخدام taxonomies)
- حساب هوامش الربح (30-50%)
- تحديث المخزون والأسعار
- معالجة الطلبات
"""

import os
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Optional

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
        """جلب المنتجات المربحة من BigBuy"""
        logger.info("📦 Fetching profitable products from BigBuy...")

        if not BIGBUY_API_KEY:
            logger.warning("⚠️ BigBuy API key not set. Using demo mode.")
            return {"products": self._get_demo_products(), "source": "demo"}

        all_products = []

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Step 1: Get taxonomies
                logger.info("📂 Fetching taxonomies...")
                tax_resp = await client.get(
                    f"{BIGBUY_API_URL}/catalog/taxonomies.json",
                    headers=self.headers
                )

                if tax_resp.status_code != 200:
                    logger.error(f"❌ Taxonomies failed: {tax_resp.status_code} - {tax_resp.text[:300]}")
                    return {"products": self._get_demo_products(), "source": "demo",
                            "error": f"Taxonomy API: {tax_resp.status_code}", "detail": tax_resp.text[:300]}

                taxonomies = tax_resp.json()
                logger.info(f"✅ Got {len(taxonomies)} taxonomies")

                # Get unique parent taxonomy IDs
                parent_ids = list(set(
                    t.get('parentTaxonomy') for t in taxonomies
                    if t.get('parentTaxonomy')
                ))[:8]

                # Step 2: For each parent taxonomy, get products
                for parent_id in parent_ids:
                    try:
                        info_resp = await client.get(
                            f"{BIGBUY_API_URL}/catalog/productsinformation.json",
                            headers=self.headers,
                            params={"isoCode": "es", "parentTaxonomy": parent_id, "pageSize": 20, "page": 1}
                        )

                        if info_resp.status_code == 200:
                            products_info = info_resp.json()
                            if not isinstance(products_info, list):
                                continue

                            for pinfo in products_info[:20]:
                                pid = pinfo.get('id')
                                if not pid:
                                    continue

                                try:
                                    pr = await client.get(
                                        f"{BIGBUY_API_URL}/catalog/productprice/{pid}.json",
                                        headers=self.headers
                                    )
                                    if pr.status_code == 200:
                                        pd = pr.json()
                                        cost = pd.get('wholesalePrice', 0)
                                        if cost and 5 <= cost <= 200:
                                            images = []
                                            try:
                                                ir = await client.get(
                                                    f"{BIGBUY_API_URL}/catalog/productimages/{pid}.json",
                                                    headers=self.headers
                                                )
                                                if ir.status_code == 200:
                                                    id_list = ir.json()
                                                    if isinstance(id_list, list):
                                                        images = [i.get('url','') for i in id_list[:5] if i.get('url')]
                                            except:
                                                pass

                                            product = self._build_product(
                                                pid, pinfo.get('sku',''),
                                                pinfo.get('name','Product'),
                                                pinfo.get('description',''),
                                                cost, images, 10
                                            )
                                            all_products.append(product)
                                except:
                                    continue
                    except Exception as e:
                        logger.warning(f"⚠️ Taxonomy {parent_id} error: {e}")
                        continue

                # If still no products, try direct endpoint
                if not all_products:
                    logger.info("🔄 Trying direct products endpoint...")
                    try:
                        dr = await client.get(
                            f"{BIGBUY_API_URL}/catalog/products.json",
                            headers=self.headers,
                            params={"pageSize": 50, "page": 1}
                        )
                        if dr.status_code == 200:
                            direct = dr.json()
                            logger.info(f"📦 Direct: {len(direct)} products")
                            for p in direct[:30]:
                                pid = p.get('id')
                                sku = p.get('sku','')
                                try:
                                    pr2 = await client.get(
                                        f"{BIGBUY_API_URL}/catalog/productprice/{pid}.json",
                                        headers=self.headers
                                    )
                                    if pr2.status_code == 200:
                                        cost = pr2.json().get('wholesalePrice', 0)
                                        if cost and 5 <= cost <= 200:
                                            all_products.append(self._build_product(
                                                pid, sku, sku, "", cost, [], 10
                                            ))
                                except:
                                    continue
                        else:
                            logger.error(f"❌ Direct products: {dr.status_code} - {dr.text[:300]}")
                    except Exception as e:
                        logger.error(f"❌ Direct error: {e}")

            all_products.sort(key=lambda p: p['profit_margin'], reverse=True)
            self.products = all_products[:100]
            logger.info(f"✅ Total profitable products: {len(self.products)}")
            return {"products": self.products, "count": len(self.products), "source": "bigbuy"}

        except Exception as e:
            logger.error(f"❌ Fetch error: {e}")
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
        if not BIGBUY_API_KEY or not self.products:
            return

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
