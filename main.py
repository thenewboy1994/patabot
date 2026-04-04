"""
PataBot — الوكيل الذكي الشامل لـ PataHogar.com v1.6.0
- Schedule: midnight fetch (00:00) — enrichment done before morning visitors
- Catalog: only shows products with images (visitors never see incomplete products)
- Stripe Checkout: Phase 3
- Meta Ads: Phase 4 — daily proposals → email approval → auto-launch
"""

import os
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from modules.product_manager import ProductManager
from modules.order_manager import OrderManager
from modules.marketing_manager import MarketingManager
from modules.research_manager import ResearchManager
from modules.customer_service import CustomerService
from modules.security_manager import SecurityManager
from modules.report_manager import ReportManager
from modules.website_manager import WebsiteManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PataBot')

app = FastAPI(title="PataBot", version="1.6.0")

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
order_manager = OrderManager()
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
        "version": "1.6.0",
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
    """Start product fetch in background — returns immediately, no timeout."""
    status = product_manager.get_enrichment_status()
    if status["total_products"] > 0 and status.get("running"):
        return {"status": "already_running", "progress": status}
    # Fire and forget — fetches 400 products (2 pages) in background
    asyncio.create_task(product_manager.fetch_profitable_products(max_pages=2, page_size=200))
    return {
        "status": "started",
        "message": "Fetching up to 400 products in background. Check /api/products/enrichment-status in 1-2 minutes."
    }

@app.get("/api/products/fetch-full")
async def fetch_full_products():
    """Start a full fetch (600 products) in background — for nightly use."""
    asyncio.create_task(product_manager.fetch_profitable_products(max_pages=3, page_size=200))
    return {
        "status": "started",
        "message": "Fetching up to 600 products in background. Check /api/products/enrichment-status."
    }

@app.get("/api/products/enrich")
async def enrich_products():
    """Manually trigger image/name enrichment for products."""
    return await product_manager.run_enrichment()

@app.get("/api/products/re-enrich-descriptions")
async def re_enrich_descriptions():
    """Force re-fetch multilingual descriptions for all single-language products.
    Run this after deploying v7 to get EN/FR/DE/NL/IT descriptions from BigBuy."""
    return await product_manager.run_re_enrich_descriptions()

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
    return await product_manager.get_catalog(
        page=page, limit=limit, category=category,
        search=search, sort=sort,
        min_price=min_price, max_price=max_price
    )

@app.get("/api/categories")
async def get_categories():
    categories = await product_manager.get_categories()
    total = len(product_manager.products_cache)
    return {"categories": categories, "total_products": total}

@app.get("/api/products/{product_id}")
async def get_product_detail(product_id: int):
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
# RESEARCH ENDPOINTS
# ════════════════════════════════════════════════════════

@app.get("/api/research/run")
async def run_research():
    asyncio.create_task(research_manager.run_daily_research())
    return {"status": "Research started — check /api/research/status in 2 minutes"}

@app.get("/api/research/status")
async def research_status():
    return await research_manager.get_research_status()

@app.get("/api/research/winning-products")
async def winning_products():
    products = await research_manager.get_trending_products()
    return {
        "winning_products": products,
        "count": len(products),
        "last_updated": research_manager.last_research_time,
    }

@app.get("/api/research/country/{country_code}")
async def country_insights(country_code: str):
    return await research_manager.get_country_insights(country_code)

@app.get("/api/research/setup-guide")
async def research_setup_guide():
    return await research_manager.get_ad_library_guide()

@app.get("/api/research/fetch-recommended")
async def fetch_recommended_products():
    research_results = await research_manager.run_daily_research()
    keywords = research_manager.winning_keywords
    asyncio.create_task(product_manager.fetch_profitable_products(max_pages=3))
    return {
        "status": "started",
        "research": {
            "winning_keywords": len(keywords),
            "sources": ["Facebook Ad Library", "TikTok Creative Center", "EU Market Research"],
        },
        "message": "Product fetch started in background. Check /api/products/enrichment-status."
    }

@app.get("/api/marketing/test-email")
async def test_email():
    """اختبار Resend API — يُظهر النتيجة بالتفصيل."""
    import httpx

    resend_key = os.environ.get("RESEND_API_KEY", "")
    owner_mail = os.environ.get("OWNER_EMAIL", "mohaelmansouri.1994@gmail.com")

    if not resend_key:
        return {
            "success": False,
            "error": "RESEND_API_KEY no está configurado en Railway",
            "fix": "1) Crea cuenta gratis en resend.com. 2) API Keys → Create API Key. 3) Añade RESEND_API_KEY en Railway Variables."
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "PataBot <onboarding@resend.dev>",
                    "to": [owner_mail],
                    "subject": "🐾 PataBot — Test email funcionando",
                    "html": "<h2 style='color:#1a5e35'>✅ PataBot email funciona</h2><p>El sistema de aprobación de anuncios está listo.<br>Cuando PataBot encuentre productos rentables, recibirás un email con botones <b>Aprobar / Rechazar</b>.</p><p><b>— PataBot 🐾</b></p>"
                }
            )
            if r.status_code in (200, 201):
                return {
                    "success": True,
                    "message": f"✅ Email enviado a {owner_mail}. Revisa también la carpeta SPAM.",
                    "resend_status": r.status_code
                }
            else:
                return {
                    "success": False,
                    "resend_status": r.status_code,
                    "error": r.text[:500]
                }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/marketing/run-daily-sync")
