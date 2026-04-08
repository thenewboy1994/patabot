"""
PataBot — الوكيل الذكي الشامل لـ PataHogar.com v1.6.0
- Schedule: midnight fetch (00:00) — enrichment done before morning visitors
- Catalog: only shows products with images (visitors never see incomplete products)
- Stripe Checkout: Phase 3
- Meta Ads: Phase 4 — daily proposals → email approval → auto-launch
"""

import os
import json
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

@app.get("/api/marketing/test-meta-adset")
async def test_meta_adset():
    """اختبار إنشاء adset خطوة بخطوة — يُظهر الخطأ الكامل من Meta."""
    import httpx
    token    = os.environ.get("META_ACCESS_TOKEN", "")
    account  = os.environ.get("META_AD_ACCOUNT_ID", "")
    pixel_id = os.environ.get("META_PIXEL_ID", "")

    if not token or not account:
        return {"error": "META_ACCESS_TOKEN or META_AD_ACCOUNT_ID missing"}

    results = {}
    async with httpx.AsyncClient(timeout=30.0) as client:

        # Step 1: create PAUSED campaign (OUTCOME_SALES)
        r = await client.post(
            f"https://graph.facebook.com/v21.0/{account}/campaigns",
            params={"access_token": token},
            json={
                "name": "PataBot ADSET-TEST — delete me",
                "objective": "OUTCOME_SALES",
                "status": "PAUSED",
                "special_ad_categories": [],
                "is_adset_budget_sharing_enabled": False,
                "buying_type": "AUCTION"
            }
        )
        results["campaign"] = {"status": r.status_code, "body": r.json()}
        if r.status_code != 200:
            return results
        campaign_id = r.json()["id"]

        # Step 2: adset WITH pixel + bid_strategy (full conversion tracking)
        adset_payload_with_pixel = {
            "name": "Test AdSet WITH pixel",
            "campaign_id": campaign_id,
            "daily_budget": 500,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "destination_type": "WEBSITE",
            "targeting": {"geo_locations": {"countries": ["ES"]}, "age_min": 22, "targeting_automation": {"advantage_audience": 1}},
            "status": "PAUSED",
            "promoted_object": {"pixel_id": pixel_id, "custom_event_type": "PURCHASE"},
            "dsa_beneficiary": "PataHogar",
            "dsa_payor": "PataHogar",
        }
        r2 = await client.post(
            f"https://graph.facebook.com/v21.0/{account}/adsets",
            params={"access_token": token},
            json=adset_payload_with_pixel
        )
        results["adset_with_pixel"] = {"status": r2.status_code, "body": r2.json()}
        results["adset_no_pixel"] = {"skipped": "Pixel is working — no need to test without pixel"}

        # Cleanup: delete test campaign
        await client.delete(
            f"https://graph.facebook.com/v21.0/{campaign_id}",
            params={"access_token": token}
        )
        results["cleanup"] = f"Campaign {campaign_id} deleted"

    return {"pixel_id_used": pixel_id, "account": account, "results": results}

