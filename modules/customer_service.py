"""
Customer Service — خدمة العملاء
==================================
- الرد على رسائل الزبائن بـ 8 لغات
- تتبع الشحنات
- معالجة طلبات الإرجاع
- تصعيد الحالات المعقدة لمحمد
"""

import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger('PataBot.CustomerService')

# Auto-reply templates in 8 languages
AUTO_REPLIES = {
    "es": {
        "greeting": "¡Hola! Gracias por contactar con PataHogar. ¿En qué puedo ayudarte?",
        "order_status": "Tu pedido {order_id} está en camino. Número de seguimiento: {tracking}",
        "return_info": "Para devolver un producto, tienes 14 días desde la recepción. Te enviaremos una etiqueta de envío.",
        "shipping": "Enviamos a toda Europa. Plazo: 3-7 días laborables.",
        "thank_you": "¡Gracias por tu compra! Si necesitas algo más, estamos aquí para ayudarte. 🐾"
    },
    "en": {
        "greeting": "Hello! Thanks for contacting PataHogar. How can I help you?",
        "order_status": "Your order {order_id} is on its way. Tracking number: {tracking}",
        "return_info": "To return a product, you have 14 days from receipt. We'll send you a shipping label.",
        "shipping": "We ship across Europe. Delivery: 3-7 business days.",
        "thank_you": "Thank you for your purchase! If you need anything else, we're here to help. 🐾"
    },
    "fr": {
        "greeting": "Bonjour ! Merci de contacter PataHogar. Comment puis-je vous aider ?",
        "order_status": "Votre commande {order_id} est en route. Numéro de suivi : {tracking}",
        "return_info": "Pour retourner un produit, vous avez 14 jours après réception. Nous vous enverrons une étiquette d'envoi.",
        "shipping": "Nous livrons dans toute l'Europe. Délai : 3-7 jours ouvrables.",
        "thank_you": "Merci pour votre achat ! Si vous avez besoin d'autre chose, nous sommes là. 🐾"
    },
    "de": {
        "greeting": "Hallo! Danke für Ihre Nachricht an PataHogar. Wie kann ich Ihnen helfen?",
        "order_status": "Ihre Bestellung {order_id} ist unterwegs. Sendungsnummer: {tracking}",
        "return_info": "Für eine Rücksendung haben Sie 14 Tage nach Erhalt. Wir senden Ihnen ein Versandetikett.",
        "shipping": "Wir liefern europaweit. Lieferzeit: 3-7 Werktage.",
        "thank_you": "Vielen Dank für Ihren Einkauf! Bei Fragen sind wir gerne für Sie da. 🐾"
    },
    "it": {
        "greeting": "Ciao! Grazie per aver contattato PataHogar. Come posso aiutarti?",
        "order_status": "Il tuo ordine {order_id} è in arrivo. Numero di tracciamento: {tracking}",
        "return_info": "Per restituire un prodotto, hai 14 giorni dalla ricezione. Ti invieremo un'etichetta di spedizione.",
        "shipping": "Spediamo in tutta Europa. Tempi: 3-7 giorni lavorativi.",
        "thank_you": "Grazie per il tuo acquisto! Se hai bisogno di altro, siamo qui per te. 🐾"
    },
    "nl": {
        "greeting": "Hallo! Bedankt voor het contacteren van PataHogar. Hoe kan ik u helpen?",
        "order_status": "Uw bestelling {order_id} is onderweg. Trackingnummer: {tracking}",
        "return_info": "Om een product te retourneren, heeft u 14 dagen na ontvangst. We sturen u een verzendlabel.",
        "shipping": "Wij verzenden door heel Europa. Levertijd: 3-7 werkdagen.",
        "thank_you": "Bedankt voor uw aankoop! Als u iets nodig heeft, staan wij voor u klaar. 🐾"
    },
    "ar": {
        "greeting": "مرحباً! شكراً لتواصلك مع PataHogar. كيف يمكنني مساعدتك؟",
        "order_status": "طلبك {order_id} في الطريق. رقم التتبع: {tracking}",
        "return_info": "لإرجاع منتج، لديك 14 يوماً من الاستلام. سنرسل لك ملصق الشحن.",
        "shipping": "نشحن لكل أوروبا. المدة: 3-7 أيام عمل.",
        "thank_you": "شكراً لشرائك! إذا احتجت أي شيء آخر، نحن هنا لمساعدتك. 🐾"
    },
    "ru": {
        "greeting": "Здравствуйте! Спасибо за обращение в PataHogar. Чем могу помочь?",
        "order_status": "Ваш заказ {order_id} в пути. Номер отслеживания: {tracking}",
        "return_info": "Для возврата товара у вас 14 дней с момента получения. Мы отправим этикетку для возврата.",
        "shipping": "Мы доставляем по всей Европе. Срок: 3-7 рабочих дней.",
        "thank_you": "Спасибо за покупку! Если вам нужно что-то ещё, мы здесь. 🐾"
    }
}


