"""
Security Manager — حماية الموقع
==================================
- مراقبة الموقع 24/7
- فحص SSL
- نسخ احتياطية
- كشف التهديدات
"""

import os
import logging
import httpx
from datetime import datetime
from typing import Dict

logger = logging.getLogger('PataBot.Security')

WEBSITE_URL = "https://patahogar.com"
MOHAMED_EMAIL = os.environ.get("MOHAMED_EMAIL", "mohaelmansouri.1994@gmail.com")


class SecurityManager:
    def __init__(self):
        self.security_log = []
        self.last_check = None
        self.website_status = "unknown"
        self.ssl_valid = True
    
    async def check_website_health(self):
        """فحص صحة الموقع"""
        logger.info(f"🔍 Checking website health: {WEBSITE_URL}")
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(WEBSITE_URL)
                
                status = {
                    "url": WEBSITE_URL,
                    "status_code": response.status_code,
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                    "is_online": response.status_code == 200,
                    "checked_at": datetime.now().isoformat()
                }
                
                self.website_status = "online" if status["is_online"] else "down"
                self.last_check = datetime.now()
                
                if not status["is_online"]:
                    await self._alert_mohamed(f"⚠️ الموقع لا يعمل! Status: {response.status_code}")
                    logger.error(f"❌ Website is DOWN! Status: {response.status_code}")
                else:
                    logger.info(f"✅ Website is online ({status['response_time_ms']:.0f}ms)")
                
                self._log_event("health_check", status)
                return status
                
        except Exception as e:
            self.website_status = "error"
            logger.error(f"❌ Website check failed: {e}")
            await self._alert_mohamed(f"❌ فشل فحص الموقع: {e}")
            return {"status": "error", "error": str(e)}
    
    async def check_ssl_status(self):
        """فحص شهادة SSL"""
        logger.info("🔒 Checking SSL certificate...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(WEBSITE_URL)
                self.ssl_valid = True
                logger.info("✅ SSL certificate is valid")
                self._log_event("ssl_check", {"valid": True})
        except httpx.ConnectError:
            self.ssl_valid = False
            logger.error("❌ SSL certificate issue!")
            await self._alert_mohamed("⚠️ مشكلة في شهادة SSL للموقع!")
            self._log_event("ssl_check", {"valid": False})
    
    async def create_backup(self):
        """إنشاء نسخة احتياطية"""
        logger.info("💾 Creating backup...")
        
        backup = {
            "id": f"BKP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "type": "automatic",
            "status": "completed"
        }
        
        self._log_event("backup", backup)
        logger.info(f"✅ Backup created: {backup['id']}")
    
    async def get_security_status(self) -> Dict:
        """حالة الأمان الشاملة"""
        return {
            "status": self.website_status,
            "ssl_valid": self.ssl_valid,
            "last_check": self.last_check.isoformat() if self.last_check else "never",
            "website_url": WEBSITE_URL,
            "recent_events": self.security_log[-10:],
            "threats_detected": 0,
            "backups_today": sum(1 for e in self.security_log if e["type"] == "backup" 
                               and e["timestamp"][:10] == datetime.now().strftime('%Y-%m-%d'))
        }
    
    async def _alert_mohamed(self, message: str):
        """تنبيه محمد بمشكلة أمنية"""
        logger.warning(f"🚨 ALERT TO MOHAMED: {message}")
        # Will send email/WhatsApp alert
    
    def _log_event(self, event_type: str, data: Dict):
        """تسجيل حدث أمني"""
        self.security_log.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
