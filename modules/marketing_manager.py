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
META_API_VERSION    = "v21.0"
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

# ── All ad target countries (EU + CH, DK, LI) ──
EU_TARGETS = {
    "ES": {"lang": "es", "name": "España",       "currency": "EUR"},
    "FR": {"lang": "fr", "name": "France",        "currency": "EUR"},
    "DE": {"lang": "de", "name": "Deutschland",   "currency": "EUR"},
    "NL": {"lang": "nl", "name": "Nederland",     "currency": "EUR"},
    "BE": {"lang": "fr", "name": "Belgique",      "currency": "EUR"},
    "LU": {"lang": "fr", "name": "Luxembourg",    "currency": "EUR"},
    "IT": {"lang": "it", "name": "Italia",        "currency": "EUR"},
    "CH": {"lang": "de", "name": "Schweiz",       "currency": "CHF"},
    "DK": {"lang": "da", "name": "Danmark",       "currency": "DKK"},
    "LI": {"lang": "de", "name": "Liechtenstein", "currency": "CHF"},
    "AT": {"lang": "de", "name": "Österreich",    "currency": "EUR"},
    "PT": {"lang": "pt", "name": "Portugal",      "currency": "EUR"},
}

# Countries for ad campaigns (Mohamed's selection)
AD_TARGET_COUNTRIES = ["ES", "FR", "DE", "NL", "BE", "LU", "IT", "CH", "DK", "LI"]

