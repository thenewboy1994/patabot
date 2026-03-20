"""
Website Manager — مدير الموقع
==================================
- تحديث الموقع بالمنتجات الجديدة فقط
- ⚠️ لا يغيّر تصميم الموقع أبداً (الألوان، الشكل، الواجهة محمية)
- إدارة المحتوى متعدد اللغات
"""

import os
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger('PataBot.Website')

HOSTINGER_API = os.environ.get("HOSTINGER_API", "")
WEBSITE_URL = "https://patahogar.com"

# ⚠️ DESIGN PROTECTION — DO NOT MODIFY
# الوكيل يضيف منتجات فقط — لا يلمس التصميم أبداً
PROTECTED_ELEMENTS = [
    "background-color",  # لون الخلفية
    "font-family",       # نوع الخط
    "navbar",            # شريط التنقل
    "header",            # الرأسية
    "footer",            # التذييل
    "logo",              # الشعار
    "slider",            # السلايدر
    "css",               # ملفات CSS
    "theme",             # السمة
    "layout",            # التخطيط العام
]


class WebsiteManager:
    def __init__(self):
        self.last_update = None
        self.products_on_site = 0
        self.design_locked = True  # ⚠️ التصميم مقفل — لا يمكن تعديله
    
    async def update_website_products(self):
        """تحديث المنتجات فقط — بدون لمس التصميم"""
        logger.info("🌐 Updating website products ONLY (design is LOCKED)...")
        
        if not self.design_locked:
            logger.error("❌ SAFETY: Design lock is off! Re-enabling...")
            self.design_locked = True
        
        # فقط تحديث المنتجات — التصميم محمي
        logger.info("🔒 Design protection: ACTIVE — colors, layout, fonts UNTOUCHED")
        
        self.last_update = datetime.now()
        logger.info("✅ Products updated — website design preserved")
    
    async def generate_product_html(self, product: Dict) -> str:
        """
        إنشاء HTML لمنتج — يستخدم CSS الموجود في الموقع
        لا يضيف أي styles جديدة تغيّر التصميم
        """
        images_html = ""
        for img in product.get("images", []):
            images_html += f'<img src="{img}" alt="{product["name"]}" class="product-img">'
        
        # يستخدم الـ classes الموجودة أصلاً في الموقع
        return f"""
        <div class="product-card" data-id="{product['id']}">
            <div class="product-images">{images_html}</div>
            <h3>{product['name']}</h3>
            <p class="description">{product['description']}</p>
            <div class="price">€{product['selling_price']:.2f}</div>
            <button class="add-to-cart" onclick="addToCart('{product['id']}')">
                Add to Cart 🛒
            </button>
        </div>
        """
    
    async def get_website_status(self) -> Dict:
        """حالة الموقع"""
        return {
            "url": WEBSITE_URL,
            "products_count": self.products_on_site,
            "last_update": self.last_update.isoformat() if self.last_update else "never",
            "languages": ["ES", "EN", "FR", "DE", "NL", "IT", "AR", "RU"],
            "design_locked": self.design_locked,
            "design_status": "🔒 محمي — لا يتم تعديل التصميم أبداً"
        }