@app.get("/api/marketing/test-meta")
async def test_meta():
    """تشخيص Meta API — يُظهر الخطأ الحقيقي من Meta."""
    import httpx
    token     = os.environ.get("META_ACCESS_TOKEN", "")
    account   = os.environ.get("META_AD_ACCOUNT_ID", "")
    page_id   = os.environ.get("META_PAGE_ID", "")
    pixel_id  = os.environ.get("META_PIXEL_ID", "")

    if not token or not account:
        return {"error": "META_ACCESS_TOKEN or META_AD_ACCOUNT_ID missing in Railway"}

    results = {}
    async with httpx.AsyncClient(timeout=20.0) as client:

        # 1. Check token validity
        r = await client.get(
            "https://graph.facebook.com/v21.0/me",
            params={"access_token": token, "fields": "id,name"}
        )
        results["token_check"] = {"status": r.status_code, "response": r.json()}

        # 2. Check ad account
        r = await client.get(
            f"https://graph.facebook.com/v21.0/{account}",
            params={"access_token": token, "fields": "id,name,account_status,currency,timezone_name"}
        )
        results["ad_account"] = {"status": r.status_code, "response": r.json()}

        # 3. Try creating a PAUSED test campaign to see real error
        r = await client.post(
            f"https://graph.facebook.com/v21.0/{account}/campaigns",
            params={"access_token": token},
            json={
                "name": "PataBot TEST — delete me",
                "objective": "OUTCOME_TRAFFIC",
                "status": "PAUSED",
                "special_ad_categories": [],
                "is_adset_budget_sharing_enabled": False
            }
        )
        results["campaign_test"] = {"status": r.status_code, "response": r.json()}

        # If campaign created, delete it immediately
        if r.status_code == 200 and r.json().get("id"):
            cid = r.json()["id"]
            await client.delete(
                f"https://graph.facebook.com/v21.0/{cid}",
                params={"access_token": token}
            )
            results["campaign_test"]["note"] = f"Test campaign {cid} created and deleted"

    return {
        "config": {
            "account": account,
            "page_id": page_id or "NOT SET",
            "pixel_id": pixel_id or "NOT SET",
            "token_prefix": token[:20] + "..."
        },
        "results": results
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

@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_page(product_id: int):
    """صفحة المنتج المخصصة — تُستخدم كـ landing page للإعلانات."""
    product = await product_manager.get_product_by_id(product_id)
    if not product:
        return HTMLResponse(content="""
            <html><body style="font-family:Arial;text-align:center;padding:60px;color:#666">
            <h2>🔍 Producto no encontrado</h2>
            <p><a href="https://patahogar.com/catalog.html" style="color:#1a5e35">← Ver catálogo</a></p>
            </body></html>""", status_code=404)

    name        = product.get("name", "Producto")
    price       = product.get("selling_price", 0)
    old_price   = product.get("old_price", price * 1.3)
    profit      = product.get("profit", 0)
    image_url   = product.get("image_url", "")
    images      = product.get("images", [image_url]) if image_url else []
    descriptions = product.get("descriptions", {})
    desc_es     = descriptions.get("es", descriptions.get("en", ""))
    category    = product.get("category", "")
    discount_pct = int(((old_price - price) / old_price) * 100) if old_price > price else 0

    # Build image gallery
    img_tags = ""
    for i, img in enumerate(images[:5]):
        display = "block" if i == 0 else "none"
        img_tags += f'<img id="img-{i}" src="{img}" style="width:100%;max-height:420px;object-fit:contain;display:{display};border-radius:8px">'
    thumb_tags = ""
    for i, img in enumerate(images[:5]):
        thumb_tags += f'<img src="{img}" onclick="showImg({i})" style="width:60px;height:60px;object-fit:cover;border-radius:6px;cursor:pointer;border:2px solid {"#1a5e35" if i==0 else "#eee"};margin:4px" id="thumb-{i}">'

    if not img_tags:
        img_tags = f'<div style="width:100%;height:300px;background:#f5f5f5;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:80px">🐾</div>'

    checkout_url = f"https://patabot-production.up.railway.app/api/checkout/create-session"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{name} | PataHogar</title>
  <meta property="og:title" content="{name} | PataHogar">
  <meta property="og:image" content="{image_url}">
  <meta property="og:description" content="🚀 Envío rápido a toda Europa | Devolución 30 días">
  <meta property="og:url" content="https://patahogar.com/product.html?id={product_id}">
  <!-- Facebook Pixel -->
  <script>
    !function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};if(!f._fbq)f._fbq=n;
    n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,
    document,'script','https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{os.getenv("META_PIXEL_ID", "")}');
    fbq('track', 'PageView');
    fbq('track', 'ViewContent', {{
      content_ids: ['{product_id}'],
      content_type: 'product',
      content_name: {json.dumps(name)},
      value: {price},
      currency: 'EUR'
    }});
  </script>
  <noscript><img height="1" width="1" style="display:none"
    src="https://www.facebook.com/tr?id={os.getenv("META_PIXEL_ID", "")}&ev=PageView&noscript=1"/></noscript>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333}}
    .nav{{background:#1a5e35;padding:12px 20px;display:flex;align-items:center;justify-content:space-between}}
    .nav a{{color:white;text-decoration:none;font-size:1.1rem;font-weight:bold}}
    .nav span{{color:#ff6b35;font-size:0.85rem}}
    .container{{max-width:900px;margin:0 auto;padding:20px}}
    .breadcrumb{{color:#888;font-size:0.85rem;margin-bottom:16px}}
    .breadcrumb a{{color:#1a5e35;text-decoration:none}}
    .product-grid{{display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-bottom:32px}}
    @media(max-width:600px){{.product-grid{{grid-template-columns:1fr}}}}
    .gallery{{position:relative}}
    .badge{{position:absolute;top:12px;right:12px;background:#ff6b35;color:white;padding:6px 12px;border-radius:20px;font-weight:bold;font-size:0.85rem}}
    .thumbs{{display:flex;flex-wrap:wrap;margin-top:8px}}
    .info h1{{font-size:1.5rem;line-height:1.3;margin-bottom:12px;color:#1a1a1a}}
    .category{{background:#e8f5e9;color:#1a5e35;padding:4px 10px;border-radius:12px;font-size:0.8rem;display:inline-block;margin-bottom:12px}}
    .price-block{{margin:16px 0}}
    .price{{font-size:2rem;font-weight:bold;color:#1a5e35}}
    .old-price{{font-size:1.1rem;color:#aaa;text-decoration:line-through;margin-left:8px}}
    .profit-badge{{background:#fff3cd;color:#856404;padding:4px 10px;border-radius:12px;font-size:0.8rem;display:inline-block;margin-top:6px}}
    .btn-buy{{width:100%;padding:16px;background:#ff6b35;color:white;border:none;border-radius:10px;font-size:1.1rem;font-weight:bold;cursor:pointer;margin:16px 0;transition:background 0.2s}}
    .btn-buy:hover{{background:#e55a25}}
    .btn-buy:disabled{{background:#ccc;cursor:not-allowed}}
    .trust{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}}
    .trust-item{{text-align:center;padding:10px;background:#f8f9fa;border-radius:8px;font-size:0.8rem}}
    .trust-item .icon{{font-size:1.4rem}}
    .desc{{background:white;padding:20px;border-radius:10px;margin-top:24px}}
    .desc h3{{color:#1a5e35;margin-bottom:10px}}
    .footer-strip{{background:#1a5e35;color:rgba(255,255,255,0.8);text-align:center;padding:16px;margin-top:32px;font-size:0.85rem}}
    .loading{{display:none;text-align:center;padding:12px;color:#1a5e35}}
    .qty-row{{display:flex;align-items:center;gap:12px;margin:12px 0}}
    .qty-btn{{width:36px;height:36px;border:2px solid #1a5e35;background:white;color:#1a5e35;border-radius:8px;font-size:1.2rem;cursor:pointer}}
    .qty-input{{width:60px;text-align:center;border:2px solid #ddd;border-radius:8px;padding:6px;font-size:1rem}}
  </style>
</head>
<body>
<nav class="nav">
  <a href="https://patahogar.com">🐾 PataHogar</a>
  <span>🚚 Envío gratis +30€</span>
</nav>

<div class="container">
  <div class="breadcrumb">
    <a href="https://patahogar.com">Inicio</a> ›
    <a href="https://patahogar.com/catalog.html">{category or "Catálogo"}</a> ›
    {name[:40]}
  </div>

  <div class="product-grid">
    <div class="gallery">
      {img_tags}
      {f'<span class="badge">-{discount_pct}%</span>' if discount_pct > 5 else ""}
      <div class="thumbs">{thumb_tags}</div>
    </div>

    <div class="info">
      {f'<span class="category">{category}</span>' if category else ""}
      <h1>{name}</h1>

      <div class="price-block">
        <span class="price">€{price:.2f}</span>
        {f'<span class="old-price">€{old_price:.2f}</span>' if discount_pct > 5 else ""}
        <br>
        <span class="profit-badge">✅ Envío en 3-7 días</span>
      </div>

      <div class="qty-row">
        <button class="qty-btn" onclick="changeQty(-1)">−</button>
        <input class="qty-input" id="qty" type="number" value="1" min="1" max="10" readonly>
        <button class="qty-btn" onclick="changeQty(1)">+</button>
        <span style="color:#888;font-size:0.85rem">unidades</span>
      </div>

      <button class="btn-buy" id="buyBtn" onclick="checkout()">
        🛒 Comprar ahora — €{price:.2f}
      </button>
      <div class="loading" id="loading">⏳ Preparando pago seguro...</div>

      <div class="trust">
        <div class="trust-item"><div class="icon">🔒</div>Pago seguro</div>
        <div class="trust-item"><div class="icon">🚚</div>Envío 3-7 días</div>
        <div class="trust-item"><div class="icon">↩️</div>30 días devolución</div>
      </div>
    </div>
  </div>

  {f'<div class="desc"><h3>📋 Descripción del producto</h3><p style="line-height:1.7;color:#555">{desc_es}</p></div>' if desc_es else ""}

</div>

<div class="footer-strip">
  PataHogar — Mascotas &amp; Hogar con Amor 🐾 | patahogar.com
</div>

<script>
  var productId = {product_id};
  var price = {price};
  var name = {json.dumps(name)};

  function showImg(i) {{
    document.querySelectorAll('[id^="img-"]').forEach(function(el){{ el.style.display='none'; }});
    document.querySelectorAll('[id^="thumb-"]').forEach(function(el){{ el.style.border='2px solid #eee'; }});
    var imgEl = document.getElementById('img-' + i);
    var thumbEl = document.getElementById('thumb-' + i);
    if(imgEl) imgEl.style.display='block';
    if(thumbEl) thumbEl.style.border='2px solid #1a5e35';
  }}

  function changeQty(delta) {{
    var inp = document.getElementById('qty');
    var val = parseInt(inp.value) + delta;
    if(val >= 1 && val <= 10) inp.value = val;
    document.getElementById('buyBtn').textContent = '🛒 Comprar ahora — €' + (price * val).toFixed(2);
  }}

  async function checkout() {{
    var qty = parseInt(document.getElementById('qty').value);
    var btn = document.getElementById('buyBtn');
    var loading = document.getElementById('loading');
    btn.disabled = true;
    loading.style.display = 'block';
    // Pixel: AddToCart + InitiateCheckout
    if(typeof fbq !== 'undefined') {{
      fbq('track', 'AddToCart', {{
        content_ids: [String(productId)],
        content_type: 'product',
        content_name: name,
        value: price * qty,
        currency: 'EUR',
        num_items: qty
      }});
      fbq('track', 'InitiateCheckout', {{
        content_ids: [String(productId)],
        content_type: 'product',
        value: price * qty,
        currency: 'EUR',
        num_items: qty
      }});
    }}
    try {{
      var resp = await fetch('{checkout_url}', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{product_id: productId, qty: qty}})
      }});
      var data = await resp.json();
      if(data.checkout_url) {{
        window.location.href = data.checkout_url;
      }} else {{
        alert('Error al preparar el pago. Intenta de nuevo.');
        btn.disabled = false;
        loading.style.display = 'none';
      }}
    }} catch(e) {{
      alert('Error de conexión. Intenta de nuevo.');
      btn.disabled = false;
      loading.style.display = 'none';
    }}
  }}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    """Política de Privacidad — GDPR compliant"""
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Política de Privacidad | PataHogar</title>
  <style>
    body{font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px 24px;color:#333;line-height:1.7}
    nav{background:#1a5e35;padding:12px 20px;border-radius:8px;margin-bottom:24px}
    nav a{color:white;text-decoration:none;font-weight:bold}
    h1{color:#1a5e35;border-bottom:3px solid #ff6b35;padding-bottom:10px}
    h2{color:#1a5e35;margin-top:28px}
    .date{background:#f0f9f4;padding:8px 14px;border-radius:6px;font-size:.9rem;color:#555;margin-bottom:20px}
    footer{margin-top:40px;padding-top:20px;border-top:1px solid #eee;text-align:center;color:#888;font-size:.85rem}
  </style>
</head>
<body>
<nav><a href="https://patahogar.com">🐾 PataHogar — Volver a la tienda</a></nav>
<h1>Política de Privacidad</h1>
<p class="date">Última actualización: Abril 2026 | Conforme al RGPD (UE) 2016/679</p>

<h2>1. Responsable del Tratamiento</h2>
<p><strong>PataHogar</strong> — Tienda online de mascotas y hogar<br>
Propietario: Mohamed El Mansouri<br>
Valencia, España<br>
Contacto: <a href="mailto:info@patahogar.com">info@patahogar.com</a></p>

<h2>2. Datos que Recopilamos</h2>
<p>Al realizar una compra recopilamos: nombre completo, dirección de envío, correo electrónico y teléfono. El pago es procesado por <strong>Stripe</strong> — no almacenamos datos de tarjeta.</p>

<h2>3. Finalidad del Tratamiento</h2>
<ul>
  <li>Procesar y enviar tu pedido a través de nuestro proveedor logístico</li>
  <li>Enviarte confirmación de compra y número de seguimiento</li>
  <li>Atender consultas y reclamaciones</li>
  <li>Mejorar nuestros servicios y experiencia de compra</li>
</ul>

<h2>4. Base Legal</h2>
<p>El tratamiento se basa en la <strong>ejecución del contrato de compraventa</strong> (Art. 6.1.b RGPD) y el <strong>interés legítimo</strong> para el funcionamiento del servicio.</p>

<h2>5. Conservación de Datos</h2>
<p>Los datos de pedidos se conservan <strong>5 años</strong> para cumplir con obligaciones fiscales. Los datos de marketing se eliminan si ejerces tu derecho de oposición.</p>

<h2>6. Tus Derechos (RGPD)</h2>
<p>Tienes derecho a: <strong>Acceso, Rectificación, Supresión, Portabilidad, Limitación y Oposición</strong>. Ejércelos en: <a href="mailto:info@patahogar.com">info@patahogar.com</a><br>
También puedes reclamar ante la <strong>Agencia Española de Protección de Datos</strong> (aepd.es).</p>

<h2>7. Cookies</h2>
<p>Usamos cookies técnicas necesarias para el carrito de compra y cookies analíticas de Google Analytics. Puedes gestionarlas desde la configuración de tu navegador.</p>

<h2>8. Transferencias Internacionales</h2>
<p>Stripe (EE.UU.) cumple con el Marco de Privacidad UE-EE.UU. BigBuy procesa pedidos desde la UE.</p>

<h2>9. Pixel de Meta (Facebook)</h2>
<p>Usamos el Pixel de Meta para medir la eficacia de nuestros anuncios y mostrar publicidad relevante. Puedes optar por no participar en <a href="https://www.facebook.com/adpreferences" target="_blank">Preferencias de anuncios de Meta</a>.</p>

<footer>PataHogar &copy; 2026 | <a href="/terms">Términos y Condiciones</a> | <a href="https://patahogar.com">Tienda</a></footer>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/terms", response_class=HTMLResponse)
async def terms_page():
    """Términos y Condiciones de compra"""
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Términos y Condiciones | PataHogar</title>
  <style>
    body{font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px 24px;color:#333;line-height:1.7}
    nav{background:#1a5e35;padding:12px 20px;border-radius:8px;margin-bottom:24px}
    nav a{color:white;text-decoration:none;font-weight:bold}
    h1{color:#1a5e35;border-bottom:3px solid #ff6b35;padding-bottom:10px}
    h2{color:#1a5e35;margin-top:28px}
    .date{background:#f0f9f4;padding:8px 14px;border-radius:6px;font-size:.9rem;color:#555;margin-bottom:20px}
    table{width:100%;border-collapse:collapse;margin:12px 0}
    td,th{padding:10px;border:1px solid #eee;text-align:left}
    th{background:#f0f9f4;color:#1a5e35}
    footer{margin-top:40px;padding-top:20px;border-top:1px solid #eee;text-align:center;color:#888;font-size:.85rem}
  </style>
</head>
<body>
<nav><a href="https://patahogar.com">🐾 PataHogar — Volver a la tienda</a></nav>
<h1>Términos y Condiciones</h1>
<p class="date">Última actualización: Abril 2026 | PataHogar, Valencia (España)</p>

<h2>1. Información General</h2>
<p>PataHogar es una tienda online de productos para mascotas y hogar operada por Mohamed El Mansouri con sede en Valencia, España. Trabajamos bajo el modelo de <strong>dropshipping</strong> con proveedor europeo certificado (BigBuy, Valencia).</p>

<h2>2. Proceso de Compra</h2>
<ol>
  <li>Selecciona el producto y haz clic en "Comprar ahora"</li>
  <li>Revisa tu carrito y confirma la cantidad</li>
  <li>Introduce tus datos de envío y pago en la página segura de <strong>Stripe</strong></li>
  <li>Recibirás confirmación por email en menos de 1 hora</li>
  <li>Tu pedido se envía desde nuestros almacenes europeos en 24-48h</li>
</ol>

<h2>3. Precios y Pago</h2>
<p>Todos los precios incluyen IVA. Aceptamos: <strong>Visa, Mastercard, American Express</strong> y otras tarjetas procesadas por Stripe (PCI DSS Level 1).</p>

<h2>4. Envíos</h2>
<table>
  <tr><th>Destino</th><th>Plazo</th><th>Coste</th></tr>
  <tr><td>España, Portugal</td><td>2-4 días laborables</td><td>Gratis +30€ / €3.99 resto</td></tr>
  <tr><td>Francia, Alemania, Italia</td><td>3-6 días laborables</td><td>Gratis +30€ / €4.99 resto</td></tr>
  <tr><td>Resto de Europa</td><td>4-8 días laborables</td><td>Gratis +30€ / €5.99 resto</td></tr>
</table>

<h2>5. Devoluciones (30 días)</h2>
<p>Tienes <strong>30 días naturales</strong> desde la recepción para devolver cualquier producto en perfectas condiciones. Los gastos de devolución corren a cargo del comprador salvo producto defectuoso. El reembolso se procesa en 3-5 días hábiles.</p>

<h2>6. Garantía</h2>
<p>Todos nuestros productos cuentan con <strong>2 años de garantía legal</strong> conforme a la Directiva UE 2019/771.</p>

<h2>7. Resolución de Conflictos</h2>
<p>Para cualquier reclamación: <a href="mailto:info@patahogar.com">info@patahogar.com</a>. En caso de disputa, puedes usar la <a href="https://ec.europa.eu/consumers/odr" target="_blank">plataforma ODR de la UE</a>.</p>

<h2>8. Legislación Aplicable</h2>
<p>Estos términos se rigen por la legislación española y el Derecho de la Unión Europea (Directiva 2011/83/UE sobre derechos de los consumidores).</p>

<footer>PataHogar &copy; 2026 | <a href="/privacy">Política de Privacidad</a> | <a href="https://patahogar.com">Tienda</a></footer>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/api/marketing/ad-details/{ad_id}")
async def ad_details(ad_id: str):
    """تفاصيل كاملة عن إعلان — للتشخيص."""
    ad = next((a for a in marketing_manager.active_ads if a["id"] == ad_id), None)
    if not ad:
        ad = next((a for a in marketing_manager.pending_ads if a["id"] == ad_id), None)
    if not ad:
        return JSONResponse(status_code=404, content={"error": "Ad not found"})
    return ad


@app.get("/api/marketing/launch-test")
async def launch_test():
    """
    اختبار شامل لكل خطوات إطلاق الإعلان — يُظهر أين يفشل بالضبط.
    يُنشئ ثم يحذف فوراً (لا أثر مالي).
    """
    import httpx
    token    = os.environ.get("META_ACCESS_TOKEN", "")
    account  = os.environ.get("META_AD_ACCOUNT_ID", "")
    pixel_id = os.environ.get("META_PIXEL_ID", "")
    page_id  = os.environ.get("META_PAGE_ID", "")
    base     = "https://graph.facebook.com/v21.0"

    if not token or not account:
        return {"error": "META credentials missing"}

    results = {"config": {"account": account, "page_id": page_id or "❌ NOT SET",
                          "pixel_id": pixel_id or "❌ NOT SET"}}
    campaign_id = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Campaign (same as real launch)
        r = await client.post(f"{base}/{account}/campaigns",
            params={"access_token": token},
            json={"name": "PataBot LAUNCH-TEST — delete me",
                  "objective": "OUTCOME_SALES", "status": "PAUSED",
                  "special_ad_categories": [], "buying_type": "AUCTION",
                  "is_adset_budget_sharing_enabled": False})
        results["step1_campaign"] = {"status": r.status_code, "ok": r.status_code == 200,
                                     "body": r.json()}
        if r.status_code != 200:
            return results
        campaign_id = r.json()["id"]

        # Step 2: AdSet ES (same as real launch)
        r = await client.post(f"{base}/{account}/adsets",
            params={"access_token": token},
            json={"name": "TEST AdSet ES", "campaign_id": campaign_id,
                  "daily_budget": 500, "billing_event": "IMPRESSIONS",
                  "optimization_goal": "OFFSITE_CONVERSIONS",
                  "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                  "destination_type": "WEBSITE",
                  "targeting": {"geo_locations": {"countries": ["ES"]}, "age_min": 22,
                                "targeting_automation": {"advantage_audience": 1}},
                  "status": "PAUSED",
                  "promoted_object": {"pixel_id": pixel_id, "custom_event_type": "PURCHASE"},
                  "dsa_beneficiary": "PataHogar", "dsa_payor": "PataHogar"})
        results["step2_adset_ES"] = {"status": r.status_code, "ok": r.status_code == 200,
                                     "body": r.json()}

        # Step 3: AdSet CH (no DSA required)
        r = await client.post(f"{base}/{account}/adsets",
            params={"access_token": token},
            json={"name": "TEST AdSet CH", "campaign_id": campaign_id,
                  "daily_budget": 500, "billing_event": "IMPRESSIONS",
                  "optimization_goal": "OFFSITE_CONVERSIONS",
                  "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                  "destination_type": "WEBSITE",
                  "targeting": {"geo_locations": {"countries": ["CH"]}, "age_min": 22,
                                "targeting_automation": {"advantage_audience": 1}},
                  "status": "PAUSED",
                  "promoted_object": {"pixel_id": pixel_id, "custom_event_type": "PURCHASE"}})
        results["step3_adset_CH"] = {"status": r.status_code, "ok": r.status_code == 200,
                                     "body": r.json()}

        # Step 4: Creative (needs page_id)
        if page_id:
            r = await client.post(f"{base}/{account}/adcreatives",
                params={"access_token": token},
                json={"name": "TEST Creative",
                      "object_story_spec": {
                          "page_id": page_id,
                          "link_data": {
                              "link": "https://patahogar.com/catalog.html",
                              "message": "Test ad from PataBot",
                              "name": "PataHogar — Test",
                              "call_to_action": {"type": "SHOP_NOW",
                                                 "value": {"link": "https://patahogar.com/catalog.html"}}
                          }}})
            results["step4_creative"] = {"status": r.status_code, "ok": r.status_code == 200,
                                         "body": r.json()}
        else:
            results["step4_creative"] = {"ok": False, "error": "META_PAGE_ID not set in Railway"}

        # Cleanup
        await client.delete(f"{base}/{campaign_id}", params={"access_token": token})
        results["cleanup"] = f"Campaign {campaign_id} deleted"

    all_ok = all(v.get("ok", False) for k, v in results.items() if k.startswith("step"))
    results["conclusion"] = "✅ All steps OK — launch should work" if all_ok else "❌ Some steps failed — see above"
    return results


@app.get("/api/marketing/update-budget")
async def update_ad_budget(ad_id: str = Query(""), budget: float = Query(10.0)):
    """
    رفع أو تغيير ميزانية إعلان نشط على Meta.
    GET /api/marketing/update-budget?ad_id=AD-xxx&budget=15
    """
    if not ad_id:
        return JSONResponse(status_code=400, content={"error": "ad_id required"})
    result = await marketing_manager.update_ad_budget(ad_id, budget)
    return result

@app.get("/api/marketing/set-default-budget")
async def set_default_budget(budget: float = Query(10.0)):
    """
    تغيير الميزانية الافتراضية للإعلانات الجديدة.
    GET /api/marketing/set-default-budget?budget=15
    """
    marketing_manager.default_daily_budget = budget
    return {"status": "ok", "new_default_budget": budget, "message": f"الإعلانات الجديدة ستكون بميزانية €{budget}/يوم"}

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
    products = await product_manager.get_current_products()
    orders   = order_manager.get_order_stats()
    marketing = await marketing_manager.get_campaigns_status()
    return await report_manager.generate_daily_report(products, orders, marketing)

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
        products  = await product_manager.get_current_products()
        orders    = order_manager.get_order_stats()
        marketing = await marketing_manager.get_campaigns_status()
        report    = await report_manager.generate_daily_report(products, orders, marketing)
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
        return "مرحباً محمد! أنا PataBot v1.6.0 جاهز. كيف أساعدك؟ 🐾"
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
        "orders": {"total": len(order_manager.orders)},
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