# DSA required for these EU member states
DSA_REQUIRED_COUNTRIES = {"ES", "FR", "DE", "NL", "BE", "LU", "IT", "DK", "AT", "PT"}

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
        self.default_daily_budget: float = float(os.getenv("DEFAULT_AD_BUDGET", "10.0"))
        self.proposed_tracker: Dict[str, str] = {}  # product_id → ISO timestamp
        self._load_ads()

    # ─── Persistence ───

    def _load_ads(self):
        try:
            if ADS_FILE.exists():
                data = json.loads(ADS_FILE.read_text(encoding="utf-8"))
                self.campaigns       = data.get("campaigns", [])
                self.pending_ads     = data.get("pending_ads", [])
                self.active_ads      = data.get("active_ads", [])
                self.proposed_tracker = data.get("proposed_tracker", {})
                logger.info(f"Loaded {len(self.campaigns)} campaigns, {len(self.active_ads)} active ads, "
                            f"{len(self.proposed_tracker)} tracked proposals")
        except Exception as e:
            logger.error(f"Ads load error: {e}")

    def _save_ads(self):
        try:
            ADS_FILE.write_text(json.dumps({
                "campaigns":        self.campaigns,
                "pending_ads":      self.pending_ads,
                "active_ads":       self.active_ads,
                "proposed_tracker": self.proposed_tracker,
                "saved_at":         datetime.now().isoformat()
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

    # Minimum profit required to run a paid ad (€5/day spend → need €10+ profit per sale to be profitable)
    MIN_AD_PROFIT = 10.0
    # Sweet spot price range for best conversion rates on Meta/TikTok
    SWEET_SPOT_MIN = 15.0
    SWEET_SPOT_MAX = 70.0
    # Pets & home keywords → bonus score (our core niche)
    NICHE_KEYWORDS = [
        "perro", "gato", "mascota", "dog", "cat", "pet", "hund", "chat", "kat",
        "cama", "collar", "correa", "comedero", "bebedero", "juguete", "arnés",
        "hogar", "home", "cocina", "baño", "jardín", "organiz", "led", "lámpara",
        "difusor", "humidif", "purificador", "soporte", "almacen",
        "bed", "feeder", "leash", "toy", "harness", "fountain", "grooming",
    ]

    def _select_ad_candidates(self, products: List[Dict], research: Dict) -> List[Dict]:
        """
        Selecciona los mejores productos para anunciar.
        Filtros obligatorios: imagen + profit >= €10
        Scoring: profit × 10 + niche bonus + sweet spot bonus + research keywords
        """
        recently_proposed = set()
        for pid, ts in self.proposed_tracker.items():
            try:
                age = (datetime.now() - datetime.fromisoformat(ts)).days
                if age < 7:
                    recently_proposed.add(str(pid))
            except Exception:
                pass

        winning_keywords = research.get("winning_keywords", [])
        if not isinstance(winning_keywords, list):
            winning_keywords = []

        scored = []
        skipped_profit = 0
        for p in products[:500]:
            if not p.get("image_url"):
                continue
            if str(p.get("id", "")) in recently_proposed:
                continue
            # Hard filter: minimum profit
            if p.get("profit", 0) < self.MIN_AD_PROFIT:
                skipped_profit += 1
                continue

            score = p.get("profit", 0) * 10
            name_lower = p.get("name", "").lower()
            desc_lower = p.get("description", "").lower()
            combined = name_lower + " " + desc_lower

            # Niche bonus: pets & home = core audience
            for kw in self.NICHE_KEYWORDS:
                if kw in combined:
                    score += 30
                    break

            # Sweet spot price bonus (€15-70 converts best with Meta ads)
            price = p.get("selling_price", 0)
            if self.SWEET_SPOT_MIN <= price <= self.SWEET_SPOT_MAX:
                score += 40

            # Research keyword match bonus
            for kw in winning_keywords:
                if str(kw).lower() in combined:
                    score += 20

            score += p.get("margin_pct", 30)
            scored.append({"product": p, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        logger.info(
            f"Ad candidates: {len(scored)} eligible (skipped {skipped_profit} low-profit, "
            f"{len(recently_proposed)} recently proposed)"
        )
        return [s["product"] for s in scored[:5]]

    async def _create_ad_proposal(self, product: Dict, research: Dict) -> Optional[Dict]:
        """إنشاء مقترح إعلان لمنتج."""
        ad_id = f"AD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{product.get('id','')}"

        # اختيار أفضل دولة للاستهداف بناءً على بحث السوق
        target_country = self._pick_target_country(product, research)
        lang = EU_TARGETS.get(target_country, {}).get("lang", "es")
        template = AD_TEMPLATES.get(lang, AD_TEMPLATES["es"])
        product_name = product.get("name", "Producto")[:50]

        daily_budget = self.default_daily_budget

        proposal = {
            "id":               ad_id,
            "product_id":       product.get("id"),
            "product_name":     product_name,
            "product_image":    product.get("image_url", ""),
            "selling_price":    product.get("selling_price", 0),
            "profit":           product.get("profit", 0),
            "target_country":   target_country,
            "target_lang":      lang,
            "headline":         template["headline"].format(product_name=product_name),
            "body":             template["body"],
            "cta":              template["cta"],
            "daily_budget":     daily_budget,
            "target_countries": AD_TARGET_COUNTRIES,  # all 10 countries
            "estimated_reach":  int(daily_budget * 400 * len(AD_TARGET_COUNTRIES)),
            "estimated_clicks": int(daily_budget * 20 * len(AD_TARGET_COUNTRIES)),
            "platform":         "facebook_instagram",
            "status":           "pending_approval",
            "created_at":       datetime.now().isoformat(),
        }

        self.pending_ads.append(proposal)
        # Mark product as proposed (prevents duplicates for 7 days)
        self.proposed_tracker[str(product.get("id", ""))] = datetime.now().isoformat()
        self._save_ads()
        logger.info(f"Ad proposal created: {ad_id} for {product_name} → {AD_TARGET_COUNTRIES}")
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
        """
        إطلاق إعلان معتمد على Meta Ads.
        يُنشئ حملة CBO واحدة + adset لكل دولة من الـ 10 دول.
        """
        ad = next((a for a in self.pending_ads if a["id"] == ad_id), None)
        if not ad:
            return {"success": False, "error": "Ad not found"}

        if not META_ACCESS_TOKEN or not META_AD_ACCOUNT_ID:
            ad["status"] = "approved_no_token"
            self.active_ads.append(ad)
            self.pending_ads.remove(ad)
            self._save_ads()
            logger.warning(f"Ad {ad_id} approved but META_ACCESS_TOKEN missing in Railway")
            return {"success": True, "status": "approved_pending_token",
                    "message": "Aprobado. Falta META_ACCESS_TOKEN en Railway Variables."}

        try:
            countries = ad.get("target_countries", AD_TARGET_COUNTRIES)
            logger.info(f"Launching ad {ad_id}: {ad['product_name']} → {countries}")

            # Step 1: Create campaign
            campaign_id = await self._meta_create_campaign_cbo(ad, countries)
            if not campaign_id:
                return {"success": False, "error": "❌ Step 1 fallo: No se pudo crear la campaña Meta. Revisa los logs de Railway."}

            # Step 2: Create creative
            ad_creative_id = await self._meta_create_creative(ad)
            if not ad_creative_id:
                async with httpx.AsyncClient(timeout=10.0) as cl:
                    await cl.delete(f"{META_BASE}/{campaign_id}", params={"access_token": META_ACCESS_TOKEN})
                return {"success": False, "error": f"❌ Step 2 fallo: No se pudo crear el creative (comprueba META_PAGE_ID={META_PAGE_ID or 'NO CONFIGURADO'})."}

            # Step 3: Create one adset + one ad per country
            adsets_created = []
            adsets_failed = []
            for country in countries:
                adset_id = await self._meta_create_adset_country(ad, campaign_id, country)
                if adset_id:
                    ad_obj_id = await self._meta_create_ad(adset_id, ad_creative_id,
                                                           f"{ad['headline'][:35]} — {country}")
                    adsets_created.append({"country": country, "adset_id": adset_id, "ad_id": ad_obj_id})
                else:
                    adsets_failed.append(country)
                await asyncio.sleep(0.5)  # Rate limit

            if not adsets_created:
                async with httpx.AsyncClient(timeout=10.0) as cl:
                    await cl.delete(f"{META_BASE}/{campaign_id}", params={"access_token": META_ACCESS_TOKEN})
                return {"success": False, "error": f"❌ Step 3 fallo: No se creó ningún adset. Países con error: {adsets_failed}. Revisa los logs de Railway."}

            ad["status"]           = "active"
            ad["meta_campaign_id"] = campaign_id
            ad["meta_creative_id"] = ad_creative_id
            ad["meta_adsets"]      = adsets_created  # one per country
            ad["countries_active"] = [a["country"] for a in adsets_created]
            ad["launched_at"]      = datetime.now().isoformat()
            self.active_ads.append(ad)
            self.pending_ads.remove(ad)
            self._save_ads()

            countries_str = ", ".join(ad["countries_active"])
            logger.info(f"✅ Ad {ad_id} launched — campaign {campaign_id} | {len(adsets_created)} countries: {countries_str}")

            # TikTok: launch in parallel (non-blocking)
            tiktok_result = {"success": False, "reason": "not configured"}
            if TIKTOK_ACCESS_TOKEN and TIKTOK_ADVERTISER_ID:
                tiktok_result = await self.launch_tiktok_ad(ad)
                if tiktok_result.get("success"):
                    ad["tiktok_campaign_id"] = tiktok_result.get("campaign_id")
                    ad["tiktok_ad_id"]       = tiktok_result.get("ad_id")
                    self._save_ads()

            tiktok_note = f"<p>🎵 <b>TikTok:</b> {'✅ lanzado — ' + str(tiktok_result.get('campaign_id','')) if tiktok_result.get('success') else '⚠️ ' + str(tiktok_result.get('reason','no configurado'))}</p>"

            await self._send_email(
                f"🚀 Anuncio lanzado en {len(adsets_created)} países: {ad['product_name']}",
                f"""<div style='font-family:Arial;max-width:600px;margin:auto;padding:20px'>
                <h2 style='color:#27ae60'>🚀 Anuncio activo en {len(adsets_created)} países</h2>
                <p><b>{ad['product_name']}</b> ya se está publicando en Facebook, Instagram y TikTok.</p>
                <p><b>Países Meta:</b> {countries_str}</p>
                <p><b>Presupuesto Meta:</b> €{ad['daily_budget'] * len(adsets_created):.0f}/día (€{ad['daily_budget']}/país)</p>
                {tiktok_note}
                <p><b>Campaña Meta ID:</b> {campaign_id}</p>
                <p><a href='https://www.facebook.com/adsmanager' style='background:#1877f2;color:white;padding:10px 20px;border-radius:6px;text-decoration:none'>
                Ver en Meta Ads Manager</a></p>
                <p><small>— PataBot 🐾</small></p>
                </div>"""
            )
            return {
                "success": True,
                "campaign_id": campaign_id,
                "adsets_created": len(adsets_created),
                "countries": ad["countries_active"],
                "daily_budget_total": ad["daily_budget"] * len(adsets_created),
                "tiktok": tiktok_result
            }

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

    async def clear_low_margin_pending_ads(self, min_profit: float = 10.0) -> Dict:
        """مسح كل الإعلانات المعلقة ذات الربح أقل من الحد الأدنى."""
        before = len(self.pending_ads)
        self.pending_ads = [a for a in self.pending_ads if a.get("profit", 0) >= min_profit]
        removed = before - len(self.pending_ads)
        self._save_ads()
        logger.info(f"Cleared {removed} low-margin pending ads (threshold: €{min_profit})")
        return {
            "removed": removed,
            "remaining": len(self.pending_ads),
            "threshold": min_profit,
            "message": f"تم حذف {removed} إعلان بربح أقل من €{min_profit}"
        }

    async def reset_proposed_tracker(self) -> Dict:
        """مسح سجل المنتجات المقترحة — يتيح اقتراحها مجدداً."""
        count = len(self.proposed_tracker)
        self.proposed_tracker = {}
        self._save_ads()
        return {"cleared": count, "message": "سجل المقترحات مُسح — يمكن اقتراح نفس المنتجات مجدداً"}

    async def _meta_create_campaign_cbo(self, ad: Dict, countries: List[str]) -> Optional[str]:
        """
        إنشاء حملة بسيطة على Meta (بدون CBO — الميزانية على مستوى كل adset).
        هذا النهج مثبت: هو نفس ما يعمل في test-meta-adset.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/campaigns",
                params={"access_token": META_ACCESS_TOKEN},
                json={
                    "name":          f"PataHogar — {ad['product_name'][:40]} — {len(countries)} países",
                    "objective":     "OUTCOME_SALES",
                    "status":        "ACTIVE",
                    "special_ad_categories": [],
                    "buying_type":   "AUCTION",
                    "is_adset_budget_sharing_enabled": False,
                }
            )
            if r.status_code == 200:
                cid = r.json().get("id")
                logger.info(f"Campaign created: {cid}")
                return cid
            logger.error(f"Meta campaign error {r.status_code}: {r.text[:400]}")
            return None

    async def _meta_create_adset_country(self, ad: Dict, campaign_id: str, country: str) -> Optional[str]:
        """
        إنشاء adset لدولة واحدة مع ميزانيتها الخاصة.
        يستخدم نفس تكوين test-meta-adset الذي أُثبت عمله.
        """
        needs_dsa = country in DSA_REQUIRED_COUNTRIES
        daily_budget_cents = int(ad["daily_budget"] * 100)

        payload = {
            "name":              f"AdSet — {country} — {ad['product_name'][:25]}",
            "campaign_id":       campaign_id,
            "daily_budget":      daily_budget_cents,
            "billing_event":     "IMPRESSIONS",
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "bid_strategy":      "LOWEST_COST_WITHOUT_CAP",
            "destination_type":  "WEBSITE",
            "targeting": {
                "geo_locations": {"countries": [country]},
                "age_min":       22,
                "targeting_automation": {"advantage_audience": 1},
            },
            "status":            "ACTIVE",
            "promoted_object": {
                "pixel_id":          META_PIXEL_ID,
                "custom_event_type": "PURCHASE"
            },
        }
        if needs_dsa:
            payload["dsa_beneficiary"] = "PataHogar"
            payload["dsa_payor"]       = "PataHogar"

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/adsets",
                params={"access_token": META_ACCESS_TOKEN},
                json=payload
            )
            if r.status_code == 200:
                asid = r.json().get("id")
                logger.info(f"AdSet created [{country}]: {asid} — €{ad['daily_budget']}/day")
                return asid
            logger.error(f"AdSet error [{country}] {r.status_code}: {r.text[:400]}")
            return None

    # Backward compatibility aliases
    async def _meta_create_campaign(self, ad: Dict) -> Optional[str]:
        return await self._meta_create_campaign_cbo(ad, [ad.get("target_country", "ES")])

    async def _meta_create_adset(self, ad: Dict, campaign_id: str) -> Optional[str]:
        return await self._meta_create_adset_country(ad, campaign_id, ad.get("target_country", "ES"))

    async def _meta_create_creative(self, ad: Dict) -> Optional[str]:
        """إنشاء creative للإعلان — يُحيل لصفحة المنتج المخصصة."""
        if not META_PAGE_ID:
            logger.warning("META_PAGE_ID not set — skipping creative creation")
            return None

        product_id  = ad.get("product_id", "")
        # Use PataBot /product/{id} — full page with Stripe checkout, pixel tracking, upsell
        product_url = (
            f"https://patabot-production.up.railway.app/product/{product_id}"
            if product_id
            else "https://patabot-production.up.railway.app/cart"
        )

        creative_body = {
            "name": f"Creative — {ad['product_name'][:40]}",
            "object_story_spec": {
                "page_id": META_PAGE_ID,
                "link_data": {
                    "link":    product_url,
                    "message": ad["body"],
                    "name":    ad["headline"],
                    "call_to_action": {
                        "type":  ad["cta"],
                        "value": {"link": product_url}
                    },
                }
            }
        }
        if ad.get("product_image"):
            creative_body["object_story_spec"]["link_data"]["picture"] = ad["product_image"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{META_BASE}/{META_AD_ACCOUNT_ID}/adcreatives",
                params={"access_token": META_ACCESS_TOKEN},
                json=creative_body
            )
            if r.status_code == 200:
                crid = r.json().get("id")
                logger.info(f"Creative created: {crid} → {product_url}")
                return crid
            logger.error(f"Meta creative error {r.status_code}: {r.text[:300]}")
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
    # TIKTOK ADS API
    # ════════════════════════════════════════════════════════

    TIKTOK_BASE = "https://business-api.tiktok.com/open_api/v1.3"

    async def launch_tiktok_ad(self, ad: Dict) -> Dict:
        """
        إطلاق إعلان على TikTok Ads بالتوازي مع Meta.
        يُنشئ: campaign → adgroup → ad
        """
        if not TIKTOK_ACCESS_TOKEN or not TIKTOK_ADVERTISER_ID:
            return {"success": False, "reason": "TikTok not configured — add TIKTOK_ACCESS_TOKEN and TIKTOK_ADVERTISER_ID"}

        headers = {
            "Access-Token": TIKTOK_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }
        product_name = ad.get("product_name", "Producto")[:40]
        product_url  = f"https://patahogar.com/product.html?id={ad.get('product_id','')}" if ad.get("product_id") else "https://patahogar.com/catalog.html"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:

                # Step 1: Campaign
                r = await client.post(
                    f"{self.TIKTOK_BASE}/campaign/create/",
                    headers=headers,
                    json={
                        "advertiser_id": TIKTOK_ADVERTISER_ID,
                        "campaign_name": f"PataHogar — {product_name}",
                        "objective_type": "PRODUCT_SALES",
                        "budget_mode": "BUDGET_MODE_INFINITE",
                        "operation_status": "ENABLE"
                    }
                )
                if r.status_code != 200 or r.json().get("code") != 0:
                    logger.error(f"TikTok campaign error: {r.text[:300]}")
                    return {"success": False, "error": f"TikTok campaign: {r.text[:200]}"}
                campaign_id = r.json()["data"]["campaign_id"]

                # Step 2: Ad Group (one for all EU countries)
                daily_budget = int(ad.get("daily_budget", 10) * 100)  # in cents
                r = await client.post(
                    f"{self.TIKTOK_BASE}/adgroup/create/",
                    headers=headers,
                    json={
                        "advertiser_id":   TIKTOK_ADVERTISER_ID,
                        "campaign_id":     campaign_id,
                        "adgroup_name":    f"PataHogar EU — {product_name}",
                        "placements":      ["PLACEMENT_TIKTOK"],
                        "location_ids":    ["ES", "FR", "DE", "NL", "IT", "BE"],
                        "age_groups":      ["AGE_25_34", "AGE_35_44", "AGE_45_54"],
                        "budget_mode":     "BUDGET_MODE_DAY",
                        "budget":          daily_budget,
                        "schedule_type":   "SCHEDULE_FROM_NOW",
                        "billing_event":   "OCPM",
                        "optimization_goal": "CONVERT",
                        "pixel_id":        os.getenv("TIKTOK_PIXEL_ID", ""),
                        "external_action": "PURCHASE",
                        "operation_status": "ENABLE"
                    }
                )
                if r.status_code != 200 or r.json().get("code") != 0:
                    logger.error(f"TikTok adgroup error: {r.text[:300]}")
                    return {"success": False, "error": f"TikTok adgroup: {r.text[:200]}"}
                adgroup_id = r.json()["data"]["adgroup_id"]

                # Step 3: Ad creative
                ad_text = AD_TEMPLATES.get("es", {}).get("body", "").replace("\n", " ")[:100]
                r = await client.post(
                    f"{self.TIKTOK_BASE}/ad/create/",
                    headers=headers,
                    json={
                        "advertiser_id": TIKTOK_ADVERTISER_ID,
                        "adgroup_id":    adgroup_id,
                        "ad_name":       f"Ad — {product_name}",
                        "ad_format":     "SINGLE_VIDEO",
                        "ad_text":       ad_text,
                        "call_to_action": "SHOP_NOW",
                        "landing_page_url": product_url,
                        "operation_status": "ENABLE"
                    }
                )
                if r.status_code != 200 or r.json().get("code") != 0:
                    logger.error(f"TikTok ad error: {r.text[:300]}")
                    return {"success": False, "error": f"TikTok ad creation: {r.text[:200]}"}

                tiktok_ad_id = r.json()["data"]["ad_id"]
                logger.info(f"✅ TikTok ad launched: campaign={campaign_id} adgroup={adgroup_id} ad={tiktok_ad_id}")

                return {
                    "success":        True,
                    "platform":       "tiktok",
                    "campaign_id":    campaign_id,
                    "adgroup_id":     adgroup_id,
                    "ad_id":          tiktok_ad_id,
                    "daily_budget":   ad.get("daily_budget", 10),
                    "countries":      ["ES", "FR", "DE", "NL", "IT", "BE"]
                }

        except Exception as e:
            logger.error(f"TikTok ads error: {e}")
            return {"success": False, "error": str(e)}

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

    async def update_ad_budget(self, ad_id: str, new_budget: float) -> Dict:
        """رفع أو تغيير ميزانية إعلان نشط على Meta."""
        ad = next((a for a in self.active_ads if a["id"] == ad_id), None)
        if not ad:
            # ابحث في pending أيضاً
            ad = next((a for a in self.pending_ads if a["id"] == ad_id), None)
        if not ad:
            return {"success": False, "error": f"Ad {ad_id} not found"}

        ad["daily_budget"] = new_budget
        meta_adset_id = ad.get("meta_adset_id")

        if meta_adset_id and META_ACCESS_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(
                        f"{META_BASE}/{meta_adset_id}",
                        params={"access_token": META_ACCESS_TOKEN},
                        json={"daily_budget": int(new_budget * 100)}
                    )
                if r.status_code == 200:
                    self._save_ads()
                    logger.info(f"Budget updated: {ad_id} → €{new_budget}/day")
                    return {"success": True, "ad_id": ad_id, "new_budget": new_budget,
                            "message": f"Presupuesto actualizado a €{new_budget}/día en Meta"}
                else:
                    return {"success": False, "meta_error": r.text[:300]}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            # Ad not on Meta yet — just update locally
            self._save_ads()
            return {"success": True, "ad_id": ad_id, "new_budget": new_budget,
                    "message": f"Presupuesto actualizado localmente a €{new_budget}/día (no hay adset Meta activo)"}

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
