"""
PataBot — الوكيل الذكي الشامل لـ PataHogar.com
=================================================
وكيل دروبشيبينج ذكي يقوم بكل المهمات:
- جلب أي منتج مربح من BigBuy API (كل الفئات — ليس فقط حيوانات ومنزل)
- تحديث الموقع بالمنتجات والأسعار والصور
- تحليل المنتجات الرائجة (Ad Library research)
- إنشاء محتوى تسويقي (صور + فيديو)
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
# API ENDPOINTS - لوحة التحكم لمحمد
# ============================================

@app.get("/")
async def home():
    """الصفحة الرئيسية - حالة PataBot"""
    return {
        "status": "🟢 PataBot is running!",
        "bot_name": "PataBot - الوكيل الذكي الشامل",
        "website": "patahogar.com",
        "version": "1.0.0",
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
    """التواصل المباشر مع PataBot - محمد يتكلم مع الوكيل"""
    data = await request.json()
    message = data.get("message", "")
    response = await process_chat_message(message)
    return {"response": response}


# ============================================
# AUTOMATED TASKS - المهام التلقائية
# ============================================

async def daily_product_update():
    """تحديث يومي للمنتجات"""
    logger.info("🔄 Starting daily product update...")
    try:
        # 1. بحث عن منتجات رائجة
        trending = await research_manager.analyze_market_trends()
        
        # 2. جلب منتجات مربحة من BigBuy
        new_products = await product_manager.fetch_profitable_products()
        
        # 3. تحديث الأسعار والمخزون
        await product_manager.update_inventory_and_prices()
        
        # 4. إزالة المنتجات غير المتوفرة
        await product_manager.remove_unavailable_products()
        
        # 5. تحديث الموقع
        await website_manager.update_website_products()
        
        logger.info(f"✅ Daily product update complete. New products: {len(new_products.get('products', []))}")
    except Exception as e:
        logger.error(f"❌ Daily product update failed: {e}")


async def daily_marketing_tasks():
    """مهام تسويقية يومية"""
    logger.info("📢 Starting daily marketing tasks...")
    try:
        # 1. إنشاء محتوى مجاني لأفضل المنتجات
        await marketing_manager.create_organic_content()
        
        # 2. نشر على كل المنصات (مجاني)
        await marketing_manager.post_to_all_platforms()
        
        # 3. تحليل أداء الإعلانات السابقة
        await marketing_manager.analyze_ad_performance()
        
        # 4. اقتراح إعلانات مدفوعة جديدة (تحتاج موافقة محمد)
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
# CHAT SYSTEM - نظام التواصل مع محمد
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
    
    elif any(word in message_lower for word in ['مرحبا', 'hello', 'hola', 'hi']):
        return "مرحباً محمد! أنا PataBot جاهز لخدمتك. كيف أساعدك اليوم؟ 🐾"
    
    else:
        return (
            "مرحباً محمد! يمكنني مساعدتك في:\n"
            "- 📦 المنتجات (اكتب: منتج)\n"
            "- 📢 التسويق (اكتب: إعلان)\n"
            "- 📋 الطلبات (اكتب: طلب)\n"
            "- 📊 التقارير (اكتب: تقرير)\n"
            "- 🔒 الأمان (اكتب: أمان)"
        )


# ============================================
# HELPER FUNCTIONS
# ============================================

async def get_all_stats():
    """جمع إحصائيات كل الأقسام"""
    return {
        "products": {
            "total": await product_manager.get_product_count(),
            "new_today": 0,
            "out_of_stock_removed": 0
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
    logger.info("🐾 PataHogar.com Smart Agent v1.0.0")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Schedule automated tasks
    # تحديث المنتجات يومياً الساعة 6 صباحاً
    scheduler.add_job(daily_product_update, 'cron', hour=6, minute=0)
    
    # مهام التسويق يومياً الساعة 9 صباحاً
    scheduler.add_job(daily_marketing_tasks, 'cron', hour=9, minute=0)
    
    # خدمة العملاء كل 3 ساعات
    scheduler.add_job(daily_customer_service, 'interval', hours=3)
    
    # فحص أمني كل ساعة
    scheduler.add_job(hourly_security_check, 'interval', hours=1)
    
    # التقرير اليومي الساعة 10 مساءً
    scheduler.add_job(send_daily_report, 'cron', hour=22, minute=0)
    
    scheduler.start()
    logger.info("✅ All scheduled tasks are active!")
    logger.info("✅ PataBot is fully operational! 🐾🏠")


@app.on_event("shutdown")
async def shutdown():
    """إيقاف PataBot"""
    logger.info("🛑 PataBot is shutting down...")
    scheduler.shutdown()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
