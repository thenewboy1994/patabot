"""
Marketing Manager v2.0 — Phase 4
==================================
- بحث يومي في السوق الأوروبية
- إنشاء حملات Meta Ads تلقائياً
- إشعار محمد بالبريد للموافقة
- إطلاق الإعلانات بعد الموافقة
- تتبع الأداء وإيقاف الخاسرين
"""

import os
import httpx
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger('PataBot.Marketing')

# ── Meta / Facebook Ads ──
META_ACCESS_TOKEN   = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID  = os.getenv("META_AD_ACCOUNT_ID", "")   # act_XXXXXXXXXX
META_PAGE_ID        = os.getenv("META_PAGE_ID", "")
META_PIXEL_ID       = os.getenv("META_PIXEL_ID", "")
META_API_VERSION    = "v19.0"
META_BASE           = f"https://graph.facebook.com/{META_API_VERSION}"

# ── TikTok Ads ──
TIKTOK_ACCESS_TOKEN   = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_ADVERTISER_ID  = os.getenv("TIKTOK_ADVERTISER_ID", "")

# ── Email (Resend API — works on Railway, no SMTP port blocking) ──
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
OWNER_EMAIL    = os.getenv("OWNER_EMAIL", "mohaelmansouri.1994@gmail.com")

# ── Storage ──
_CACHE_DIR    = Path(os.getenv("CACHE_DIR", "."))
ADS_FILE      = _CACHE_DIR / "ads_cache.json"

# ── European targets ──
EU_TARGETS = {
    "ES": {"lang": "es", "name": "España",      "currency": "EUR"},
    "FR": {"lang": "fr", "name": "France",       "currency": "EUR"},
    "DE": {"lang": "de", "name": "Deutschland",  "currency": "EUR"},
    "NL": {"lang": "nl", "name": "Nederland",    "currency": "EUR"},
    "IT": {"lang": "it", "name": "Italia",       "currency": "EUR"},
    "BE": {"lang": "fr", "name": "Belgique",     "currency": "EUR"},
    "PT": {"lang": "pt", "name": "Portugal",     "currency": "EUR"},
    "AT": {"lang": "de", "name": "Österreich",   "currency": "EUR"},
}

# ── Ad copy templates (8 languages) ──
AD_TEMPLATES = {
    "es": {
        "headline": "🔥 {product_name} — Oferta exclusiva",
        "body": "✅ Envío rápido a España\n✅ Precio increíble\n✅ Devolución en 14 días\n\n👉 patahogar.com",
        "cta": "SHOP_NOW"
    },
    "en": {
        "headline": "🔥 {product_name} — Exclusive deal",
        "body": "✅ Fast shipping to Europe\n✅ Best price guaranteed\n✅ Easy 14-day returns\n\n👉 patahogar.com",
        "cta": "SHOP_NOW"
    },
    "fr": {
        "headline": "🔥 {product_name} — Offre exclusive",
        "body": "✅ Livraison rapide en France\n✅ Meilleur prix garanti\n✅ Retours sous 14 jours\n\n👉 patahogar.com",
        "cta": "SHOP_NOW"
    },
    "de": {
        "headline": "🔥 {product_name} — Exklusives Angebot",
        "body": "✅ Schneller Versand nach Deutschland\n✅ Bester Preis garantiert\n✅ 14 Tage Rückgabe\n\n👉 patahogar.com",
        "cta": "SHOP_NOW"
    },
    "nl": {
        "headline": "🔥 {product_name} — Exclusieve deal",
        "body": "✅ Snelle levering in Nederland\n✅ Beste prijs gegarandeerd\n✅ 14 dagen retour\n\n👉 patahogar.com",
        "cta": "SHOP_NOW"
    },
    "it": {
        "headline": "🔥 {product_name} — Offerta esclusiva",
        "body": "✅ Spedizione rapida in Italia\n✅ Prezzo migliore garantito\n✅ Reso entro 14 giorni\n\n👉 patahogar.com",
        "cta": "SHOP_NOW"
    },
}


