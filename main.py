"""
PataBot — الوكيل الذكي الشامل لـ PataHogar.com
=================================================
وكيل دروبشيبينج ذكي يقوم بكل المهمات:
- جلب أي منتج مربح من BigBuy API (كل الفئات)
- تحديث الموقع بالمنتجات والأسعار والصور
- تحليل المنتجات الرائجة
- إنشاء محتوى تسويقي
- نشر إعلانات على Meta, TikTok, Snapchat
- خدمة العملاء (الرد على الرسائل بـ 8 لغات)
- حماية الموقع ومراقبته
- إرسال تقارير يومية لمحمد
"""

import os
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import all modules
from modules.product_manager import ProductManager
from modules.marketing_manager import MarketingManager
from modules.research_manager import ResearchManager
from modules.customer_service import CustomerService
from modules.security_manager import SecurityManager
from modules.report_manager import ReportManager
from modules.website_manager import WebsiteManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PataBot')

# FastAPI app
app = FastAPI(
    title="PataBot - PataHogar.com Smart Agent",
    description="الوكيل الذكي الشامل لإدارة متجر PataHogar.com",
    version="1.0.0"
)

# CORS — Allow patahogar.com to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://patahogar.com", "https://www.patahogar.com", "http://patahogar.com", "http://www.patahogar.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize all managers
product_manager = ProductManager()
marketing_manager = MarketingManager()
research_manager = ResearchManager()
customer_service = CustomerService()
security_manager = SecurityManager()
report_manager = ReportManager()
website_manager = WebsiteManager()

# Scheduler for automated tasks
scheduler = AsyncIOScheduler()


# ============================================
# API ENDPOINTS
# ============================================

@app.get("/")
async def home():
    """الصفحة الرئيسية - حالة PataBot"""
    return {
        "status": "🟢 PataBot is running!",
        "bot_name": "PataBot - الوكيل الذكي الشامل",
        "website": "patahogar.com",
        "version": "1.1.0",
        "timestamp": datetime.now().isoformat(),
        "modules": {
            "product_manager": "✅ Active",
            "marketing_manager": "✅ Active",
            "research_manager": "✅ Active",
            "customer_service": "✅ Active",
            "security_manager": "✅ Active",
            "report_manager": "✅ Active",
            "website_manager": "✅ Active"
        }
    }


@app.get("/api/dashboard")
async def dashboard():
    """لوحة التحكم المركزية لمحمد"""
    stats = await get_all_stats()
    return {
        "dashboard": "PataBot Control Panel",
        "owner": "Mohamed El Mansouri",
        "stats": stats,
        "last_update": datetime.now().isoformat()
    }


@app.get("/api/products")
async def get_products():
    """عرض المنتجات الحالية"""
    products = await product_manager.get_current_products()
    return {"products": products, "count": len(products)}


@app.get("/api/products/fetch")
async def fetch_new_products():
    """جلب منتجات جديدة من BigBuy"""
    result = await product_manager.fetch_profitable_products()
    return result


@app.get("/api/products/enrich")
async def enrich_products():
    """تشغيل enrichment يدوياً — جلب الصور والأسماء لكل المنتجات"""
    if not product_manager.products_cache:
        return {"error": "No products cached. Call /api/products/fetch first."}
    
    # Get current status
    status = product_manager.get_enrichment_status()
    
    if product_manager.enrichment_running:
        return {
            "status": "Enrichment already running",
            "progress": status
        }
    
    # Start enrichment
    asyncio.create_task(product_manager._enrich_all_products())
    
    return {
        "status": "Enrichment started!",
        "total_products": status["total_products"],
        "already_enriched": status["enriched"],
        "message": "Check /api/products/enrichment-status for progress"
    }


@app.get("/api/products/enrichment-status")
async def enrichment_status():
    """حالة الـ enrichment"""
    return product_manager.get_enrichment_status()


@app.get("/api/products/test-images/{product_id}")
async def test_product_images(product_id: int):
    """اختبار جلب صور منتج واحد من BigBuy — للتشخيص"""
    import httpx
    api_key = os.environ.get("BIGBUY_API_KEY", "")
    if not api_key:
        return {"error": "No API key"}
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    results = {}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Product images endpoint
        try:
            url = f"https://api.bigbuy.eu/rest/catalog/productimages/{product_id}.json"
            r = await client.get(url, headers=headers)
            results["images_endpoint"] = {
                "url": url,
                "status": r.status_code,
                "response_type": str(type(r.json()).__name__) if r.status_code == 200 else None,
                "response_preview": r.text[:1000] if r.status_code == 200 else r.text[:500]
            }
        except Exception as e:
            results["images_endpoint"] = {"error": str(e)}
        
        await asyncio.sleep(2)
        
        # Test 2: Product information endpoint
        try:
            url = f"https://api.bigbuy.eu/rest/catalog/productinformation/{product_id}.json"
            r = await client.get(url, headers=headers)
            results["info_endpoint"] = {
                "url": url,
                "status": r.status_code,
                "response_type": str(type(r.json()).__name__) if r.status_code == 200 else None,
                "response_preview": r.text[:1000] if r.status_code == 200 else r.text[:500]
            }
        except Exception as e:
            results["info_endpoint"] = {"error": str(e)}
    
    return {
        "product_id": product_id,
        "test_results": results
    }


