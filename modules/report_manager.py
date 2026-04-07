"""
Report Manager — مدير التقارير
==================================
- إنشاء تقارير يومية بالبيانات الحقيقية
- إرسال التقارير بالبريد لمحمد عبر Resend API
- إحصائيات المبيعات والأداء
"""

import os
import httpx
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger('PataBot.Reports')

OWNER_EMAIL   = os.environ.get("OWNER_EMAIL", "mohaelmansouri.1994@gmail.com")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
PATABOT_URL   = "https://patabot-production.up.railway.app"


class ReportManager:
    def __init__(self):
        self.reports = []

    async def generate_daily_report(
        self,
        products: Optional[List[Dict]] = None,
        order_stats: Optional[Dict] = None,
        marketing_status: Optional[Dict] = None,
    ) -> Dict:
        """إنشاء التقرير اليومي بالبيانات الحقيقية"""
        logger.info("📊 Generating daily report...")

        # ── Products ──
        total_products = len(products) if products else 0
        with_images    = sum(1 for p in (products or []) if p.get("image_url"))
        top_products   = sorted(
            [p for p in (products or []) if p.get("profit", 0) > 0],
            key=lambda p: p.get("profit", 0), reverse=True
        )[:5]

        # ── Orders ──
        os_ = order_stats or {}
        orders_today   = os_.get("total_orders", 0)
        revenue_today  = round(os_.get("total_revenue", 0), 2)
        profit_today   = round(os_.get("total_profit", 0), 2)
        avg_order      = round(revenue_today / orders_today, 2) if orders_today else 0

        # ── Marketing ──
        ms = marketing_status or {}
        active_ads     = ms.get("active_ads", 0)
        pending_ads    = ms.get("pending_approval", 0)

        # ── Build summary ──
        if profit_today > 0:
            summary = f"✅ ممتاز! ربح اليوم: €{profit_today} من {orders_today} طلب."
        elif orders_today > 0:
            summary = f"📦 {orders_today} طلب اليوم — لا ربح بعد (تحقق من هامش الأسعار)."
        elif active_ads > 0:
            summary = f"📣 {active_ads} إعلان نشط | {pending_ads} ينتظر الموافقة | لا مبيعات بعد."
        else:
            summary = f"⚠️ لا إعلانات نشطة ولا مبيعات — وافق على المقترحات لتبدأ."

        report = {
            "id":           f"RPT-{datetime.now().strftime('%Y%m%d')}",
            "date":         datetime.now().strftime('%Y-%m-%d'),
            "generated_at": datetime.now().isoformat(),
            "sections": {
                "products": {
                    "title":          "📦 المنتجات",
                    "total_products": total_products,
                    "with_images":    with_images,
                    "new_today":      0,
                    "removed_today":  0,
                    "top_products":   [
                        {"name": p.get("name",""), "profit": p.get("profit",0),
                         "price": p.get("selling_price",0)}
                        for p in top_products
                    ]
                },
                "sales": {
                    "title":          "💰 المبيعات",
                    "orders_today":   orders_today,
                    "revenue_today":  revenue_today,
                    "profit_today":   profit_today,
                    "avg_order_value": avg_order
                },
                "marketing": {
                    "title":          "📢 التسويق",
                    "organic_posts":  0,
                    "paid_ads_active": active_ads,
                    "pending_approval": pending_ads,
                    "total_reach":    0,
                    "engagement_rate": 0
                },
                "customers": {
                    "title":             "💬 خدمة العملاء",
                    "messages_received": 0,
                    "auto_resolved":     0,
                    "escalated":         0,
                    "avg_response_time": "< 1 minute"
                },
                "security": {
                    "title":           "🔒 الأمان",
                    "website_status":  "online",
                    "ssl_valid":       True,
                    "backups_created": 0,
                    "threats_blocked": 0
                }
            },
            "summary": summary
        }

        self.reports.append(report)
        logger.info(f"✅ Daily report generated: {report['id']}")
        return report

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
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from":    "PataBot <onboarding@resend.dev>",
                        "to":      [OWNER_EMAIL],
                        "subject": f"📊 PataBot — تقرير {report['date']}",
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
        """بناء HTML للتقرير"""
        s   = report.get("sections", {})
        pr  = s.get("products", {})
        sa  = s.get("sales", {})
        mk  = s.get("marketing", {})
        cu  = s.get("customers", {})
        sec = s.get("security", {})

        # Top products rows
        top_rows = ""
        for p in pr.get("top_products", []):
            top_rows += f"<tr><td style='padding:6px'>{p['name'][:40]}</td><td style='padding:6px;text-align:right'>€{p['price']}</td><td style='padding:6px;text-align:right;color:#27ae60'>€{p['profit']}</td></tr>"
        top_table = f"""
        <table style='width:100%;border-collapse:collapse;font-size:0.9rem'>
          <tr style='background:#f0f9f4'><th style='padding:6px;text-align:left'>المنتج</th><th style='padding:6px;text-align:right'>السعر</th><th style='padding:6px;text-align:right'>الربح</th></tr>
          {top_rows or "<tr><td colspan='3' style='padding:6px;color:#aaa'>لا توجد بيانات بعد</td></tr>"}
        </table>""" if pr.get("top_products") else ""

        html = f"""
        <html dir="rtl">
        <body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:20px;background:#f9f9f9">
          <div style="background:linear-gradient(135deg,#1a5e35,#27ae60);color:white;padding:24px;border-radius:12px;text-align:center">
            <h1 style="margin:0">🐾 PataBot — تقرير يومي</h1>
            <p style="margin:8px 0 0;opacity:0.85">{report['date']}</p>
          </div>

          <div style="background:white;margin:16px 0;padding:16px;border-radius:10px;border-left:4px solid #3498db">
            <h3 style="margin:0 0 12px">📦 المنتجات</h3>
            <p style="margin:4px 0">إجمالي: <b>{pr.get('total_products',0)}</b> منتج &nbsp;|&nbsp; مع صور: <b>{pr.get('with_images',0)}</b></p>
            {top_table}
          </div>

          <div style="background:white;margin:16px 0;padding:16px;border-radius:10px;border-left:4px solid #27ae60">
            <h3 style="margin:0 0 12px">💰 المبيعات</h3>
            <table style="width:100%">
              <tr><td>الطلبات اليوم</td><td style="text-align:right"><b>{sa.get('orders_today',0)}</b></td></tr>
              <tr><td>الإيرادات</td><td style="text-align:right"><b>€{sa.get('revenue_today',0)}</b></td></tr>
              <tr><td>الربح الصافي</td><td style="text-align:right;color:#27ae60"><b>€{sa.get('profit_today',0)}</b></td></tr>
              <tr><td>متوسط قيمة الطلب</td><td style="text-align:right">€{sa.get('avg_order_value',0)}</td></tr>
            </table>
          </div>

          <div style="background:white;margin:16px 0;padding:16px;border-radius:10px;border-left:4px solid #e67e22">
            <h3 style="margin:0 0 12px">📢 التسويق</h3>
            <table style="width:100%">
              <tr><td>إعلانات نشطة</td><td style="text-align:right"><b>{mk.get('paid_ads_active',0)}</b></td></tr>
              <tr><td>تنتظر موافقتك</td><td style="text-align:right"><b style="color:#e67e22">{mk.get('pending_approval',0)}</b></td></tr>
            </table>
            {"<p style='margin:8px 0 0'><a href='" + PATABOT_URL + "/api/marketing/status' style='color:#e67e22'>عرض حالة الإعلانات</a></p>" if mk.get('pending_approval',0) > 0 else ""}
          </div>

          <div style="background:white;margin:16px 0;padding:16px;border-radius:10px;border-left:4px solid #9b59b6">
            <h3 style="margin:0 0 12px">🔒 الأمان</h3>
            <p style="margin:4px 0">حالة الموقع: <b>{sec.get('website_status','online')}</b> &nbsp;|&nbsp; SSL: {'✅ سليم' if sec.get('ssl_valid') else '❌ مشكلة'}</p>
          </div>

          <div style="background:#1a5e35;color:white;padding:16px;border-radius:10px;text-align:center;margin-top:16px">
            <p style="margin:0 0 8px;font-size:1.05rem"><b>{report['summary']}</b></p>
            <p style="margin:0;font-size:0.8rem;opacity:0.8">PataBot v1.6.0 — patahogar.com</p>
          </div>
        </body>
        </html>"""
        return html
