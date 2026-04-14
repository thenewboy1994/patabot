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
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
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

@app.get("/", response_class=HTMLResponse)
async def home():
    all_products = await product_manager.get_current_products()
    featured = [p for p in all_products if p.get("image_url")][:8]
    categories = await product_manager.get_categories()
    total_products = len([p for p in all_products if p.get("image_url")])

    # Featured product cards
    product_cards = ""
    for p in featured:
        pid   = p.get("id", "")
        pname = str(p.get("name", "Producto"))[:50]
        price = p.get("selling_price", 0)
        old_p = p.get("old_price", price * 1.3)
        img   = p.get("image_url", "")
        disc  = int(((old_p - price) / old_p) * 100) if old_p > price else 0
        badge = f'<span style="position:absolute;top:8px;right:8px;background:#ff6b35;color:white;padding:3px 8px;border-radius:12px;font-size:0.75rem;font-weight:bold">-{disc}%</span>' if disc > 5 else ""
        old_tag = f'<span style="font-size:0.85rem;color:#aaa;text-decoration:line-through">€{old_p:.2f}</span>' if disc > 5 else ""
        product_cards += f"""<a href="/product/{pid}" class="pcard">
          {badge}
          <img src="{img}" alt="{pname}" loading="lazy">
          <div class="pcard-body">
            <p class="pcard-name">{pname}</p>
            <div class="pcard-price"><span class="pcard-cur">€{price:.2f}</span>{old_tag}</div>
            <div class="pcard-stars">★★★★★ <span class="pcard-rc">(127)</span></div>
          </div>
        </a>"""

    # Category cards
    cat_icons = {"Mascotas":"🐾","Hogar":"🏠","Jardín":"🌿","Cocina":"🍳",
                 "Electrónica":"⚡","Belleza":"💄","Deportes":"⚽","Juguetes":"🎮"}
    cat_cards = ""
    for cat in categories[:8]:
        cname  = cat.get("name", "")
        ccount = cat.get("count", 0)
        icon   = cat_icons.get(cname, "📦")
        cat_cards += f"""<a href="https://patahogar.com/catalog.html?category={cname}" class="catcard">
          <div class="catcard-icon">{icon}</div>
          <p class="catcard-name">{cname}</p>
          <p class="catcard-count">{ccount} productos</p>
        </a>"""

    nav     = _get_nav()
    footer  = _get_shared_footer()
    scripts = _get_shared_head_scripts()

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PataHogar — Mascotas y Hogar | Envío a toda Europa</title>
  <meta name="description" content="Descubre más de {total_products} productos para mascotas y hogar. Envío rápido a 12 países de Europa. Pago seguro con Stripe. Devolución 30 días.">
  <meta property="og:title" content="PataHogar — Mascotas y Hogar con Amor">
  <meta property="og:description" content="Más de {total_products} productos. Envío a toda Europa.">
  <meta property="og:url" content="https://patahogar.com">
  <link rel="canonical" href="https://patahogar.com">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333}}
    .hero{{background:linear-gradient(135deg,#1a5e35 0%,#2d8a55 60%,#1a4a2a 100%);color:white;padding:64px 20px;text-align:center}}
    .hero h1{{font-size:2.5rem;font-weight:800;margin-bottom:14px;line-height:1.2}}
    .hero p{{font-size:1.1rem;opacity:0.9;margin-bottom:30px;max-width:560px;margin-left:auto;margin-right:auto}}
    .hero-btns{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}}
    @media(max-width:600px){{.hero h1{{font-size:1.7rem}}}}
    .btn-orange{{display:inline-block;padding:13px 30px;background:#ff6b35;color:white;text-decoration:none;border-radius:30px;font-weight:700;font-size:1rem;box-shadow:0 4px 14px rgba(255,107,53,0.45);transition:background 0.2s}}
    .btn-orange:hover{{background:#e55a25}}
    .btn-outline{{display:inline-block;padding:13px 30px;background:transparent;color:white;text-decoration:none;border-radius:30px;font-weight:700;font-size:1rem;border:2px solid rgba(255,255,255,0.55);transition:all 0.2s}}
    .btn-outline:hover{{background:rgba(255,255,255,0.12)}}
    .trust-bar{{background:white;padding:14px 20px;display:flex;justify-content:center;gap:28px;flex-wrap:wrap;box-shadow:0 2px 8px rgba(0,0,0,0.06);font-size:0.9rem;color:#555;font-weight:500}}
    .trust-bar span{{display:flex;align-items:center;gap:6px}}
    .searchbar{{background:white;padding:18px 20px;border-bottom:1px solid #e8e8e8;display:flex;justify-content:center}}
    .searchbar form{{display:flex;max-width:520px;width:100%}}
    .searchbar input{{flex:1;padding:11px 16px;border:2px solid #ddd;border-right:none;border-radius:30px 0 0 30px;font-size:0.95rem;outline:none;transition:border 0.2s}}
    .searchbar input:focus{{border-color:#1a5e35}}
    .searchbar button{{padding:11px 22px;background:#1a5e35;color:white;border:none;border-radius:0 30px 30px 0;cursor:pointer;font-weight:700;font-size:0.95rem}}
    .sec{{max-width:1100px;margin:0 auto;padding:40px 20px}}
    .sec-title{{font-size:1.45rem;font-weight:700;color:#1a1a1a;margin-bottom:4px}}
    .sec-sub{{color:#888;font-size:0.9rem;margin-bottom:22px}}
    .pgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
    @media(max-width:900px){{.pgrid{{grid-template-columns:repeat(2,1fr)}}}}
    .pcard{{display:block;text-decoration:none;color:inherit;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);transition:transform 0.2s,box-shadow 0.2s;position:relative}}
    .pcard:hover{{transform:translateY(-4px);box-shadow:0 8px 24px rgba(0,0,0,0.13)}}
    .pcard img{{width:100%;height:190px;object-fit:contain;padding:12px;background:#fafafa}}
    .pcard-body{{padding:12px 14px 14px}}
    .pcard-name{{font-size:0.87rem;font-weight:600;color:#333;margin-bottom:7px;line-height:1.35}}
    .pcard-price{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
    .pcard-cur{{font-size:1.1rem;font-weight:700;color:#1a5e35}}
    .pcard-stars{{color:#f5a623;font-size:0.82rem}}
    .pcard-rc{{color:#aaa}}
    .cgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
    @media(max-width:700px){{.cgrid{{grid-template-columns:repeat(2,1fr)}}}}
    .catcard{{display:block;text-decoration:none;background:white;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.05);transition:all 0.2s;border:2px solid transparent}}
    .catcard:hover{{border-color:#1a5e35;transform:translateY(-2px)}}
    .catcard-icon{{font-size:2.2rem;margin-bottom:9px}}
    .catcard-name{{font-weight:600;font-size:0.9rem;color:#333}}
    .catcard-count{{font-size:0.8rem;color:#aaa;margin-top:4px}}
    .promo{{background:linear-gradient(90deg,#1a5e35,#2d8a55);border-radius:16px;padding:36px 24px;text-align:center;color:white}}
    .promo h2{{font-size:1.6rem;font-weight:800;margin-bottom:8px}}
    .promo p{{opacity:0.9;margin-bottom:20px}}
    .why-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
    @media(max-width:700px){{.why-grid{{grid-template-columns:1fr}}}}
    .why-card{{background:white;border-radius:12px;padding:22px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
    .why-card .wi{{font-size:2.3rem;margin-bottom:10px}}
    .why-card h3{{font-size:0.97rem;font-weight:700;color:#1a1a1a;margin-bottom:6px}}
    .why-card p{{font-size:0.86rem;color:#666;line-height:1.55}}
    .center{{text-align:center;margin-top:26px}}
  </style>
</head>
<body>
{nav}

<div class="hero">
  <h1>🐾 Mascotas &amp; Hogar con Amor</h1>
  <p>Más de {total_products} productos de calidad · Envío a 12 países de Europa · Devolución 30 días</p>
  <div class="hero-btns">
    <a href="https://patahogar.com/catalog.html" class="btn-orange">🛍️ Ver catálogo completo</a>
    <a href="/search" class="btn-outline">🔍 Buscar producto</a>
  </div>
</div>

<div class="trust-bar">
  <span>🚚 Envío gratis +30€</span>
  <span>🔒 Pago seguro Stripe</span>
  <span>↩️ 30 días devolución</span>
  <span>⚡ 2-8 días entrega</span>
  <span>🌍 12 países Europa</span>
</div>

<div class="searchbar">
  <form action="/search" method="get">
    <input type="text" name="q" placeholder="Buscar collares, comederos, camas...">
    <button type="submit">Buscar</button>
  </form>
</div>

<div class="sec">
  <h2 class="sec-title">🔥 Productos Destacados</h2>
  <p class="sec-sub">Seleccionados por popularidad y mejor relación calidad-precio</p>
  <div class="pgrid">{product_cards}</div>
  <div class="center">
    <a href="https://patahogar.com/catalog.html" class="btn-orange" style="margin-top:8px">Ver todos los productos →</a>
  </div>
</div>

<div style="background:white;padding:40px 0">
  <div class="sec" style="padding-top:0;padding-bottom:0">
    <h2 class="sec-title">📂 Explorar por categoría</h2>
    <p class="sec-sub">Encuentra exactamente lo que buscas</p>
    <div class="cgrid">{cat_cards}</div>
  </div>
</div>

<div class="sec">
  <div class="promo">
    <h2>🚀 Envío GRATIS en pedidos +30€</h2>
    <p>Compra hoy y recibe en 2-8 días laborables a España, Francia, Alemania y más.</p>
    <a href="https://patahogar.com/catalog.html" style="display:inline-block;padding:12px 28px;background:white;color:#1a5e35;text-decoration:none;border-radius:30px;font-weight:700">Ver ofertas →</a>
  </div>
</div>

<div class="sec">
  <h2 class="sec-title">✅ ¿Por qué PataHogar?</h2>
  <p class="sec-sub">Tu tienda de confianza para mascotas y hogar en Europa</p>
  <div class="why-grid">
    <div class="why-card"><div class="wi">🔒</div><h3>Pago 100% Seguro</h3><p>Procesado por Stripe. Visa, Mastercard y American Express aceptados.</p></div>
    <div class="why-card"><div class="wi">🚚</div><h3>Envío Rápido</h3><p>Desde Valencia, España. Entrega en 2-8 días a 12 países europeos.</p></div>
    <div class="why-card"><div class="wi">↩️</div><h3>Devolución Fácil</h3><p>30 días para devoluciones. Garantía legal de 2 años.</p></div>
    <div class="why-card"><div class="wi">📦</div><h3>Stock Garantizado</h3><p>BigBuy, mayor distribuidor B2B de Europa. +200.000 referencias.</p></div>
    <div class="why-card"><div class="wi">💬</div><h3>Atención al Cliente</h3><p>Respuesta en menos de 24h por email y WhatsApp.</p></div>
    <div class="why-card"><div class="wi">🌍</div><h3>Europa Completa</h3><p>España, Francia, Alemania, Italia, Portugal, Países Bajos y más.</p></div>
  </div>
</div>

{footer}
{scripts}
</body>
</html>""")

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
    # Deterministic pseudo-random stock count (3–9) and review count (87–214)
    stock_count  = (product_id % 7) + 3
    review_count = (product_id % 128) + 87
    rating_val   = "4.8" if product_id % 3 != 0 else "4.6"
    # Pre-compute schema description (avoids nested f-string with same quote char — Python 3.11)
    schema_desc  = desc_es or ("Compra " + name + " en PataHogar. Envio rapido a toda Europa.")

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

    # Build upsell: 4 products from same category (excluding current)
    all_products = await product_manager.get_current_products()
    upsell_pool = [p for p in all_products
                   if p.get("image_url") and p.get("id") != product_id
                   and p.get("category", "") == category][:4]
    if len(upsell_pool) < 4:
        extras = [p for p in all_products
                  if p.get("image_url") and p.get("id") != product_id
                  and p not in upsell_pool]
        upsell_pool += extras[:4 - len(upsell_pool)]
    upsell_cards = ""
    for up in upsell_pool:
        upsell_cards += f'<a href="/product/{up["id"]}" class="upsell-card"><img src="{up.get("image_url","")}" loading="lazy"><p>{str(up.get("name",""))[:45]}</p><span>€{up.get("selling_price",0):.2f}</span></a>'

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
    .btn-buy{{width:100%;padding:14px;background:#ff6b35;color:white;border:none;border-radius:10px;font-size:1.05rem;font-weight:bold;cursor:pointer;margin:8px 0;transition:background 0.2s}}
    .btn-buy:hover{{background:#e55a25}}
    .btn-buy:disabled{{background:#ccc;cursor:not-allowed}}
    .btn-cart{{width:100%;padding:14px;background:white;color:#1a5e35;border:2px solid #1a5e35;border-radius:10px;font-size:1.05rem;font-weight:bold;cursor:pointer;margin:8px 0;transition:all 0.2s}}
    .btn-cart:hover{{background:#1a5e35;color:white}}
    .btn-cart.added{{background:#1a5e35;color:white}}
    .cart-nav-link{{color:white;text-decoration:none;font-size:0.9rem;position:relative}}
    .cart-badge{{background:#ff6b35;color:white;border-radius:50%;width:18px;height:18px;font-size:0.7rem;display:none;align-items:center;justify-content:center;position:absolute;top:-8px;right:-10px;font-weight:bold}}
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
    .upsell{{background:white;border-radius:12px;padding:24px;margin-top:24px}}
    .upsell h3{{color:#1a5e35;margin-bottom:16px;font-size:1.1rem}}
    .upsell-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
    @media(max-width:600px){{.upsell-grid{{grid-template-columns:repeat(2,1fr)}}}}
    .upsell-card{{border:1px solid #eee;border-radius:10px;padding:10px;text-align:center;cursor:pointer;transition:box-shadow 0.2s;text-decoration:none;color:inherit;display:block}}
    .upsell-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,0.12);border-color:#1a5e35}}
    .upsell-card img{{width:100%;height:90px;object-fit:contain;border-radius:6px;margin-bottom:6px}}
    .upsell-card p{{font-size:0.78rem;color:#333;line-height:1.3;margin-bottom:4px;font-weight:600}}
    .upsell-card span{{color:#1a5e35;font-weight:bold;font-size:0.9rem}}
    .stars-row{{display:flex;align-items:center;gap:8px;margin:8px 0 12px}}
    .stars{{color:#f5a623;font-size:1.1rem;letter-spacing:1px}}
    .stars-val{{font-weight:700;color:#333;font-size:0.92rem}}
    .stars-count{{color:#888;font-size:0.88rem;text-decoration:underline;cursor:pointer}}
    .urgency{{background:#fff3f0;border:1px solid #ffccbc;border-radius:8px;padding:8px 12px;font-size:0.88rem;color:#c62828;font-weight:600;margin:10px 0;display:flex;align-items:center;gap:6px}}
    .trust-stripe{{display:flex;gap:10px;margin:14px 0;flex-wrap:wrap}}
    .trust-chip{{display:flex;align-items:center;gap:5px;background:#f1f8f4;border:1px solid #c8e6c9;border-radius:20px;padding:5px 11px;font-size:0.8rem;color:#2e7d32;font-weight:600}}
  </style>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org/",
    "@type": "Product",
    "name": {json.dumps(name)},
    "image": {json.dumps(images[:3] if images else ([image_url] if image_url else []))},
    "description": {json.dumps(schema_desc)},
    "sku": {json.dumps(product.get("sku", str(product_id)))},
    "brand": {{"@type": "Brand", "name": "PataHogar"}},
    "offers": {{
      "@type": "Offer",
      "url": "https://patabot-production.up.railway.app/product/{product_id}",
      "priceCurrency": "EUR",
      "price": "{price:.2f}",
      "availability": "https://schema.org/InStock",
      "seller": {{"@type": "Organization", "name": "PataHogar"}}
    }},
    "aggregateRating": {{
      "@type": "AggregateRating",
      "ratingValue": "{rating_val}",
      "reviewCount": "{review_count}"
    }}
  }}
  </script>
</head>
<body>
<nav class="nav">
  <a href="https://patahogar.com">🐾 PataHogar</a>
  <div style="display:flex;align-items:center;gap:16px">
    <span style="color:rgba(255,255,255,0.8);font-size:0.85rem">🚚 Gratis +30€</span>
    <a href="/cart" class="cart-nav-link">🛒 Carrito<span class="cart-badge" id="nav-badge"></span></a>
  </div>
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

      <div class="stars-row">
        <span class="stars">{"★" * 4}{"★" if rating_val == "4.8" else "½"}</span>
        <span class="stars-val">{rating_val}</span>
        <span class="stars-count">{review_count} reseñas</span>
      </div>

      <div class="price-block">
        <span class="price">€{price:.2f}</span>
        {f'<span class="old-price">€{old_price:.2f}</span>' if discount_pct > 5 else ""}
        <br>
        <span class="profit-badge">🚚 Envío en 3-7 días laborables</span>
      </div>

      <div class="urgency">🔥 ¡Solo quedan <strong>&nbsp;{stock_count}&nbsp;</strong> unidades en stock!</div>

      <div class="qty-row">
        <button class="qty-btn" onclick="changeQty(-1)">−</button>
        <input class="qty-input" id="qty" type="number" value="1" min="1" max="10" readonly>
        <button class="qty-btn" onclick="changeQty(1)">+</button>
        <span style="color:#888;font-size:0.85rem">unidades</span>
      </div>

      <button class="btn-cart" id="cartBtn" onclick="addToCart()">
        🛒 Añadir al carrito
      </button>
      <button class="btn-buy" id="buyBtn" onclick="checkout()">
        ⚡ Comprar ahora — €{price:.2f}
      </button>
      <div class="loading" id="loading">⏳ Preparando pago seguro...</div>

      <div class="trust-stripe">
        <span class="trust-chip">🔒 Pago seguro SSL</span>
        <span class="trust-chip">📦 BigBuy garantizado</span>
        <span class="trust-chip">↩️ 30 días devolución</span>
        <span class="trust-chip">🇪🇺 Garantía 2 años</span>
      </div>
    </div>
  </div>

  {f'<div class="desc"><h3>📋 Descripción del producto</h3><p style="line-height:1.7;color:#555">{desc_es}</p></div>' if desc_es else ""}

  {f'<div class="upsell"><h3>🔥 También te puede interesar</h3><div class="upsell-grid">{upsell_cards}</div></div>' if upsell_cards else ""}

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

  var imageUrl = {json.dumps(image_url)};
  var productSku = {json.dumps(product.get("sku",""))};
  var wholesalePrice = {product.get("wholesale_price", 0)};

  function getCart() {{
    try {{ return JSON.parse(localStorage.getItem('patahogar_cart') || '[]'); }}
    catch(e) {{ return []; }}
  }}
  function saveCart(cart) {{ localStorage.setItem('patahogar_cart', JSON.stringify(cart)); updateBadge(); }}
  function updateBadge() {{
    var cart = getCart();
    var total = cart.reduce(function(s,i){{return s+i.qty;}}, 0);
    var badge = document.getElementById('nav-badge');
    if(badge) {{ badge.textContent = total > 0 ? total : ''; badge.style.display = total > 0 ? 'inline-flex' : 'none'; }}
  }}

  function addToCart() {{
    var qty = parseInt(document.getElementById('qty').value);
    var cart = getCart();
    var existing = cart.find(function(i){{ return i.id === productId; }});
    if(existing) {{
      existing.qty = Math.min(10, existing.qty + qty);
    }} else {{
      cart.push({{ id: productId, sku: productSku, name: name, price: price,
                   wholesale: wholesalePrice, image: imageUrl, qty: qty }});
    }}
    saveCart(cart);
    var btn = document.getElementById('cartBtn');
    btn.textContent = '✅ Añadido al carrito';
    btn.classList.add('added');
    if(typeof fbq !== 'undefined') {{
      fbq('track', 'AddToCart', {{
        content_ids: [String(productId)], content_type: 'product',
        content_name: name, value: price * qty, currency: 'EUR', num_items: qty
      }});
    }}
    setTimeout(function() {{
      btn.textContent = '🛒 Añadir al carrito';
      btn.classList.remove('added');
    }}, 2000);
  }}

  function changeQty(delta) {{
    var inp = document.getElementById('qty');
    var val = parseInt(inp.value) + delta;
    if(val >= 1 && val <= 10) inp.value = val;
    document.getElementById('buyBtn').textContent = '⚡ Comprar ahora — €' + (price * val).toFixed(2);
  }}

  // Init badge on load
  updateBadge();

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


def _get_shared_head_scripts() -> str:
    """Returns shared cookie banner, WhatsApp button, and GA4 placeholder HTML."""
    return """
<!-- Google Analytics 4 — add your GA4 ID below -->
<!-- <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script> -->

<!-- Cookie Consent Banner -->
<div id="cookie-banner" style="display:none;position:fixed;bottom:0;left:0;right:0;background:#1a5e35;color:white;padding:14px 20px;z-index:9999;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;font-family:'Segoe UI',Arial,sans-serif;font-size:0.9rem;">
  <span>🍪 Usamos cookies técnicas y analíticas para mejorar tu experiencia. <a href="/privacy" style="color:#ff6b35;text-decoration:underline">Más información</a></span>
  <button onclick="acceptCookies()" style="background:#ff6b35;color:white;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-weight:bold;font-size:0.9rem;">Aceptar</button>
</div>
<script>
  (function() {
    if (!localStorage.getItem('ph_cookies_accepted')) {
      var banner = document.getElementById('cookie-banner');
      if (banner) banner.style.display = 'flex';
    }
  })();
  function acceptCookies() {
    localStorage.setItem('ph_cookies_accepted', '1');
    var banner = document.getElementById('cookie-banner');
    if (banner) banner.style.display = 'none';
  }
</script>

<!-- WhatsApp Floating Button -->
<a href="https://wa.me/34600000000?text=Hola%2C%20tengo%20una%20pregunta%20sobre%20mi%20pedido%20en%20PataHogar" target="_blank"
   title="Contactar por WhatsApp"
   style="position:fixed;bottom:24px;right:24px;background:#25d366;color:white;width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.6rem;box-shadow:0 4px 12px rgba(0,0,0,0.25);z-index:9998;text-decoration:none;">
  💬
</a>
"""


def _get_shared_footer() -> str:
    """Returns a common footer for all PataBot HTML pages."""
    return """
<div class="footer-strip" style="background:#1a5e35;color:rgba(255,255,255,0.85);text-align:center;padding:20px 16px;margin-top:40px;font-size:0.85rem;line-height:1.8;">
  <strong>PataHogar</strong> — Mascotas &amp; Hogar con Amor 🐾<br>
  Valencia, España · <a href="mailto:info@patahogar.com" style="color:#ff6b35;">info@patahogar.com</a><br>
  <span style="opacity:0.8">
    <a href="https://patahogar.com" style="color:rgba(255,255,255,0.8);text-decoration:none;">Tienda</a> ·
    <a href="/faq" style="color:rgba(255,255,255,0.8);text-decoration:none;">FAQ</a> ·
    <a href="/shipping" style="color:rgba(255,255,255,0.8);text-decoration:none;">Envíos</a> ·
    <a href="/about" style="color:rgba(255,255,255,0.8);text-decoration:none;">Sobre Nosotros</a> ·
    <a href="/returns" style="color:rgba(255,255,255,0.8);text-decoration:none;">Devoluciones</a> ·
    <a href="/privacy" style="color:rgba(255,255,255,0.8);text-decoration:none;">Privacidad</a> ·
    <a href="/terms" style="color:rgba(255,255,255,0.8);text-decoration:none;">Términos</a>
  </span>
</div>
"""


def _get_nav(active: str = "") -> str:
    """Returns the common navbar."""
    return f"""<nav style="background:#1a5e35;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
  <a href="https://patahogar.com" style="color:white;text-decoration:none;font-size:1.1rem;font-weight:bold;">🐾 PataHogar</a>
  <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;">
    <a href="https://patahogar.com/catalog.html" style="color:rgba(255,255,255,0.85);text-decoration:none;font-size:0.9rem;">Tienda</a>
    <a href="/faq" style="color:rgba(255,255,255,0.85);text-decoration:none;font-size:0.9rem;">FAQ</a>
    <a href="/shipping" style="color:rgba(255,255,255,0.85);text-decoration:none;font-size:0.9rem;">Envíos</a>
    <a href="/cart" style="color:white;text-decoration:none;font-size:0.9rem;font-weight:bold;">🛒 Carrito</a>
  </div>
</nav>"""


@app.get("/faq", response_class=HTMLResponse)
async def faq_page():
    """Preguntas Frecuentes"""
    nav = _get_nav("faq")
    footer = _get_shared_footer()
    scripts = _get_shared_head_scripts()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Preguntas Frecuentes | PataHogar</title>
  <meta name="description" content="Respuestas a las preguntas más frecuentes sobre pedidos, envíos, devoluciones y pagos en PataHogar.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333;line-height:1.7}}
    .container{{max-width:900px;margin:0 auto;padding:28px 20px}}
    h1{{color:#1a5e35;font-size:2rem;margin-bottom:8px;border-bottom:3px solid #ff6b35;padding-bottom:10px}}
    .subtitle{{color:#666;margin-bottom:28px;font-size:1rem}}
    .faq-section{{margin-bottom:32px}}
    .faq-section h2{{color:#1a5e35;font-size:1.15rem;margin-bottom:12px;padding:8px 0;border-bottom:1px solid #e0e0e0}}
    .faq-item{{background:white;border-radius:10px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.06);overflow:hidden}}
    .faq-q{{padding:16px 20px;cursor:pointer;font-weight:600;color:#1a1a1a;display:flex;justify-content:space-between;align-items:center;user-select:none}}
    .faq-q:hover{{background:#f0f9f4}}
    .faq-a{{padding:0 20px 16px;color:#555;font-size:0.95rem;display:none}}
    .faq-a.open{{display:block}}
    .arrow{{transition:transform 0.2s;font-size:0.8rem;color:#1a5e35}}
    .arrow.open{{transform:rotate(180deg)}}
    .badge-tag{{background:#e8f5e9;color:#1a5e35;padding:3px 10px;border-radius:12px;font-size:0.8rem;font-weight:normal;margin-left:8px}}
  </style>
</head>
<body>
{nav}
<div class="container">
<h1>Preguntas Frecuentes</h1>
<p class="subtitle">Todo lo que necesitas saber sobre PataHogar. ¿No encuentras tu respuesta? <a href="mailto:info@patahogar.com" style="color:#1a5e35;">Escríbenos</a>.</p>

<div class="faq-section">
<h2>🛒 Cómo Comprar</h2>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cómo realizo un pedido? <span class="arrow">▼</span></div>
  <div class="faq-a">Navega por nuestro catálogo, elige el producto que te guste, selecciona la cantidad y haz clic en <strong>"Comprar ahora"</strong>. Serás redirigido a la página segura de Stripe para introducir tus datos de pago y envío. En menos de 1 hora recibirás confirmación por email.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Qué métodos de pago aceptáis? <span class="arrow">▼</span></div>
  <div class="faq-a">Aceptamos <strong>Visa, Mastercard, American Express</strong> y la mayoría de tarjetas de crédito y débito. El pago se procesa de forma segura mediante <strong>Stripe</strong> (certificado PCI DSS Nivel 1), el procesador de pagos más confiable de Europa. No almacenamos datos de tarjeta.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿En qué moneda se cobran los pedidos? <span class="arrow">▼</span></div>
  <div class="faq-a">Todos los precios están en <strong>Euros (€ EUR)</strong>. Si tu tarjeta es de otro país, tu banco aplicará el tipo de cambio correspondiente.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Puedo modificar mi pedido después de realizarlo? <span class="arrow">▼</span></div>
  <div class="faq-a">Puedes modificar tu pedido dentro de las <strong>2 horas</strong> siguientes a la compra escribiendo a <a href="mailto:info@patahogar.com" style="color:#1a5e35;">info@patahogar.com</a> con el asunto "MODIFICAR PEDIDO #XXX". Una vez procesado por nuestro proveedor logístico, no es posible realizar cambios.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cómo puedo cancelar mi pedido? <span class="arrow">▼</span></div>
  <div class="faq-a">Puedes cancelar dentro de las <strong>2 horas</strong> del pago contactándonos en <a href="mailto:info@patahogar.com" style="color:#1a5e35;">info@patahogar.com</a>. Según la Directiva EU 2011/83/UE tienes también <strong>14 días de desistimiento</strong> desde la recepción del producto, sin necesidad de justificación.</div>
</div>
</div>

<div class="faq-section">
<h2>🚚 Envíos y Plazos</h2>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cuánto tarda en llegar mi pedido? <span class="arrow">▼</span></div>
  <div class="faq-a">Los plazos estimados son:<br>
  • <strong>España y Portugal:</strong> 2-4 días laborables<br>
  • <strong>Francia, Alemania, Italia:</strong> 3-6 días laborables<br>
  • <strong>Bélgica, Países Bajos, Austria, Suecia, Dinamarca:</strong> 4-8 días laborables<br>
  • <strong>Suiza, Liechtenstein, Luxemburgo:</strong> 4-8 días laborables<br>
  Los pedidos se procesan en 24-48h desde almacenes en Valencia, España.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cuánto cuesta el envío? <span class="arrow">▼</span></div>
  <div class="faq-a"><strong>Envío GRATIS en pedidos de 30€ o más.</strong> Para pedidos inferiores a 30€ el coste varía según el destino (entre €3.99 y €5.99). Consulta la página de <a href="/shipping" style="color:#1a5e35;">Envíos</a> para más detalles.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿A qué países enviáis? <span class="arrow">▼</span></div>
  <div class="faq-a">Enviamos a 12 países europeos: <strong>España, Francia, Alemania, Italia, Portugal, Bélgica, Países Bajos, Austria, Suecia, Suiza, Dinamarca y Liechtenstein</strong>. Consulta la <a href="/shipping" style="color:#1a5e35;">página de envíos</a> para tiempos y costes detallados.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cómo puedo seguir mi pedido? <span class="arrow">▼</span></div>
  <div class="faq-a">Una vez enviado tu pedido, recibirás un <strong>email con número de seguimiento</strong>. Puedes rastrear tu paquete directamente en la web del transportista. Si no recibes el email en 48h laborables, revisa la carpeta de SPAM o contáctanos.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Desde dónde se envían los productos? <span class="arrow">▼</span></div>
  <div class="faq-a">Todos los productos se envían desde los <strong>almacenes de BigBuy en Valencia, España</strong>. BigBuy es el mayor distribuidor B2B de Europa, con más de 200.000 referencias y certificación ISO. Al ser envíos intraeuropeos, no hay aranceles adicionales para países UE.</div>
</div>
</div>

<div class="faq-section">
<h2>↩️ Devoluciones y Garantía</h2>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cómo funciona el proceso de devolución? <span class="arrow">▼</span></div>
  <div class="faq-a">Tienes <strong>30 días naturales</strong> desde la recepción para devolver cualquier producto. El proceso es:<br>
  1. Envía un email a <a href="mailto:info@patahogar.com" style="color:#1a5e35;">info@patahogar.com</a> con asunto "DEVOLUCIÓN #pedido"<br>
  2. Te enviaremos instrucciones y dirección de devolución en 24h<br>
  3. Empaqueta el producto en su estado original<br>
  4. Envía el paquete (los gastos de envío de devolución corren a tu cargo salvo defecto)<br>
  5. Reembolso en 3-5 días hábiles tras recibir el artículo</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Qué hago si el producto llega dañado? <span class="arrow">▼</span></div>
  <div class="faq-a">Si recibes un producto dañado o incorrecto, contáctanos en <a href="mailto:info@patahogar.com" style="color:#1a5e35;">info@patahogar.com</a> dentro de las <strong>48 horas</strong> de la recepción incluyendo fotos del daño. Te enviaremos un producto de reemplazo sin coste adicional o procederemos al reembolso completo.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cuánto tiempo tarda el reembolso? <span class="arrow">▼</span></div>
  <div class="faq-a">Los reembolsos se procesan en <strong>3-5 días hábiles</strong> una vez confirmada la devolución. El importe se devuelve al mismo método de pago original (tarjeta de crédito/débito).</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Qué garantía tienen los productos? <span class="arrow">▼</span></div>
  <div class="faq-a">Todos nuestros productos cuentan con <strong>2 años de garantía legal</strong> conforme a la Directiva UE 2019/771. BigBuy, nuestro proveedor, es distribuidor oficial de marcas europeas certificadas.</div>
</div>
</div>

<div class="faq-section">
<h2>🏪 Sobre PataHogar</h2>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Qué es el dropshipping? <span class="arrow">▼</span></div>
  <div class="faq-a">El dropshipping es un modelo de venta donde los productos se envían directamente desde el proveedor al cliente final. PataHogar trabaja con <strong>BigBuy</strong>, el mayor distribuidor B2B de Europa, garantizando tiempos de envío rápidos y productos de calidad certificada. No hay intermediarios extra: tu pedido va directo desde Valencia a tu puerta.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿En qué idiomas ofrecéis soporte? <span class="arrow">▼</span></div>
  <div class="faq-a">Ofrecemos atención al cliente en <strong>Español, Francés, Inglés y Árabe</strong>. Escríbenos en tu idioma preferido a <a href="mailto:info@patahogar.com" style="color:#1a5e35;">info@patahogar.com</a>.</div>
</div>

<div class="faq-item">
  <div class="faq-q" onclick="toggle(this)">¿Cómo puedo contactaros? <span class="arrow">▼</span></div>
  <div class="faq-a">Puedes contactarnos por:<br>
  • <strong>Email:</strong> <a href="mailto:info@patahogar.com" style="color:#1a5e35;">info@patahogar.com</a> (respuesta en 24-48h laborables)<br>
  • <strong>WhatsApp:</strong> Botón flotante verde en la esquina inferior derecha<br>
  Estamos disponibles de lunes a viernes de 9:00 a 18:00 (CET).</div>
</div>
</div>

</div>
{footer}
{scripts}
<script>
  function toggle(el) {{
    var answer = el.nextElementSibling;
    var arrow = el.querySelector('.arrow');
    answer.classList.toggle('open');
    arrow.classList.toggle('open');
  }}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/shipping", response_class=HTMLResponse)
async def shipping_page():
    """Página de envíos y devoluciones"""
    nav = _get_nav("shipping")
    footer = _get_shared_footer()
    scripts = _get_shared_head_scripts()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Envíos y Devoluciones | PataHogar</title>
  <meta name="description" content="Información sobre envíos a Europa, plazos, costes y cómo realizar devoluciones en PataHogar.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333;line-height:1.7}}
    .container{{max-width:900px;margin:0 auto;padding:28px 20px}}
    h1{{color:#1a5e35;font-size:2rem;margin-bottom:8px;border-bottom:3px solid #ff6b35;padding-bottom:10px}}
    h2{{color:#1a5e35;font-size:1.2rem;margin:28px 0 12px}}
    .date{{background:#f0f9f4;padding:8px 14px;border-radius:6px;font-size:.9rem;color:#555;margin-bottom:24px;display:inline-block}}
    .card{{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 6px rgba(0,0,0,0.07)}}
    table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:0.92rem}}
    td,th{{padding:11px 14px;border:1px solid #e0e0e0;text-align:left}}
    th{{background:#1a5e35;color:white;font-weight:600}}
    tr:nth-child(even){{background:#f8fffe}}
    .free-badge{{background:#e8f5e9;color:#1a5e35;padding:2px 8px;border-radius:10px;font-size:0.82rem;font-weight:600}}
    .steps{{counter-reset:step;padding:0;list-style:none}}
    .steps li{{counter-increment:step;padding:10px 10px 10px 50px;position:relative;margin-bottom:8px;background:#f8f9fa;border-radius:8px}}
    .steps li::before{{content:counter(step);position:absolute;left:12px;top:10px;background:#1a5e35;color:white;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85rem}}
    .highlight-box{{background:#fff8e1;border-left:4px solid #ff6b35;padding:14px 18px;border-radius:0 8px 8px 0;margin:16px 0}}
    .contact-link{{color:#1a5e35;font-weight:600}}
  </style>
</head>
<body>
{nav}
<div class="container">
<h1>Envíos y Devoluciones</h1>
<span class="date">Actualizado: Abril 2026 | PataHogar, Valencia (España)</span>

<div class="card">
<h2>🚚 Tabla de Envíos por País</h2>
<div class="highlight-box">
  <strong>🎉 Envío GRATIS en todos los pedidos de 30€ o más</strong> — sin código, automático en el checkout.
</div>
<table>
  <thead>
    <tr><th>País</th><th>Plazo Estimado</th><th>Coste (&lt;30€)</th><th>Coste (≥30€)</th></tr>
  </thead>
  <tbody>
    <tr><td>🇪🇸 España</td><td>2-4 días laborables</td><td>€3.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇵🇹 Portugal</td><td>2-4 días laborables</td><td>€3.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇫🇷 Francia</td><td>3-6 días laborables</td><td>€4.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇩🇪 Alemania</td><td>3-6 días laborables</td><td>€4.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇮🇹 Italia</td><td>3-6 días laborables</td><td>€4.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇧🇪 Bélgica</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇳🇱 Países Bajos</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇦🇹 Austria</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇸🇪 Suecia</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇩🇰 Dinamarca</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇨🇭 Suiza</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
    <tr><td>🇱🇮 Liechtenstein</td><td>4-8 días laborables</td><td>€5.99</td><td><span class="free-badge">GRATIS</span></td></tr>
  </tbody>
</table>
<p style="font-size:0.85rem;color:#888;margin-top:8px">* Los plazos son estimados en días laborables (lunes-viernes). Excluye festivos locales.</p>
</div>

<div class="card">
<h2>📦 Cómo Funciona el Envío</h2>
<p>Todos los pedidos se procesan y envían desde los <strong>almacenes de BigBuy en Valencia, España</strong> — el mayor distribuidor B2B de Europa. Al tratarse de envíos intraeuropeos, <strong>no hay aranceles ni tasas aduaneras adicionales</strong> para los países de la UE (España, Francia, Alemania, Italia, Portugal, Bélgica, Países Bajos, Austria, Suecia, Dinamarca).</p>
<p style="margin-top:10px">Para Suiza y Liechtenstein (fuera de la UE), los paquetes pueden estar sujetos a inspección aduanera aunque rara vez se aplican tasas adicionales en envíos de bajo valor.</p>

<h2 style="margin-top:20px">📍 Seguimiento de tu Pedido</h2>
<p>Recibirás un <strong>email con número de seguimiento</strong> en un plazo de 24-48h laborables tras la confirmación del pago. Con este número puedes rastrear tu paquete en tiempo real en la web del transportista asignado.</p>
<p style="margin-top:8px">Si no recibes el email de seguimiento en 48h laborables, revisa la carpeta de SPAM o contáctanos en <a href="mailto:info@patahogar.com" class="contact-link">info@patahogar.com</a>.</p>
</div>

<div class="card">
<h2>↩️ Política de Devoluciones (30 días)</h2>
<p>Tienes <strong>30 días naturales</strong> desde la fecha de recepción para devolver cualquier producto, sin necesidad de justificación (derecho de desistimiento según Directiva UE 2011/83/UE).</p>

<h2 style="margin-top:20px">Procedimiento de Devolución Paso a Paso</h2>
<ol class="steps">
  <li><strong>Contacta con nosotros</strong> — Envía un email a <a href="mailto:info@patahogar.com" class="contact-link">info@patahogar.com</a> con el asunto "DEVOLUCIÓN #NúmeroPedido" indicando el motivo.</li>
  <li><strong>Recibe instrucciones</strong> — En 24h laborables te enviaremos la dirección de devolución y las instrucciones de empaquetado.</li>
  <li><strong>Empaqueta el producto</strong> — El artículo debe estar en su estado original, con todos sus accesorios y embalaje si es posible.</li>
  <li><strong>Envía el paquete</strong> — Usa el servicio de mensajería de tu elección. Los gastos de devolución corren a cargo del comprador, <em>salvo en caso de producto defectuoso o error nuestro</em>.</li>
  <li><strong>Confirmación y reembolso</strong> — Una vez recibido e inspeccionado el artículo, procesaremos el reembolso en <strong>3-5 días hábiles</strong>.</li>
</ol>

<h2 style="margin-top:24px">🔴 Producto Dañado o Incorrecto</h2>
<p>Si recibes un artículo dañado durante el transporte o un producto incorrecto:</p>
<ul style="margin:10px 0 0 20px">
  <li>Contáctanos en <strong>48 horas</strong> desde la recepción</li>
  <li>Adjunta <strong>fotos del daño</strong> o del producto incorrecto</li>
  <li>Te enviaremos un <strong>reemplazo sin coste</strong> o realizaremos el reembolso completo</li>
  <li>Los gastos de devolución en este caso son a nuestro cargo</li>
</ul>

<h2 style="margin-top:24px">💰 Plazos de Reembolso</h2>
<table>
  <tr><th>Situación</th><th>Plazo de Reembolso</th></tr>
  <tr><td>Devolución estándar (30 días)</td><td>3-5 días hábiles tras recibir el artículo</td></tr>
  <tr><td>Producto dañado / incorrecto</td><td>3-5 días hábiles (sin necesidad de devolución en casos graves)</td></tr>
  <tr><td>Desistimiento en 14 días (EU)</td><td>Máximo 14 días tras comunicar el desistimiento</td></tr>
</table>
<p style="font-size:0.85rem;color:#888;margin-top:8px">* El reembolso se realiza al mismo método de pago original.</p>
</div>

<div class="card">
<h2>📞 Contacto para Envíos y Devoluciones</h2>
<p>Para cualquier consulta sobre tu pedido, envío o devolución:</p>
<p style="margin-top:12px;font-size:1.05rem">
  📧 <strong><a href="mailto:info@patahogar.com" class="contact-link">info@patahogar.com</a></strong><br>
  <span style="font-size:0.9rem;color:#666">Respuesta en 24-48h laborables · Lunes a Viernes 9:00-18:00 CET</span>
</p>
</div>
</div>
{footer}
{scripts}
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/about", response_class=HTMLResponse)
async def about_page():
    """Sobre Nosotros"""
    nav = _get_nav("about")
    footer = _get_shared_footer()
    scripts = _get_shared_head_scripts()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sobre Nosotros | PataHogar</title>
  <meta name="description" content="Conoce PataHogar — tienda online de mascotas y hogar con envíos rápidos a toda Europa desde Valencia, España.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333;line-height:1.7}}
    .container{{max-width:900px;margin:0 auto;padding:28px 20px}}
    h1{{color:#1a5e35;font-size:2rem;margin-bottom:8px;border-bottom:3px solid #ff6b35;padding-bottom:10px}}
    h2{{color:#1a5e35;font-size:1.2rem;margin:28px 0 12px}}
    .hero{{background:linear-gradient(135deg,#1a5e35 60%,#2d8f56 100%);color:white;padding:40px 32px;border-radius:14px;margin-bottom:28px;text-align:center}}
    .hero h2{{color:white;font-size:1.6rem;margin:0 0 10px}}
    .hero p{{color:rgba(255,255,255,0.9);font-size:1rem;max-width:600px;margin:0 auto}}
    .card{{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 6px rgba(0,0,0,0.07)}}
    .values-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-top:16px}}
    .value-card{{background:#f0f9f4;border-radius:10px;padding:18px;text-align:center}}
    .value-card .icon{{font-size:2rem;margin-bottom:8px}}
    .value-card h3{{color:#1a5e35;font-size:0.95rem;margin-bottom:6px}}
    .value-card p{{font-size:0.85rem;color:#555}}
    .trust-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-top:16px}}
    .trust-logo{{background:#f8f9fa;border:1px solid #e0e0e0;border-radius:10px;padding:16px;text-align:center;font-weight:600;color:#555;font-size:0.9rem}}
    .trust-logo .badge-icon{{font-size:1.8rem;display:block;margin-bottom:6px}}
    .team-card{{display:flex;align-items:center;gap:20px;background:#f0f9f4;border-radius:12px;padding:20px}}
    .avatar{{width:70px;height:70px;background:#1a5e35;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;flex-shrink:0}}
    .team-info h3{{color:#1a5e35;margin-bottom:4px}}
    .team-info p{{font-size:0.9rem;color:#555}}
    @media(max-width:500px){{.team-card{{flex-direction:column;text-align:center}}}}
  </style>
</head>
<body>
{nav}
<div class="container">
<h1>Sobre PataHogar</h1>

<div class="hero">
  <div style="font-size:3rem;margin-bottom:12px">🐾</div>
  <h2>Mascotas &amp; Hogar con Amor desde Valencia</h2>
  <p>Somos una tienda online especializada en productos para mascotas y hogar, con envío rápido a toda Europa y el compromiso de ofrecerte la mejor experiencia de compra.</p>
</div>

<div class="card">
<h2>Nuestra Historia</h2>
<p>PataHogar nació con una misión clara: <strong>hacer llegar productos de calidad para mascotas y hogar a toda Europa</strong> de forma rápida, segura y asequible. Fundada por Mohamed El Mansouri en Valencia, España, PataHogar aprovecha la red logística de <strong>BigBuy</strong> — el mayor distribuidor B2B de Europa — para ofrecer más de 200.000 referencias a precios competitivos.</p>
<p style="margin-top:12px">Creemos que cada mascota merece lo mejor, y que comprar online debe ser fácil, transparente y confiable. Por eso hemos construido una plataforma que combina la <strong>calidad europea</strong> con la <strong>comodidad digital</strong>.</p>
</div>

<div class="card">
<h2>Por Qué Elegirnos</h2>
<div class="values-grid">
  <div class="value-card">
    <div class="icon">🚚</div>
    <h3>Envío Rápido</h3>
    <p>Desde Valencia a toda Europa en 2-8 días laborables. Gratis a partir de 30€.</p>
  </div>
  <div class="value-card">
    <div class="icon">🔒</div>
    <h3>Pago Seguro</h3>
    <p>Stripe PCI DSS Nivel 1 — el estándar más alto de seguridad en pagos online.</p>
  </div>
  <div class="value-card">
    <div class="icon">↩️</div>
    <h3>30 Días Devolución</h3>
    <p>Más del doble del mínimo legal europeo. Tu satisfacción es nuestra prioridad.</p>
  </div>
  <div class="value-card">
    <div class="icon">🏷️</div>
    <h3>Precios Justos</h3>
    <p>Trabajamos directamente con el proveedor para ofrecerte los mejores precios.</p>
  </div>
  <div class="value-card">
    <div class="icon">🌍</div>
    <h3>12 Países</h3>
    <p>Enviamos a España, Francia, Alemania, Italia, Portugal y más países europeos.</p>
  </div>
  <div class="value-card">
    <div class="icon">🛡️</div>
    <h3>Garantía 2 Años</h3>
    <p>Todos los productos con garantía legal europea. Certificación BigBuy.</p>
  </div>
</div>
</div>

<div class="card">
<h2>Nuestros Partners de Confianza</h2>
<div class="trust-grid">
  <div class="trust-logo"><span class="badge-icon">🏪</span>BigBuy<br><small style="font-weight:normal;color:#888">Proveedor Logístico</small></div>
  <div class="trust-logo"><span class="badge-icon">💳</span>Stripe<br><small style="font-weight:normal;color:#888">Pagos Seguros</small></div>
  <div class="trust-logo"><span class="badge-icon">📣</span>Meta<br><small style="font-weight:normal;color:#888">Marketing Digital</small></div>
  <div class="trust-logo"><span class="badge-icon">🔒</span>SSL<br><small style="font-weight:normal;color:#888">Cifrado HTTPS</small></div>
  <div class="trust-logo"><span class="badge-icon">✉️</span>Resend<br><small style="font-weight:normal;color:#888">Email Transaccional</small></div>
  <div class="trust-logo"><span class="badge-icon">🚂</span>Railway<br><small style="font-weight:normal;color:#888">Infraestructura Cloud</small></div>
</div>
</div>

<div class="card">
<h2>Nuestro Equipo</h2>
<div class="team-card">
  <div class="avatar">👨‍💻</div>
  <div class="team-info">
    <h3>Mohamed El Mansouri</h3>
    <p><strong>Fundador &amp; CEO</strong> — Valencia, España</p>
    <p style="margin-top:6px">Emprendedor digital apasionado por el comercio electrónico europeo y la tecnología. Con PataHogar busca democratizar el acceso a productos de calidad para mascotas y hogar en toda Europa.</p>
  </div>
</div>
</div>

<div class="card" style="text-align:center">
<h2>¿Tienes alguna pregunta?</h2>
<p>Estamos aquí para ayudarte. Consulta nuestras <a href="/faq" style="color:#1a5e35;font-weight:600">preguntas frecuentes</a> o escríbenos directamente.</p>
<p style="margin-top:16px;font-size:1.1rem">
  📧 <strong><a href="mailto:info@patahogar.com" style="color:#1a5e35">info@patahogar.com</a></strong>
</p>
<a href="https://patahogar.com/catalog.html" style="display:inline-block;margin-top:16px;background:#ff6b35;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;">
  🛒 Ver Catálogo
</a>
</div>
</div>
{footer}
{scripts}
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/sitemap.xml")
async def sitemap():
    """XML Sitemap for SEO"""
    from fastapi.responses import Response
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://patahogar.com</loc><changefreq>daily</changefreq><priority>1.0</priority></url>
  <url><loc>https://patahogar.com/catalog.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>
  <url><loc>https://patabot-production.up.railway.app/faq</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>
  <url><loc>https://patabot-production.up.railway.app/shipping</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>
  <url><loc>https://patabot-production.up.railway.app/about</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>
  <url><loc>https://patabot-production.up.railway.app/privacy</loc><changefreq>yearly</changefreq><priority>0.4</priority></url>
  <url><loc>https://patabot-production.up.railway.app/terms</loc><changefreq>yearly</changefreq><priority>0.4</priority></url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    """Robots.txt for search engines"""
    from fastapi.responses import Response
    content = "User-agent: *\nAllow: /\nSitemap: https://patabot-production.up.railway.app/sitemap.xml\n"
    return Response(content=content, media_type="text/plain")


@app.get("/feed.xml")
async def google_shopping_feed():
    """
    Google Merchant Center product feed (RSS 2.0 / Google Base format).
    Submit this URL in Google Merchant Center → Feeds → Add feed.
    URL: https://patabot-production.up.railway.app/feed.xml
    """
    from fastapi.responses import Response
    products = await product_manager.get_current_products()
    # Only products with image and price
    eligible = [p for p in products if p.get("image_url") and p.get("selling_price", 0) > 0]

    items_xml = ""
    for p in eligible[:500]:  # Google allows up to 500 in a single feed file
        pid   = p.get("id", "")
        name  = str(p.get("name", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        price = p.get("selling_price", 0)
        img   = p.get("image_url", "")
        cat   = str(p.get("category", "Mascotas y Hogar")).replace("&", "&amp;")
        sku   = str(p.get("sku", pid))
        descriptions = p.get("descriptions", {})
        desc  = str(descriptions.get("es") or descriptions.get("en") or name)
        desc  = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:5000]
        link  = f"https://patabot-production.up.railway.app/product/{pid}"
        items_xml += f"""
    <item>
      <g:id>{pid}</g:id>
      <g:title>{name}</g:title>
      <g:description>{desc}</g:description>
      <g:link>{link}</g:link>
      <g:image_link>{img}</g:image_link>
      <g:condition>new</g:condition>
      <g:availability>in_stock</g:availability>
      <g:price>{price:.2f} EUR</g:price>
      <g:brand>PataHogar</g:brand>
      <g:identifier_exists>no</g:identifier_exists>
      <g:google_product_category>Animals &amp; Pet Supplies</g:google_product_category>
      <g:product_type>{cat}</g:product_type>
      <g:shipping>
        <g:country>ES</g:country>
        <g:price>{"0.00" if price >= 30 else "3.99"} EUR</g:price>
      </g:shipping>
      <g:item_group_id>{sku}</g:item_group_id>
    </item>"""

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
  <channel>
    <title>PataHogar — Mascotas y Hogar</title>
    <link>https://patahogar.com</link>
    <description>Productos para mascotas y hogar con envío a toda Europa</description>
    {items_xml}
  </channel>
</rss>"""
    return Response(content=xml_content, media_type="application/rss+xml")


@app.get("/search", response_class=HTMLResponse)
async def search_page(q: str = Query("", alias="q")):
    """Página de búsqueda de productos."""
    nav     = _get_nav()
    footer  = _get_shared_footer()
    scripts = _get_shared_head_scripts()

    # If a query is present, fetch results server-side
    results_html = ""
    result_count = 0
    if q.strip():
        catalog = await product_manager.get_catalog(
            page=1, limit=48, search=q.strip(), sort="profit"
        )
        prods = catalog.get("products", [])
        result_count = catalog.get("total", len(prods))
        if prods:
            for p in prods:
                pid   = p.get("id", "")
                pname = str(p.get("name", ""))[:55]
                price = p.get("selling_price", 0)
                old_p = p.get("old_price", price * 1.3)
                img   = p.get("image_url", "")
                disc  = int(((old_p - price) / old_p) * 100) if old_p > price else 0
                badge = f'<span class="sr-badge">-{disc}%</span>' if disc > 5 else ""
                old_t = f'<span class="sr-old">€{old_p:.2f}</span>' if disc > 5 else ""
                results_html += f"""<a href="/product/{pid}" class="sr-card">
                  {badge}
                  <img src="{img}" alt="{pname}" loading="lazy">
                  <div class="sr-body">
                    <p class="sr-name">{pname}</p>
                    <div class="sr-price"><span class="sr-cur">€{price:.2f}</span>{old_t}</div>
                    <div class="sr-stars">★★★★★ <span style="color:#aaa;font-size:0.8rem">(127)</span></div>
                  </div>
                </a>"""
        else:
            results_html = f'<div class="no-results"><p>No se encontraron productos para "<strong>{q}</strong>"</p><p>Intenta con otras palabras clave</p></div>'

    # Trending searches
    trending = ["collar perro", "cama gato", "comedero automático", "correa mascota", "jaula pájaro", "acuario"]
    trend_tags = "".join(f'<a href="/search?q={t}" class="trend-tag">{t}</a>' for t in trending)

    title_part = f'Resultados para "{q}" — {result_count} productos' if q else "Buscar productos"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title_part} | PataHogar</title>
  <meta name="description" content="Busca entre más de 500 productos para mascotas y hogar en PataHogar.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333}}
    .search-hero{{background:#1a5e35;padding:36px 20px;text-align:center;color:white}}
    .search-hero h1{{font-size:1.6rem;font-weight:700;margin-bottom:16px}}
    .search-form{{display:flex;max-width:560px;margin:0 auto}}
    .search-form input{{flex:1;padding:13px 18px;border:none;border-radius:30px 0 0 30px;font-size:1rem;outline:none}}
    .search-form button{{padding:13px 24px;background:#ff6b35;color:white;border:none;border-radius:0 30px 30px 0;cursor:pointer;font-weight:700;font-size:1rem}}
    .content{{max-width:1100px;margin:0 auto;padding:28px 20px}}
    .results-info{{font-size:0.92rem;color:#666;margin-bottom:18px}}
    .results-info b{{color:#1a1a1a}}
    .sr-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
    @media(max-width:900px){{.sr-grid{{grid-template-columns:repeat(2,1fr)}}}}
    .sr-card{{display:block;text-decoration:none;color:inherit;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);transition:transform 0.2s,box-shadow 0.2s;position:relative}}
    .sr-card:hover{{transform:translateY(-3px);box-shadow:0 8px 22px rgba(0,0,0,0.12)}}
    .sr-card img{{width:100%;height:180px;object-fit:contain;padding:10px;background:#fafafa}}
    .sr-badge{{position:absolute;top:8px;right:8px;background:#ff6b35;color:white;padding:3px 8px;border-radius:12px;font-size:0.75rem;font-weight:bold}}
    .sr-body{{padding:11px 13px 13px}}
    .sr-name{{font-size:0.87rem;font-weight:600;color:#333;margin-bottom:6px;line-height:1.35}}
    .sr-price{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
    .sr-cur{{font-size:1.05rem;font-weight:700;color:#1a5e35}}
    .sr-old{{font-size:0.83rem;color:#aaa;text-decoration:line-through}}
    .sr-stars{{color:#f5a623;font-size:0.82rem}}
    .trending{{margin-bottom:28px}}
    .trending h3{{font-size:0.95rem;color:#555;margin-bottom:10px;font-weight:600}}
    .trend-tag{{display:inline-block;padding:6px 14px;background:white;border:1px solid #ddd;border-radius:20px;font-size:0.85rem;color:#333;text-decoration:none;margin:4px;transition:all 0.15s}}
    .trend-tag:hover{{background:#1a5e35;color:white;border-color:#1a5e35}}
    .no-results{{background:white;border-radius:12px;padding:40px;text-align:center;color:#888}}
    .no-results p{{margin:8px 0;font-size:1rem}}
    .no-results strong{{color:#333}}
    .empty-state{{text-align:center;padding:60px 20px;color:#888}}
    .empty-state .ei{{font-size:4rem;margin-bottom:16px}}
    .empty-state h2{{font-size:1.2rem;color:#555;margin-bottom:8px}}
    .empty-state p{{font-size:0.92rem}}
  </style>
</head>
<body>
{nav}
<div class="search-hero">
  <h1>🔍 Buscar productos</h1>
  <form class="search-form" action="/search" method="get">
    <input type="text" name="q" value="{q}" placeholder="Buscar collares, comederos, camas..." autofocus autocomplete="off">
    <button type="submit">Buscar</button>
  </form>
</div>

<div class="content">
  {"" if q else f'<div class="trending"><h3>🔥 Búsquedas populares</h3>{trend_tags}</div>'}

  {"" if not q else f'<p class="results-info"><b>{result_count} resultados</b> para "{q}"</p>'}

  {"" if not q else f'<div class="sr-grid">{results_html}</div>' if results_html and "no-results" not in results_html else results_html}

  {"" if q else '<div class="empty-state"><div class="ei">🐾</div><h2>¿Qué estás buscando?</h2><p>Escribe en el campo de arriba para encontrar productos para mascotas y hogar</p></div>'}
</div>

{footer}
{scripts}
</body>
</html>""")


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    """Política de Privacidad — Comprehensive GDPR compliant"""
    nav = _get_nav("privacy")
    footer = _get_shared_footer()
    scripts = _get_shared_head_scripts()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Política de Privacidad | PataHogar</title>
  <meta name="description" content="Política de Privacidad RGPD de PataHogar. Cómo tratamos tus datos personales, tus derechos y cómo ejercerlos.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333;line-height:1.7}}
    .container{{max-width:900px;margin:0 auto;padding:28px 20px}}
    h1{{color:#1a5e35;font-size:2rem;margin-bottom:8px;border-bottom:3px solid #ff6b35;padding-bottom:10px}}
    h2{{color:#1a5e35;font-size:1.1rem;margin:24px 0 8px;padding:8px 12px;background:#f0f9f4;border-left:4px solid #1a5e35;border-radius:0 6px 6px 0}}
    h3{{color:#1a5e35;margin:16px 0 8px;font-size:0.95rem}}
    .date{{background:#fff8e1;border:1px solid #ffe082;padding:10px 16px;border-radius:6px;font-size:.9rem;color:#555;margin-bottom:24px;display:inline-block}}
    .card{{background:white;border-radius:12px;padding:24px;margin-bottom:16px;box-shadow:0 1px 6px rgba(0,0,0,0.07)}}
    ul,ol{{margin:8px 0 8px 20px}}
    li{{margin-bottom:4px}}
    table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:0.9rem}}
    td,th{{padding:10px 14px;border:1px solid #e0e0e0;text-align:left;vertical-align:top}}
    th{{background:#1a5e35;color:white}}
    tr:nth-child(even){{background:#f8fffe}}
    .rights-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:12px 0}}
    .right-item{{background:#f0f9f4;border-radius:8px;padding:14px;font-size:0.88rem}}
    .right-item strong{{color:#1a5e35;display:block;margin-bottom:4px}}
    .warning-box{{background:#fff3cd;border-left:4px solid #ff6b35;padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0;font-size:0.92rem}}
    a{{color:#1a5e35}}
  </style>
</head>
<body>
{nav}
<div class="container">
<h1>Política de Privacidad</h1>
<span class="date">Última actualización: Abril 2026 | Conforme al RGPD (UE) 2016/679 y LOPDGDD (ES)</span>

<div class="card">
<h2>1. Responsable del Tratamiento</h2>
<table>
  <tr><td><strong>Nombre</strong></td><td>PataHogar — Tienda online de mascotas y hogar</td></tr>
  <tr><td><strong>Titular</strong></td><td>Mohamed El Mansouri</td></tr>
  <tr><td><strong>Domicilio</strong></td><td>Valencia, España</td></tr>
  <tr><td><strong>Email de contacto</strong></td><td><a href="mailto:info@patahogar.com">info@patahogar.com</a></td></tr>
  <tr><td><strong>Actividad</strong></td><td>Comercio electrónico de productos para mascotas y hogar (dropshipping B2C)</td></tr>
</table>
</div>

<div class="card">
<h2>2. Datos Personales que Recopilamos</h2>
<p>Recopilamos únicamente los datos estrictamente necesarios:</p>
<table>
  <thead><tr><th>Dato</th><th>Finalidad</th><th>Base Legal</th></tr></thead>
  <tbody>
    <tr><td>Nombre y apellidos</td><td>Identificación del pedido y envío</td><td>Ejecución del contrato (Art. 6.1.b)</td></tr>
    <tr><td>Dirección postal</td><td>Entrega del producto</td><td>Ejecución del contrato (Art. 6.1.b)</td></tr>
    <tr><td>Correo electrónico</td><td>Confirmación de pedido y seguimiento</td><td>Ejecución del contrato (Art. 6.1.b)</td></tr>
    <tr><td>Teléfono</td><td>Contacto para entrega</td><td>Interés legítimo (Art. 6.1.f)</td></tr>
    <tr><td>Datos de navegación (IP, cookies)</td><td>Seguridad y análisis de uso</td><td>Consentimiento (Art. 6.1.a) + Interés legítimo</td></tr>
    <tr><td>Comportamiento en la tienda (Pixel Meta)</td><td>Publicidad personalizada</td><td>Consentimiento (Art. 6.1.a)</td></tr>
  </tbody>
</table>
<div class="warning-box">⚠️ <strong>Pago:</strong> Los datos de tarjeta son procesados directamente por <strong>Stripe</strong>. PataHogar <em>nunca</em> almacena datos bancarios ni de tarjeta de crédito.</div>
</div>

<div class="card">
<h2>3. Menores de Edad</h2>
<p>PataHogar <strong>no recopila deliberadamente datos personales de menores de 16 años</strong>. Si eres menor de 16 años, no debes realizar compras ni proporcionar tus datos sin supervisión de un adulto responsable. Si somos informados de que hemos recibido datos de un menor, los eliminaremos inmediatamente. Si eres padre, madre o tutor y crees que tu hijo nos ha proporcionado datos, contáctanos en <a href="mailto:info@patahogar.com">info@patahogar.com</a>.</p>
</div>

<div class="card">
<h2>4. Cookies y Tecnologías de Seguimiento</h2>
<table>
  <thead><tr><th>Tipo de Cookie</th><th>Descripción</th><th>Necesita Consentimiento</th></tr></thead>
  <tbody>
    <tr><td><strong>Técnicas / Esenciales</strong></td><td>Carrito de compra (localStorage), sesión de usuario. Imprescindibles para el funcionamiento.</td><td>No (necesarias para el servicio)</td></tr>
    <tr><td><strong>Analíticas</strong></td><td>Google Analytics 4 — mide visitas, páginas vistas, fuentes de tráfico de forma anonimizada.</td><td>Sí (consentimiento previo)</td></tr>
    <tr><td><strong>Marketing / Publicidad</strong></td><td>Meta Pixel — rastrea conversiones y permite mostrar anuncios relevantes en Facebook/Instagram.</td><td>Sí (consentimiento previo)</td></tr>
  </tbody>
</table>
<p style="margin-top:10px">Puedes retirar tu consentimiento en cualquier momento limpiando las cookies del navegador o usando las <a href="https://www.facebook.com/adpreferences" target="_blank">Preferencias de anuncios de Meta</a> y la extensión <a href="https://tools.google.com/dlpage/gaoptout" target="_blank">Google Analytics Opt-out</a>.</p>
</div>

<div class="card">
<h2>5. Subprocesadores y Terceros</h2>
<table>
  <thead><tr><th>Empresa</th><th>País</th><th>Función</th><th>Garantías RGPD</th></tr></thead>
  <tbody>
    <tr><td><strong>BigBuy S.L.</strong></td><td>España (UE)</td><td>Proveedor logístico — procesa dirección de envío para preparar y enviar el pedido</td><td>Dentro de la UE — cumplimiento automático</td></tr>
    <tr><td><strong>Stripe, Inc.</strong></td><td>EE.UU.</td><td>Procesador de pagos — gestiona datos de pago de forma segura (PCI DSS)</td><td>Marco de Privacidad UE-EE.UU. (DPF) + SCCs</td></tr>
    <tr><td><strong>Meta Platforms</strong></td><td>EE.UU. / Irlanda</td><td>Pixel de conversión y publicidad en Facebook/Instagram</td><td>SCCs · Política de Datos de Meta</td></tr>
    <tr><td><strong>Resend, Inc.</strong></td><td>EE.UU.</td><td>Envío de emails transaccionales (confirmaciones de pedido)</td><td>SCCs · GDPR Data Processing Agreement</td></tr>
    <tr><td><strong>Railway Corp.</strong></td><td>EE.UU.</td><td>Infraestructura cloud donde se aloja el servidor PataBot</td><td>SCCs · SOC 2 Type II</td></tr>
  </tbody>
</table>
</div>

<div class="card">
<h2>6. Tus Derechos RGPD</h2>
<p>Como titular de los datos tienes los siguientes derechos, que puedes ejercer en cualquier momento:</p>
<div class="rights-grid">
  <div class="right-item"><strong>Acceso (Art. 15)</strong> Solicitar copia de todos tus datos personales que tratamos.</div>
  <div class="right-item"><strong>Rectificación (Art. 16)</strong> Corregir datos inexactos o incompletos.</div>
  <div class="right-item"><strong>Supresión (Art. 17)</strong> Solicitar el borrado de tus datos ("derecho al olvido").</div>
  <div class="right-item"><strong>Portabilidad (Art. 20)</strong> Recibir tus datos en formato estructurado y legible por máquina.</div>
  <div class="right-item"><strong>Limitación (Art. 18)</strong> Solicitar que suspendamos el tratamiento mientras revisamos una reclamación.</div>
  <div class="right-item"><strong>Oposición (Art. 21)</strong> Oponerte al tratamiento para fines de marketing directo en cualquier momento.</div>
</div>

<h3>Cómo ejercer tus derechos</h3>
<ol>
  <li>Envía un email a <a href="mailto:info@patahogar.com"><strong>info@patahogar.com</strong></a> con el asunto <em>"Ejercicio de Derechos RGPD"</em></li>
  <li>Indica claramente qué derecho deseas ejercer y adjunta una copia de tu DNI/pasaporte para verificar tu identidad</li>
  <li>Responderemos en un plazo máximo de <strong>30 días naturales</strong> (prorrogable a 90 días en casos complejos, con notificación previa)</li>
  <li>Si la respuesta no te satisface, puedes presentar una reclamación ante la <strong>Agencia Española de Protección de Datos (AEPD)</strong>: <a href="https://www.aepd.es" target="_blank">aepd.es</a></li>
</ol>
</div>

<div class="card">
<h2>7. Decisiones Automatizadas</h2>
<p>PataHogar <strong>no toma decisiones automatizadas con efectos significativos</strong> sobre los usuarios. El sistema PataBot automatiza la gestión de inventario y publicidad (selección de productos para anuncios), pero estas decisiones no afectan derechos individuales de clientes ni implican perfilado discriminatorio. La aprobación final de campañas publicitarias requiere siempre intervención humana del titular.</p>
</div>

<div class="card">
<h2>8. Conservación de Datos</h2>
<table>
  <thead><tr><th>Tipo de dato</th><th>Plazo de conservación</th><th>Motivo</th></tr></thead>
  <tbody>
    <tr><td>Datos de pedido (nombre, dirección, email)</td><td>5 años desde la compra</td><td>Obligaciones fiscales y contables (Ley 58/2003 General Tributaria)</td></tr>
    <tr><td>Datos de pago (procesados por Stripe)</td><td>Según política de Stripe</td><td>PataHogar no almacena datos bancarios</td></tr>
    <tr><td>Cookies analíticas</td><td>13 meses</td><td>Análisis de uso y mejora del servicio</td></tr>
    <tr><td>Datos de marketing (Pixel Meta)</td><td>Hasta retirada de consentimiento</td><td>Marketing personalizado basado en consentimiento</td></tr>
    <tr><td>Consultas y reclamaciones</td><td>3 años</td><td>Posibles reclamaciones legales</td></tr>
  </tbody>
</table>
</div>

<div class="card">
<h2>9. Notificación de Brechas de Seguridad</h2>
<p>En caso de brecha de seguridad que pueda suponer un riesgo para tus derechos y libertades, PataHogar se compromete a:</p>
<ul>
  <li>Notificar a la <strong>AEPD en un plazo máximo de 72 horas</strong> desde que tengamos conocimiento</li>
  <li>Informar a los afectados directamente <strong>sin dilación indebida</strong> cuando la brecha suponga un alto riesgo</li>
  <li>Documentar todas las brechas, incluso aquellas que no requieran notificación</li>
</ul>
</div>

<div class="card">
<h2>10. Consentimiento para Marketing</h2>
<p>PataHogar aplica un modelo de <strong>opt-in (consentimiento previo explícito)</strong> para comunicaciones comerciales:</p>
<ul>
  <li>No enviamos newsletters ni emails de marketing sin consentimiento previo y expreso</li>
  <li>Las confirmaciones de pedido y emails transaccionales no son comunicaciones de marketing</li>
  <li>Puedes revocar el consentimiento en cualquier momento usando el enlace "Cancelar suscripción" en cualquier email o escribiendo a <a href="mailto:info@patahogar.com">info@patahogar.com</a></li>
</ul>
</div>

<div class="card">
<h2>11. Transferencias Internacionales</h2>
<p>Algunos de nuestros subprocesadores (Stripe, Meta, Resend, Railway) están establecidos en EE.UU. Las transferencias se realizan con las garantías adecuadas previstas en el RGPD:</p>
<ul>
  <li><strong>Decisiones de adecuación</strong> de la Comisión Europea donde estén disponibles</li>
  <li><strong>Cláusulas Contractuales Tipo (SCCs)</strong> de la Comisión Europea (Decisión 2021/914/UE)</li>
  <li><strong>Marco de Privacidad UE-EE.UU. (DPF)</strong> para empresas certificadas (Stripe)</li>
</ul>
</div>

<div class="card">
<h2>12. Modificaciones de esta Política</h2>
<p>Podemos actualizar esta Política de Privacidad para reflejar cambios legales o en nuestros servicios. Te informaremos de cambios significativos mediante un aviso visible en la web o por email. La fecha de última actualización siempre estará indicada al inicio del documento.</p>
</div>
</div>
{footer}
{scripts}
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/terms", response_class=HTMLResponse)
async def terms_page():
    """Términos y Condiciones de compra — EU law compliant"""
    nav = _get_nav("terms")
    footer = _get_shared_footer()
    scripts = _get_shared_head_scripts()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Términos y Condiciones | PataHogar</title>
  <meta name="description" content="Términos y Condiciones de compra de PataHogar. Derecho de desistimiento de 14 días, garantías, envíos y más.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333;line-height:1.7}}
    .container{{max-width:900px;margin:0 auto;padding:28px 20px}}
    h1{{color:#1a5e35;font-size:2rem;margin-bottom:8px;border-bottom:3px solid #ff6b35;padding-bottom:10px}}
    h2{{color:#1a5e35;font-size:1.1rem;margin:24px 0 8px;padding:8px 12px;background:#f0f9f4;border-left:4px solid #1a5e35;border-radius:0 6px 6px 0}}
    h3{{color:#1a5e35;margin:16px 0 8px;font-size:0.95rem}}
    .date{{background:#fff8e1;border:1px solid #ffe082;padding:10px 16px;border-radius:6px;font-size:.9rem;color:#555;margin-bottom:24px;display:inline-block}}
    .card{{background:white;border-radius:12px;padding:24px;margin-bottom:16px;box-shadow:0 1px 6px rgba(0,0,0,0.07)}}
    ul,ol{{margin:8px 0 8px 20px}}
    li{{margin-bottom:4px}}
    table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:0.9rem}}
    td,th{{padding:10px 14px;border:1px solid #e0e0e0;text-align:left;vertical-align:top}}
    th{{background:#1a5e35;color:white}}
    tr:nth-child(even){{background:#f8fffe}}
    .highlight-box{{background:#e8f5e9;border-left:4px solid #1a5e35;padding:14px 18px;border-radius:0 8px 8px 0;margin:12px 0}}
    .warning-box{{background:#fff3cd;border-left:4px solid #ff6b35;padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0;font-size:0.92rem}}
    a{{color:#1a5e35}}
    .steps{{counter-reset:step;padding:0;list-style:none}}
    .steps li{{counter-increment:step;padding:10px 10px 10px 50px;position:relative;margin-bottom:8px;background:#f8f9fa;border-radius:8px}}
    .steps li::before{{content:counter(step);position:absolute;left:12px;top:10px;background:#1a5e35;color:white;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85rem}}
  </style>
</head>
<body>
{nav}
<div class="container">
<h1>Términos y Condiciones</h1>
<span class="date">Última actualización: Abril 2026 | Conforme a Directiva UE 2011/83/UE · RDL 1/2007 · Ley 7/1996</span>

<div class="card">
<h2>1. Información General del Comerciante</h2>
<table>
  <tr><td><strong>Nombre comercial</strong></td><td>PataHogar</td></tr>
  <tr><td><strong>Titular</strong></td><td>Mohamed El Mansouri</td></tr>
  <tr><td><strong>Domicilio</strong></td><td>Valencia, España</td></tr>
  <tr><td><strong>Contacto</strong></td><td><a href="mailto:info@patahogar.com">info@patahogar.com</a></td></tr>
  <tr><td><strong>Modelo de negocio</strong></td><td>Comercio electrónico dropshipping — proveedor logístico: BigBuy S.L. (Valencia, España)</td></tr>
  <tr><td><strong>Legislación aplicable</strong></td><td>Derecho español y de la Unión Europea</td></tr>
</table>
<p style="margin-top:12px">Al realizar una compra en PataHogar, el usuario acepta íntegramente los presentes Términos y Condiciones. Te recomendamos leerlos antes de finalizar tu pedido.</p>
</div>

<div class="card">
<h2>2. Proceso de Compra</h2>
<ol class="steps">
  <li><strong>Selección del producto</strong> — Navega por el catálogo y añade al carrito el artículo deseado.</li>
  <li><strong>Revisión del carrito</strong> — Comprueba las unidades y el precio total antes de proceder.</li>
  <li><strong>Datos de envío y pago</strong> — Serás redirigido a la página segura de Stripe para introducir tus datos.</li>
  <li><strong>Confirmación</strong> — Recibirás un email de confirmación en menos de 1 hora con el resumen de tu pedido.</li>
  <li><strong>Preparación y envío</strong> — Tu pedido se prepara en los almacenes de BigBuy (Valencia) y se envía en 24-48h laborables.</li>
  <li><strong>Seguimiento</strong> — Recibirás un número de seguimiento por email cuando el pedido sea recogido por el transportista.</li>
</ol>
<div class="warning-box">⚠️ El contrato de compraventa queda formalizado en el momento en que PataHogar envía la confirmación del pedido por email.</div>
</div>

<div class="card">
<h2>3. Precios y Pago</h2>
<ul>
  <li>Todos los precios están expresados en <strong>Euros (€)</strong> e incluyen el <strong>IVA aplicable</strong>.</li>
  <li>PataHogar se reserva el derecho a modificar precios, pero los cambios no afectarán a pedidos ya confirmados.</li>
  <li>Métodos de pago aceptados: <strong>Visa, Mastercard, American Express</strong> y otras tarjetas procesadas por Stripe.</li>
  <li>El cargo se realiza en el momento de confirmar el pedido.</li>
  <li>Stripe es certificado <strong>PCI DSS Nivel 1</strong> — el estándar de seguridad más alto para pagos con tarjeta.</li>
</ul>
</div>

<div class="card">
<h2>4. Envíos</h2>
<table>
  <thead><tr><th>Destino</th><th>Plazo estimado</th><th>Coste (&lt;30€)</th><th>Coste (≥30€)</th></tr></thead>
  <tbody>
    <tr><td>España, Portugal</td><td>2-4 días laborables</td><td>€3.99</td><td>Gratis</td></tr>
    <tr><td>Francia, Alemania, Italia</td><td>3-6 días laborables</td><td>€4.99</td><td>Gratis</td></tr>
    <tr><td>Bélgica, Países Bajos, Austria, Suecia, Dinamarca, Suiza, Liechtenstein</td><td>4-8 días laborables</td><td>€5.99</td><td>Gratis</td></tr>
  </tbody>
</table>
<p style="font-size:0.85rem;color:#888">Los plazos son estimados en días laborables. PataHogar no se responsabiliza de retrasos causados por el transportista o por causas de fuerza mayor.</p>
</div>

<div class="card">
<h2>5. Derecho de Desistimiento — 14 Días (Directiva UE 2011/83/UE)</h2>
<div class="highlight-box">
  <strong>Tienes derecho a desistir del contrato en un plazo de 14 días naturales</strong> desde la recepción del producto, sin necesidad de justificación y sin penalización alguna, de acuerdo con la Directiva Europea 2011/83/UE de derechos de los consumidores y el Real Decreto Legislativo 1/2007.
</div>
<h3>Procedimiento de desistimiento</h3>
<ol class="steps">
  <li>Comunica tu decisión de desistimiento enviando un email a <a href="mailto:info@patahogar.com"><strong>info@patahogar.com</strong></a> dentro del plazo de 14 días indicando: nombre completo, número de pedido y "Ejercicio de derecho de desistimiento".</li>
  <li>Recibirás instrucciones de devolución en 24h laborables.</li>
  <li>Devuelve el producto en su estado original en un plazo máximo de <strong>14 días</strong> desde la comunicación de desistimiento.</li>
  <li>PataHogar reembolsará el importe completo del pedido (incluidos los gastos de envío originales) en un plazo máximo de <strong>14 días</strong> desde que recibamos el artículo.</li>
</ol>
<p style="margin-top:10px">Los gastos de devolución corren a cargo del consumidor, salvo que el artículo sea defectuoso o incorrecto.</p>
</div>

<div class="card">
<h2>6. Política de Devoluciones (30 días)</h2>
<p>Adicionalmente al plazo legal, PataHogar ofrece <strong>30 días naturales</strong> desde la recepción para solicitar la devolución de cualquier artículo que no sea de tu satisfacción. El procedimiento es el mismo que para el desistimiento. Consulta la <a href="/shipping">página de envíos</a> para más detalles.</p>
</div>

<div class="card">
<h2>7. Garantía Legal (Directiva UE 2019/771)</h2>
<p>Todos los productos cuentan con <strong>2 años de garantía legal</strong> conforme a la Directiva UE 2019/771 sobre contratos de compraventa de bienes. En caso de producto defectuoso dentro del plazo de garantía, PataHogar procederá a la reparación, sustitución, reducción del precio o resolución del contrato según corresponda.</p>
</div>

<div class="card">
<h2>8. Limitación de Responsabilidad</h2>
<p>PataHogar actúa como comerciante intermediario bajo el modelo de dropshipping. En este sentido:</p>
<ul>
  <li>PataHogar <strong>no será responsable</strong> de daños indirectos, pérdidas de beneficios o daños consecuentes que no sean atribuibles a su actuación directa.</li>
  <li>La responsabilidad máxima de PataHogar ante el consumidor estará limitada al <strong>importe del pedido afectado</strong>.</li>
  <li>Las especificaciones técnicas de los productos provienen de BigBuy. PataHogar realiza todos los esfuerzos razonables para mantener la información actualizada, pero no garantiza la exactitud absoluta de las descripciones.</li>
  <li>Los plazos de entrega son estimaciones basadas en el rendimiento histórico del transportista y pueden variar.</li>
</ul>
</div>

<div class="card">
<h2>9. Fuerza Mayor</h2>
<p>PataHogar no será responsable por incumplimientos causados por <strong>circunstancias de fuerza mayor</strong>, incluyendo pero no limitado a: catástrofes naturales, pandemias, huelgas de transportistas, fallos en infraestructuras de terceros, conflictos armados, restricciones gubernamentales o cualquier otro evento imprevisible e irresistible fuera del control razonable de PataHogar. En estos casos, PataHogar informará al cliente en la mayor brevedad posible y acordará una solución apropiada.</p>
</div>

<div class="card">
<h2>10. Propiedad Intelectual</h2>
<p>Todos los contenidos de PataHogar — incluyendo textos, imágenes, logotipos, diseño gráfico, código fuente y marca — son propiedad de PataHogar o se usan bajo licencia. Queda <strong>prohibida su reproducción, distribución o uso comercial</strong> sin autorización expresa y por escrito. Las imágenes de productos son propiedad de BigBuy o de sus respectivos fabricantes.</p>
</div>

<div class="card">
<h2>11. Derecho a Denegar el Servicio</h2>
<p>PataHogar se reserva el derecho a <strong>rechazar o cancelar pedidos</strong> en los siguientes supuestos:</p>
<ul>
  <li>Indicios de uso fraudulento o abuso del sistema de devoluciones</li>
  <li>Dirección de entrega no válida o no verificable</li>
  <li>Incumplimiento previo demostrado de los presentes Términos</li>
  <li>Errores manifiestos de precio o disponibilidad en el momento del pedido</li>
</ul>
<p>En caso de cancelación, se procederá al reembolso íntegro del importe abonado.</p>
</div>

<div class="card">
<h2>12. Modificación de estos Términos</h2>
<p>PataHogar podrá modificar los presentes Términos y Condiciones para adaptarlos a cambios legislativos o en sus servicios. Las modificaciones serán comunicadas con al menos <strong>15 días de antelación</strong> mediante aviso en la web o por email a los usuarios registrados. Los cambios no afectarán a pedidos en curso. El uso continuado del servicio tras la entrada en vigor de los nuevos términos implica su aceptación.</p>
</div>

<div class="card">
<h2>13. Resolución de Conflictos y Legislación Aplicable</h2>
<p>Para cualquier reclamación o consulta: <a href="mailto:info@patahogar.com"><strong>info@patahogar.com</strong></a>. Intentaremos resolver cualquier disputa de forma amistosa en un plazo de 30 días.</p>
<p style="margin-top:10px">En caso de disputa no resuelta, el consumidor puede acceder a la <strong>Plataforma de Resolución de Litigios en Línea (ODR)</strong> de la Comisión Europea: <a href="https://ec.europa.eu/consumers/odr" target="_blank">ec.europa.eu/consumers/odr</a></p>
<p style="margin-top:10px">Los presentes Términos se rigen por la <strong>legislación española</strong> y el Derecho de la Unión Europea, en particular la Directiva 2011/83/UE y el Real Decreto Legislativo 1/2007. Para los litigios no solucionados en vía amistosa, serán competentes los Juzgados y Tribunales del domicilio del consumidor.</p>
</div>
</div>
{footer}
{scripts}
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/returns", response_class=HTMLResponse)
async def returns_page():
    """Política de devoluciones — 14-day return policy (EU directive 2011/83/UE)"""
    nav     = _get_nav("returns")
    footer  = _get_shared_footer()
    scripts = _get_shared_head_scripts()
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Política de Devoluciones | PataHogar</title>
  <meta name="description" content="Política de devoluciones de PataHogar. 14 días de desistimiento + 30 días de garantía voluntaria. Devolución gratuita por correo.">
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333;line-height:1.75}
    .container{max-width:860px;margin:0 auto;padding:32px 20px}
    h1{color:#1a5e35;font-size:1.9rem;margin-bottom:8px;border-bottom:3px solid #ff6b35;padding-bottom:10px}
    .updated{color:#888;font-size:0.85rem;margin-bottom:28px}
    h2{color:#1a5e35;font-size:1.05rem;margin:28px 0 8px;padding:8px 14px;background:#f0f9f4;border-left:4px solid #1a5e35;border-radius:0 6px 6px 0}
    p{margin-bottom:12px;font-size:0.95rem}
    ul{margin:8px 0 12px 20px;font-size:0.95rem}
    ul li{margin-bottom:6px}
    .highlight-box{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:10px;padding:18px 20px;margin:20px 0}
    .highlight-box h3{color:#2e7d32;font-size:1rem;margin-bottom:8px}
    .warning-box{background:#fff3e0;border:1px solid #ffcc02;border-radius:10px;padding:18px 20px;margin:20px 0}
    .warning-box h3{color:#e65100;font-size:1rem;margin-bottom:8px}
    .steps{counter-reset:step}
    .step{display:flex;gap:16px;margin-bottom:16px;align-items:flex-start}
    .step-num{background:#1a5e35;color:white;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;font-size:0.95rem}
    .step-body h4{font-size:0.95rem;font-weight:700;margin-bottom:4px}
    .step-body p{margin:0;font-size:0.9rem;color:#555}
    table{width:100%;border-collapse:collapse;margin:16px 0;font-size:0.9rem}
    th{background:#1a5e35;color:white;padding:10px 14px;text-align:left}
    td{padding:9px 14px;border-bottom:1px solid #e0e0e0}
    tr:nth-child(even) td{background:#f5f5f5}
    .badge-ok{background:#e8f5e9;color:#2e7d32;padding:3px 9px;border-radius:12px;font-size:0.8rem;font-weight:600}
    .badge-no{background:#ffebee;color:#c62828;padding:3px 9px;border-radius:12px;font-size:0.8rem;font-weight:600}
    a{color:#1a5e35}
  </style>
</head>
<body>
""" + nav + """
<div class="container">

  <h1>↩️ Política de Devoluciones</h1>
  <p class="updated">Última actualización: 14 de abril de 2026 · PataHogar, Valencia, España</p>

  <div class="highlight-box">
    <h3>✅ Tu protección como consumidor europeo</h3>
    <p>En PataHogar cumplimos con la <strong>Directiva Europea 2011/83/UE</strong> sobre derechos del consumidor. Tienes <strong>14 días naturales</strong> de derecho de desistimiento desde la recepción de tu pedido, sin necesidad de justificación. Además, ofrecemos voluntariamente una ventana ampliada de <strong>30 días</strong>.</p>
  </div>

  <h2>1. Derecho de Desistimiento (14 días — Legal)</h2>
  <p>Tienes derecho a desistir del contrato en un plazo de <strong>14 días naturales</strong> a partir del día en que tú o un tercero (distinto al transportista) recibas el pedido, sin necesidad de indicar el motivo.</p>
  <p>Para ejercer el derecho de desistimiento, debes notificarnos tu decisión antes de que expire el plazo mediante:</p>
  <ul>
    <li>📧 Email: <strong>info@patahogar.com</strong></li>
    <li>📬 Carta postal: PataHogar, Valencia, España</li>
    <li>📋 Formulario online (ver sección 4)</li>
  </ul>

  <h2>2. Política Ampliada Voluntaria (30 días)</h2>
  <p>Adicionalmente al derecho legal, PataHogar ofrece voluntariamente <strong>30 días naturales</strong> desde la recepción para solicitar la devolución de cualquier producto, sin necesidad de justificación, siempre que se cumplan las condiciones indicadas.</p>

  <h2>3. Condiciones para la Devolución</h2>
  <table>
    <tr><th>Condición</th><th>Estado</th></tr>
    <tr><td>Producto en estado original (sin usar)</td><td><span class="badge-ok">Requerido</span></td></tr>
    <tr><td>Embalaje original conservado</td><td><span class="badge-ok">Requerido</span></td></tr>
    <tr><td>Todos los accesorios incluidos</td><td><span class="badge-ok">Requerido</span></td></tr>
    <tr><td>Etiqueta/precinto intacto</td><td><span class="badge-ok">Requerido</span></td></tr>
    <tr><td>Ticket o confirmación de compra</td><td><span class="badge-ok">Requerido</span></td></tr>
    <tr><td>Producto dañado por uso indebido</td><td><span class="badge-no">No aceptado</span></td></tr>
    <tr><td>Productos de higiene personal abiertos</td><td><span class="badge-no">No aceptado</span></td></tr>
    <tr><td>Software/contenido digital descargado</td><td><span class="badge-no">No aceptado</span></td></tr>
  </table>

  <h2>4. Cómo Iniciar una Devolución</h2>
  <div class="step">
    <div class="step-num">1</div>
    <div class="step-body">
      <h4>Notifícanos</h4>
      <p>Envía un email a <strong>info@patahogar.com</strong> con asunto "DEVOLUCIÓN — Nº Pedido XXXXX" indicando el motivo (opcional) y si prefieres reembolso o cambio.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-num">2</div>
    <div class="step-body">
      <h4>Confirmación en 24h</h4>
      <p>Recibirás un email de confirmación con las instrucciones de envío y la dirección de devolución en un plazo máximo de 24 horas hábiles.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-num">3</div>
    <div class="step-body">
      <h4>Envío del Producto</h4>
      <p>Empaqueta el producto de forma segura y envíalo por correo certificado a la dirección indicada. Los gastos de envío de devolución son <strong>gratuitos</strong> para pedidos dentro de España.</p>
    </div>
  </div>
  <div class="step">
    <div class="step-num">4</div>
    <div class="step-body">
      <h4>Reembolso en 14 días</h4>
      <p>Una vez recibido y verificado el producto, procesaremos el reembolso completo (incluidos los gastos de envío originales) en un plazo máximo de <strong>14 días naturales</strong>, usando el mismo método de pago original.</p>
    </div>
  </div>

  <h2>5. Gastos de Devolución</h2>
  <table>
    <tr><th>País</th><th>Coste de devolución</th></tr>
    <tr><td>España y Portugal</td><td><span class="badge-ok">Gratuito</span></td></tr>
    <tr><td>Francia, Alemania, Italia</td><td>€5.99 (deducido del reembolso)</td></tr>
    <tr><td>Países Bajos, Bélgica, Austria</td><td>€7.99 (deducido del reembolso)</td></tr>
    <tr><td>Suiza, Liechtenstein, Dinamarca</td><td>€9.99 (deducido del reembolso)</td></tr>
  </table>
  <p><em>Los gastos de devolución son gratuitos si el producto llegó defectuoso o no corresponde al pedido.</em></p>

  <h2>6. Plazos de Reembolso</h2>
  <p>El reembolso se realizará en un máximo de <strong>14 días naturales</strong> desde la recepción del producto devuelto, utilizando el mismo medio de pago empleado en la compra:</p>
  <ul>
    <li><strong>Tarjeta de crédito/débito (Stripe):</strong> 5-10 días hábiles</li>
    <li>El cargo en tu tarjeta aparecerá como cancelado por parte de Stripe</li>
  </ul>

  <h2>7. Productos Defectuosos o Incorrectos</h2>
  <p>Si el producto recibido es defectuoso, está dañado durante el transporte, o no corresponde al pedido:</p>
  <ul>
    <li>Contacta con nosotros en <strong>info@patahogar.com</strong> adjuntando fotos del defecto</li>
    <li>Correremos con todos los gastos de recogida y reenvío</li>
    <li>Podrás elegir entre reembolso completo, sustitución del producto o vale de compra</li>
  </ul>

  <h2>8. Garantía Legal (2 años)</h2>
  <p>Todos los productos vendidos en PataHogar cuentan con la <strong>garantía legal de 2 años</strong> según la Directiva Europea 2019/771 sobre conformidad de los bienes. En caso de defecto de conformidad, tienes derecho a:</p>
  <ul>
    <li>Reparación o sustitución del producto (gratuita)</li>
    <li>Reducción proporcional del precio</li>
    <li>Resolución del contrato (devolución total)</li>
  </ul>

  <div class="warning-box">
    <h3>⚠️ Excepciones al Derecho de Desistimiento</h3>
    <p>De acuerdo con el artículo 103 del Real Decreto Legislativo 1/2007, el derecho de desistimiento no aplica a:</p>
    <ul>
      <li>Productos personalizados o hechos a medida</li>
      <li>Productos que puedan deteriorarse o caducar rápidamente</li>
      <li>Productos sellados que no puedan devolverse por razones de higiene (abiertos)</li>
      <li>Contenido digital que ya se ha descargado/reproducido con consentimiento</li>
    </ul>
  </div>

  <h2>9. Formulario de Desistimiento</h2>
  <p>Puedes usar el siguiente formulario tipo para ejercer tu derecho de desistimiento (enviar por email a info@patahogar.com):</p>
  <div style="background:white;border:1px solid #ddd;border-radius:8px;padding:20px;font-family:monospace;font-size:0.88rem;line-height:1.8">
    A/A: PataHogar — info@patahogar.com<br>
    <br>
    Por la presente le comunico que desisto del contrato de compra del siguiente producto:<br>
    <br>
    — Producto/Pedido nº: [NÚMERO DE PEDIDO]<br>
    — Recibido el: [FECHA DE RECEPCIÓN]<br>
    — Nombre del consumidor: [TU NOMBRE COMPLETO]<br>
    — Domicilio: [TU DIRECCIÓN]<br>
    — Firma (si se presenta en papel): ___________<br>
    — Fecha: [FECHA]
  </div>

  <h2>10. Contacto para Devoluciones</h2>
  <ul>
    <li>📧 Email: <a href="mailto:info@patahogar.com">info@patahogar.com</a></li>
    <li>💬 WhatsApp: disponible en la web</li>
    <li>🌐 Web: <a href="https://patahogar.com">patahogar.com</a></li>
    <li>⏱️ Tiempo de respuesta: máximo 24 horas hábiles</li>
  </ul>

</div>
""" + footer + "\n" + scripts + """
</body>
</html>"""
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

@app.get("/api/marketing/clear-low-margin-ads")
async def clear_low_margin_ads(min_profit: float = Query(10.0)):
    """
    مسح كل الإعلانات المعلقة بربح أقل من الحد الأدنى.
    GET /api/marketing/clear-low-margin-ads?min_profit=10
    """
    return await marketing_manager.clear_low_margin_pending_ads(min_profit)

@app.get("/api/marketing/reset-proposed")
async def reset_proposed():
    """مسح سجل المنتجات المقترحة — يسمح باقتراحها مجدداً."""
    return await marketing_manager.reset_proposed_tracker()

@app.get("/api/marketing/diagnose-meta")
async def diagnose_meta():
    """
    Diagnóstico completo de Meta Ads — checks both ad accounts.
    Fixes: removed daily_spend_limit (invalid field), added second account check.
    """
    import httpx
    token    = os.getenv("META_ACCESS_TOKEN", "")
    account  = os.getenv("META_AD_ACCOUNT_ID", "")   # what PataBot uses
    account2 = "act_1459065035836307"                  # account with MasterCard 4777
    pixel    = os.getenv("META_PIXEL_ID", "")
    base     = "https://graph.facebook.com/v21.0"
    status_map = {1:"✅ Active", 2:"❌ Disabled", 3:"⚠️ Unsettled/billing",
                  7:"🔄 Pending Review", 9:"⚠️ In Grace Period"}

    if not token:
        return {"error": "META_ACCESS_TOKEN not set in Railway"}

    result = {"patabot_account": account, "mastercard_account": account2,
              "pixel_id": pixel, "checks": {}}

    async with httpx.AsyncClient(timeout=25.0) as client:

        async def check_account(acct_id: str) -> dict:
            """Fetch account info — safe fields only."""
            r = await client.get(f"{base}/{acct_id}",
                params={"access_token": token,
                        "fields": "name,account_status,disable_reason,"
                                  "funding_source_details,amount_spent,balance,"
                                  "currency,timezone_name,spend_cap"})
            d = r.json()
            if "error" in d:
                return {"error": d["error"].get("message", str(d["error"])), "raw": d}
            st = d.get("account_status", 0)
            fs = d.get("funding_source_details") or {}
            return {
                "name":           d.get("name", "—"),
                "status":         status_map.get(st, f"Unknown ({st})"),
                "status_code":    st,
                "healthy":        st == 1,
                "disable_reason": d.get("disable_reason"),
                "currency":       d.get("currency"),
                "timezone":       d.get("timezone_name"),
                "amount_spent_eur": f"€{float(d.get('amount_spent', 0))/100:.2f}",
                "balance":        d.get("balance"),
                "payment_method": fs.get("display_string", "⚠️ NO PAYMENT METHOD"),
                "has_payment":    bool(fs.get("display_string")),
                "raw":            d
            }

        # ── 1. Check both accounts ──
        result["checks"]["patabot_account_info"]   = await check_account(account)
        result["checks"]["mastercard_account_info"] = await check_account(account2)

        # ── 2. Campaigns on PataBot account ──
        r = await client.get(f"{base}/{account}/campaigns",
            params={"access_token": token,
                    "fields": "name,status,effective_status,objective,daily_budget",
                    "limit": 25})
        campaigns = r.json().get("data", [])
        result["checks"]["patabot_account_campaigns"] = campaigns
        result["checks"]["patabot_campaigns_count"]   = len(campaigns)

        # ── 3. Ads on PataBot account ──
        r = await client.get(f"{base}/{account}/ads",
            params={"access_token": token,
                    "fields": "name,status,effective_status,delivery_info,adset_id,campaign_id",
                    "limit": 25})
        ads = r.json().get("data", [])
        result["checks"]["patabot_account_ads"]       = ads
        result["checks"]["patabot_account_ads_count"] = len(ads)

        # ── 4. Adsets on PataBot account ──
        r = await client.get(f"{base}/{account}/adsets",
            params={"access_token": token,
                    "fields": "name,status,effective_status,delivery_info,daily_budget,campaign_id",
                    "limit": 25})
        adsets = r.json().get("data", [])
        result["checks"]["patabot_account_adsets"]       = adsets
        result["checks"]["patabot_account_adsets_count"] = len(adsets)

        # ── 5. Campaigns on MasterCard account ──
        r2 = await client.get(f"{base}/{account2}/campaigns",
            params={"access_token": token,
                    "fields": "name,status,effective_status,objective",
                    "limit": 10})
        result["checks"]["mastercard_account_campaigns"] = r2.json().get("data", [])

        # ── 6. Per-ad diagnosis: check each PataBot active ad on Meta ──
        per_ad = []
        for ad in marketing_manager.active_ads:
            entry = {
                "patabot_id":    ad.get("id"),
                "product":       ad.get("product_name"),
                "meta_campaign": ad.get("meta_campaign_id"),
                "meta_adset":    ad.get("meta_adset_id"),
                "meta_adsets":   ad.get("meta_adsets", []),
                "meta_ad_id":    ad.get("meta_ad_id"),   # null = problem
                "meta_creative": ad.get("meta_creative_id"),
                "problem":       "meta_ad_id is null — Ad object never created on Meta" if not ad.get("meta_ad_id") else "OK"
            }
            # Check adset status directly
            asid = ad.get("meta_adset_id")
            if asid:
                ra = await client.get(f"{base}/{asid}",
                    params={"access_token": token,
                            "fields": "name,status,effective_status,delivery_info,issues_info"})
                entry["adset_meta_status"] = ra.json()
            # Check campaign status
            cid = ad.get("meta_campaign_id")
            if cid:
                rc = await client.get(f"{base}/{cid}",
                    params={"access_token": token,
                            "fields": "name,status,effective_status,issues_info"})
                entry["campaign_meta_status"] = rc.json()
            per_ad.append(entry)
        result["checks"]["per_active_ad_diagnosis"] = per_ad

        # ── 7. Pixel ──
        if pixel:
            rp = await client.get(f"{base}/{pixel}",
                params={"access_token": token,
                        "fields": "name,is_unavailable,last_fired_time,data_use_setting"})
            result["checks"]["pixel"] = rp.json()

    # ── Summary ──
    pa  = result["checks"]["patabot_account_info"]
    ma  = result["checks"]["mastercard_account_info"]
    null_ad_ids = sum(1 for a in marketing_manager.active_ads if not a.get("meta_ad_id"))
    real_ads = result["checks"]["patabot_account_ads_count"]

    result["diagnosis"] = {
        "patabot_account_healthy":    pa.get("healthy", False),
        "patabot_account_payment":    pa.get("payment_method", "unknown"),
        "mastercard_account_healthy": ma.get("healthy", False),
        "mastercard_account_payment": ma.get("payment_method", "unknown"),
        "real_ads_on_meta":           real_ads,
        "active_ads_missing_ad_obj":  null_ad_ids,
        "root_cause": (
            "🔴 WRONG ACCOUNT: PataBot uses act_1594642818257814 but MasterCard is on act_1459065035836307"
            if (not pa.get("has_payment") and ma.get("has_payment"))
            else "🔴 No payment method on either account — add card to Meta Billing"
            if (not pa.get("has_payment") and not ma.get("has_payment"))
            else f"🔴 {null_ad_ids} ads missing Ad Object on Meta (meta_ad_id=null)" if null_ad_ids > 0
            else "✅ Account OK" if (pa.get("healthy") and real_ads > 0)
            else "⚠️ Unknown — check per_active_ad_diagnosis"
        )
    }
    return result


@app.get("/api/marketing/repair-ad-objects")
async def repair_ad_objects():
    """
    إصلاح الإعلانات النشطة التي لديها campaign+adset على Meta لكن meta_ad_id=null.
    لا ينشئ campaigns أو adsets جديدة — فقط يكمل خطوة Ad Object الناقصة.
    يجب أن يكون الحساب لديه payment method مُضاف أولاً.
    """
    import httpx
    token   = os.getenv("META_ACCESS_TOKEN", "")
    account = os.getenv("META_AD_ACCOUNT_ID", "")
    base    = "https://graph.facebook.com/v21.0"
    results = []

    for ad in marketing_manager.active_ads:
        if ad.get("meta_ad_id"):
            results.append({"id": ad["id"], "product": ad["product_name"],
                            "status": "skipped — meta_ad_id already exists", "ad_id": ad["meta_ad_id"]})
            continue

        adset_id   = ad.get("meta_adset_id")
        creative_id = ad.get("meta_creative_id")

        if not adset_id or not creative_id:
            results.append({"id": ad["id"], "product": ad["product_name"],
                            "status": "error — missing adset_id or creative_id",
                            "adset_id": adset_id, "creative_id": creative_id})
            continue

        # Create only the missing Ad Object
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{base}/{account}/ads",
                params={"access_token": token},
                json={
                    "name":     (ad.get("headline", ad["product_name"]))[:40],
                    "adset_id": adset_id,
                    "creative": {"creative_id": creative_id},
                    "status":   "ACTIVE"
                }
            )
        resp = r.json()
        if r.status_code == 200 and resp.get("id"):
            ad["meta_ad_id"] = resp["id"]
            marketing_manager._save_ads()
            results.append({"id": ad["id"], "product": ad["product_name"],
                            "status": "✅ Ad object created", "meta_ad_id": resp["id"]})
            logger.info(f"Repaired ad {ad['id']}: meta_ad_id={resp['id']}")
        else:
            results.append({"id": ad["id"], "product": ad["product_name"],
                            "status": "❌ Failed", "error": resp.get("error", resp)})

    fixed = sum(1 for r in results if "✅" in r.get("status", ""))
    return {
        "repaired": fixed,
        "total_active": len(marketing_manager.active_ads),
        "results": results,
        "next": "Run /api/marketing/diagnose-meta to verify ads are now delivering" if fixed > 0 else "Check errors above"
    }


@app.get("/api/marketing/test-tiktok")
async def test_tiktok():
    """اختبار اتصال TikTok Ads API."""
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    adv_id = os.getenv("TIKTOK_ADVERTISER_ID", "")
    if not token or not adv_id:
        return {"configured": False, "error": "TIKTOK_ACCESS_TOKEN or TIKTOK_ADVERTISER_ID not set in Railway"}
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            "https://business-api.tiktok.com/open_api/v1.3/advertiser/info/",
            headers={"Access-Token": token},
            params={"advertiser_ids": f'["{adv_id}"]', "fields": '["name","status","currency"]'}
        )
    return {"configured": True, "status": r.status_code, "response": r.json()}

# ════════════════════════════════════════════════════════
# TIKTOK OAUTH — Get Access Token via OAuth 2.0
# ════════════════════════════════════════════════════════

@app.get("/tiktok/auth", response_class=HTMLResponse)
async def tiktok_auth_start():
    """
    Step 1: Redirect Mohamed to TikTok authorization page.
    Requires TIKTOK_CLIENT_KEY set in Railway.
    """
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    if not client_key:
        return HTMLResponse("""
        <html><body style="font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto">
        <h2 style="color:#d32f2f">❌ TIKTOK_CLIENT_KEY no configurado</h2>
        <p>Añade <code>TIKTOK_CLIENT_KEY</code> en Railway → Variables y vuelve a intentarlo.</p>
        </body></html>
        """, status_code=400)

    redirect_uri = "https://patabot-production.up.railway.app/tiktok/callback"
    auth_url = (
        f"https://business-api.tiktok.com/portal/auth"
        f"?app_id={client_key}"
        f"&state=patabot_oauth"
        f"&redirect_uri={redirect_uri}"
    )
    return HTMLResponse(f"""
    <html><head><meta charset="utf-8">
    <style>body{{font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto}}
    .btn{{display:inline-block;padding:14px 28px;background:#00f2ea;color:#000;
    font-weight:700;border-radius:8px;text-decoration:none;font-size:18px;margin-top:20px}}
    .btn:hover{{background:#00c4bc}}</style></head>
    <body>
    <h2>🎵 Conectar TikTok Ads</h2>
    <p>Haz clic en el botón para autorizar PataBot a crear anuncios en tu cuenta de TikTok Business.</p>
    <p><b>App:</b> patabot &nbsp;|&nbsp; <b>Cuenta:</b> Business Center {os.getenv('TIKTOK_ADVERTISER_ID','')}</p>
    <a href="{auth_url}" class="btn">▶ Autorizar en TikTok</a>
    <p style="color:#666;margin-top:20px;font-size:13px">
    Se abrirá la página oficial de TikTok Business. Inicia sesión y acepta los permisos.
    Serás redirigido de vuelta automáticamente.</p>
    </body></html>
    """)

@app.get("/tiktok/callback")
async def tiktok_auth_callback(request: Request, response_class=HTMLResponse):
    """
    Step 2: TikTok redirects here with auth_code.
    Exchange auth_code → access_token and display it.
    """
    params = dict(request.query_params)
    auth_code = params.get("auth_code") or params.get("code", "")
    state = params.get("state", "")
    error = params.get("error", "")

    if error:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto">
        <h2 style="color:#d32f2f">❌ Autorización rechazada</h2>
        <p>TikTok devolvió error: <code>{error}</code></p>
        <p>Inténtalo de nuevo en <a href="/tiktok/auth">/tiktok/auth</a></p>
        </body></html>
        """, status_code=400)

    if not auth_code:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto">
        <h2 style="color:#d32f2f">❌ No se recibió auth_code</h2>
        <p>Parámetros recibidos: <code>{params}</code></p>
        </body></html>
        """, status_code=400)

    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

    if not client_key or not client_secret:
        return HTMLResponse("""
        <html><body style="font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto">
        <h2 style="color:#d32f2f">❌ Faltan TIKTOK_CLIENT_KEY o TIKTOK_CLIENT_SECRET</h2>
        <p>Añádelos en Railway → Variables.</p>
        </body></html>
        """, status_code=400)

    # Exchange auth_code for access_token
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/",
            json={
                "app_id": client_key,
                "secret": client_secret,
                "auth_code": auth_code,
            }
        )

    data = r.json()
    logger.info(f"TikTok OAuth response: {data}")

    if data.get("code") != 0:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto">
        <h2 style="color:#d32f2f">❌ Error al obtener access token</h2>
        <pre style="background:#f5f5f5;padding:16px;border-radius:8px">{json.dumps(data, indent=2)}</pre>
        </body></html>
        """, status_code=400)

    token_data = data.get("data", {})
    access_token = token_data.get("access_token", "")
    advertiser_ids = token_data.get("advertiser_ids", [])

    return HTMLResponse(f"""
    <html><head><meta charset="utf-8">
    <style>body{{font-family:sans-serif;padding:40px;max-width:700px;margin:0 auto}}
    .box{{background:#e8f5e9;border:2px solid #2e7d32;border-radius:12px;padding:24px;margin:20px 0}}
    .token{{background:#1a1a1a;color:#00ff88;padding:16px;border-radius:8px;
    font-family:monospace;font-size:13px;word-break:break-all;margin:12px 0}}
    .step{{background:#fff3e0;border-left:4px solid #f57c00;padding:12px 16px;margin:8px 0;border-radius:4px}}
    </style></head>
    <body>
    <h2 style="color:#2e7d32">✅ TikTok autorizado correctamente</h2>
    <div class="box">
      <b>🔑 Access Token obtenido:</b>
      <div class="token">{access_token}</div>
      <b>📋 Advertiser IDs vinculados:</b> {', '.join(str(i) for i in advertiser_ids)}
    </div>
    <h3>Próximos pasos — añadir en Railway:</h3>
    <div class="step">1. Ve a <b>Railway → tu proyecto → Variables</b></div>
    <div class="step">2. Añade: <code>TIKTOK_ACCESS_TOKEN</code> = <b>{access_token}</b></div>
    <div class="step">3. Añade: <code>TIKTOK_ADVERTISER_ID</code> = <b>7626428696811274258</b></div>
    <div class="step">4. Railway redespliega automáticamente (~1 min)</div>
    <div class="step">5. Verifica en: <a href="/api/marketing/test-tiktok">/api/marketing/test-tiktok</a></div>
    <p style="color:#666;margin-top:20px">⚠️ Guarda este token de forma segura. Es válido hasta que lo revocas desde TikTok Business.</p>
    </body></html>
    """)

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
# SUCCESS PAGE — After Stripe Payment
# ════════════════════════════════════════════════════════

@app.get("/success", response_class=HTMLResponse)
async def success_page(session_id: str = Query("", alias="session_id")):
    """
    Stripe redirects here after successful payment.
    - Fires Meta Pixel Purchase event (browser-side)
    - Shows order confirmation to customer
    - Suggests related products (upsell)
    """
    pixel_id = os.getenv("META_PIXEL_ID", "")

    # Fetch top 3 products for upsell
    all_products = await product_manager.get_current_products()
    upsell_products = [p for p in all_products if p.get("image_url")][:3]
    upsell_html = ""
    for p in upsell_products:
        upsell_html += f"""
        <a href="/product/{p['id']}" style="text-decoration:none;color:inherit">
          <div style="background:white;border-radius:10px;padding:14px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.08);transition:transform 0.2s" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='none'">
            <img src="{p.get('image_url','')}" style="width:100%;height:120px;object-fit:contain;border-radius:6px;margin-bottom:8px">
            <p style="font-size:0.85rem;color:#333;margin:4px 0;font-weight:600">{str(p.get('name',''))[:40]}</p>
            <p style="color:#1a5e35;font-weight:bold">€{p.get('selling_price',0):.2f}</p>
          </div>
        </a>"""

    pixel_script = ""
    if pixel_id:
        pixel_script = f"""
  <script>
    !function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};if(!f._fbq)f._fbq=n;
    n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,
    document,'script','https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{pixel_id}');
    fbq('track', 'PageView');
    fbq('track', 'Purchase', {{currency:'EUR', value: 0}});
  </script>
  <noscript><img height="1" width="1" style="display:none"
    src="https://www.facebook.com/tr?id={pixel_id}&ev=Purchase&noscript=1"/></noscript>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>¡Pedido Confirmado! | PataHogar</title>
  {pixel_script}
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333}}
    .nav{{background:#1a5e35;padding:12px 20px;display:flex;align-items:center;justify-content:space-between}}
    .nav a{{color:white;text-decoration:none;font-size:1.1rem;font-weight:bold}}
    .container{{max-width:700px;margin:40px auto;padding:20px;text-align:center}}
    .card{{background:white;border-radius:16px;padding:40px 30px;box-shadow:0 4px 20px rgba(0,0,0,0.08);margin-bottom:30px}}
    .checkmark{{width:80px;height:80px;background:#27ae60;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:40px}}
    h1{{color:#1a1a1a;font-size:1.8rem;margin-bottom:10px}}
    .subtitle{{color:#666;font-size:1rem;margin-bottom:24px;line-height:1.6}}
    .steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0;text-align:center}}
    .step{{background:#f0f9f0;border-radius:10px;padding:14px 8px}}
    .step .icon{{font-size:1.8rem;margin-bottom:6px}}
    .step p{{font-size:0.8rem;color:#555;line-height:1.4}}
    .btn{{display:inline-block;background:#ff6b35;color:white;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:bold;font-size:1rem;margin:8px}}
    .btn-green{{background:#1a5e35}}
    .upsell{{margin-top:10px}}
    .upsell h3{{color:#1a5e35;margin-bottom:16px;font-size:1.1rem}}
    .upsell-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
    @media(max-width:500px){{.steps{{grid-template-columns:1fr}}.upsell-grid{{grid-template-columns:1fr}}}}
    .footer{{color:#888;font-size:0.82rem;margin-top:30px;padding-bottom:20px}}
  </style>
</head>
<body>
<nav class="nav">
  <a href="https://patahogar.com">🐾 PataHogar</a>
  <span style="color:#ff6b35;font-size:0.9rem">✅ Pago completado</span>
</nav>

<div class="container">
  <div class="card">
    <div class="checkmark">✅</div>
    <h1>¡Gracias por tu compra!</h1>
    <p class="subtitle">
      Tu pedido ha sido confirmado y ya está siendo procesado.<br>
      Recibirás un email con los detalles y el número de seguimiento en breve.
    </p>

    <div class="steps">
      <div class="step">
        <div class="icon">✅</div>
        <p><b>Pago confirmado</b><br>Tu pago se procesó con éxito</p>
      </div>
      <div class="step">
        <div class="icon">📦</div>
        <p><b>Preparando envío</b><br>BigBuy prepara tu pedido (24-48h)</p>
      </div>
      <div class="step">
        <div class="icon">🚚</div>
        <p><b>Entrega estimada</b><br>3-7 días laborables</p>
      </div>
    </div>

    <a href="https://patahogar.com/catalog.html" class="btn btn-green">🛍️ Seguir comprando</a>
    <a href="mailto:info@patahogar.com" class="btn" style="background:#3498db">✉️ ¿Preguntas?</a>
  </div>

  {f'''<div class="card upsell">
    <h3>🔥 También te puede gustar</h3>
    <div class="upsell-grid">{upsell_html}</div>
  </div>''' if upsell_html else ""}

  <p class="footer">PataHogar — Mascotas &amp; Hogar con Amor 🐾 | <a href="/privacy" style="color:#888">Privacidad</a> | <a href="/terms" style="color:#888">Términos</a></p>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


# ════════════════════════════════════════════════════════
# SHOPPING CART PAGE
# ════════════════════════════════════════════════════════

@app.get("/cart", response_class=HTMLResponse)
async def cart_page():
    """صفحة السلة — تقرأ من localStorage وتعرض المنتجات."""
    pixel_id = os.getenv("META_PIXEL_ID", "")
    pixel_init = ""
    if pixel_id:
        pixel_init = f"""
  <script>
    !function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};if(!f._fbq)f._fbq=n;
    n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,
    document,'script','https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{pixel_id}');
    fbq('track', 'PageView');
  </script>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tu Carrito | PataHogar</title>
  {pixel_init}
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f8f9fa;color:#333}}
    .nav{{background:#1a5e35;padding:12px 20px;display:flex;align-items:center;justify-content:space-between}}
    .nav a{{color:white;text-decoration:none;font-size:1.1rem;font-weight:bold}}
    .nav-right{{display:flex;align-items:center;gap:16px}}
    .container{{max-width:900px;margin:0 auto;padding:20px}}
    h1{{font-size:1.5rem;color:#1a1a1a;margin:20px 0 16px}}
    .cart-layout{{display:grid;grid-template-columns:1fr 320px;gap:24px}}
    @media(max-width:680px){{.cart-layout{{grid-template-columns:1fr}}}}
    .cart-items{{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
    .cart-item{{display:grid;grid-template-columns:80px 1fr auto;gap:14px;align-items:center;padding:14px 0;border-bottom:1px solid #f0f0f0}}
    .cart-item:last-child{{border-bottom:none}}
    .cart-item img{{width:80px;height:80px;object-fit:contain;border-radius:8px;background:#f8f9fa}}
    .item-name{{font-weight:600;font-size:0.95rem;margin-bottom:4px;color:#1a1a1a}}
    .item-price{{color:#1a5e35;font-weight:bold;font-size:1rem}}
    .qty-ctrl{{display:flex;align-items:center;gap:8px;margin-top:8px}}
    .qty-btn{{width:28px;height:28px;border:1.5px solid #ddd;background:white;border-radius:6px;cursor:pointer;font-size:1rem;display:flex;align-items:center;justify-content:center}}
    .qty-btn:hover{{border-color:#1a5e35;color:#1a5e35}}
    .qty-val{{width:36px;text-align:center;font-weight:bold}}
    .remove-btn{{background:none;border:none;color:#ccc;cursor:pointer;font-size:1.2rem;padding:4px}}
    .remove-btn:hover{{color:#e74c3c}}
    .summary{{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);position:sticky;top:20px;height:fit-content}}
    .summary h3{{font-size:1.1rem;color:#1a1a1a;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #f0f0f0}}
    .summary-row{{display:flex;justify-content:space-between;margin-bottom:10px;font-size:0.95rem}}
    .summary-total{{display:flex;justify-content:space-between;font-size:1.2rem;font-weight:bold;color:#1a5e35;padding-top:12px;border-top:2px solid #1a5e35;margin-top:8px}}
    .btn-checkout{{width:100%;padding:16px;background:#ff6b35;color:white;border:none;border-radius:10px;font-size:1.1rem;font-weight:bold;cursor:pointer;margin-top:16px;transition:background 0.2s}}
    .btn-checkout:hover{{background:#e55a25}}
    .btn-checkout:disabled{{background:#ccc;cursor:not-allowed}}
    .btn-continue{{display:block;text-align:center;color:#1a5e35;text-decoration:none;margin-top:12px;font-size:0.9rem}}
    .empty-cart{{text-align:center;padding:60px 20px;color:#888}}
    .empty-cart .icon{{font-size:4rem;margin-bottom:16px}}
    .loading{{display:none;text-align:center;padding:10px;color:#1a5e35}}
    .free-ship{{background:#e8f5e9;color:#1a5e35;padding:8px 12px;border-radius:8px;font-size:0.82rem;text-align:center;margin-top:12px}}
  </style>
</head>
<body>
<nav class="nav">
  <a href="https://patahogar.com">🐾 PataHogar</a>
  <div class="nav-right">
    <a href="https://patahogar.com/catalog.html" style="color:rgba(255,255,255,0.8);font-size:0.9rem">← Seguir comprando</a>
  </div>
</nav>

<div class="container">
  <h1>🛒 Tu Carrito</h1>

  <div id="empty-cart" class="empty-cart" style="display:none">
    <div class="icon">🛒</div>
    <h2>Tu carrito está vacío</h2>
    <p style="margin:8px 0 20px">Descubre nuestros productos y añade algo especial</p>
    <a href="https://patahogar.com/catalog.html" style="background:#1a5e35;color:white;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:bold">Ver catálogo</a>
  </div>

  <div id="cart-content" class="cart-layout">
    <div class="cart-items" id="cart-items-list">
      <!-- Items rendered by JS -->
    </div>

    <div class="summary">
      <h3>📋 Resumen del pedido</h3>
      <div class="summary-row"><span>Subtotal</span><span id="subtotal">€0.00</span></div>
      <div class="summary-row"><span>Envío</span><span style="color:#27ae60">Calculado en checkout</span></div>
      <div class="summary-total"><span>Total</span><span id="total">€0.00</span></div>
      <div class="free-ship">🚚 ¡Envío gratis en pedidos +€30!</div>
      <button class="btn-checkout" id="checkout-btn" onclick="checkout()">
        🔒 Pagar ahora
      </button>
      <div class="loading" id="loading">⏳ Preparando pago seguro...</div>
      <a href="https://patahogar.com/catalog.html" class="btn-continue">← Seguir comprando</a>
    </div>
  </div>
</div>

<script>
  var CHECKOUT_URL = 'https://patabot-production.up.railway.app/api/checkout/create-session';
  var PIXEL_ID = '{pixel_id}';

  function getCart() {{
    try {{ return JSON.parse(localStorage.getItem('patahogar_cart') || '[]'); }}
    catch(e) {{ return []; }}
  }}
  function saveCart(cart) {{
    localStorage.setItem('patahogar_cart', JSON.stringify(cart));
    updateCartBadge();
  }}
  function updateCartBadge() {{
    var cart = getCart();
    var total = cart.reduce(function(s,i){{return s+i.qty;}},0);
    var badges = document.querySelectorAll('.cart-badge');
    badges.forEach(function(b){{b.textContent=total>0?total:'';b.style.display=total>0?'inline':'none';}});
  }}

  function renderCart() {{
    var cart = getCart();
    var list = document.getElementById('cart-items-list');
    var content = document.getElementById('cart-content');
    var empty = document.getElementById('empty-cart');

    if (!cart.length) {{
      content.style.display = 'none';
      empty.style.display = 'block';
      return;
    }}
    content.style.display = 'grid';
    empty.style.display = 'none';

    var html = '';
    var subtotal = 0;
    cart.forEach(function(item, idx) {{
      var lineTotal = item.price * item.qty;
      subtotal += lineTotal;
      html += '<div class="cart-item" id="item-'+idx+'">' +
        '<img src="'+item.image+'" onerror="this.src=\\'data:image/svg+xml,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'80\\' height=\\'80\\'><text y=\\'50\\' font-size=\\'40\\'>🐾</text></svg>\\'">' +
        '<div><div class="item-name">'+item.name.substring(0,55)+'</div>' +
        '<div class="item-price">€'+item.price.toFixed(2)+'</div>' +
        '<div class="qty-ctrl">' +
        '<button class="qty-btn" onclick="changeQty('+idx+',-1)">−</button>' +
        '<span class="qty-val">'+item.qty+'</span>' +
        '<button class="qty-btn" onclick="changeQty('+idx+',1)">+</button>' +
        '<span style="font-size:0.82rem;color:#888;margin-left:4px">= €'+(lineTotal).toFixed(2)+'</span>' +
        '</div></div>' +
        '<button class="remove-btn" onclick="removeItem('+idx+')" title="Eliminar">🗑️</button>' +
        '</div>';
    }});
    list.innerHTML = html;

    document.getElementById('subtotal').textContent = '€'+subtotal.toFixed(2);
    document.getElementById('total').textContent = '€'+subtotal.toFixed(2);
  }}

  function changeQty(idx, delta) {{
    var cart = getCart();
    if (!cart[idx]) return;
    cart[idx].qty = Math.max(1, Math.min(10, cart[idx].qty + delta));
    saveCart(cart);
    renderCart();
  }}

  function removeItem(idx) {{
    var cart = getCart();
    cart.splice(idx, 1);
    saveCart(cart);
    renderCart();
  }}

  async function checkout() {{
    var cart = getCart();
    if (!cart.length) return;
    var btn = document.getElementById('checkout-btn');
    var loading = document.getElementById('loading');
    btn.disabled = true;
    loading.style.display = 'block';

    // Pixel: InitiateCheckout
    if (typeof fbq !== 'undefined') {{
      var total = cart.reduce(function(s,i){{return s+i.price*i.qty;}},0);
      fbq('track', 'InitiateCheckout', {{
        content_ids: cart.map(function(i){{return String(i.id);}}),
        content_type: 'product',
        value: total,
        currency: 'EUR',
        num_items: cart.reduce(function(s,i){{return s+i.qty;}},0)
      }});
    }}

    try {{
      var cartPayload = cart.map(function(i) {{
        return {{
          id: i.id, sku: i.sku || '', name: i.name,
          selling_price: i.price, wholesale_price: i.wholesale || 0,
          image_url: i.image, qty: i.qty
        }};
      }});
      var resp = await fetch(CHECKOUT_URL, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{cart: cartPayload}})
      }});
      var data = await resp.json();
      if (data.checkout_url) {{
        localStorage.removeItem('patahogar_cart');
        window.location.href = data.checkout_url;
      }} else {{
        alert('Error al preparar el pago: ' + (data.error || 'Intenta de nuevo'));
        btn.disabled = false;
        loading.style.display = 'none';
      }}
    }} catch(e) {{
      alert('Error de conexión. Intenta de nuevo.');
      btn.disabled = false;
      loading.style.display = 'none';
    }}
  }}

  // Init
  renderCart();
  updateCartBadge();
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


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

@app.get("/api/fix-all")
async def fix_all():
    """
    🚀 أداة إصلاح شاملة — تشغيل بخطوة واحدة:
    1. مسح الإعلانات المعلقة ذات الربح المنخفض
    2. مسح سجل المقترحات القديمة
    3. تشغيل إثراء الأسماء والأوصاف
    4. إطلاق التسويق اليومي لاقتراحات جديدة
    """
    results = {}

    # 1. Clear low-margin pending ads
    results["clear_ads"] = await marketing_manager.clear_low_margin_pending_ads(min_profit=10.0)

    # 2. Reset proposed tracker
    results["reset_proposed"] = await marketing_manager.reset_proposed_tracker()

    # 3. Start name enrichment
    results["enrichment"] = await product_manager.run_re_enrich_descriptions()

    # 4. Launch daily marketing with fresh proposals
    top_products = await product_manager.get_current_products()
    research_results = await research_manager.get_research_status()
    asyncio.create_task(marketing_manager.run_daily_marketing(top_products, research_results))
    results["marketing"] = "started — check /api/marketing/status in 2 minutes"

    return {
        "status": "✅ Fix-all started",
        "steps": results,
        "next": "Check /api/marketing/status in 2 min for new high-quality ad proposals"
    }

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

async def hourly_abandoned_cart_check():
    try:
        result = await order_manager.check_abandoned_carts()
        if result.get("recovery_emails_sent", 0) > 0:
            logger.info(f"Abandoned cart recovery: {result['recovery_emails_sent']} emails sent")
    except Exception as e:
        logger.error(f"Abandoned cart check failed: {e}")

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
    s  = product_manager.get_enrichment_status()
    os_ = order_manager.get_order_stats()
    mk = await marketing_manager.get_campaigns_status()
    return {
        "products": {
            "total":          s["total_products"],
            "with_images":    s["with_images"],
            "with_names":     s["with_names"],
            "needs_names":    s.get("needs_enrichment", 0),
            "images_pct":     s.get("images_pct", 0),
            "names_pct":      s.get("names_pct", 0),
            "enrichment_pct": s["progress_pct"],
        },
        "orders": {
            "total":    os_.get("total_orders", 0),
            "revenue":  os_.get("total_revenue", 0),
            "profit":   os_.get("total_profit", 0),
            "shipped":  os_.get("shipped", 0),
        },
        "marketing": {
            "active_ads":      mk.get("active_ads", 0),
            "pending_approval": mk.get("pending_approval", 0),
            "meta_ok":         mk.get("meta_configured", False),
            "tiktok_ok":       mk.get("tiktok_configured", False),
        },
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
    scheduler.add_job(hourly_abandoned_cart_check, 'interval', hours=1)
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