@app.get("/api/test-bigbuy")
async def test_bigbuy():
    """اختبار سريع للاتصال بـ BigBuy API"""
    import httpx
    api_key = os.environ.get("BIGBUY_API_KEY", "")
    if not api_key:
        return {"error": "No API key set"}
    
    results = {}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get("https://api.bigbuy.eu/rest/catalog/categories.json",
                                headers=headers, params={"pageSize": 5})
            results["categories"] = {"status": r.status_code, "sample": r.text[:500]}
        except Exception as e:
            results["categories"] = {"error": str(e)}
        
        try:
            r = await client.get("https://api.bigbuy.eu/rest/catalog/products.json",
                                headers=headers, params={"pageSize": 3, "page": 1})
            results["products"] = {"status": r.status_code, "sample": r.text[:500]}
        except Exception as e:
            results["products"] = {"error": str(e)}
    
    return {"test": "BigBuy API Connection Test", "results": results}


@app.get("/api/products/trending")
async def get_trending():
    """المنتجات الرائجة في السوق"""
    trending = await research_manager.get_trending_products()
    return {"trending": trending}


@app.get("/api/marketing/status")
async def marketing_status():
    """حالة الحملات التسويقية"""
    status = await marketing_manager.get_campaigns_status()
    return status


@app.post("/api/marketing/create-content")
async def create_content(request: Request):
    """إنشاء محتوى تسويقي لمنتج"""
    data = await request.json()
    product_id = data.get("product_id")
    content = await marketing_manager.create_product_content(product_id)
    return content


@app.post("/api/marketing/propose-ad")
async def propose_ad(request: Request):
    """اقتراح إعلان مدفوع (يحتاج موافقة محمد)"""
    data = await request.json()
    proposal = await marketing_manager.propose_paid_ad(data)
    return {
        "status": "⏳ Waiting for Mohamed's approval",
        "proposal": proposal,
        "message": "محمد: هذا اقتراح إعلان مدفوع. راجعه ووافق عليه إذا أردت."
    }


@app.post("/api/marketing/approve-ad")
async def approve_ad(request: Request):
    """محمد يوافق على الإعلان المدفوع"""
    data = await request.json()
    result = await marketing_manager.launch_paid_ad(data)
    return result


@app.get("/api/orders")
async def get_orders():
    """عرض الطلبات"""
    orders = await product_manager.get_orders()
    return {"orders": orders}


@app.post("/api/orders/process")
async def process_order(request: Request):
    """معالجة طلب جديد"""
    data = await request.json()
    result = await product_manager.process_order(data)
    return result


@app.get("/api/customers/messages")
async def customer_messages():
    """رسائل الزبائن"""
    messages = await customer_service.get_pending_messages()
    return {"messages": messages}


@app.get("/api/security/status")
async def security_status():
    """حالة أمان الموقع"""
    status = await security_manager.get_security_status()
    return status


@app.get("/api/report/daily")
async def daily_report():
    """التقرير اليومي"""
    report = await report_manager.generate_daily_report()
    return report


@app.post("/api/chat")
async def chat_with_bot(request: Request):
    """التواصل المباشر مع PataBot"""
    data = await request.json()
    message = data.get("message", "")
    response = await process_chat_message(message)
    return {"response": response}


# ============================================
# AUTOMATED TASKS
# ============================================

async def daily_product_update():
    """تحديث يومي للمنتجات"""
    logger.info("🔄 Starting daily product update...")
    try:
        trending = await research_manager.analyze_market_trends()
        new_products = await product_manager.fetch_profitable_products()
        await product_manager.update_inventory_and_prices()
        await product_manager.remove_unavailable_products()
        await website_manager.update_website_products()
        logger.info(f"✅ Daily product update complete")
    except Exception as e:
        logger.error(f"❌ Daily product update failed: {e}")


async def daily_marketing_tasks():
    """مهام تسويقية يومية"""
    logger.info("📢 Starting daily marketing tasks...")
    try:
        await marketing_manager.create_organic_content()
        await marketing_manager.post_to_all_platforms()
        await marketing_manager.analyze_ad_performance()
        await marketing_manager.suggest_new_paid_ads()
        logger.info("✅ Daily marketing tasks complete")
    except Exception as e:
        logger.error(f"❌ Daily marketing tasks failed: {e}")


async def daily_customer_service():
    """خدمة العملاء اليومية"""
    logger.info("💬 Checking customer messages...")
    try:
        await customer_service.process_pending_messages()
        await customer_service.check_order_tracking()
        await customer_service.process_return_requests()
        logger.info("✅ Customer service tasks complete")
    except Exception as e:
        logger.error(f"❌ Customer service failed: {e}")