async def run_daily_marketing_sync():
    """
    Versión síncrona de run-daily — espera el resultado completo.
    Útil para ver si hay productos candidatos o si el email se envía.
    """
    top_products = await product_manager.get_current_products()
    research_results = await research_manager.get_research_status()

    products_with_images = [p for p in top_products if p.get("image_url")]

    if not products_with_images:
        return {
            "status": "no_products_with_images",
            "total_products": len(top_products),
            "products_with_images": 0,
            "fix": "Espera a que el enriquecimiento termine. Revisa /api/products/enrichment-status"
        }

    result = await marketing_manager.run_daily_marketing(top_products, research_results)
    return {
        "status": result,
        "total_products": len(top_products),
        "products_with_images": len(products_with_images),
        "pending_ads": len(marketing_manager.pending_ads)
    }

@app.get("/api/marketing/status")
async def marketing_status():
    return await marketing_manager.get_campaigns_status()

@app.get("/api/marketing/campaigns-status")
async def campaigns_status():
    """Alias for /api/marketing/status — full Phase 4 dashboard."""
    return await marketing_manager.get_campaigns_status()

@app.get("/api/marketing/run-daily")
async def run_daily_marketing():
    """
    Trigger the full Phase 4 pipeline manually:
    1. Select best products for ads
    2. Create proposals
    3. Email Mohamed for approval
    4. Check active ads performance
    """
    top_products = await product_manager.get_current_products()
    research_results = await research_manager.get_research_status()
    asyncio.create_task(marketing_manager.run_daily_marketing(top_products, research_results))
    return {
        "status": "started",
        "message": "Daily marketing pipeline started. Mohamed will receive an email with ad proposals."
    }

@app.get("/api/marketing/approve-ad")
async def approve_ad_get(ad_id: str = Query(""), action: str = Query("approve")):
    """
    Called from email buttons — Mohamed clicks Approve/Reject link.
    GET /api/marketing/approve-ad?ad_id=AD-xxx&action=approve
    GET /api/marketing/approve-ad?ad_id=AD-xxx&action=reject
    """
    if not ad_id:
        return JSONResponse(status_code=400, content={"error": "ad_id required"})

    if action == "approve":
        result = await marketing_manager.launch_approved_ad(ad_id)
        if result.get("success"):
            return HTMLResponse(content="""
                <html><body style="font-family:Arial;text-align:center;padding:40px">
                <h2 style="color:#27ae60">✅ Anuncio aprobado y lanzado</h2>
                <p>El anuncio se está publicando en Facebook e Instagram.</p>
                <p><a href="https://www.facebook.com/adsmanager" style="color:#1877f2">Ver en Meta Ads Manager</a></p>
                <p><a href="https://patabot-production.up.railway.app/api/marketing/status">Ver estado completo</a></p>
                </body></html>""")
        return HTMLResponse(content=f"""
            <html><body style="font-family:Arial;text-align:center;padding:40px">
            <h2 style="color:#e74c3c">⚠️ Error al lanzar</h2>
            <p>{result.get('error','Unknown error')}</p>
            <p><a href="https://patabot-production.up.railway.app/api/marketing/status">Ver estado</a></p>
            </body></html>""")

    elif action == "reject":
        await marketing_manager.reject_ad(ad_id)
        return HTMLResponse(content="""
            <html><body style="font-family:Arial;text-align:center;padding:40px">
            <h2 style="color:#e67e22">❌ Anuncio rechazado</h2>
            <p>El anuncio ha sido descartado. PataBot buscará mejores opciones mañana.</p>
            <p><a href="https://patabot-production.up.railway.app/api/marketing/status">Ver estado</a></p>
            </body></html>""")

    return JSONResponse(status_code=400, content={"error": "action must be approve or reject"})

@app.post("/api/marketing/approve-ad")
async def approve_ad_post(request: Request):
    """POST version for direct API calls."""
    data = await request.json()
    ad_id = data.get("ad_id", "")
    action = data.get("action", "approve")
    if action == "approve":
        return await marketing_manager.launch_approved_ad(ad_id)
    return await marketing_manager.reject_ad(ad_id)

@app.post("/api/marketing/propose-ad")
async def propose_ad(request: Request):
    data = await request.json()
    proposal = await marketing_manager.propose_paid_ad(data)
    return {"status": "Waiting for Mohamed's approval", "proposal": proposal}

@app.post("/api/marketing/create-content")
async def create_content(request: Request):
    data = await request.json()
    return await marketing_manager.create_product_content(data.get("product_id"))

