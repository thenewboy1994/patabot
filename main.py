
"""
PataBot — الوكيل الذكي الشامل لـ PataHogar.com v1.2.0
"""

import os
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, Request
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

app = FastAPI(title="PataBot", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://patahogar.com", "https://www.patahogar.com", "http://patahogar.com", "http://www.patahogar.com"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

product_manager = ProductManager()
marketing_manager = MarketingManager()
research_manager = ResearchManager()
customer_service = CustomerService()
security_manager = SecurityManager()
report_manager = ReportManager()
website_manager = WebsiteManager()
scheduler = AsyncIOScheduler()

# ─── ENDPOINTS ───

@app.get("/")
async def home():
    return {
        "status": "🟢 PataBot is running!",
        "bot_name": "PataBot - الوكيل الذكي الشامل",
        "website": "patahogar.com", "version": "1.2.0",
        "timestamp": datetime.now().isoformat(),
        "modules": {k: "✅ Active" for k in ["product_manager","marketing_manager","research_manager","customer_service","security_manager","report_manager","website_manager"]}
    }

@app.get("/api/dashboard")
async def dashboard():
    return {"dashboard": "PataBot Control Panel", "owner": "Mohamed El Mansouri",
            "stats": await get_all_stats(), "last_update": datetime.now().isoformat()}

@app.get("/api/products")
async def get_products():
    products = await product_manager.get_current_products()
    return {"products": products, "count": len(products)}

@app.get("/api/products/fetch")
async def fetch_new_products():
    return await product_manager.fetch_profitable_products()

@app.get("/api/products/enrich")
async def enrich_products():
    """Manually trigger image enrichment for products missing images."""
    return await product_manager.run_enrichment()

@app.get("/api/products/enrichment-status")
async def enrichment_status():
    return product_manager.get_enrichment_status()

@app.get("/api/products/test-images/{product_id}")
async def test_product_images(product_id: int):
    import httpx
    api_key = os.environ.get("BIGBUY_API_KEY", "")
    if not api_key: return {"error": "No API key"}
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "Content-Type": "application/json"}
    results = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            url = f"https://api.bigbuy.eu/rest/catalog/productimages/{product_id}.json"
            r = await client.get(url, headers=headers)
            results["images_endpoint"] = {"url": url, "status": r.status_code,
                "response_type": str(type(r.json()).__name__) if r.status_code == 200 else None,
                "response_preview": r.text[:1000] if r.status_code == 200 else r.text[:500]}
        except Exception as e: results["images_endpoint"] = {"error": str(e)}
        await asyncio.sleep(2)
        try:
            url = f"https://api.bigbuy.eu/rest/catalog/productinformation/{product_id}.json"
            r = await client.get(url, headers=headers)
            results["info_endpoint"] = {"url": url, "status": r.status_code,
                "response_type": str(type(r.json()).__name__) if r.status_code == 200 else None,
                "response_preview": r.text[:1000] if r.status_code == 200 else r.text[:500]}
        except Exception as e: results["info_endpoint"] = {"error": str(e)}
    return {"product_id": product_id, "test_results": results}

@app.get("/api/test-bigbuy")
async def test_bigbuy():
    import httpx
    api_key = os.environ.get("BIGBUY_API_KEY", "")
    if not api_key: return {"error": "No API key set"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get("https://api.bigbuy.eu/rest/catalog/categories.json", headers=headers, params={"pageSize": 5})
            results["categories"] = {"status": r.status_code, "sample": r.text[:500]}
        except Exception as e: results["categories"] = {"error": str(e)}
        try:
            r = await client.get("https://api.bigbuy.eu/rest/catalog/products.json", headers=headers, params={"pageSize": 3, "page": 1})
            results["products"] = {"status": r.status_code, "sample": r.text[:500]}
        except Exception as e: results["products"] = {"error": str(e)}
    return {"test": "BigBuy API Connection Test", "results": results}

@app.get("/api/products/trending")
async def get_trending():
    return {"trending": await research_manager.get_trending_products()}

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
    return {"status": "⏳ Waiting for Mohamed's approval", "proposal": proposal}

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

# ─── SCHEDULED TASKS ───

async def daily_product_update():
    try:
        await product_manager.fetch_profitable_products()
    except Exception as e: logger.error(f"Daily update failed: {e}")

async def daily_marketing_tasks():
    try:
        await marketing_manager.create_organic_content()
        await marketing_manager.post_to_all_platforms()
    except Exception as e: logger.error(f"Marketing failed: {e}")

async def daily_customer_service():
    try:
        await customer_service.process_pending_messages()
    except Exception as e: logger.error(f"Customer service failed: {e}")

async def hourly_security_check():
    try:
        await security_manager.check_website_health()
    except Exception as e: logger.error(f"Security failed: {e}")

async def send_daily_report():
    try:
        report = await report_manager.generate_daily_report()
        await report_manager.send_email_report(report)
    except Exception as e: logger.error(f"Report failed: {e}")

# ─── CHAT ───

async def process_chat_message(message):
    ml = message.lower()
    if any(w in ml for w in ['منتج','product','producto']):
        p = await product_manager.get_current_products()
        return f"لديك {len(p)} منتج. {sum(1 for x in p if x.get('image_url'))} مع صور."
    elif any(w in ml for w in ['صور','images','enrichment']):
        s = product_manager.get_enrichment_status()
        return f"الصور: {s['with_images']}/{s['total_products']}. الأسماء: {s['with_names']}/{s['total_products']}."
    elif any(w in ml for w in ['مرحبا','hello','hola']):
        return "مرحباً محمد! أنا PataBot جاهز. كيف أساعدك؟ 🐾"
    else:
        return "يمكنني مساعدتك: منتج | صور | إعلان | طلب | تقرير | أمان"

async def get_all_stats():
    s = product_manager.get_enrichment_status()
    return {"products": {"total": await product_manager.get_product_count(), "with_images": s["with_images"], "with_names": s["with_names"]},
            "orders": {"total": 0}, "security": {"status": "online"}}

# ─── STARTUP ───

@app.on_event("startup")
async def startup():
    logger.info("🚀 PataBot v1.2.0 starting...")
    scheduler.add_job(daily_product_update, 'cron', hour=6)
    scheduler.add_job(daily_marketing_tasks, 'cron', hour=9)
    scheduler.add_job(daily_customer_service, 'interval', hours=3)
    scheduler.add_job(hourly_security_check, 'interval', hours=1)
    scheduler.add_job(send_daily_report, 'cron', hour=22)
    scheduler.start()
    logger.info("✅ PataBot operational! 🐾")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
