"""
Product Manager — مدير المنتجات
================================
- جلب المنتجات من BigBuy API
- حساب هوامش الربح (30-50%)
- تحديث المخزون والأسعار
- معالجة الطلبات
- إزالة المنتجات غير المتوفرة
"""

import os
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger('PataBot.Products')

# BigBuy API Configuration
BIGBUY_API_URL = "https://api.bigbuy.eu/rest"
BIGBUY_API_KEY = os.environ.get("BIGBUY_API_KEY", "")

# Profit margin settings
MIN_PROFIT_MARGIN = 0.30  # 30% minimum
MAX_PROFIT_MARGIN = 0.50  # 50% maximum
TARGET_PROFIT_MARGIN = 0.40  # 40% target

# ALL profitable categories in BigBuy — ANY profitable product!
# PataBot fetches the most profitable products from ALL categories
TARGET_CATEGORIES = [
    # 🐾 Pets (priority — matches brand)
    3,    # Pets / Mascotas
    126,  # Pet Food
    127,  # Pet Accessories
    # 🏠 Home & Garden
    6,    # Home & Garden
    156,  # Home Decoration
    157,  # Kitchen
    # 💡 Electronics & Gadgets
    4,    # Electronics
    140,  # Smart Home
    141,  # Phone Accessories
    # 💪 Health & Beauty
    7,    # Health & Beauty
    142,  # Personal Care
    143,  # Fitness & Sport
    # 👶 Kids & Baby
    8,    # Kids & Baby
    144,  # Toys
    # 🎒 Fashion & Accessories
    9,    # Fashion
    145,  # Bags & Wallets
    146,  # Jewelry & Watches
    # 🚗 Auto & Outdoor
    10,   # Auto Accessories
    147,  # Outdoor & Camping
    # 🎁 Gifts & Trending
    11,   # Gifts
    148,  # Seasonal / Trending
]


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
            async with httpx.AsyncClient(timeout=30.0) as client:
                for category_id in TARGET_CATEGORIES:
                    # Fetch products from category
                    response = await client.get(
                        f"{BIGBUY_API_URL}/catalog/products.json",
                        headers=self.headers,
                        params={
                            "isoCode": "es",
                            "pageSize": 50,
                            "category": category_id
                        }
                    )
                    
                    if response.status_code == 200:
                        products = response.json()
                        
                        for product in products:
                            # Get product details with pricing
                            detail = await self._get_product_details(client, product.get('id'))
                            if detail and self._is_profitable(detail):
                                processed = self._process_product(detail)
                                all_products.append(processed)
                    
                    else:
                        logger.warning(f"⚠️ BigBuy API returned {response.status_code} for category {category_id}")
            
            # Sort by profit margin (highest first)
            all_products.sort(key=lambda p: p['profit_margin'], reverse=True)
            
            # Keep top 100 most profitable
            self.products = all_products[:100]
            
            logger.info(f"✅ Found {len(self.products)} profitable products")
            return {"products": self.products, "count": len(self.products), "source": "bigbuy"}
        
        except Exception as e:
            logger.error(f"❌ Error fetching products: {e}")
            return {"products": self._get_demo_products(), "source": "demo", "error": str(e)}
    
    async def _get_product_details(self, client: httpx.AsyncClient, product_id: int) -> Optional[Dict]:
        """جلب تفاصيل منتج واحد"""
        try:
            response = await client.get(
                f"{BIGBUY_API_URL}/catalog/product/{product_id}.json",
                headers=self.headers,
                params={"isoCode": "es"}
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"Could not get details for product {product_id}: {e}")
        return None
    
    def _is_profitable(self, product: Dict) -> bool:
        """التحقق من أن المنتج مربح"""
        cost = product.get('wholesalePrice', 0)
        if cost <= 0:
            return False
        # Products between 5€ and 200€ cost price
        if cost < 5 or cost > 200:
            return False
        # Must have images
        if not product.get('images'):
            return False
        # Must be in stock
        if not product.get('inShopsQuantity', 0) > 0:
            return False
        return True
    
    def _process_product(self, product: Dict) -> Dict:
        """معالجة المنتج وحساب السعر النهائي"""
        cost = product.get('wholesalePrice', 0)
        
        # Dynamic pricing strategy
        if cost < 15:
            margin = MAX_PROFIT_MARGIN  # 50% for cheap items
        elif cost < 50:
            margin = TARGET_PROFIT_MARGIN  # 40% for mid-range
        else:
            margin = MIN_PROFIT_MARGIN  # 30% for expensive items
        
        selling_price = round(cost * (1 + margin), 2)
        profit = round(selling_price - cost, 2)
        
        # Get best image
        images = product.get('images', [])
        image_urls = [img.get('url', '') for img in images] if images else []
        
        return {
            "id": product.get('id'),
            "sku": product.get('sku', ''),
            "name": product.get('name', 'Product'),
            "description": product.get('description', ''),
            "cost_price": cost,
            "selling_price": selling_price,
            "profit": profit,
            "profit_margin": margin,
            "category": product.get('category', ''),
            "images": image_urls[:5],  # Max 5 images
            "weight": product.get('weight', 0),
            "in_stock": product.get('inShopsQuantity', 0) > 0,
            "stock_quantity": product.get('inShopsQuantity', 0),
            "added_date": datetime.now().isoformat()
        }
    
    async def update_inventory_and_prices(self):
        """تحديث المخزون والأسعار"""
        logger.info("🔄 Updating inventory and prices...")
        
        if not BIGBUY_API_KEY:
            logger.info("Demo mode - skipping inventory update")
            return
        
        updated = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for product in self.products:
                    detail = await self._get_product_details(client, product['id'])
                    if detail:
                        new_cost = detail.get('wholesalePrice', 0)
                        if new_cost != product['cost_price']:
                            product = self._process_product(detail)
                            updated += 1
                        
                        stock = detail.get('inShopsQuantity', 0)
                        product['in_stock'] = stock > 0
                        product['stock_quantity'] = stock
            
            logger.info(f"✅ Updated {updated} product prices")
        except Exception as e:
            logger.error(f"❌ Inventory update error: {e}")
    
    async def remove_unavailable_products(self):
        """إزالة المنتجات غير المتوفرة"""
        before = len(self.products)
        self.products = [p for p in self.products if p.get('in_stock', False)]
        removed = before - len(self.products)
        if removed > 0:
            logger.info(f"🗑️ Removed {removed} out-of-stock products")
    
    async def get_current_products(self) -> List[Dict]:
        """عرض المنتجات الحالية"""
        if not self.products:
            await self.fetch_profitable_products()
        return self.products
    
    async def get_product_count(self) -> int:
        """عدد المنتجات"""
        return len(self.products)
    
    async def process_order(self, order_data: Dict) -> Dict:
        """معالجة طلب جديد وإرساله لـ BigBuy"""
        logger.info(f"📋 Processing new order...")
        
        order = {
            "id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "customer": order_data.get("customer", {}),
            "items": order_data.get("items", []),
            "total": order_data.get("total", 0),
            "status": "processing",
            "created_at": datetime.now().isoformat()
        }
        
        # Send to BigBuy if API key is set
        if BIGBUY_API_KEY:
            bigbuy_result = await self._send_to_bigbuy(order)
            order["bigbuy_order_id"] = bigbuy_result.get("id")
            order["tracking"] = bigbuy_result.get("tracking")
        
        self.orders.append(order)
        logger.info(f"✅ Order {order['id']} processed successfully")
        return {"status": "success", "order": order}
    
    async def _send_to_bigbuy(self, order: Dict) -> Dict:
        """إرسال الطلب لـ BigBuy"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{BIGBUY_API_URL}/order/create.json",
                    headers=self.headers,
                    json={
                        "internalReference": order["id"],
                        "language": "es",
                        "paymentMethod": "moneybox",
                        "carriers": [{"name": "default"}],
                        "shippingAddress": order["customer"],
                        "products": [
                            {
                                "reference": item["sku"],
                                "quantity": item.get("quantity", 1)
                            }
                            for item in order["items"]
                        ]
                    }
                )
                if response.status_code in [200, 201]:
                    return response.json()
        except Exception as e:
            logger.error(f"❌ BigBuy order error: {e}")
        return {}
    
    async def get_orders(self) -> List[Dict]:
        """عرض الطلبات"""
        return self.orders
    
    def _get_demo_products(self) -> List[Dict]:
        """منتجات تجريبية للعرض"""
        return [
            {
                "id": "demo-001",
                "sku": "DEMO-PET-001",
                "name": "Premium Dog Bed - Orthopedic",
                "description": "Cama ortopédica premium para perros. Diseño ergonómico con espuma viscoelástica.",
                "cost_price": 25.00,
                "selling_price": 37.50,
                "profit": 12.50,
                "profit_margin": 0.50,
                "category": "Pets",
                "images": [],
                "in_stock": True,
                "stock_quantity": 150,
                "added_date": datetime.now().isoformat()
            },
            {
                "id": "demo-002",
                "sku": "DEMO-PET-002",
                "name": "Automatic Pet Feeder - Smart WiFi",
                "description": "Comedero automático inteligente con WiFi. Programa las comidas desde tu móvil.",
                "cost_price": 35.00,
                "selling_price": 52.50,
                "profit": 17.50,
                "profit_margin": 0.50,
                "category": "Pets",
                "images": [],
                "in_stock": True,
                "stock_quantity": 80,
                "added_date": datetime.now().isoformat()
            },
            {
                "id": "demo-003",
                "sku": "DEMO-HOME-001",
                "name": "LED Pet Night Light - Paw Print",
                "description": "Luz nocturna LED con forma de huella de mascota. Perfecta decoración para el hogar.",
                "cost_price": 8.00,
                "selling_price": 15.90,
                "profit": 7.90,
                "profit_margin": 0.50,
                "category": "Home",
                "images": [],
                "in_stock": True,
                "stock_quantity": 300,
                "added_date": datetime.now().isoformat()
            }
        ]
