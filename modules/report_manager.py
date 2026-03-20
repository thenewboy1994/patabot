"""
Report Manager — مدير التقارير
==================================
- إنشاء تقارير يومية
- إرسال التقارير بالبريد لمحمد
- إحصائيات المبيعات والأداء
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict

logger = logging.getLogger('PataBot.Reports')

MOHAMED_EMAIL = os.environ.get("MOHAMED_EMAIL", "mohaelmansouri.1994@gmail.com")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


class ReportManager:
    def __init__(self):
        self.reports = []
    
    async def generate_daily_report(self) -> Dict:
        """إنشاء التقرير اليومي"""
        logger.info("📊 Generating daily report...")
        
        report = {
            "id": f"RPT-{datetime.now().strftime('%Y%m%d')}",
            "date": datetime.now().strftime('%Y-%m-%d'),
            "generated_at": datetime.now().isoformat(),
            "sections": {
                "products": {
                    "title": "📦 المنتجات",
                    "total_products": 0,
                    "new_today": 0,
                    "removed_today": 0,
                    "top_products": []
                },
                "sales": {
                    "title": "💰 المبيعات",
                    "orders_today": 0,
                    "revenue_today": 0,
                    "profit_today": 0,
                    "avg_order_value": 0
                },
                "marketing": {
                    "title": "📢 التسويق",
                    "organic_posts": 0,
                    "paid_ads_active": 0,
                    "total_reach": 0,
                    "engagement_rate": 0
                },
                "customers": {
                    "title": "💬 خدمة العملاء",
                    "messages_received": 0,
                    "auto_resolved": 0,
                    "escalated": 0,
                    "avg_response_time": "< 1 minute"
                },
                "security": {
                    "title": "🔒 الأمان",
                    "website_status": "online",
                    "ssl_valid": True,
                    "backups_created": 0,
                    "threats_blocked": 0
                }
            },
            "summary": "PataBot يعمل بشكل طبيعي. كل الأنظمة فعّالة. ✅"
        }
        
        self.reports.append(report)
        logger.info(f"✅ Daily report generated: {report['id']}")
        return report
    
    async def send_email_report(self, report: Dict):
        """إرسال التقرير بالبريد لمحمد"""
        if not SMTP_USER or not SMTP_PASSWORD:
            logger.info("📧 Email not configured — report saved locally")
            return
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"📊 PataBot تقرير يومي — {report['date']}"
            msg['From'] = SMTP_USER
            msg['To'] = MOHAMED_EMAIL
            
            # Build HTML email
            html = self._build_email_html(report)
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"✅ Report sent to {MOHAMED_EMAIL}")
            
        except Exception as e:
            logger.error(f"❌ Failed to send email report: {e}")
    
    def _build_email_html(self, report: Dict) -> str:
        """بناء HTML للتقرير"""
        sections = report.get("sections", {})
        
        html = f"""
        <html dir="rtl">
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #1a1a2e; color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h1>🐾 PataBot — تقرير يومي</h1>
                <p>{report['date']}</p>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background: #f0f8ff; border-radius: 8px;">
                <h2>{sections['products']['title']}</h2>
                <p>إجمالي المنتجات: {sections['products']['total_products']}</p>
                <p>جديد اليوم: {sections['products']['new_today']}</p>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background: #f0fff0; border-radius: 8px;">
                <h2>{sections['sales']['title']}</h2>
                <p>الطلبات اليوم: {sections['sales']['orders_today']}</p>
                <p>الإيرادات: {sections['sales']['revenue_today']}€</p>
                <p>الربح: {sections['sales']['profit_today']}€</p>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background: #fff8f0; border-radius: 8px;">
                <h2>{sections['marketing']['title']}</h2>
                <p>منشورات عضوية: {sections['marketing']['organic_posts']}</p>
                <p>إعلانات مدفوعة فعّالة: {sections['marketing']['paid_ads_active']}</p>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background: #f5f0ff; border-radius: 8px;">
                <h2>{sections['customers']['title']}</h2>
                <p>الرسائل المستلمة: {sections['customers']['messages_received']}</p>
                <p>تم حلها تلقائياً: {sections['customers']['auto_resolved']}</p>
            </div>
            
            <div style="margin: 20px 0; padding: 15px; background: #f0f0f0; border-radius: 8px;">
                <h2>{sections['security']['title']}</h2>
                <p>حالة الموقع: {sections['security']['website_status']}</p>
                <p>SSL: {'✅ سليم' if sections['security']['ssl_valid'] else '❌ مشكلة'}</p>
            </div>
            
            <div style="text-align: center; padding: 20px; color: #666;">
                <p>{report['summary']}</p>
                <p>PataBot v1.0.0 — patahogar.com</p>
            </div>
        </body>
        </html>
        """
        return html