class MarketingManager:

    def __init__(self):
        self.campaigns: List[Dict] = []
        self.pending_ads: List[Dict] = []
        self.active_ads: List[Dict] = []
        self.organic_posts: List[Dict] = []
        self._load_ads()

    # ─── Persistence ───

    def _load_ads(self):
        try:
            if ADS_FILE.exists():
                data = json.loads(ADS_FILE.read_text(encoding="utf-8"))
                self.campaigns    = data.get("campaigns", [])
                self.pending_ads  = data.get("pending_ads", [])
                self.active_ads   = data.get("active_ads", [])
                logger.info(f"Loaded {len(self.campaigns)} campaigns, {len(self.active_ads)} active ads")
        except Exception as e:
            logger.error(f"Ads load error: {e}")

    def _save_ads(self):
        try:
            ADS_FILE.write_text(json.dumps({
                "campaigns":   self.campaigns,
                "pending_ads": self.pending_ads,
                "active_ads":  self.active_ads,
                "saved_at":    datetime.now().isoformat()
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Ads save error: {e}")

    # ─── Email Helper ───

    async def _send_email(self, subject: str, html: str):
        """Send via Resend API (HTTPS port 443 — never blocked by Railway)."""
        if not RESEND_API_KEY:
            logger.warning("RESEND_API_KEY not set — email not sent. Add it in Railway env vars.")
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": "PataBot <onboarding@resend.dev>",
                        "to": [OWNER_EMAIL],
                        "subject": subject,
                        "html": html
                    }
                )
                if r.status_code in (200, 201):
                    logger.info(f"✅ Email sent via Resend: {subject}")
                else:
                    logger.error(f"Resend error {r.status_code}: {r.text[:300]}")
        except Exception as e:
            logger.error(f"Email error: {type(e).__name__}: {e}")

    # ════════════════════════════════════════════════════════
    # PHASE 4 — DAILY MARKETING PIPELINE
    # ════════════════════════════════════════════════════════

    async def run_daily_marketing(self, top_products: List[Dict], research_results: Dict):
        """
        Pipeline اليومي الكامل للتسويق:
        1. اختيار أفضل 5 منتجات للإعلان
        2. إنشاء مقترح إعلان لكل منتج
        3. إرسال طلب موافقة لمحمد
        4. تحليل أداء الإعلانات النشطة
        """
        logger.info("📣 Starting daily marketing pipeline...")

        if not top_products:
            logger.warning("No products for marketing — skipping")
            return {"status": "no_products"}

        # Step 1: Pick best 5 products for ads
        ad_candidates = self._select_ad_candidates(top_products, research_results)

        # Step 2: Create ad proposals
        proposals = []
        for product in ad_candidates[:3]:  # Max 3 proposals per day
            proposal = await self._create_ad_proposal(product, research_results)
            if proposal:
                proposals.append(proposal)

        # Step 3: Notify Mohamed
        if proposals:
            await self._notify_mohamed_proposals(proposals)

        # Step 4: Check active ads performance
        await self._check_active_ads_performance()

        logger.info(f"✅ Daily marketing done — {len(proposals)} proposals sent to Mohamed")
        return {"status": "done", "proposals": len(proposals)}

    def _select_ad_candidates(self, products: List[Dict], research: Dict) -> List[Dict]:
        """اختيار المنتجات الأفضل للإعلان."""
        scored = []
        winning_keywords = research.get("winning_keywords", [])
        # get_research_status() sometimes returns a count (int) instead of a list
        if not isinstance(winning_keywords, list):
            winning_keywords = []

        for p in products[:100]:
            if not p.get("image_url"):
                continue  # بدون صورة لا إعلان

            score = p.get("profit", 0) * 10  # الربح أهم معيار

            # زيادة النقطة إذا يطابق ترند
            name_lower = p.get("name", "").lower()
            for kw in winning_keywords:
                if str(kw).lower() in name_lower:
                    score += 20

            # المنتجات ذات الهامش الأعلى أولاً
            score += p.get("margin_pct", 30)

            scored.append({"product": p, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return [s["product"] for s in scored[:5]]

    async def _create_ad_proposal(self, product: Dict, research: Dict) -> Optional[Dict]:
        """إنشاء مقترح إعلان لمنتج."""
        ad_id = f"AD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{product.get('id','')}"

        # اختيار أفضل دولة للاستهداف بناءً على بحث السوق
        target_country = self._pick_target_country(product, research)
        lang = EU_TARGETS.get(target_country, {}).get("lang", "es")
        template = AD_TEMPLATES.get(lang, AD_TEMPLATES["es"])
        product_name = product.get("name", "Producto")[:50]

        daily_budget = 5.0  # ميزانية يومية ابتدائية 5€

        proposal = {
            "id":             ad_id,
            "product_id":     product.get("id"),
            "product_name":   product_name,
            "product_image":  product.get("image_url", ""),
            "selling_price":  product.get("selling_price", 0),
            "profit":         product.get("profit", 0),
            "target_country": target_country,
            "target_lang":    lang,
            "headline":       template["headline"].format(product_name=product_name),
            "body":           template["body"],
            "cta":            template["cta"],
            "daily_budget":   daily_budget,
            "estimated_reach": int(daily_budget * 400),  # ~400 أشخاص لكل يورو
            "estimated_clicks": int(daily_budget * 20),  # ~20 نقرة لكل يورو
            "platform":       "facebook_instagram",
            "status":         "pending_approval",
            "created_at":     datetime.now().isoformat(),
        }

        self.pending_ads.append(proposal)
        self._save_ads()
        logger.info(f"Ad proposal created: {ad_id} for {product_name} → {target_country}")
        return proposal

    def _pick_target_country(self, product: Dict, research: Dict) -> str:
        """اختيار أفضل دولة للإعلان بناءً على بحث السوق."""
        recommendations = research.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations = []
        name_lower = product.get("name", "").lower()

        # ابحث عن تطابق في توصيات البحث
        for rec in recommendations:
            kw = rec.get("keyword", "").lower()
            if any(word in name_lower for word in kw.split()[:2]):
                country = rec.get("country", "ES")
                if country in EU_TARGETS:
                    return country

        return "ES"  # افتراضي: إسبانيا

    async def _notify_mohamed_proposals(self, proposals: List[Dict]):
        """إرسال بريد لمحمد بمقترحات الإعلانات."""
        if not proposals:
            return

        rows = ""
        for p in proposals:
            approve_url = f"https://patabot-production.up.railway.app/api/marketing/approve-ad?ad_id={p['id']}&action=approve"
            reject_url  = f"https://patabot-production.up.railway.app/api/marketing/approve-ad?ad_id={p['id']}&action=reject"
            rows += f"""
            <tr style="border-bottom:1px solid #eee">
              <td style="padding:12px"><img src="{p['product_image']}" width="60" style="border-radius:8px"></td>
              <td style="padding:12px"><b>{p['product_name']}</b><br>
                <small style="color:#888">💰 Venta: €{p['selling_price']} | Beneficio: €{p['profit']}</small><br>
                <small style="color:#555">🎯 País: {p['target_country']} | Presupuesto: €{p['daily_budget']}/día</small><br>
                <small style="color:#555">📢 {p['headline']}</small>
              </td>
              <td style="padding:12px;text-align:center">
                <a href="{approve_url}" style="background:#27ae60;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none;display:inline-block;margin:4px">✅ Aprobar</a><br>
                <a href="{reject_url}" style="background:#e74c3c;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none;display:inline-block;margin:4px">❌ Rechazar</a>
              </td>
            </tr>"""

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px">
          <h2 style="color:#1a5e35">📣 PataBot — {len(proposals)} propuestas de anuncios nuevas</h2>
          <p>PataBot ha analizado el mercado europeo y ha encontrado los mejores productos para anunciar hoy.</p>
          <table style="width:100%;border-collapse:collapse">
            <tr style="background:#f0f9f4">
              <th style="padding:10px;text-align:left">Producto</th>
              <th style="padding:10px;text-align:left">Detalles</th>
              <th style="padding:10px;text-align:center">Acción</th>
            </tr>
            {rows}
          </table>
          <p style="color:#888;font-size:0.85rem;margin-top:20px">
            Los anuncios aprobados se lanzarán automáticamente en Facebook e Instagram.<br>
            Presupuesto inicial: €{proposals[0]['daily_budget']}/día por anuncio.
          </p>
          <p><b>— PataBot 🐾</b></p>
        </div>"""

        await self._send_email(
            f"📣 PataBot: {len(proposals)} propuestas de anuncios — ¿Apruebas?",
            html
        )

    # ════════════════════════════════════════════════════════
    # META ADS API — CAMPAIGN CREATION
    # ════════════════════════════════════════════════════════

    async def launch_approved_ad(self, ad_id: str) -> Dict:
        """إطلاق إعلان معتمد على Meta Ads."""
        ad = next((a for a in self.pending_ads if a["id"] == ad_id), None)
        if not ad:
            return {"success": False, "error": "Ad not found"}

        if not META_ACCESS_TOKEN or not META_AD_ACCOUNT_ID:
            # حفظ كـ "approved" بدون إطلاق — سيُطلق عند إضافة الـ tokens
            ad["status"] = "approved_no_token"
            self.active_ads.append(ad)
            self.pending_ads.remove(ad)
            self._save_ads()
            logger.info(f"Ad {ad_id} approved — waiting for META_ACCESS_TOKEN in Railway")
            return {"success": True, "status": "approved_pending_token",
                    "message": "Aprobado. Añade META_ACCESS_TOKEN en Railway para lanzar."}

        try:
            campaign_id = await self._meta_create_campaign(ad)
            if not campaign_id:
                return {"success": False, "error": "Failed to create Meta campaign"}

            adset_id = await self._meta_create_adset(ad, campaign_id)
            if not adset_id:
                return {"success": False, "error": "Failed to create Meta ad set"}

            ad_creative_id = await self._meta_create_creative(ad)
            if not ad_creative_id:
                return {"success": False, "error": "Failed to create Meta ad creative"}

            final_ad_id = await self._meta_create_ad(adset_id, ad_creative_id, ad["headline"])

            ad["status"]       = "active"
            ad["meta_campaign_id"] = campaign_id
            ad["meta_adset_id"]    = adset_id
            ad["meta_ad_id"]       = final_ad_id
            ad["launched_at"]  = datetime.now().isoformat()
            self.active_ads.append(ad)
            self.pending_ads.remove(ad)
            self._save_ads()

            logger.info(f"✅ Ad {ad_id} launched on Meta — campaign: {campaign_id}")
            await self._send_email(
                f"🚀 Anuncio lanzado: {ad['product_name']}",
                f"<p>El anuncio <b>{ad['product_name']}</b> está activo en Facebook/Instagram.</p>"
                f"<p>País: {ad['target_country']} | Presupuesto: €{ad['daily_budget']}/día</p>"
                f"<p>Seguimiento en <a href='https://www.facebook.com/adsmanager'>Meta Ads Manager</a></p>"
            )
            return {"success": True, "campaign_id": campaign_id, "status": "active"}

        except Exception as e:
            logger.error(f"Meta ads launch error: {e}")
            return {"success": False, "error": str(e)}

    async def reject_ad(self, ad_id: str) -> Dict:
        """رفض مقترح إعلان."""
        ad = next((a for a in self.pending_ads if a["id"] == ad_id), None)
        if not ad:
            return {"success": False, "error": "Ad not found"}
        ad["status"] = "rejected"
        self.pending_ads.remove(ad)
        self._save_ads()
        logger.info(f"Ad {ad_id} rejected by Mohamed")
        return {"success": True, "status": "rejected"}

    async def _meta_create_campaign(self, ad: Dict) -> Optional[str]:
        """إنشاء حملة على Meta."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/campaigns",
                params={"access_token": META_ACCESS_TOKEN},
                json={
                    "name":      f"PataHogar — {ad['product_name'][:40]} ({ad['target_country']})",
                    "objective": "OUTCOME_SALES",
                    "status":    "ACTIVE",
                    "special_ad_categories": [],
                    "is_adset_budget_sharing_enabled": False
                }
            )
            if r.status_code == 200:
                return r.json().get("id")
            logger.error(f"Meta campaign error: {r.text[:300]}")
            return None

    async def _meta_create_adset(self, ad: Dict, campaign_id: str) -> Optional[str]:
        """إنشاء مجموعة إعلانية على Meta."""
        daily_budget_cents = int(ad["daily_budget"] * 100)
        country = ad["target_country"]

        targeting = {
            "geo_locations": {"countries": [country]},
            "age_min": 22,
            "age_max": 55,
            "interests": [
                {"id": "6003107902433", "name": "Pets"},
                {"id": "6003200395100", "name": "Home decoration"},
                {"id": "6003139266461", "name": "Online shopping"},
            ]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/adsets",
                params={"access_token": META_ACCESS_TOKEN},
                json={
                    "name":              f"AdSet — {country} — {ad['product_name'][:30]}",
                    "campaign_id":       campaign_id,
                    "daily_budget":      daily_budget_cents,
                    "billing_event":     "IMPRESSIONS",
                    "optimization_goal": "OFFSITE_CONVERSIONS",
                    "targeting":         targeting,
                    "status":            "ACTIVE",
                    "pixel_id":          META_PIXEL_ID if META_PIXEL_ID else None,
                }
            )
            if r.status_code == 200:
                return r.json().get("id")
            logger.error(f"Meta adset error: {r.text[:300]}")
            return None

    async def _meta_create_creative(self, ad: Dict) -> Optional[str]:
        """إنشاء creative للإعلان (صورة + نص)."""
        if not META_PAGE_ID:
            logger.warning("META_PAGE_ID not set — skipping creative creation")
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/adcreatives",
                params={"access_token": META_ACCESS_TOKEN},
                json={
                    "name": f"Creative — {ad['product_name'][:40]}",
                    "object_story_spec": {
                        "page_id": META_PAGE_ID,
                        "link_data": {
                            "link":        "https://patahogar.com",
                            "message":     ad["body"],
                            "name":        ad["headline"],
                            "call_to_action": {"type": ad["cta"], "value": {"link": "https://patahogar.com"}},
                            "picture":     ad["product_image"] if ad.get("product_image") else None,
                        }
                    }
                }
            )
            if r.status_code == 200:
                return r.json().get("id")
            logger.error(f"Meta creative error: {r.text[:300]}")
            return None

    async def _meta_create_ad(self, adset_id: str, creative_id: str, name: str) -> Optional[str]:
        """إنشاء الإعلان النهائي على Meta."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/ads",
                params={"access_token": META_ACCESS_TOKEN},
                json={
                    "name":       name[:40],
                    "adset_id":   adset_id,
                    "creative":   {"creative_id": creative_id},
                    "status":     "ACTIVE"
                }
            )
            if r.status_code == 200:
                return r.json().get("id")
            logger.error(f"Meta ad error: {r.text[:300]}")
            return None

    # ════════════════════════════════════════════════════════
    # PERFORMANCE TRACKING
    # ════════════════════════════════════════════════════════

    async def _check_active_ads_performance(self):
        """تحقق من أداء الإعلانات النشطة — أوقف الخاسرين."""
        if not META_ACCESS_TOKEN or not self.active_ads:
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            for ad in self.active_ads:
                meta_ad_id = ad.get("meta_ad_id")
                if not meta_ad_id:
                    continue
                try:
                    r = await client.get(
                        f"{META_BASE}/{meta_ad_id}/insights",
                        params={
                            "access_token": META_ACCESS_TOKEN,
                            "fields": "spend,clicks,impressions,actions",
                            "date_preset": "last_3d"
                        }
                    )
                    if r.status_code == 200:
                        insights = r.json().get("data", [{}])[0]
                        spend   = float(insights.get("spend", 0))
                        clicks  = int(insights.get("clicks", 0))
                        actions = insights.get("actions", [])
                        purchases = sum(int(a.get("value", 0)) for a in actions if a.get("action_type") == "purchase")

                        ad["performance"] = {
                            "spend": spend, "clicks": clicks, "purchases": purchases,
                            "cpc": round(spend / clicks, 2) if clicks else 0,
                            "roas": round((purchases * ad.get("selling_price", 0)) / spend, 2) if spend else 0,
                            "updated_at": datetime.now().isoformat()
                        }

                        # إيقاف إعلان خاسر (أنفق أكثر من 15€ بدون مبيعات)
                        if spend > 15 and purchases == 0:
                            await self._pause_meta_ad(meta_ad_id)
                            ad["status"] = "paused_no_conversions"
                            logger.info(f"Ad {meta_ad_id} paused — spent €{spend} with 0 sales")
                            await self._send_email(
                                f"⚠️ Anuncio pausado: {ad['product_name']}",
                                f"<p>El anuncio <b>{ad['product_name']}</b> fue pausado automáticamente.</p>"
                                f"<p>Gasto: €{spend} | Ventas: 0 | Clics: {clicks}</p>"
                                f"<p>Puedes revisarlo en <a href='https://www.facebook.com/adsmanager'>Meta Ads Manager</a>.</p>"
                            )

                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Performance check error for {meta_ad_id}: {e}")

        self._save_ads()

    async def _pause_meta_ad(self, meta_ad_id: str):
        """إيقاف إعلان على Meta."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(
                    f"{META_BASE}/{meta_ad_id}",
                    params={"access_token": META_ACCESS_TOKEN},
                    json={"status": "PAUSED"}
                )
        except Exception as e:
            logger.error(f"Pause ad error: {e}")

    # ════════════════════════════════════════════════════════
    # ORGANIC CONTENT
    # ════════════════════════════════════════════════════════

    async def create_organic_content(self):
        logger.info("📝 Organic content creation scheduled")

    async def post_to_all_platforms(self):
        logger.info("📤 Organic posting scheduled")

    # ════════════════════════════════════════════════════════
    # LEGACY / API ENDPOINTS
    # ════════════════════════════════════════════════════════

    async def create_product_content(self, product_id=None) -> Dict:
        return {"status": "Use /api/marketing/run-daily to generate ad proposals"}

    async def propose_paid_ad(self, ad_data: Dict) -> Dict:
        return await self._create_ad_proposal(
            ad_data.get("product", {}),
            {"winning_keywords": [], "recommendations": []}
        )

    async def launch_paid_ad(self, data: Dict) -> Dict:
        return await self.launch_approved_ad(data.get("ad_id", ""))

    async def get_campaigns_status(self) -> Dict:
        return {
            "pending_approval":  len(self.pending_ads),
            "active_ads":        len(self.active_ads),
            "total_campaigns":   len(self.campaigns),
            "meta_configured":   bool(META_ACCESS_TOKEN and META_AD_ACCOUNT_ID),
            "tiktok_configured": bool(TIKTOK_ACCESS_TOKEN),
            "pending_ads":       self.pending_ads[-5:],  # أحدث 5
            "active_ads_summary": [
                {
                    "id":      a["id"],
                    "product": a.get("product_name",""),
                    "country": a.get("target_country",""),
                    "budget":  a.get("daily_budget",0),
                    "status":  a.get("status",""),
                    "perf":    a.get("performance",{})
                }
                for a in self.active_ads[-10:]
            ]
        }