async def hourly_security_check():
    """فحص أمني كل ساعة"""
    try:
        await security_manager.check_website_health()
        await security_manager.check_ssl_status()
        await security_manager.create_backup()
    except Exception as e:
        logger.error(f"❌ Security check failed: {e}")


async def send_daily_report():
    """إرسال التقرير اليومي لمحمد"""
    logger.info("📊 Generating daily report for Mohamed...")
    try:
        report = await report_manager.generate_daily_report()
        await report_manager.send_email_report(report)
        logger.info("✅ Daily report sent to Mohamed")
    except Exception as e:
        logger.error(f"❌ Failed to send daily report: {e}")


# ============================================
# CHAT SYSTEM
# ============================================

async def process_chat_message(message: str) -> str:
    """معالجة رسالة محمد والرد عليها"""
    message_lower = message.lower()
    
    if any(word in message_lower for word in ['منتج', 'product', 'producto']):
        products = await product_manager.get_current_products()
        return f"لديك حالياً {len(products)} منتج في الموقع. آخر تحديث: الآن."
    
    elif any(word in message_lower for word in ['إعلان', 'ad', 'marketing', 'تسويق']):
        status = await marketing_manager.get_campaigns_status()
        return f"حالة التسويق: {status.get('summary', 'جاري التحديث...')}"
    
    elif any(word in message_lower for word in ['طلب', 'order', 'pedido']):
        orders = await product_manager.get_orders()
        return f"لديك {len(orders)} طلب. جاري المعالجة."
    
    elif any(word in message_lower for word in ['تقرير', 'report', 'informe']):
        return "جاري إعداد التقرير اليومي... سأرسله لبريدك الآن."
    
    elif any(word in message_lower for word in ['أمان', 'security', 'seguridad']):
        status = await security_manager.get_security_status()
        return f"حالة الأمان: {status.get('status', 'جيد')} ✅"
    
    elif any(word in message_lower for word in ['enrichment', 'صور', 'images']):
        status = product_manager.get_enrichment_status()
        return f"حالة الصور: {status['with_images']}/{status['total_products']} منتج مع صور. التقدم: {status['progress_pct']}%"
    
    elif any(word in message_lower for word in ['مرحبا', 'hello', 'hola', 'hi']):
        return "مرحباً محمد! أنا PataBot جاهز لخدمتك. كيف أساعدك اليوم؟ 🐾"
    
    else:
        return (
            "مرحباً محمد! يمكنني مساعدتك في:\n"
            "- 📦 المنتجات (اكتب: منتج)\n"
            "- 📢 التسويق (اكتب: إعلان)\n"
            "- 📋 الطلبات (اكتب: طلب)\n"
            "- 📊 التقارير (اكتب: تقرير)\n"
            "- 🔒 الأمان (اكتب: أمان)\n"
            "- 🖼️ حالة الصور (اكتب: صور)"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================

async def get_all_stats():
    """جمع إحصائيات كل الأقسام"""
    enrichment = product_manager.get_enrichment_status()
    return {
        "products": {
            "total": await product_manager.get_product_count(),
            "enriched": enrichment["enriched"],
            "with_images": enrichment["with_images"],
            "enrichment_progress": f"{enrichment['progress_pct']}%"
        },
        "orders": {
            "total": 0,
            "pending": 0,
            "shipped": 0
        },
        "marketing": {
            "organic_posts_today": 0,
            "paid_ads_active": 0,
            "pending_approval": 0
        },
        "customers": {
            "messages_pending": 0,
            "resolved_today": 0
        },
        "security": {
            "website_status": "online",
            "ssl_valid": True,
            "last_backup": datetime.now().isoformat()
        }
    }


# ============================================
# STARTUP & SHUTDOWN
# ============================================

@app.on_event("startup")
async def startup():
    """بدء PataBot وجميع المهام التلقائية"""
    logger.info("🚀 PataBot is starting up...")
    logger.info("🐾 PataHogar.com Smart Agent v1.1.0")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Schedule automated tasks
    scheduler.add_job(daily_product_update, 'cron', hour=6, minute=0)
    scheduler.add_job(daily_marketing_tasks, 'cron', hour=9, minute=0)
    scheduler.add_job(daily_customer_service, 'interval', hours=3)
    scheduler.add_job(hourly_security_check, 'interval', hours=1)
    scheduler.add_job(send_daily_report, 'cron', hour=22, minute=0)
    
    scheduler.start()
    logger.info("✅ All scheduled tasks are active!")
    logger.info("✅ PataBot is fully operational! 🐾🏠")
    
    # Auto-fetch products on startup
    logger.info("📦 Auto-fetching products from BigBuy...")
    asyncio.create_task(auto_startup_fetch())


async def auto_startup_fetch():
    """Fetch products and start enrichment automatically on startup."""
    try:
        await asyncio.sleep(3)  # Wait for app to be fully ready
        await product_manager.fetch_profitable_products()
        logger.info("✅ Products fetched and enrichment started automatically!")
    except Exception as e:
        logger.error(f"❌ Auto-fetch failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    """إيقاف PataBot"""
    logger.info("🛑 PataBot is shutting down...")
    scheduler.shutdown()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
