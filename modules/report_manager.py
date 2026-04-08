"""
Report Manager v2.0 — تقارير يومية قابلة للتنفيذ
==================================================
- أفضل 5 منتجات مع هامش الربح
- أداء الإعلانات بالتفصيل
- توصيات واضحة: ماذا تفعل اليوم؟
- إرسال تقرير HTML جميل عبر Resend
"""

import os
import httpx
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger('PataBot.Reports')

OWNER_EMAIL    = os.environ.get("OWNER_EMAIL", "mohaelmansouri.1994@gmail.com")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
PATABOT_URL    = "https://patabot-production.up.railway.app"


class ReportManager:
    def __init__(self):
        self.reports = []

    async def generate_daily_report(
        self,
        products: Optional[List[Dict]] = None,
        order_stats: Optional[Dict] = None,
        marketing_status: Optional[Dict] = None,
    ) -> Dict:
        """إنشاء تقرير يومي شامل مع توصيات قابلة للتنفيذ"""
        logger.info("📊 Generating daily report v2.0...")

        # ── Products ──
        prods = products or []
        total_products = len(prods)
        with_images    = sum(1 for p in prods if p.get("image_url"))
        enrichment_pct = round(with_images / total_products * 100) if total_products else 0

        top_by_profit = sorted(
            [p for p in prods if p.get("profit", 0) > 0],
            key=lambda p: p.get("profit", 0), reverse=True
        )[:5]

        top_by_price = sorted(
            [p for p in prods if p.get("selling_price", 0) > 0],
            key=lambda p: p.get("selling_price", 0), reverse=True
        )[:5]

        # ── Orders ──
        os_ = order_stats or {}
        total_orders   = os_.get("total_orders", 0)
        revenue        = round(os_.get("total_revenue", 0), 2)
        profit         = round(os_.get("total_profit", 0), 2)
        avg_order      = round(revenue / total_orders, 2) if total_orders else 0
        confirmed      = os_.get("confirmed", 0)
        shipped        = os_.get("shipped", 0)
        failed         = os_.get("failed", 0)

        # ── Marketing ──
        ms = marketing_status or {}
        active_ads     = ms.get("active_ads", 0)
        pending_ads    = ms.get("pending_approval", 0)
        active_list    = ms.get("active_ads_list", [])
        total_ad_spend = sum(float(a.get("daily_budget", 0)) for a in active_list)

        # ── ROI Calculation ──
        roi = round((profit / total_ad_spend * 100), 1) if total_ad_spend > 0 and profit > 0 else 0
        roas = round(revenue / total_ad_spend, 2) if total_ad_spend > 0 and revenue > 0 else 0

        # ── Actionable Recommendations ──
        recommendations = self._build_recommendations(
            total_orders, profit, active_ads, pending_ads,
            with_images, total_products, failed, total_ad_spend, roas
        )

        # ── Summary Line ──
        if profit > 50:
            summary = f"🚀 يوم ممتاز! ربح €{profit} من {total_orders} طلب — واصل!"
        elif profit > 0:
            summary = f"✅ ربح €{profit} من {total_orders} طلب — ارفع الميزانية للإعلانات الجيدة."
        elif total_orders > 0:
            summary = f"📦 {total_orders} طلب بدون ربح — راجع هوامش الأسعار فوراً."
        elif active_ads > 0:
            summary = f"📣 {active_ads} إعلان نشط، ميزانية €{total_ad_spend:.0f}/يوم — لا مبيعات بعد، صبر."
        elif pending_ads > 0:
            summary = f"⏳ {pending_ads} إعلان ينتظر موافقتك — وافق الآن لتبدأ المبيعات!"
        else:
            summary = "⚠️ لا إعلانات ولا مبيعات — اضغط على رابط 'إطلاق التسويق' أدناه."

        report = {
            "id":           f"RPT-{datetime.now().strftime('%Y%m%d')}",
            "date":         datetime.now().strftime('%Y-%m-%d'),
            "generated_at": datetime.now().isoformat(),
            "summary":      summary,
            "sections": {
                "products": {
                    "total": total_products,
                    "with_images": with_images,
                    "enrichment_pct": enrichment_pct,
                    "top_by_profit": [
                        {"name": p.get("name","")[:45], "profit": p.get("profit",0),
                         "price": p.get("selling_price",0), "category": p.get("category","")}
                        for p in top_by_profit
                    ],
                    "top_by_price": [
                        {"name": p.get("name","")[:45], "price": p.get("selling_price",0)}
                        for p in top_by_price
                    ],
                },
                "sales": {
                    "total_orders": total_orders,
                    "confirmed": confirmed,
                    "shipped": shipped,
                    "failed": failed,
                    "revenue": revenue,
                    "profit": profit,
                    "avg_order": avg_order,
                },
                "marketing": {
                    "active_ads": active_ads,
                    "pending_approval": pending_ads,
                    "daily_spend": round(total_ad_spend, 2),
                    "roi_pct": roi,
                    "roas": roas,
                    "active_ads_list": [
                        {"name": a.get("product_name","")[:35],
                         "budget": a.get("daily_budget", 0),
                         "countries": a.get("countries", [])}
                        for a in active_list[:5]
                    ],
                },
                "recommendations": recommendations,
            }
        }

        self.reports.append(report)
        logger.info(f"✅ Daily report v2.0 generated: {report['id']}")
        return report

    def _build_recommendations(
        self, orders, profit, active_ads, pending_ads,
        with_images, total_products, failed, spend, roas
    ) -> List[Dict]:
        """توصيات قابلة للتنفيذ بناءً على البيانات الحقيقية."""
        recs = []

        if pending_ads > 0:
            recs.append({
                "priority": "🔴 عاجل",
                "action": f"وافق على {pending_ads} إعلان ينتظرك",
                "why": "الإعلانات الموقوفة = خسارة مبيعات يومية",
                "link": f"{PATABOT_URL}/api/marketing/status"
            })

        if failed > 0:
            recs.append({
                "priority": "🔴 عاجل",
                "action": f"راجع {failed} طلب فاشل",
                "why": "طلبات مدفوعة لم تُرسل لـ BigBuy — الزبون ينتظر",
                "link": f"{PATABOT_URL}/api/orders"
            })

        enrichment_pct = round(with_images / total_products * 100) if total_products else 0
        if enrichment_pct < 80:
            recs.append({
                "priority": "🟡 مهم",
                "action": f"إثراء المنتجات: {enrichment_pct}% فقط لديها صور",
                "why": "المنتجات بدون صور لا تظهر في الكتالوج",
                "link": f"{PATABOT_URL}/api/products/enrich"
            })

        if active_ads > 0 and orders == 0 and spend > 20:
            recs.append({
                "priority": "🟡 مهم",
                "action": "راجع صفحات المنتجات — الإعلانات تعمل لكن لا مبيعات",
                "why": "قد تكون المشكلة في السعر أو صفحة المنتج",
                "link": f"{PATABOT_URL}/api/marketing/status"
            })

        if roas > 3 and active_ads > 0:
            recs.append({
                "priority": "🟢 فرصة",
                "action": f"ROAS = {roas}x — ارفع ميزانية الإعلانات الجيدة",
                "why": "عندما ROAS > 3 يعني كل €1 تنفق يجلب €3+",
                "link": f"{PATABOT_URL}/api/marketing/update-budget"
            })

        if active_ads == 0 and pending_ads == 0:
            recs.append({
                "priority": "🟡 مهم",
                "action": "أطلق التسويق اليومي لإنشاء مقترحات إعلانات جديدة",
                "why": "لا إعلانات = لا زوار = لا مبيعات",
                "link": f"{PATABOT_URL}/api/marketing/run-daily"
            })

        if profit > 0 and orders > 2:
            recs.append({
                "priority": "🟢 فرصة",
                "action": "أضف منتجات جديدة لتوسيع الكتالوج",
                "why": "المبيعات تسير — كتالوج أكبر = فرص أكثر",
                "link": f"{PATABOT_URL}/api/products/fetch"
            })

        if not recs:
            recs.append({
                "priority": "ℹ️ عادي",
                "action": "كل شيء يسير بشكل طبيعي — تابع غداً",
                "why": "لا إجراءات عاجلة مطلوبة الآن",
                "link": PATABOT_URL
            })

        return recs

    async def send_email_report(self, report: Dict):
        """إرسال التقرير بالبريد لمحمد عبر Resend API"""
        if not RESEND_API_KEY:
            logger.warning("RESEND_API_KEY not set — report not emailed")
            return
        try:
            html = self._build_email_html(report)
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "from":    "PataBot <onboarding@resend.dev>",
                        "to":      [OWNER_EMAIL],
                        "subject": f"📊 PataBot — تقرير {report['date']} | {report['summary'][:60]}",
                        "html":    html
                    }
                )
            if r.status_code in (200, 201):
                logger.info(f"✅ Daily report emailed to {OWNER_EMAIL}")
            else:
                logger.error(f"Resend error {r.status_code}: {r.text[:300]}")
        except Exception as e:
            logger.error(f"❌ Failed to send report: {e}")

    def _build_email_html(self, report: Dict) -> str:
        s  = report.get("sections", {})
        pr = s.get("products", {})
        sa = s.get("sales", {})
        mk = s.get("marketing", {})
        rc = s.get("recommendations", [])

        # Top products table
        top_rows = ""
        for p in pr.get("top_by_profit", []):
            top_rows += f"""<tr>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0">{p['name']}</td>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0;text-align:right">€{p['price']}</td>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0;text-align:right;color:#27ae60;font-weight:bold">€{p['profit']}</td>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0;font-size:0.8rem;color:#888">{p.get('category','')[:20]}</td>
            </tr>"""

        # Active ads table
        ads_rows = ""
        for a in mk.get("active_ads_list", []):
            ads_rows += f"""<tr>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0">{a['name']}</td>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0;text-align:right">€{a['budget']}/día</td>
              <td style="padding:7px;border-bottom:1px solid #f0f0f0;font-size:0.8rem;color:#888">{', '.join(a.get('countries',[]))}</td>
            </tr>"""

        # Recommendations
        recs_html = ""
        for r in rc:
            color = "#e74c3c" if "عاجل" in r["priority"] else "#e67e22" if "مهم" in r["priority"] else "#27ae60"
            recs_html += f"""
            <div style="border-left:4px solid {color};padding:10px 14px;margin:8px 0;background:#fafafa;border-radius:0 8px 8px 0">
              <div style="font-weight:bold;color:{color}">{r['priority']}</div>
              <div style="margin:4px 0;font-size:0.95rem">{r['action']}</div>
              <div style="font-size:0.82rem;color:#888">{r['why']}</div>
              <a href="{r['link']}" style="font-size:0.82rem;color:#3498db">تنفيذ ←</a>
            </div>"""

        roas_color = "#27ae60" if mk.get("roas", 0) >= 2 else "#e67e22" if mk.get("roas", 0) >= 1 else "#e74c3c"

        return f"""
        <html dir="rtl">
        <body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;padding:20px;background:#f5f5f5;color:#333">

          <!-- Header -->
          <div style="background:linear-gradient(135deg,#1a5e35,#27ae60);color:white;padding:24px 28px;border-radius:14px;margin-bottom:16px">
            <h2 style="margin:0 0 6px">🐾 PataBot — تقرير يومي</h2>
            <p style="margin:0;opacity:0.9;font-size:1.05rem">{report['date']}</p>
            <p style="margin:12px 0 0;font-size:1.1rem;font-weight:bold;background:rgba(255,255,255,0.15);padding:10px 14px;border-radius:8px">{report['summary']}</p>
          </div>

          <!-- KPI Cards -->
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px">
            <div style="background:white;padding:16px;border-radius:10px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
              <div style="font-size:1.8rem;font-weight:bold;color:#1a5e35">€{sa.get('revenue',0):.0f}</div>
              <div style="font-size:0.82rem;color:#888">إيرادات</div>
            </div>
            <div style="background:white;padding:16px;border-radius:10px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
              <div style="font-size:1.8rem;font-weight:bold;color:#27ae60">€{sa.get('profit',0):.0f}</div>
              <div style="font-size:0.82rem;color:#888">ربح صافي</div>
            </div>
            <div style="background:white;padding:16px;border-radius:10px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
              <div style="font-size:1.8rem;font-weight:bold;color:#3498db">{sa.get('total_orders',0)}</div>
              <div style="font-size:0.82rem;color:#888">طلبات</div>
            </div>
          </div>

          <!-- Sales Detail -->
          <div style="background:white;padding:18px;border-radius:10px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
            <h3 style="margin:0 0 12px;color:#1a1a1a">💰 المبيعات</h3>
            <table style="width:100%">
              <tr><td style="padding:5px;color:#555">متوسط قيمة الطلب</td><td style="padding:5px;text-align:right;font-weight:bold">€{sa.get('avg_order',0)}</td></tr>
              <tr><td style="padding:5px;color:#555">مؤكدة</td><td style="padding:5px;text-align:right">{sa.get('confirmed',0)}</td></tr>
              <tr><td style="padding:5px;color:#555">مشحونة</td><td style="padding:5px;text-align:right">{sa.get('shipped',0)}</td></tr>
              {'<tr><td style="padding:5px;color:#e74c3c">فاشلة ⚠️</td><td style="padding:5px;text-align:right;color:#e74c3c;font-weight:bold">'+str(sa.get('failed',0))+'</td></tr>' if sa.get('failed',0) > 0 else ''}
            </table>
          </div>

          <!-- Marketing -->
          <div style="background:white;padding:18px;border-radius:10px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
            <h3 style="margin:0 0 12px;color:#1a1a1a">📢 الإعلانات</h3>
            <table style="width:100%;margin-bottom:12px">
              <tr><td style="padding:5px;color:#555">إعلانات نشطة</td><td style="padding:5px;text-align:right;font-weight:bold">{mk.get('active_ads',0)}</td></tr>
              <tr><td style="padding:5px;color:#555">ميزانية يومية</td><td style="padding:5px;text-align:right">€{mk.get('daily_spend',0):.0f}/يوم</td></tr>
              <tr><td style="padding:5px;color:#555">ROAS</td><td style="padding:5px;text-align:right;font-weight:bold;color:{roas_color}">{mk.get('roas',0)}x</td></tr>
              {'<tr><td style="padding:5px;color:#e67e22;font-weight:bold">⏳ تنتظر موافقتك</td><td style="padding:5px;text-align:right;color:#e67e22;font-weight:bold">'+str(mk.get('pending_approval',0))+'</td></tr>' if mk.get('pending_approval',0) > 0 else ''}
            </table>
            {f'<table style="width:100%;border-collapse:collapse;font-size:0.88rem"><tr style="background:#f5f5f5"><th style="padding:6px;text-align:right">الإعلان</th><th style="padding:6px;text-align:right">الميزانية</th><th style="padding:6px;text-align:right">الدول</th></tr>{ads_rows}</table>' if ads_rows else '<p style="color:#aaa;font-size:0.88rem">لا إعلانات نشطة</p>'}
          </div>

          <!-- Top Products -->
          {f'<div style="background:white;padding:18px;border-radius:10px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,0.06)"><h3 style="margin:0 0 12px;color:#1a1a1a">🏆 أفضل المنتجات ربحاً</h3><table style="width:100%;border-collapse:collapse;font-size:0.88rem"><tr style="background:#f5f5f5"><th style="padding:7px;text-align:right">المنتج</th><th style="padding:7px;text-align:right">السعر</th><th style="padding:7px;text-align:right">الربح</th><th style="padding:7px;text-align:right">الفئة</th></tr>{top_rows}</table></div>' if top_rows else ''}

          <!-- Products Status -->
          <div style="background:white;padding:18px;border-radius:10px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
            <h3 style="margin:0 0 12px;color:#1a1a1a">📦 المنتجات</h3>
            <p style="margin:4px 0">إجمالي: <b>{pr.get('total','')}</b> &nbsp;|&nbsp; مع صور: <b>{pr.get('with_images','')}</b> &nbsp;|&nbsp; الإثراء: <b>{pr.get('enrichment_pct',0)}%</b></p>
            <div style="background:#eee;border-radius:4px;height:8px;margin-top:8px"><div style="background:#27ae60;height:8px;border-radius:4px;width:{pr.get('enrichment_pct',0)}%"></div></div>
          </div>

          <!-- Recommendations -->
          <div style="background:white;padding:18px;border-radius:10px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,0.06)">
            <h3 style="margin:0 0 12px;color:#1a1a1a">🎯 ماذا تفعل اليوم؟</h3>
            {recs_html}
          </div>

          <!-- Footer -->
          <div style="background:#1a5e35;color:white;padding:16px 20px;border-radius:10px;text-align:center">
            <p style="margin:0 0 8px;font-size:0.9rem;opacity:0.85">PataBot v1.6.0 — patahogar.com</p>
            <a href="{PATABOT_URL}/api/dashboard" style="color:#fff;font-size:0.85rem;opacity:0.8">عرض لوحة التحكم الكاملة</a>
          </div>

        </body>
        </html>"""