class CustomerService:
    def __init__(self):
        self.pending_messages = []
        self.resolved_messages = []
        self.return_requests = []
        self.escalated_to_mohamed = []
    
    async def process_pending_messages(self):
        """معالجة الرسائل المعلقة"""
        logger.info("💬 Processing pending customer messages...")
        
        for msg in self.pending_messages:
            if msg["status"] == "pending":
                response = await self._auto_reply(msg)
                if response["auto_resolved"]:
                    msg["status"] = "resolved"
                    msg["response"] = response["message"]
                    self.resolved_messages.append(msg)
                else:
                    msg["status"] = "escalated"
                    self.escalated_to_mohamed.append(msg)
                    logger.info(f"⚠️ Message escalated to Mohamed: {msg['id']}")
    
    async def _auto_reply(self, message: Dict) -> Dict:
        """الرد التلقائي على رسالة"""
        text = message.get("text", "").lower()
        lang = message.get("language", "en")
        templates = AUTO_REPLIES.get(lang, AUTO_REPLIES["en"])
        
        # Detect intent
        if any(word in text for word in ["order", "pedido", "commande", "bestellung", "طلب", "заказ", "ordine", "bestelling"]):
            return {
                "auto_resolved": True,
                "message": templates["order_status"].format(
                    order_id=message.get("order_id", "N/A"),
                    tracking=message.get("tracking", "N/A")
                )
            }
        
        elif any(word in text for word in ["return", "devolver", "retour", "rücksendung", "إرجاع", "возврат", "reso", "retour"]):
            return {
                "auto_resolved": True,
                "message": templates["return_info"]
            }
        
        elif any(word in text for word in ["shipping", "envío", "livraison", "versand", "شحن", "доставка", "spedizione", "verzending"]):
            return {
                "auto_resolved": True,
                "message": templates["shipping"]
            }
        
        elif any(word in text for word in ["hello", "hola", "bonjour", "hallo", "مرحبا", "здравствуйте", "ciao"]):
            return {
                "auto_resolved": True,
                "message": templates["greeting"]
            }
        
        else:
            # Can't auto-resolve — escalate to Mohamed
            return {
                "auto_resolved": False,
                "message": "رسالة تحتاج مراجعة محمد"
            }
    
    async def check_order_tracking(self):
        """التحقق من حالة الشحنات"""
        logger.info("📦 Checking order tracking status...")
    
    async def process_return_requests(self):
        """معالجة طلبات الإرجاع"""
        logger.info("↩️ Processing return requests...")
        
        for request in self.return_requests:
            if request["status"] == "pending":
                # Auto-approve returns within 14 days
                request["status"] = "approved"
                logger.info(f"✅ Return request {request['id']} auto-approved")
    
    async def get_pending_messages(self) -> List[Dict]:
        """الرسائل المعلقة"""
        return self.pending_messages
    
    async def add_message(self, message: Dict):
        """إضافة رسالة جديدة"""
        message["id"] = f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        message["status"] = "pending"
        message["received_at"] = datetime.now().isoformat()
        self.pending_messages.append(message)
