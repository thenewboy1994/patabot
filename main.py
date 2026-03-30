"""
PataBot — الوكيل الذكي الشامل لـ PataHogar.com v1.3.0
"""

import os
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from modules.product_manager import ProductManager
from modules.marketing_manager import MarketingManager
from modules.research_manager import ResearchManager
from modules.customer_service import CustomerService
from modules.security_manager import SecurityManager
from modules.report_manager import ReportManager
from modules.website_manager import WebsiteManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PataBot')

app = FastAPI(title="PataBot", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://patahogar.com",
        "https://www.patahogar.com",
        "http://patahogar.com",
        "http://www.patahogar.com",
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

product_manager = ProductManager()
marketing_manager = MarketingManager()
research_manager = ResearchManager()
customer_service = CustomerService()
security_manager = SecurityManager()
report_manager = ReportManager()
website_manager = WebsiteManager()
scheduler = AsyncIOScheduler()

# ════════════════════════════════════════════════════════
# CORE ENDPOINTS
# ════════════════════════════════════════════════════════

@app.get("/")
async def home():
    return {
        "status": "🟢 PataBot is running!",
        "bot_name": "PataBot - الوكيل الذكي الشامل",
        "website": "patahogar.com",
        "version": "1.3.0",
        "timestamp": datetime.now().isoformat(),
        "modules": {k: "✅ Active" for k in [
            "product_manager", "marketing_manager", "research_manager",
            "customer_service", "security_manager", "report_manager", "website_manager"
        ]}
    }

@app.get("/api/dashboard")
async def dashboard():
    return {
        "dashboard": "PataBot Control Panel",
        "owner": "Mohamed El Mansouri",
        "stats": await get_all_stats(),
        "last_update": datetime.now().isoformat()
    }

# ════════════════════════════════════════════════════════
# PRODUCTS ENDPOINTS
# ════════════════════════════════════════════════════════

@app.get("/api/products")
async def get_products():
    """Returns up to 200 products for the homepage connector."""
    products = await product_manager.get_current_products()
    return {"products": products, "count": len(products)}

@app.get("/api/products/fetch")
async def fetch_new_products():
    """Fetch fresh products from BigBuy and rebuild cache."""
    return await product_manager.fetch_profitable_products(max_pages=5, page_size=200)

@app.get("/api/products/enrich")
async def enrich_products():
    """Manually trigger image/name enrichment for products."""
    return await product_manager.run_enrichment()

@app.get("/api/products/enrichment-status")
async def enrichment_status():
    return product_manager.get_enrichment_status()

@app.get("/api/products/test-images/{product_id}")
async def test_product_images(product_id: int):
    import httpx
    api_key = os.environ.get("BIGBUY_API_KEY", "")
    if not api_key:
        return {"error": "No API key"}
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "Content-Type": "application/json"}
    results = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            url = f"https://api.bigbuy.eu/rest/catalog/productimages/{product_id}.json"
            r = await client.get(url, headers=headers)
            results["images_endpoint"] = {
                "url": url, "status": r.status_code,
                "response_preview": r.text[:1000] if r.status_code == 200 else r.text[:500]
            }
        except Exception as e:
            results["images_endpoint"] = {"error": str(e)}
        await asyncio.sleep(2)
        try:
            url = f"https://api.bigbuy.eu/rest/catalog/productinformation/{product_id}.json"
            r = await client.get(url, headers=headers)
            results["info_endpoint"] = {
                "url": url, "status": r.status_code,
                "response_preview": r.text[:1000] if r.status_code == 200 else r.text[:500]
            }
        except Exception as e:
            results["info_endpoint"] = {"error": str(e)}
    return {"product_id": product_id, "test_results": results}

# ════════════════════════════════════════════════════════
# CATALOG ENDPOINTS (for catalog.html page)
# ════════════════════════════════════════════════════════

@app.get("/api/catalog")
async def get_catalog(
    page: int = Query(1, ge=1),
    limit: int = Query(48, ge=1, le=100),
    category: str = Query(""),
    search: str = Query(""),
    sort: str = Query("profit"),
    min_price: float = Query(0, ge=0),
    max_price: float = Query(99999, ge=0)
):
    """Paginated catalog for the catalog.html page.

    sort options: profit | price_asc | price_desc | newest
    """
    return await product_manager.get_catalog(
        page=page, limit=limit, category=category,
        search=search, sort=sort,
        min_price=min_price, max_price=max_price
    )

@app.get("/api/categories")
async def get_categories():
    """Get all product categories with counts."""
    categories = await product_manager.get_categories()
    total = len(product_manager.products_cache)
    return {
        "categories": categories,
        "total_products": total
    }

