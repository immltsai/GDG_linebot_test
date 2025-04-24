import os
from places import get_nearby_restaurants
from stock import txt_to_img_url
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler, Event
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging.models import TextMessage
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, 
    TextMessage, 
    TextSendMessage,
    ImageSendMessage)
from linebot.exceptions import InvalidSignatureError
import logging

import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro")

# 加載 .env 文件中的變數
load_dotenv()

# 從環境變數中讀取 LINE 的 Channel Access Token 和 Channel Secret
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')

# 檢查是否設置了環境變數
if not line_token or not line_secret:
    print(f"LINE_TOKEN: {line_token}")  # 調試輸出
    print(f"LINE_SECRET: {line_secret}")  # 調試輸出
    raise ValueError("LINE_TOKEN 或 LINE_SECRET 未設置")

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# 創建 Flask 應用
app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# 設置一個路由來處理 LINE Webhook 的回調請求
@app.route("/", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭
    signature = request.headers['X-Line-Signature']

    # 取得請求的原始內容
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # 驗證簽名並處理請求
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 設置一個事件處理器來處理 TextMessage 事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: Event):
    if event.message.type == "text":
        user_message = event.message.text  # 使用者的訊息
        app.logger.info(f"收到的訊息: {user_message}")

        # 使用 GPT 生成回應
        if user_message == "附近的餐廳":
            reply_text = get_nearby_restaurants()
        elif user_message == "課表":
            reply_text = "這是你的課表～"
        elif user_message == "台積電股票":
            try:
                image_url = txt_to_img_url()
                if not image_url:
                    error_message = f"抱歉，沒有取得股票趨勢圖，{image_url}。"
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextMessage(text=error_message)
                    )
                    return
                line_bot_api.reply_message(
                    event.reply_token,
                    ImageSendMessage(
                        original_content_url=image_url,
                        preview_image_url=image_url
                    )
                )
            except Exception as e:
                error_message = f"抱歉，無法生成股票趨勢圖，錯誤原因：{e}"
                line_bot_api.reply_message(
                    event.reply_token,
                    TextMessage(text=error_message)
                )
            return

        else:
            prompt = f"你是一個親切的繁體中文助手，請用繁體中文回答以下問題：{user_message}"
            response = model.generate_content(prompt) # 傳送使用者的問題給 Gemini
            reply_text = response.text.replace("\n", " ") if response else "抱歉，我無法回答這個問題。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
# 應用程序入口點
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
