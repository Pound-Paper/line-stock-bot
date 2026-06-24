import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ---- Line Config ----
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ---- Shopify Config ----
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")          # เช่น mystore.myshopify.com
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")    # Admin API access token


# ---- Shopify: ค้นหาสินค้าตามชื่อ ----
async def search_stock(product_name: str) -> str:
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    params = {"title": product_name, "limit": 5, "fields": "title,variants"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)

    if resp.status_code != 200:
        return "เกิดข้อผิดพลาดในการเช็คสต็อก กรุณาลองใหม่อีกครั้งค่ะ"

    products = resp.json().get("products", [])

    if not products:
        return f"ไม่พบสินค้า \"{product_name}\" ในระบบค่ะ\nลองพิมพ์ชื่อใหม่หรือสอบถามเจ้าหน้าที่ได้เลยนะคะ 😊"

    lines = []
    for product in products:
        for variant in product["variants"]:
            qty = variant.get("inventory_quantity", 0)
            title = product["title"]
            variant_title = variant.get("title", "")
            # ถ้า variant มีตัวเลือก เช่น สี/ขนาด
            if variant_title and variant_title != "Default Title":
                name = f"{title} ({variant_title})"
            else:
                name = title

            if qty > 0:
                lines.append(f"✅ {name} — มีสต็อก {qty} ชิ้น")
            else:
                lines.append(f"❌ {name} — สินค้าหมด")

    result = "\n".join(lines)
    return f"ผลการค้นหา \"{product_name}\":\n\n{result}"


# ---- Line Webhook Endpoint ----
@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    import asyncio

    user_text = event.message.text.strip()

    # ตอบแบบ async ผ่าน loop
    loop = asyncio.new_event_loop()
    reply_text = loop.run_until_complete(search_stock(user_text))
    loop.close()

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


# ---- Health Check ----
@app.get("/")
def root():
    return {"status": "Line Stock Bot is running 🚀"}
