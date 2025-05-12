import os
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    ImageSendMessage
)
import firebase_admin
from firebase_admin import credentials, initialize_app, firestore
import google.generativeai as genai
import re

# === 環境變數載入 ===
load_dotenv()

# === Firebase 初始化 ===
firebase_cred_str = os.getenv("FIREBASE_KEY")
if not firebase_cred_str:
    raise ValueError("未設定 FIREBASE_KEY 環境變數")

cred_dict = json.loads(firebase_cred_str)
cred = credentials.Certificate(cred_dict)
initialize_app(cred)
db = firestore.client()

# === LINE Bot 初始化 ===
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')

# 檢查是否設置了環境變數
if not line_token or not line_secret:
    raise ValueError("LINE_TOKEN 或 LINE_SECRET 未設置")

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# === Gemini AI 初始化 ===
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-pro")

# 創建 Flask 應用
app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# === MET 常用活動參考值 ===
MET_VALUES = {
    "走路": 2,
    "快走": 3.5,
    "慢跑": 7,
    "騎腳踏車": 6,
    "游泳": 8,
    "跳繩": 12,
    "瑜珈": 2.5
}

# === 計算熱量公式 ===
def calculate_calories(weight, met, minutes):
    return met * weight * (minutes / 60)

# === BMI 計算 ===
def calculate_bmi(weight, height_cm):
    height_m = height_cm / 100
    return round(weight / (height_m ** 2), 2)

# === 清理 Gemini 回傳文字的函式 ===
def clean_gemini_text(text: str) -> str:
    """
    清理 Gemini 回傳的文字：
    - 移除多餘空白行（含中間只有空格的行）
    - 清除尾端的換行與空格，避免 LINE 手機版多顯示一行
    """
    if not text:
        return ""
    cleaned = re.sub(r'\n\s*\n', '\n', text)  # 多餘空行變成一個換行
    cleaned = cleaned.rstrip()  # 移除尾端空格或換行
    return cleaned

# === Gemini AI 產生建議函式整合清理功能 ===
def generate_gemini_advice(history, user_message):
    try:
        prompt = (
            f"使用者最近的運動紀錄：{history}\n"
            f"使用者問題：{user_message}\n"
            "請用親切且鼓勵的語氣，使用繁體中文，給予個人化健康建議。"
        )
        response = gemini_model.generate_content(prompt)
        raw_text = response.text if response else "很抱歉，暫時無法提供建議。"
        return clean_gemini_text(raw_text)
    except Exception as e:
        return f"系統忙碌中，請稍後再試～ ({e})"

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