@app.get("/api/products/{product_id}")
async def get_product_detail(product_id: int):
    """Get a single product by ID for product detail view."""
    product = await product_manager.get_product_by_id(product_id)
    if not product:
        return JSONResponse(status_code=404, content={"error": "Product not found"})
    return product

# ════════════════════════════════════════════════════════
# OTHER ENDPOINTS
# ════════════════════════════════════════════════════════

@app.get("/api/test-bigbuy")
async def test_bigbuy():
    import httpx
    api_key = os.environ.get("BIGBUY_API_KEY", "")
    if not api_key:
        return {"error": "No API key set"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = {}
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
    return {"trending": await research_manager.get_trending_products()}

# ════════════════════════════════════════════════════════
# RESEARCH ENDPOINTS — بحث المنتجات المربحة في أوروبا
# ════════════════════════════════════════════════════════

@app.get("/api/research/run")
async def run_research():
    """شغّل البحث الآن: Facebook Ad Library + TikTok Trends"""
    asyncio.create_task(research_manager.run_daily_research())
    return {"status": "Research started — check /api/research/status in 2 minutes"}

@app.get("/api/research/status")
async def research_status():
    """حالة البحث ونتائجه"""
    return await research_manager.get_research_status()

@app.get("/api/research/winning-products")
async def winning_products():
    """المنتجات الفائزة المُوصى بها للمتجر"""
    products = await research_manager.get_trending_products()
    return {
        "winning_products": products,
        "count": len(products),
        "last_updated": research_manager.last_research_time,
        "tip": "هذه المنتجات تُعلن عنها بنجاح في أوروبا — ابحث عنها في BigBuy"
    }

@app.get("/api/research/country/{country_code}")
async def country_insights(country_code: str):
    """معلومات سوق دولة معينة: ES, DE, NL, FR, BE, CH, LU, IT"""
    return await research_manager.get_country_insights(country_code)

@app.get("/api/research/setup-guide")
async def research_setup_guide():
    """دليل إعداد Facebook Ad Library للبحث الآلي"""
    return await research_manager.get_ad_library_guide()

@app.get("/api/research/fetch-recommended")
async def fetch_recommended_products():
    """
    خطوتان في واحدة:
    1. يشغّل البحث في Ad Library
    2. يجلب منتجات BigBuy المطابقة ويرتبها حسب الطلب في أوروبا
    """
    # Run research
    research_results = await research_manager.run_daily_research()
    keywords = research_manager.winning_keywords

    # Fetch fresh BigBuy products
    fetch_result = await product_manager.fetch_profitable_products(max_pages=10)

    # Re-sort with research insights
    if keywords:
        product_manager.products_cache = research_manager.find_matching_bigbuy_products(
            product_manager.products_cache
        )
        product_manager._save_to_file()

    return {
        "status": "success",
        "research": {
            "winning_keywords": len(keywords),
            "sources": ["Facebook Ad Library", "TikTok Creative Center", "EU Market Research"],
            "countries_analyzed": research_manager.TARGET_COUNTRIES
        },
        "products": {
            "total_fetched": fetch_result.get("count", 0),
            "research_matched": sum(1 for p in product_manager.products_cache if p.get("research_match")),
            "message": fetch_result.get("message", "")
        }
    }

@app.get("/api/marketing/status")
async def marketing_status():
    return await marketing_manager.get_campaigns_status()

@app.post("/api/marketing/create-content")
async def create_content(request: Request):
    data = await request.json()
    return await marketing_manager.create_product_content(data.get("product_id"))

@app.post("/api/marketing/propose-ad")
async def propose_ad(request: Request):
    data = await request.json()
    proposal = await marketing_manager.propose_paid_ad(data)
    return {"status": "Waiting for Mohamed's approval", "proposal": proposal}

@app.post("/api/marketing/approve-ad")
async def approve_ad(request: Request):
    return await marketing_manager.launch_paid_ad(await request.json())

@app.get("/api/orders")
async def get_orders():
    return {"orders": await product_manager.get_orders()}

@app.post("/api/orders/process")
async def process_order(request: Request):
    return await product_manager.process_order(await request.json())

@app.get("/api/customers/messages")
async def customer_messages():
    return {"messages": await customer_service.get_pending_messages()}

@app.get("/api/security/status")
async def security_status():
    return await security_manager.get_security_status()

@app.get("/api/report/daily")
async def daily_report():
    return await report_manager.generate_daily_report()

@app.post("/api/chat")
async def chat_with_bot(request: Request):
    data = await request.json()
    return {"response": await process_chat_message(data.get("message", ""))}

# ════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ════════════════════════════════════════════════════════

async def daily_research_and_fetch():
    """كل يوم 5 صباحاً: بحث في Ad Library + جلب منتجات مطابقة من BigBuy"""
    try:
        logger.info("🔍 Daily research starting...")
        await research_manager.run_daily_research()
        await product_manager.fetch_profitable_products(max_pages=10)
        # Re-sort with research insights
        if research_manager.winning_keywords:
            product_manager.products_cache = research_manager.find_matching_bigbuy_products(
                product_manager.products_cache
            )
            product_manager._save_to_file()
        logger.info("✅ Daily research + fetch complete")
    except Exception as e:
        logger.error(f"Daily research failed: {e}")

async def daily_product_update():
    try:
        await product_manager.fetch_profitable_products(max_pages=5)
    except Exception as e:
        logger.error(f"Daily product update failed: {e}")

async def daily_marketing_tasks():
    try:
        await marketing_manager.create_organic_content()
        await marketing_manager.post_to_all_platforms()
    except Exception as e:
        logger.error(f"Marketing tasks failed: {e}")

async def daily_customer_service():
    try:
        await customer_service.process_pending_messages()
    except Exception as e:
        logger.error(f"Customer service failed: {e}")

async def hourly_security_check():
    try:
        await security_manager.check_website_health()
    except Exception as e:
        logger.error(f"Security check failed: {e}")

async def send_daily_report():
    try:
        report = await report_manager.generate_daily_report()
        await report_manager.send_email_report(report)
    except Exception as e:
        logger.error(f"Daily report failed: {e}")

# ════════════════════════════════════════════════════════
# CHAT
# ════════════════════════════════════════════════════════

async def process_chat_message(message):
    ml = message.lower()
    if any(w in ml for w in ['منتج', 'product', 'producto']):
        p = await product_manager.get_current_products()
        return f"لديك {len(p)} منتج. {sum(1 for x in p if x.get('image_url'))} مع صور."
    elif any(w in ml for w in ['صور', 'images', 'enrichment']):
        s = product_manager.get_enrichment_status()
        return f"الصور: {s['with_images']}/{s['total_products']}. الأسماء: {s['with_names']}/{s['total_products']}."
    elif any(w in ml for w in ['مرحبا', 'hello', 'hola']):
        return "مرحباً محمد! أنا PataBot v1.3.0 جاهز. كيف أساعدك؟ 🐾"
    elif any(w in ml for w in ['كتالوج', 'catalog', 'catálogo']):
        s = product_manager.get_enrichment_status()
        return f"الكتالوج يحتوي على {s['total_products']} منتج. {s['with_images']} منتج مع صور. اذهب لـ patahogar.com/catalog.html"
    else:
        return "يمكنني مساعدتك: منتجات | صور | كتالوج | إعلان | طلب | تقرير | أمان"

async def get_all_stats():
    s = product_manager.get_enrichment_status()
    return {
        "products": {
            "total": s["total_products"],
            "with_images": s["with_images"],
            "with_names": s["with_names"],
            "enrichment_pct": s["progress_pct"]
        },
        "orders": {"total": len(product_manager.orders)},
        "security": {"status": "online"}
    }

# ════════════════════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    logger.info("PataBot v1.3.0 starting...")

    # Schedule daily tasks
    scheduler.add_job(daily_research_and_fetch, 'cron', hour=5, minute=0)  # بحث + جلب منتجات 5 صباحاً
    scheduler.add_job(daily_product_update, 'cron', hour=6, minute=0)       # تحديث منتجات 6 صباحاً
    scheduler.add_job(daily_marketing_tasks, 'cron', hour=9, minute=0)      # تسويق 9 صباحاً
    scheduler.add_job(daily_customer_service, 'interval', hours=3)
    scheduler.add_job(hourly_security_check, 'interval', hours=1)
    scheduler.add_job(send_daily_report, 'cron', hour=22, minute=0)
    scheduler.start()

    # Auto-fetch products if cache is empty (happens after new deploy)
    if not product_manager.products_cache:
        logger.info("Cache empty — auto-fetching products on startup (10 pages = up to 2000 products)...")
        asyncio.create_task(product_manager.fetch_profitable_products(max_pages=10))
    else:
        logger.info(f"Loaded {len(product_manager.products_cache)} products from file cache")
        missing = sum(1 for p in product_manager.products_cache if not p.get("has_images"))
        if missing > 0 and not product_manager.enrichment_running:
            logger.info(f"{missing} products missing images — scheduling enrichment...")
            asyncio.create_task(product_manager._delayed_enrichment(60))

    logger.info("PataBot v1.3.0 operational! 🐾")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    product_manager._save_to_file()  # Save on clean shutdown

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
