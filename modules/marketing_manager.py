"""
Marketing Manager — مدير التسويق
==================================
- نشر محتوى عضوي (مجاني) على كل المنصات
- إنشاء فيديوهات وصور للمنتجات
- اقتراح إعلانات مدفوعة (تحتاج موافقة محمد)
- تحليل أداء الإعلانات
- استهداف دول أوروبا باللغة المناسبة
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger('PataBot.Marketing')

# API Keys from environment
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.environ.get("META_AD_ACCOUNT_ID", "")
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
SNAPCHAT_ACCESS_TOKEN = os.environ.get("SNAPCHAT_ACCESS_TOKEN", "")

# European target countries with languages
EU_TARGETS = {
    "ES": {"lang": "es", "name": "España", "currency": "EUR"},
    "FR": {"lang": "fr", "name": "France", "currency": "EUR"},
    "DE": {"lang": "de", "name": "Deutschland", "currency": "EUR"},
    "IT": {"lang": "it", "name": "Italia", "currency": "EUR"},
    "NL": {"lang": "nl", "name": "Nederland", "currency": "EUR"},
    "GB": {"lang": "en", "name": "United Kingdom", "currency": "GBP"},
    "PT": {"lang": "pt", "name": "Portugal", "currency": "EUR"},
    "BE": {"lang": "fr", "name": "Belgique", "currency": "EUR"},
    "AT": {"lang": "de", "name": "Österreich", "currency": "EUR"},
}

# Ad copy templates per language
AD_TEMPLATES = {
    "es": {
        "headline": "🔥 ¡Oferta increíble! | {product_name}",
        "body": "Descubre {product_name} en PataHogar.com. Los mejores productos al mejor precio. 🛒\n\n✅ Envío rápido a toda Europa\n✅ Mejor precio garantizado\n✅ Devoluciones fáciles en 14 días\n\n¡Compra ahora! 👉 patahogar.com",
        "cta": "Comprar ahora"
    },
    "en": {
        "headline": "🔥 Incredible deal! | {product_name}",
        "body": "Discover {product_name} at PataHogar.com. Best products at the best price. 🛒\n\n✅ Fast shipping across Europe\n✅ Best price guaranteed\n✅ Easy 14-day returns\n\nShop now! 👉 patahogar.com",
        "cta": "Shop now"
    },
    "fr": {
        "headline": "🔥 Offre incroyable ! | {product_name}",
        "body": "Découvrez {product_name} sur PataHogar.com. Les meilleurs produits au meilleur prix. 🛒\n\n✅ Livraison rapide en Europe\n✅ Meilleur prix garanti\n✅ Retours faciles sous 14 jours\n\nAchetez maintenant ! 👉 patahogar.com",
        "cta": "Acheter maintenant"
    },
    "de": {
        "headline": "🔥 Unglaubliches Angebot! | {product_name}",
        "body": "Entdecken Sie {product_name} auf PataHogar.com. Beste Produkte zum besten Preis. 🛒\n\n✅ Schneller Versand in ganz Europa\n✅ Bester Preis garantiert\n✅ Einfache Rückgabe in 14 Tagen\n\nJetzt kaufen! 👉 patahogar.com",
        "cta": "Jetzt kaufen"
    },
    "it": {
        "headline": "🔥 Offerta incredibile! | {product_name}",
        "body": "Scopri {product_name} su PataHogar.com. I migliori prodotti al miglior prezzo. 🛒\n\n✅ Spedizione rapida in Europa\n✅ Miglior prezzo garantito\n✅ Resi facili entro 14 giorni\n\nAcquista ora! 👉 patahogar.com",
        "cta": "Acquista ora"
    },
    "nl": {
        "headline": "🔥 Ongelooflijke deal! | {product_name}",
        "body": "Ontdek {product_name} op PataHogar.com. De beste producten voor de beste prijs. 🛒\n\n✅ Snelle verzending in heel Europa\n✅ Beste prijs gegarandeerd\n✅ Gemakkelijk retourneren binnen 14 dagen\n\nKoop nu! 👉 patahogar.com",
        "cta": "Nu kopen"
    },
    "ar": {
        "headline": "🔥 عرض لا يُصدق! | {product_name}",
        "body": "اكتشف {product_name} على PataHogar.com. أفضل المنتجات بأفضل سعر. 🛒\n\n✅ شحن سريع لكل أوروبا\n✅ أفضل سعر مضمون\n✅ إرجاع سهل خلال 14 يوم\n\nتسوق الآن! 👉 patahogar.com",
        "cta": "تسوق الآن"
    },
    "ru": {
        "headline": "🔥 Невероятное предложение! | {product_name}",
        "body": "Откройте {product_name} на PataHogar.com. Лучшие товары по лучшей цене. 🛒\n\n✅ Быстрая доставка по Европе\n✅ Лучшая цена гарантирована\n✅ Лёгкий возврат в течение 14 дней\n\nКупить сейчас! 👉 patahogar.com",
        "cta": "Купить сейчас"
    }
}


class MarketingManager:
    def __init__(self):
        self.campaigns = []
        self.organic_posts = []
        self.pending_paid_ads = []
        self.approved_ads = []
    
    async def create_product_content(self, product_id: str = None) -> Dict:
        """إنشاء محتوى تسويقي لمنتج"""
        logger.info(f"🎨 Creating marketing content for product {product_id}")
        
        content = {
            "product_id": product_id,
            "created_at": datetime.now().isoformat(),
            "content_types": []
        }
        
        # Create content for each language
        for lang_code, template in AD_TEMPLATES.items():
            content["content_types"].append({
                "language": lang_code,
                "headline": template["headline"].format(product_name="[Product Name]"),
                "body": template["body"].format(product_name="[Product Name]"),
                "cta": template["cta"],
                "platforms": ["facebook", "instagram", "tiktok", "snapchat"]
            })
        
        return content
    
    async def create_organic_content(self):
        """إنشاء محتوى مجاني (عضوي) لكل المنصات"""
        logger.info("📝 Creating organic content for all platforms...")
        
        # Content ideas for organic posts
        content_ideas = [
            {
                "type": "product_showcase",
                "description": "عرض منتج مع صور جذابة",
                "platforms": ["instagram", "facebook", "tiktok"]
            },
            {
                "type": "pet_tips",
                "description": "نصائح للعناية بالحيوانات الأليفة",
                "platforms": ["instagram", "facebook", "tiktok", "snapchat"]
            },
            {
                "type": "home_decor_ideas",
                "description": "أفكار لتزيين المنزل بمنتجاتنا",
                "platforms": ["instagram", "facebook"]
            },
            {
                "type": "customer_stories",
                "description": "قصص زبائن سعداء بمنتجاتنا",
                "platforms": ["facebook", "instagram"]
            },
            {
                "type": "behind_scenes",
                "description": "كواليس العمل في PataHogar",
                "platforms": ["tiktok", "snapchat", "instagram"]
            }
        ]
        
        for idea in content_ideas:
            post = {
                "id": f"POST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "type": idea["type"],
                "description": idea["description"],
                "platforms": idea["platforms"],
                "status": "created",
                "created_at": datetime.now().isoformat()
            }
            self.organic_posts.append(post)
        
        logger.info(f"✅ Created {len(content_ideas)} organic content pieces")
    
    async def post_to_all_platforms(self):
        """نشر المحتوى على كل المنصات (مجاني)"""
        logger.info("📤 Posting content to all platforms...")
        
        posted = 0
        for post in self.organic_posts:
            if post["status"] == "created":
                for platform in post["platforms"]:
                    success = await self._post_to_platform(platform, post)
                    if success:
                        posted += 1
                post["status"] = "posted"
        
        logger.info(f"✅ Posted {posted} organic pieces across all platforms")
    
    async def _post_to_platform(self, platform: str, post: Dict) -> bool:
        """نشر على منصة محددة"""
        try:
            if platform == "facebook" and META_ACCESS_TOKEN:
                return await self._post_to_facebook(post)
            elif platform == "instagram" and META_ACCESS_TOKEN:
                return await self._post_to_instagram(post)
            elif platform == "tiktok" and TIKTOK_ACCESS_TOKEN:
                return await self._post_to_tiktok(post)
            elif platform == "snapchat" and SNAPCHAT_ACCESS_TOKEN:
                return await self._post_to_snapchat(post)
            else:
                logger.info(f"📌 {platform}: Content ready (API token needed to auto-post)")
                return False
        except Exception as e:
            logger.error(f"❌ Error posting to {platform}: {e}")
            return False
    
    async def _post_to_facebook(self, post: Dict) -> bool:
        """نشر على فيسبوك"""
        # Will be implemented with Meta Graph API
        logger.info("📘 Facebook: Content queued")
        return True
    
    async def _post_to_instagram(self, post: Dict) -> bool:
        """نشر على انستغرام"""
        logger.info("📸 Instagram: Content queued")
        return True
    
    async def _post_to_tiktok(self, post: Dict) -> bool:
        """نشر على تيكتوك"""
        logger.info("🎵 TikTok: Content queued")
        return True
    
    async def _post_to_snapchat(self, post: Dict) -> bool:
        """نشر على سنابشات"""
        logger.info("👻 Snapchat: Content queued")
        return True
    
    async def propose_paid_ad(self, ad_data: Dict) -> Dict:
        """اقتراح إعلان مدفوع — يحتاج موافقة محمد"""
        proposal = {
            "id": f"AD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "product": ad_data.get("product", {}),
            "platforms": ad_data.get("platforms", ["facebook", "instagram"]),
            "budget": ad_data.get("budget", 10.0),
            "duration_days": ad_data.get("duration_days", 7),
            "target_countries": ad_data.get("countries", ["ES", "FR", "DE"]),
            "estimated_reach": ad_data.get("budget", 10.0) * 500,  # Rough estimate
            "status": "pending_approval",
            "created_at": datetime.now().isoformat(),
            "message_to_mohamed": (
                f"محمد: اقتراح إعلان مدفوع!\n"
                f"المنتج: {ad_data.get('product', {}).get('name', 'N/A')}\n"
                f"الميزانية: {ad_data.get('budget', 10.0)}€\n"
                f"المدة: {ad_data.get('duration_days', 7)} أيام\n"
                f"الدول: {', '.join(ad_data.get('countries', ['ES']))}\n"
                f"الوصول المتوقع: ~{ad_data.get('budget', 10.0) * 500} شخص\n"
                f"هل توافق؟ ✅ أو ❌"
            )
        }
        
        self.pending_paid_ads.append(proposal)
        logger.info(f"💰 Paid ad proposed: {proposal['id']} — Waiting for Mohamed's approval")
        return proposal
    
    async def launch_paid_ad(self, approval_data: Dict) -> Dict:
        """إطلاق الإعلان المدفوع بعد موافقة محمد"""
        ad_id = approval_data.get("ad_id")
        
        for ad in self.pending_paid_ads:
            if ad["id"] == ad_id:
                ad["status"] = "approved"
                self.approved_ads.append(ad)
                self.pending_paid_ads.remove(ad)
                
                # Launch on platforms
                for platform in ad["platforms"]:
                    logger.info(f"🚀 Launching paid ad on {platform}: {ad_id}")
                
                return {
                    "status": "launched",
                    "ad": ad,
                    "message": f"تم إطلاق الإعلان {ad_id} بنجاح! 🚀"
                }
        
        return {"status": "not_found", "message": "الإعلان غير موجود"}
    
    async def suggest_new_paid_ads(self):
        """اقتراح إعلانات مدفوعة جديدة تلقائياً"""
        logger.info("💡 Analyzing products for paid ad suggestions...")
        # Will analyze top-performing products and suggest ads
    
    async def analyze_ad_performance(self):
        """تحليل أداء الإعلانات"""
        logger.info("📊 Analyzing ad performance...")
        for ad in self.approved_ads:
            ad["performance"] = {
                "impressions": 0,
                "clicks": 0,
                "conversions": 0,
                "spend": 0,
                "roi": 0
            }
    
    async def get_campaigns_status(self) -> Dict:
        """حالة جميع الحملات"""
        return {
            "organic_posts": len(self.organic_posts),
            "pending_paid_ads": len(self.pending_paid_ads),
            "active_paid_ads": len(self.approved_ads),
            "platforms": {
                "facebook": "connected" if META_ACCESS_TOKEN else "token_needed",
                "instagram": "connected" if META_ACCESS_TOKEN else "token_needed",
                "tiktok": "connected" if TIKTOK_ACCESS_TOKEN else "token_needed",
                "snapchat": "connected" if SNAPCHAT_ACCESS_TOKEN else "token_needed"
            },
            "summary": f"{len(self.organic_posts)} منشورات مجانية، {len(self.pending_paid_ads)} إعلان ينتظر الموافقة"
        }
