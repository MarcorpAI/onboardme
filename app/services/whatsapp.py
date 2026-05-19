import httpx
import logging
from app.config import settings
from app.services.message_formatting import normalize_message_links

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(self, bridge_url: str = None):
        self.bridge_url = bridge_url or settings.whatsapp_bridge_url

    async def send_message(self, to: str, message: str):
        message = normalize_message_links(message)
        payload = {
            "to": to,
            "message": message
        }
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Sending WhatsApp message to {to} via {self.bridge_url}/send")
                response = await client.post(
                    f"{self.bridge_url}/send",
                    json=payload,
                    timeout=30.0
                )
                if response.status_code != 200:
                    logger.error(f"Bridge returned {response.status_code}: {response.text}")
                    return False, None

                data = response.json()
                jid = data.get("jid")
                logger.info(f"Message sent successfully. JID: {jid}")
                return True, jid

        except Exception as e:
            logger.error(f"Error sending WhatsApp message to {to}: {e}")
            return False, None

    async def disconnect(self):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.bridge_url}/disconnect", timeout=30.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error disconnecting WhatsApp bridge: {e}")
            raise

    def format_phone(self, phone: str) -> str:
        # Strip everything that isn't a digit
        phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")

        # Already full international Nigerian number: 2348XXXXXXXXX (13 digits)
        if phone.startswith("234") and len(phone) == 13:
            return "+" + phone

        # Local Nigerian format: 08XXXXXXXXX or 09XXXXXXXXX (11 digits)
        if phone.startswith("0") and len(phone) == 11:
            return "+234" + phone[1:]

        # International without leading 234, e.g. just the 10-digit subscriber number
        if len(phone) == 10 and not phone.startswith("0"):
            return "+234" + phone

        # Fallback — prepend + and send as-is, let the bridge handle it
        logger.warning(f"Unrecognized phone format: {phone}, sending with + prefix")
        return "+" + phone


whatsapp_service = WhatsAppService()