# === 處理使用者訊息 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()
    reply_token = event.reply_token

    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()

    # === 使用者資料設定 ===
    if user_message.startswith("身高"):
        try:
            height = int(user_message.replace("身高", "").replace("公分", "").strip())
            user_ref.set({"height": height}, merge=True)
            reply = f"已紀錄身高：{height} 公分"
        except:
            reply = "請輸入正確的身高，例如：身高170公分"

    elif user_message.startswith("體重"):
        try:
            weight = float(user_message.replace("體重", "").replace("公斤", "").strip())
            user_ref.set({"weight": weight}, merge=True)
            reply = f"已紀錄體重：{weight} 公斤"
        except:
            reply = "請輸入正確的體重，例如：體重60公斤"

    elif user_message.startswith("年齡"):
        try:
            age = int(user_message.replace("年齡", "").replace("歲", "").strip())
            user_ref.set({"age": age}, merge=True)
            reply = f"已紀錄年齡：{age} 歲"
        except:
            reply = "請輸入正確的年齡，例如：年齡25歲"

    elif user_message.startswith("性別"):
        gender = user_message.replace("性別", "").strip()
        if gender in ["男", "女"]:
            user_ref.set({"gender": gender}, merge=True)
            reply = f"已紀錄性別：{gender}"
        else:
            reply = "請輸入正確的性別，例如：性別男"

    # === 註冊資料 ===
    elif user_message == "註冊資料":
        reply = (
            "請分別輸入以下個人資料，範例如下：\n"
            "身高170公分\n"
            "體重60公斤\n"
            "年齡25歲\n"
            "性別男"
        )
    
    # === 運動紀錄 ===
    elif user_message == "運動紀錄":
        reply = (
            "運動類型包含走路、快走、慢跑、騎腳踏車、游泳、跳繩、瑜珈\n"
            "請分別輸入各種運動，範例如下：\n"
            "快走30分鐘\n"
            "慢跑20分鐘\n"
            "游泳45分鐘"
        )
        
    # === 運動資料儲存 ===    
    elif any(activity in user_message for activity in MET_VALUES):
        if not user_doc.exists:
            reply = "請先設定身高與體重。"
        else:
            user_data = user_doc.to_dict()
            weight = user_data.get("weight")
            if not weight:
                reply = "請先設定體重。"

            else:
                for activity, met in MET_VALUES.items():
                    if activity in user_message:
                        try:
                            minutes = int(user_message.replace(activity, "").replace("分鐘", "").strip())
                            calories = calculate_calories(weight, met, minutes)
                            date_str = datetime.now().strftime("%Y-%m-%d")
                            activity_ref = user_ref.collection("activities").document(date_str)
                            activity_doc = activity_ref.get()

                            if activity_doc.exists:
                                record = activity_doc.to_dict().get("records", [])
                            else:
                                record = []

                            record.append({
                                "activity": activity,
                                "minutes": minutes,
                                "calories": round(calories, 2)
                            })

                            activity_ref.set({"records": record})

                            reply = f"已紀錄：{activity} {minutes} 分鐘，消耗約 {round(calories, 2)} 大卡。"
                        except:
                            reply = "請輸入正確格式，例如：快走30分鐘"
                        break
                else:
                    reply = "未找到對應的運動類型。"

    # === 運動建議 + Gemini 提醒 ===
    elif user_message == "運動建議":
        if not user_doc.exists:
            reply = "請先輸入身高和體重資料。"
        else:
            user_data = user_doc.to_dict()
            height = user_data.get("height")
            weight = user_data.get("weight")

            if height and weight:
                bmi = calculate_bmi(weight, height)
                bmi_status = ""
                if bmi < 18.5:
                    bmi_status = "體重過輕"
                elif 18.5 <= bmi < 24:
                    bmi_status = "體重正常"
                elif 24 <= bmi < 27:
                    bmi_status = "體重稍重"
                else:
                    bmi_status = "體重過重"
                    
                # 最近 7 天運動歷史
                history_records = []
                for i in range(7):
                    date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    activity_doc = user_ref.collection("activities").document(date_str).get()
                    if activity_doc.exists:
                        records = activity_doc.to_dict().get("records", [])
                        history_records.extend(records)
                
                # 整理資料給 Gemini
                user_profile_info = f"使用者的 BMI 為 {bmi} ({bmi_status})。"
                prompt_context_1 = {
                    "最近 7 天運動紀錄": history_records,
                    "個人健康狀態": user_profile_info
                }        

                # Gemini AI 給個人化建議
                gemini_advice = generate_gemini_advice(prompt_context_1, "請根據我的健康狀態和運動紀錄提供運動建議")

                reply = (
                    f"你的 BMI 為 {bmi}。\n\n"
                    f"💡 運動建議：\n{gemini_advice}"
                )
            else:
                reply = "請確認已完整輸入身高與體重。"

    # === 週報告 + Gemini 建議 ===
    elif user_message == "週報告":
        if not user_doc.exists:
            reply = "請先設定個人資料。"
        else:
            total_calories = 0
            total_minutes = 0
            activity_summary = {}
    
            for i in range(7):
                date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                activity_doc = user_ref.collection("activities").document(date_str).get()
                if activity_doc.exists:
                    records = activity_doc.to_dict().get("records", [])
                    for record in records:
                        activity = record["activity"]
                        minutes = record["minutes"]
                        calories = record["calories"]
                        total_calories += calories
                        total_minutes += minutes
                        activity_summary[activity] = activity_summary.get(activity, 0) + minutes
    
            if total_minutes == 0:
                reply = "這週還沒有紀錄任何運動，加油！💪"
            else:
                activity_details = "\n".join([f"- {act}: {mins} 分鐘" for act, mins in activity_summary.items()])
                prompt_context_2 = {
                    "最近 7 天總運動時間": f"{total_minutes} 分鐘",
                    "總消耗熱量": f"{total_calories} 大卡",
                    "活動分佈": activity_summary
                }
                gemini_advice = generate_gemini_advice(prompt_context_2, "請給我一份週報告的健康建議")
    
                reply = (
                    f"📅【本週運動報告】\n"
                    f"總運動時間：{total_minutes} 分鐘\n"
                    f"總消耗熱量：{round(total_calories, 2)} 大卡\n"
                    f"活動分佈：\n{activity_details}\n\n"
                    f"💡 運動建議：\n{gemini_advice}"
                )

    # === 月報告 + Gemini 建議 ===
    elif user_message == "月報告":
        if not user_doc.exists:
            reply = "請先設定個人資料。"
        else:
            total_calories = 0
            total_minutes = 0
            activity_summary = {}
    
            for i in range(30):
                date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                activity_doc = user_ref.collection("activities").document(date_str).get()
                if activity_doc.exists:
                    records = activity_doc.to_dict().get("records", [])
                    for record in records:
                        activity = record["activity"]
                        minutes = record["minutes"]
                        calories = record["calories"]
                        total_calories += calories
                        total_minutes += minutes
                        activity_summary[activity] = activity_summary.get(activity, 0) + minutes
    
            if total_minutes == 0:
                reply = "這週還沒有紀錄任何運動，加油！💪"
            else:
                activity_details = "\n".join([f"- {act}: {mins} 分鐘" for act, mins in activity_summary.items()])
                prompt_context_3 = {
                    "最近 30 天總運動時間": f"{total_minutes} 分鐘",
                    "總消耗熱量": f"{total_calories} 大卡",
                    "活動分佈": activity_summary
                }
                gemini_advice = generate_gemini_advice(prompt_context_3, "請給我一份週報告的健康建議")
    
                reply = (
                    f"📅【本月運動報告】\n"
                    f"總運動時間：{total_minutes} 分鐘\n"
                    f"總消耗熱量：{round(total_calories, 2)} 大卡\n"
                    f"活動分佈：\n{activity_details}\n\n"
                    f"💡 運動建議：\n{gemini_advice}"
                )

    # === 幫助 ===
    elif user_message == "幫助":
        reply = (
            "📖【健康管理教練 使用說明】\n\n"
            "指令需要逐條輸入哦～\n"
            "📝 個人資料設定範例：\n"
            "  - 身高170公分\n"
            "  - 體重60公斤\n"
            "  - 年齡25歲\n"
            "  - 性別男\n\n"
            "🏃‍♂️ 運動紀錄範例：\n"
            "  - 快走30分鐘\n"
            "  - 慢跑20分鐘\n"
            "  - 游泳45分鐘\n\n"
            "目前有的運動包含走路、快走、慢跑、騎腳踏車、游泳、跳繩、瑜珈"
            "📅 報告功能：\n"
            "  - 週報告（統計最近 7 天運動）\n"
            "  - 月報告（統計最近 30 天運動）\n\n"
            "💡 其他指令：\n"
            "  - 註冊資料（查看個人資料設定範例）\n"
            "  - 幫助（顯示本說明）\n\n"
            "✨ 請試著輸入範例看看吧！一起邁向更健康的生活～💪"
        )

    else:
        reply = "請輸入有效的指令，例如：註冊資料、運動建議等。"

    line_bot_api.reply_message(reply_token, TextSendMessage(text=reply))


# === 啟動應用 ===
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