# ════════════════════════════════════════════════════════
# STRIPE CHECKOUT + ORDERS (Phase 3)
# ════════════════════════════════════════════════════════

@app.post("/api/checkout/create-session")
async def create_checkout_session(request: Request):
    """
    Customer clicks Pay → frontend sends cart → we return Stripe Checkout URL → redirect.
    Body: { cart: [{id, sku, name, selling_price, wholesale_price, image_url, qty}, ...] }
    OR single product: { product_id: int }
    """
    data = await request.json()

    # Option A: full cart from frontend
    if data.get("cart"):
        cart_items = data["cart"]
    # Option B: single product_id
    elif data.get("product_id"):
        product = await product_manager.get_product_by_id(int(data["product_id"]))
        if not product:
            return JSONResponse(status_code=404, content={"error": "Product not found"})
        cart_items = [{
            "id": product["id"],
            "sku": product.get("sku", ""),
            "name": product.get("name", ""),
            "selling_price": product["selling_price"],
            "wholesale_price": product.get("wholesale_price", 0),
            "image_url": product.get("image_url", ""),
            "qty": 1
        }]
    else:
        return JSONResponse(status_code=400, content={"error": "cart or product_id required"})

    result = await order_manager.create_checkout_session(cart_items)
    return result

@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe calls this after payment — PataBot auto-submits order to BigBuy."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = await order_manager.handle_webhook_event(payload, sig)
    return result

@app.get("/api/orders")
async def get_orders():
    return {"orders": order_manager.get_all_orders(), "stats": order_manager.get_order_stats()}

@app.get("/api/orders/stats")
async def order_stats():
    return order_manager.get_order_stats()

@app.get("/api/orders/{order_id}/tracking")
async def get_tracking(order_id: str):
    return await order_manager.fetch_tracking(order_id)

@app.get("/api/orders/refresh-tracking")
async def refresh_tracking():
    """Check tracking for all confirmed orders — run manually if needed."""
    return await order_manager.refresh_all_tracking()

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

async def _fetch_with_retry():
    """Fetches 600 products on startup — retries every 5 min if rate limited (max 3 attempts)."""
    for attempt in range(3):
        try:
            logger.info(f"Auto-fetch attempt {attempt + 1}/3 (600 products)...")
            result = await product_manager.fetch_profitable_products(max_pages=3, page_size=200)
            count = result.get("count", 0)
            if count > 0:
                logger.info(f"✅ Auto-fetch success: {count} products!")
                return
            else:
                logger.warning(f"Attempt {attempt+1}: 0 products — waiting 5 min...")
                await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Auto-fetch error: {e} — retrying in 5 min...")
            await asyncio.sleep(300)
    logger.error("Auto-fetch failed after 3 attempts — will retry at midnight via scheduler")

async def daily_research_and_fetch():
    """كل يوم منتصف الليل 00:00: بحث + جلب 600 منتج — الإثراء ينتهي قبل الصباح"""
    try:
        logger.info("🔍 Daily research starting...")
        await research_manager.run_daily_research()
        await product_manager.fetch_profitable_products(max_pages=3, page_size=200)
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
        await product_manager.fetch_profitable_products(max_pages=3, page_size=200)
    except Exception as e:
        logger.error(f"Daily product update failed: {e}")

async def daily_marketing_tasks():
    """Phase 4: select best products → create proposals → email Mohamed → check performance."""
    try:
        top_products = await product_manager.get_current_products()
        research_results = await research_manager.get_research_status()
        await marketing_manager.run_daily_marketing(top_products, research_results)
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
        return "مرحباً محمد! أنا PataBot v1.4.0 جاهز. كيف أساعدك؟ 🐾"
    elif any(w in ml for w in ['كتالوج', 'catalog', 'catálogo']):
        s = product_manager.get_enrichment_status()
        return f"الكتالوج: {s['total_products']} منتج. {s['with_images']} مع صور. → patahogar.com/catalog.html"
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
    logger.info("PataBot v1.6.0 starting...")

    scheduler.add_job(daily_research_and_fetch, 'cron', hour=0, minute=0)
    scheduler.add_job(daily_product_update, 'cron', hour=8, minute=0)
    scheduler.add_job(daily_marketing_tasks, 'cron', hour=9, minute=0)
    scheduler.add_job(daily_customer_service, 'interval', hours=3)
    scheduler.add_job(hourly_security_check, 'interval', hours=1)
    scheduler.add_job(send_daily_report, 'cron', hour=22, minute=0)
    scheduler.start()

    if not product_manager.products_cache:
        logger.info("Cache empty — starting auto-fetch (600 products)...")
        asyncio.create_task(_fetch_with_retry())
    else:
        logger.info(f"✅ Loaded {len(product_manager.products_cache)} products from file cache")
        missing = sum(1 for p in product_manager.products_cache if not p.get("has_images"))
        if missing > 0 and not product_manager.enrichment_running:
            asyncio.create_task(product_manager._delayed_enrichment(60))

    logger.info("PataBot v1.6.0 operational! 🐾")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    product_manager._save_to_file()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
