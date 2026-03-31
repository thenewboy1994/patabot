"""
PataBot — Order Manager v1.0
Full order processing pipeline:
  1. Customer places order → Stripe charges card
  2. PataBot submits order to BigBuy API
  3. BigBuy ships to customer (dropshipping)
  4. PataBot fetches tracking → emails customer
"""

import httpx
import asyncio
import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("patabot.orders")

BIGBUY_API_KEY = os.getenv("BIGBUY_API_KEY", "")
BIGBUY_BASE = "https://api.bigbuy.eu"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "mohaelmansouri.1994@gmail.com")
SUCCESS_URL = os.getenv("SUCCESS_URL", "https://patahogar.com/success.html")
CANCEL_URL = os.getenv("CANCEL_URL", "https://patahogar.com/catalog.html")
ORDERS_FILE = Path("orders.json")

# BigBuy carrier codes by country
COUNTRY_CARRIERS = {
    "ES": "CORREOS",
    "DE": "DHL",
    "FR": "CHRONOPOST",
    "NL": "DPD",
    "BE": "DPD",
    "IT": "BRT",
    "CH": "DHL",
    "LU": "DPD",
    "AT": "DHL",
    "PT": "CTT",
}
DEFAULT_CARRIER = "DHL"

BIGBUY_HEADERS = {
    "Authorization": f"Bearer {BIGBUY_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}


class OrderManager:

    def __init__(self):
        self.orders = []
        self._load_orders()

    # ─── Persistence ───

    def _load_orders(self):
        try:
            if ORDERS_FILE.exists():
                data = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
                self.orders = data.get("orders", [])
                logger.info(f"Loaded {len(self.orders)} orders from file")
        except Exception as e:
            logger.error(f"Order load error: {e}")

    def _save_orders(self):
        try:
            ORDERS_FILE.write_text(
                json.dumps({"orders": self.orders, "saved_at": datetime.now().isoformat()},
                           ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Order save error: {e}")

    # ─── Stripe Checkout Session ───

    async def create_checkout_session(self, cart_items: list) -> dict:
        """
        Create a Stripe Checkout Session for one or more products.
        Stripe collects card + shipping address on their secure page.
        cart_items = [{id, sku, name, selling_price, wholesale_price, image_url, qty}, ...]
        """
        if not STRIPE_SECRET_KEY:
            return {"success": False, "error": "Stripe not configured — add STRIPE_SECRET_KEY to Railway env vars"}
        if not cart_items:
            return {"success": False, "error": "Cart is empty"}

        try:
            params = {
                "mode": "payment",
                "success_url": SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
                "cancel_url": CANCEL_URL,
                "payment_method_types[0]": "card",
                "phone_number_collection[enabled]": "true",
                "shipping_address_collection[allowed_countries][0]": "ES",
                "shipping_address_collection[allowed_countries][1]": "FR",
                "shipping_address_collection[allowed_countries][2]": "DE",
                "shipping_address_collection[allowed_countries][3]": "NL",
                "shipping_address_collection[allowed_countries][4]": "IT",
                "shipping_address_collection[allowed_countries][5]": "BE",
                "shipping_address_collection[allowed_countries][6]": "AT",
                "shipping_address_collection[allowed_countries][7]": "PT",
            }

            # Build line items + collect metadata
            skus = []
            wholesale_prices = []
            for i, item in enumerate(cart_items):
                qty = max(1, int(item.get("qty", 1)))
                amount_cents = int(round(float(item["selling_price"]) * 100))
                name = str(item.get("name", "Producto PataHogar"))[:127]
                params[f"line_items[{i}][price_data][currency]"] = "eur"
                params[f"line_items[{i}][price_data][unit_amount]"] = str(amount_cents)
                params[f"line_items[{i}][price_data][product_data][name]"] = name
                params[f"line_items[{i}][quantity]"] = str(qty)
                if item.get("image_url"):
                    params[f"line_items[{i}][price_data][product_data][images][0]"] = item["image_url"]
                skus.append(str(item.get("sku", "")))
                wholesale_prices.append(str(item.get("wholesale_price", 0)))

            # Store cart in metadata for webhook processing
            params["metadata[cart_skus]"] = ",".join(skus)
            params["metadata[cart_wholesale]"] = ",".join(wholesale_prices)
            params["metadata[cart_json]"] = json.dumps([
                {"sku": item.get("sku",""), "name": str(item.get("name",""))[:100],
                 "qty": int(item.get("qty",1)), "wholesale_price": float(item.get("wholesale_price",0))}
                for item in cart_items
            ])[:500]

            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "https://api.stripe.com/v1/checkout/sessions",
                    auth=(STRIPE_SECRET_KEY, ""),
                    data=params
                )
                result = r.json()
                if r.status_code == 200 and result.get("url"):
                    logger.info(f"Stripe session created: {result['id']} — {len(cart_items)} items")
                    return {"success": True, "checkout_url": result["url"], "session_id": result["id"]}
                else:
                    err = result.get("error", {}).get("message", "Stripe error")
                    logger.error(f"Stripe session error: {err}")
                    return {"success": False, "error": err}

        except Exception as e:
            logger.error(f"create_checkout_session error: {e}")
            return {"success": False, "error": str(e)}

    async def handle_webhook_event(self, payload: bytes, stripe_signature: str) -> dict:
        """
        Process Stripe webhook — called when Stripe confirms payment.
        Triggers BigBuy order submission automatically.
        """
        # Verify webhook signature
        if STRIPE_WEBHOOK_SECRET:
            try:
                import hmac
                import hashlib
                parts = {}
                for item in stripe_signature.split(","):
                    k, v = item.split("=", 1)
                    parts[k] = v
                timestamp = parts.get("t", "")
                sig = parts.get("v1", "")
                signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
                expected = hmac.new(
                    STRIPE_WEBHOOK_SECRET.encode(),
                    signed_payload.encode(),
                    hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(expected, sig):
                    return {"error": "Invalid webhook signature"}
            except Exception as e:
                logger.warning(f"Webhook signature check failed: {e}")

        try:
            event = json.loads(payload)
            event_type = event.get("type", "")
            logger.info(f"Stripe webhook: {event_type}")

            if event_type == "checkout.session.completed":
                session = event["data"]["object"]
                await self._process_completed_checkout(session)
                return {"status": "processed"}

            return {"status": "ignored", "type": event_type}

        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            return {"error": str(e)}

    async def _process_completed_checkout(self, session: dict):
        """Build order(s) from Stripe session and submit to BigBuy."""
        meta = session.get("metadata", {})
        shipping = session.get("shipping_details") or session.get("shipping", {})
        address = shipping.get("address", {}) if shipping else {}
        customer_name = shipping.get("name", "") if shipping else ""
        name_parts = customer_name.split(" ", 1)

        customer = {
            "first_name": name_parts[0] if name_parts else "",
            "last_name": name_parts[1] if len(name_parts) > 1 else "",
            "email": session.get("customer_details", {}).get("email", ""),
            "phone": session.get("customer_details", {}).get("phone", ""),
            "address": address.get("line1", "") + (" " + address.get("line2", "") if address.get("line2") else ""),
            "city": address.get("city", ""),
            "postcode": address.get("postal_code", ""),
            "country": address.get("country", "ES"),
        }

        # Parse cart items from metadata
        cart_items = []
        try:
            if meta.get("cart_json"):
                cart_items = json.loads(meta["cart_json"])
        except Exception:
            pass

        if not cart_items:
            # Fallback: single product from metadata
            cart_items = [{
                "sku": meta.get("product_sku", ""),
                "name": meta.get("product_name", "Producto PataHogar"),
                "qty": 1,
                "wholesale_price": float(meta.get("wholesale_price", 0))
            }]

        total_selling = session.get("amount_total", 0) / 100
        total_wholesale = sum(float(i.get("wholesale_price", 0)) * int(i.get("qty", 1)) for i in cart_items)

        order_id = f"PH{len(self.orders) + 1:04d}"
        order = {
            "id": order_id,
            "cart_items": cart_items,
            "product_sku": cart_items[0].get("sku", "") if cart_items else "",
            "product_name": ", ".join(i.get("name","")[:40] for i in cart_items),
            "wholesale_price": total_wholesale,
            "selling_price": total_selling,
            "quantity": sum(int(i.get("qty",1)) for i in cart_items),
            "customer": customer,
            "status": "confirmed",
            "payment_status": "paid",
            "stripe_session_id": session.get("id"),
            "bigbuy_order_id": None,
            "tracking_number": None,
            "carrier": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "notes": [f"Payment confirmed via Stripe Checkout — {len(cart_items)} items"]
        }
        self.orders.append(order)
        self._save_orders()

        # Submit each cart item to BigBuy
        for item in cart_items:
            item_order = dict(order)
            item_order["product_sku"] = item.get("sku", "")
            item_order["quantity"] = int(item.get("qty", 1))
            bigbuy_result = await self._submit_to_bigbuy(item_order)
            if bigbuy_result["success"]:
                order["notes"].append(f"BigBuy {item.get('sku','?')}: {bigbuy_result['bigbuy_order_id']}")
                if not order["bigbuy_order_id"]:
                    order["bigbuy_order_id"] = bigbuy_result["bigbuy_order_id"]
            else:
                order["notes"].append(f"BigBuy ERROR {item.get('sku','?')}: {bigbuy_result['error']}")
                order["status"] = "bigbuy_error"
                await self._notify_owner_error(order, bigbuy_result["error"])
            await asyncio.sleep(2)

        self._save_orders()
        await self._send_customer_confirmation(order)
        await self._notify_owner_new_order(order)

        if order["bigbuy_order_id"]:
            asyncio.create_task(self._check_tracking_later(order_id, delay=1800))

        logger.info(f"Checkout processed: {order_id} | {len(cart_items)} items | BigBuy: {order.get('bigbuy_order_id', 'ERROR')}")

    # ─── Main Entry Point ───

    async def create_order(self, order_data: dict) -> dict:
        """
        Full order flow:
        order_data = {
          "product_sku": "BB123",
          "product_name": "...",
          "wholesale_price": 15.0,
          "selling_price": 22.5,
          "quantity": 1,
          "customer": {
            "first_name": "...", "last_name": "...",
            "email": "...", "phone": "...",
            "address": "...", "city": "...",
            "postcode": "...", "country": "ES"
          },
          "payment_method_id": "pm_xxx"   # Stripe PaymentMethod ID (from frontend)
        }
        """
        order_id = f"PH{len(self.orders) + 1:04d}"
        order = {
            "id": order_id,
            "product_sku": order_data.get("product_sku"),
            "product_name": order_data.get("product_name", ""),
            "wholesale_price": order_data.get("wholesale_price", 0),
            "selling_price": order_data.get("selling_price", 0),
            "quantity": order_data.get("quantity", 1),
            "customer": order_data.get("customer", {}),
            "status": "pending",
            "payment_status": "pending",
            "bigbuy_order_id": None,
            "tracking_number": None,
            "carrier": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "notes": []
        }
        self.orders.append(order)
        self._save_orders()

        # Step 1: Process payment
        if STRIPE_SECRET_KEY and order_data.get("payment_method_id"):
            payment_result = await self._charge_stripe(order, order_data["payment_method_id"])
            if not payment_result["success"]:
                order["status"] = "payment_failed"
                order["payment_status"] = "failed"
                order["notes"].append(f"Payment failed: {payment_result['error']}")
                self._save_orders()
                return {"success": False, "error": payment_result["error"], "order_id": order_id}
            order["payment_status"] = "paid"
            order["stripe_payment_id"] = payment_result.get("payment_id")
            order["notes"].append("Payment successful via Stripe")
        else:
            # Manual payment (bank transfer / cash on delivery)
            order["payment_status"] = "manual"
            order["notes"].append("Manual payment — awaiting confirmation")

        # Step 2: Submit to BigBuy
        bigbuy_result = await self._submit_to_bigbuy(order)
        if not bigbuy_result["success"]:
            order["status"] = "bigbuy_error"
            order["notes"].append(f"BigBuy error: {bigbuy_result['error']}")
            self._save_orders()
            # Notify owner immediately on error
            await self._notify_owner_error(order, bigbuy_result["error"])
            return {"success": False, "error": f"Order payment OK but supplier error: {bigbuy_result['error']}", "order_id": order_id}

        order["bigbuy_order_id"] = bigbuy_result["bigbuy_order_id"]
        order["status"] = "confirmed"
        order["notes"].append(f"BigBuy order created: {bigbuy_result['bigbuy_order_id']}")
        self._save_orders()

        # Step 3: Send confirmation to customer
        await self._send_customer_confirmation(order)

        # Step 4: Notify owner
        await self._notify_owner_new_order(order)

        # Step 5: Schedule tracking check (30 min later)
        asyncio.create_task(self._check_tracking_later(order_id, delay=1800))

        logger.info(f"Order {order_id} created successfully — BigBuy: {bigbuy_result['bigbuy_order_id']}")
        return {
            "success": True,
            "order_id": order_id,
            "bigbuy_order_id": bigbuy_result["bigbuy_order_id"],
            "status": "confirmed",
            "message": "Pedido confirmado. Recibirás un email con el seguimiento en breve."
        }

    # ─── Stripe ───

    async def _charge_stripe(self, order: dict, payment_method_id: str) -> dict:
        """Charge the customer via Stripe."""
        try:
            amount_cents = int(order["selling_price"] * order["quantity"] * 100)
            customer = order["customer"]

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create PaymentIntent
                r = await client.post(
                    "https://api.stripe.com/v1/payment_intents",
                    auth=(STRIPE_SECRET_KEY, ""),
                    data={
                        "amount": amount_cents,
                        "currency": "eur",
                        "payment_method": payment_method_id,
                        "confirm": "true",
                        "description": f"PataHogar — {order['product_name']} ({order['id']})",
                        "receipt_email": customer.get("email", ""),
                        "metadata[order_id]": order["id"],
                        "metadata[product_sku]": order.get("product_sku", ""),
                        "metadata[customer_country]": customer.get("country", "")
                    }
                )
                result = r.json()
                if r.status_code == 200 and result.get("status") in ("succeeded", "requires_capture"):
                    return {"success": True, "payment_id": result["id"]}
                else:
                    err = result.get("error", {}).get("message", "Stripe error")
                    return {"success": False, "error": err}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── BigBuy Order Submission ───

    async def _submit_to_bigbuy(self, order: dict) -> dict:
        """Submit order to BigBuy. BigBuy will ship directly to customer."""
        customer = order["customer"]
        country = customer.get("country", "ES").upper()
        carrier_code = COUNTRY_CARRIERS.get(country, DEFAULT_CARRIER)

        payload = {
            "order": {
                "cashOnDelivery": "0",
                "carriers": [{"code": carrier_code}],
                "internalReference": order["id"],
                "comments": f"PataHogar dropshipping order {order['id']}",
                "shippingAddress": {
                    "firstName": customer.get("first_name", ""),
                    "lastName": customer.get("last_name", ""),
                    "country": country,
                    "postcode": customer.get("postcode", ""),
                    "town": customer.get("city", ""),
                    "address": customer.get("address", ""),
                    "phone": customer.get("phone", ""),
                    "email": customer.get("email", ""),
                    "vatNumber": customer.get("vat_number", ""),
                    "companyName": customer.get("company", "")
                },
                "products": [{
                    "reference": order["product_sku"],
                    "quantity": order["quantity"]
                }]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{BIGBUY_BASE}/rest/order/create.json",
                    headers=BIGBUY_HEADERS,
                    json=payload
                )
                if r.status_code in (200, 201):
                    result = r.json()
                    bb_id = result.get("id") or result.get("order_id") or str(result)
                    return {"success": True, "bigbuy_order_id": bb_id}
                else:
                    logger.error(f"BigBuy order error {r.status_code}: {r.text[:500]}")
                    return {"success": False, "error": f"BigBuy HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Tracking ───

    async def _check_tracking_later(self, order_id: str, delay: int = 1800):
        """Wait then fetch tracking number from BigBuy."""
        await asyncio.sleep(delay)
        await self.fetch_tracking(order_id)

    async def fetch_tracking(self, order_id: str) -> dict:
        """Fetch tracking number from BigBuy and update order."""
        order = self._get_order(order_id)
        if not order or not order.get("bigbuy_order_id"):
            return {"error": "Order not found or no BigBuy ID"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{BIGBUY_BASE}/rest/order/{order['bigbuy_order_id']}/trackingcodes.json",
                    headers=BIGBUY_HEADERS
                )
                if r.status_code == 200:
                    data = r.json()
                    # BigBuy returns list of tracking codes
                    if isinstance(data, list) and data:
                        tracking = data[0].get("trackingCode") or data[0].get("code")
                        carrier = data[0].get("carrier", "")
                    elif isinstance(data, dict):
                        tracking = data.get("trackingCode") or data.get("code")
                        carrier = data.get("carrier", "")
                    else:
                        return {"status": "not_available_yet"}

                    if tracking:
                        order["tracking_number"] = tracking
                        order["carrier"] = carrier
                        order["status"] = "shipped"
                        order["updated_at"] = datetime.now().isoformat()
                        order["notes"].append(f"Shipped — tracking: {tracking} via {carrier}")
                        self._save_orders()

                        # Send tracking to customer
                        await self._send_tracking_email(order)
                        logger.info(f"Order {order_id} shipped — tracking: {tracking}")
                        return {"tracking_number": tracking, "carrier": carrier}
                    return {"status": "no_tracking_yet"}
                else:
                    return {"status": "bigbuy_error", "code": r.status_code}
        except Exception as e:
            return {"error": str(e)}

    # ─── Email Notifications ───

    def _send_email(self, to: str, subject: str, html_body: str):
        """Send email via SMTP."""
        if not SMTP_USER or not SMTP_PASS:
            logger.warning("SMTP not configured — email not sent")
            return
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"PataHogar <{SMTP_USER}>"
            msg["To"] = to
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(SMTP_USER, to, msg.as_string())
            logger.info(f"Email sent to {to}")
        except Exception as e:
            logger.error(f"Email error: {e}")

    async def _send_customer_confirmation(self, order: dict):
        customer = order["customer"]
        email = customer.get("email")
        if not email:
            return
        name = customer.get("first_name", "Cliente")
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
          <h2 style="color:#e67e22">✅ ¡Pedido Confirmado! — PataHogar</h2>
          <p>Hola <b>{name}</b>,</p>
          <p>Tu pedido ha sido confirmado y está siendo procesado.</p>
          <table style="width:100%;border-collapse:collapse;margin:20px 0">
            <tr style="background:#f8f8f8"><td style="padding:8px"><b>Nº Pedido</b></td><td style="padding:8px">{order['id']}</td></tr>
            <tr><td style="padding:8px"><b>Producto</b></td><td style="padding:8px">{order['product_name']}</td></tr>
            <tr style="background:#f8f8f8"><td style="padding:8px"><b>Cantidad</b></td><td style="padding:8px">{order['quantity']}</td></tr>
            <tr><td style="padding:8px"><b>Total</b></td><td style="padding:8px">€{order['selling_price'] * order['quantity']:.2f}</td></tr>
            <tr style="background:#f8f8f8"><td style="padding:8px"><b>Dirección entrega</b></td><td style="padding:8px">{customer.get('address','')}, {customer.get('city','')}, {customer.get('country','')}</td></tr>
          </table>
          <p>Recibirás el número de seguimiento en cuanto el paquete sea enviado (24-48h).</p>
          <p style="color:#888">¿Preguntas? Contáctanos por WhatsApp o email.</p>
          <p><b>— Equipo PataHogar 🐾</b></p>
        </div>
        """
        self._send_email(email, f"✅ Pedido Confirmado #{order['id']} — PataHogar", html)

    async def _send_tracking_email(self, order: dict):
        customer = order["customer"]
        email = customer.get("email")
        if not email:
            return
        name = customer.get("first_name", "Cliente")
        tracking = order.get("tracking_number", "")
        carrier = order.get("carrier", "")
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
          <h2 style="color:#27ae60">🚚 ¡Tu pedido está en camino! — PataHogar</h2>
          <p>Hola <b>{name}</b>,</p>
          <p>Tu pedido <b>{order['id']}</b> ha sido enviado.</p>
          <div style="background:#f0f9f0;border-radius:8px;padding:20px;margin:20px 0;text-align:center">
            <p style="font-size:14px;color:#555">Número de seguimiento</p>
            <p style="font-size:24px;font-weight:bold;color:#27ae60">{tracking}</p>
            <p style="color:#888">Transportista: {carrier}</p>
          </div>
          <p>El plazo de entrega habitual es 3–7 días laborables.</p>
          <p><b>— Equipo PataHogar 🐾</b></p>
        </div>
        """
        self._send_email(email, f"🚚 Tu pedido {order['id']} está en camino — PataHogar", html)

    async def _notify_owner_new_order(self, order: dict):
        customer = order["customer"]
        profit = round(order["selling_price"] - order["wholesale_price"], 2) * order["quantity"]
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
          <h2 style="color:#2980b9">💰 Nueva Venta — PataHogar</h2>
          <table style="width:100%;border-collapse:collapse">
            <tr style="background:#f0f8ff"><td style="padding:8px"><b>Pedido</b></td><td style="padding:8px">{order['id']}</td></tr>
            <tr><td style="padding:8px"><b>Producto</b></td><td style="padding:8px">{order['product_name']} ({order['product_sku']})</td></tr>
            <tr style="background:#f0f8ff"><td style="padding:8px"><b>Venta</b></td><td style="padding:8px">€{order['selling_price'] * order['quantity']:.2f}</td></tr>
            <tr><td style="padding:8px"><b>Coste BigBuy</b></td><td style="padding:8px">€{order['wholesale_price'] * order['quantity']:.2f}</td></tr>
            <tr style="background:#e8f8e8"><td style="padding:8px"><b>BENEFICIO</b></td><td style="padding:8px;color:green;font-weight:bold">€{profit:.2f}</td></tr>
            <tr><td style="padding:8px"><b>Cliente</b></td><td style="padding:8px">{customer.get('first_name','')} {customer.get('last_name','')}</td></tr>
            <tr style="background:#f0f8ff"><td style="padding:8px"><b>País</b></td><td style="padding:8px">{customer.get('country','')}</td></tr>
            <tr><td style="padding:8px"><b>BigBuy ID</b></td><td style="padding:8px">{order.get('bigbuy_order_id','')}</td></tr>
          </table>
        </div>
        """
        self._send_email(OWNER_EMAIL, f"💰 Nueva venta €{order['selling_price']:.2f} — {order['product_name'][:40]}", html)

    async def _notify_owner_error(self, order: dict, error: str):
        html = f"""
        <div style="font-family:Arial,sans-serif;padding:20px">
          <h2 style="color:#e74c3c">⚠️ Error en Pedido — PataHogar</h2>
          <p><b>Pedido:</b> {order['id']}</p>
          <p><b>Producto:</b> {order['product_name']}</p>
          <p><b>Cliente:</b> {order['customer'].get('email','')}</p>
          <p><b>Error:</b> {error}</p>
          <p><b>Estado pago:</b> {order['payment_status']}</p>
          <p style="color:#e74c3c"><b>Acción requerida: verificar y procesar manualmente si el cliente pagó.</b></p>
        </div>
        """
        self._send_email(OWNER_EMAIL, f"⚠️ Error pedido {order['id']} — REVISAR", html)

    # ─── Order Queries ───

    def _get_order(self, order_id: str) -> dict | None:
        return next((o for o in self.orders if o["id"] == order_id), None)

    def get_all_orders(self) -> list:
        return sorted(self.orders, key=lambda x: x["created_at"], reverse=True)

    def get_order_stats(self) -> dict:
        total = len(self.orders)
        confirmed = sum(1 for o in self.orders if o["status"] == "confirmed")
        shipped = sum(1 for o in self.orders if o["status"] == "shipped")
        pending = sum(1 for o in self.orders if o["status"] == "pending")
        failed = sum(1 for o in self.orders if o["status"] in ("payment_failed", "bigbuy_error"))
        total_revenue = sum(o["selling_price"] * o["quantity"] for o in self.orders
                            if o["status"] in ("confirmed", "shipped"))
        total_cost = sum(o["wholesale_price"] * o["quantity"] for o in self.orders
                         if o["status"] in ("confirmed", "shipped"))
        return {
            "total_orders": total,
            "confirmed": confirmed,
            "shipped": shipped,
            "pending": pending,
            "failed": failed,
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_profit": round(total_revenue - total_cost, 2)
        }

    async def refresh_all_tracking(self) -> dict:
        """Check tracking for all confirmed (not yet shipped) orders."""
        confirmed = [o for o in self.orders if o["status"] == "confirmed" and o.get("bigbuy_order_id")]
        updated = 0
        for order in confirmed:
            result = await self.fetch_tracking(order["id"])
            if result.get("tracking_number"):
                updated += 1
            await asyncio.sleep(2)
        return {"checked": len(confirmed), "updated_with_tracking": updated}

    async def get_bigbuy_order_status(self, order_id: str) -> dict:
        """Get the real-time status of an order from BigBuy."""
        order = self._get_order(order_id)
        if not order or not order.get("bigbuy_order_id"):
            return {"error": "Order not found"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{BIGBUY_BASE}/rest/order/{order['bigbuy_order_id']}.json",
                    headers=BIGBUY_HEADERS
                )
                if r.status_code == 200:
                    return {"bigbuy_data": r.json(), "local_order": order}
                return {"error": f"BigBuy HTTP {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}
