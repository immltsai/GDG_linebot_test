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

import re

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,
    ButtonsTemplate, PostbackEvent, PostbackTemplateAction, MessageAction,
    CarouselTemplate, CarouselColumn, FlexSendMessage
)
import os
import json
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

# LINE Bot 的 Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi('YOUR_CHANNEL_ACCESS_TOKEN')
handler = WebhookHandler('YOUR_CHANNEL_SECRET')

# 用戶資料儲存
USERS_DATA_FILE = 'users_data.json'
EXERCISE_DATA_FILE = 'exercise_data.json'

# 初始化用戶資料
def init_user_data():
    if not os.path.exists(USERS_DATA_FILE):
        with open(USERS_DATA_FILE, 'w') as f:
            json.dump({}, f)
    
    if not os.path.exists(EXERCISE_DATA_FILE):
        with open(EXERCISE_DATA_FILE, 'w') as f:
            json.dump({}, f)

init_user_data()

# 讀取用戶資料
def load_user_data():
    with open(USERS_DATA_FILE, 'r') as f:
        return json.load(f)

# 儲存用戶資料
def save_user_data(data):
    with open(USERS_DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False)

# 讀取運動資料
def load_exercise_data():
    with open(EXERCISE_DATA_FILE, 'r') as f:
        return json.load(f)

# 儲存運動資料
def save_exercise_data(data):
    with open(EXERCISE_DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False)

# 計算基礎代謝率 (BMR)
def calculate_bmr(gender, weight, height, age):
    if gender == '男':
        # 使用修訂版的Harris-Benedict公式
        return 10 * weight + 6.25 * height - 5 * age + 5
    else:  # 女性
        return 10 * weight + 6.25 * height - 5 * age - 161

# 計算運動熱量消耗
def calculate_exercise_calories(exercise_type, weight, duration_minutes):
    # MET (Metabolic Equivalent of Task) 值
    met_values = {
        '走路慢': 2.5,  # 慢走 (~3.2 km/h)
        '走路中': 3.5,  # 一般步行 (~4.8 km/h)
        '走路快': 4.3,  # 快走 (~6.4 km/h)
        '慢跑': 7.0,    # 慢跑 (~8 km/h)
        '跑步': 10.0,   # 跑步 (~10 km/h)
        '騎自行車慢': 4.0,  # 休閒騎車 (~15 km/h)
        '騎自行車中': 8.0,  # 中速騎車 (~20 km/h)
        '騎自行車快': 10.0, # 快速騎車 (~25+ km/h)
        '游泳': 7.0,    # 一般游泳
        '健身房輕度': 3.5,  # 輕度健身器材訓練
        '健身房中度': 5.0,  # 中度健身器材訓練
        '健身房重度': 8.0,  # 重度健身器材訓練
        '有氧運動': 7.5,  # 一般有氧課程
        '瑜珈': 3.0,    # 瑜珈
        '打籃球': 8.0,   # 籃球
        '打羽球': 5.5,   # 羽球
        '打桌球': 4.0,   # 桌球
    }
    
    # 如果找不到運動類型，使用中等強度的默認值
    met = met_values.get(exercise_type, 5.0)
    
    # 熱量(大卡) = MET × 體重(kg) × 時間(小時)
    calories = met * weight * (duration_minutes / 60)
    
    return round(calories)

# 根據衛福部建議計算每週建議運動量
def get_exercise_recommendation(user_data, weekly_calories):
    # 衛福部建議成人每週至少進行150分鐘中等強度或75分鐘高強度身體活動
    weight = float(user_data['weight'])
    
    # 中等強度運動 (MET約4.0) 150分鐘的熱量消耗
    recommended_med_calories = 4.0 * weight * (150 / 60)
    
    # 高強度運動 (MET約8.0) 75分鐘的熱量消耗
    recommended_high_calories = 8.0 * weight * (75 / 60)
    
    # 取平均值作為建議值
    recommended_calories = (recommended_med_calories + recommended_high_calories) / 2
    
    if weekly_calories < recommended_calories * 0.5:
        deficit_med_minutes = round((recommended_calories - weekly_calories) / (4.0 * weight / 60))
        deficit_high_minutes = round((recommended_calories - weekly_calories) / (8.0 * weight / 60))
        return f"您本週的運動量顯著低於建議標準。建議每週增加約 {deficit_med_minutes} 分鐘的中強度運動（如快走、騎自行車）或 {deficit_high_minutes} 分鐘的高強度運動（如跑步、有氧運動）。"
    elif weekly_calories < recommended_calories:
        deficit_med_minutes = round((recommended_calories - weekly_calories) / (4.0 * weight / 60))
        deficit_high_minutes = round((recommended_calories - weekly_calories) / (8.0 * weight / 60))
        return f"您的運動量接近但仍低於建議標準。建議每週增加約 {deficit_med_minutes} 分鐘的中強度運動或 {deficit_high_minutes} 分鐘的高強度運動以達到理想水平。"
    elif weekly_calories < recommended_calories * 1.5:
        return "恭喜！您的運動量已達到衛福部建議標準，繼續保持良好的習慣！"
    else:
        return "做得好！您的運動量已超過衛福部建議標準。請確保有足夠的休息時間以避免過度訓練。"

# 生成每週運動報告圖表
def generate_weekly_report_image(user_id):
    exercise_data = load_exercise_data()
    if user_id not in exercise_data:
        return None
    
    # 獲取最近7天的日期
    today = datetime.datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    
    # 準備數據
    daily_calories = {date: 0 for date in dates}
    
    for record in exercise_data[user_id]:
        record_date = record['date']
        if record_date in daily_calories:
            daily_calories[record_date] += record['calories']
    
    # 創建圖表
    plt.figure(figsize=(10, 6))
    plt.bar(range(len(dates)), [daily_calories[date] for date in dates], color='skyblue')
    plt.xticks(range(len(dates)), [date[5:] for date in dates], rotation=45)
    plt.xlabel('日期')
    plt.ylabel('消耗熱量 (大卡)')
    plt.title('最近一週運動熱量消耗')
    plt.tight_layout()
    
    # 轉換圖表為 base64 字符串
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png')
    img_buf.seek(0)
    img_str = base64.b64encode(img_buf.read()).decode()
    plt.close()
    
    return img_str

# 生成每月運動報告圖表
def generate_monthly_report_image(user_id):
    exercise_data = load_exercise_data()
    if user_id not in exercise_data:
        return None
    
    # 獲取本月的所有日期
    today = datetime.datetime.now().date()
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    
    days_in_month = (next_month - first_day).days
    dates = [(first_day + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days_in_month)]
    
    # 準備數據
    daily_calories = {date: 0 for date in dates}
    
    for record in exercise_data[user_id]:
        record_date = record['date']
        if record_date in daily_calories:
            daily_calories[record_date] += record['calories']
    
    # 創建圖表
    plt.figure(figsize=(12, 6))
    plt.bar(range(len(dates)), [daily_calories[date] for date in dates], color='lightgreen')
    plt.xticks(range(0, len(dates), 5), [date[8:10] for date in dates[::5]], rotation=0)
    plt.xlabel('日期')
    plt.ylabel('消耗熱量 (大卡)')
    plt.title(f'{today.year}年{today.month}月運動熱量消耗')
    plt.tight_layout()
    
    # 轉換圖表為 base64 字符串
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png')
    img_buf.seek(0)
    img_str = base64.b64encode(img_buf.read()).decode()
    plt.close()
    
    return img_str

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text
    user_id = event.source.user_id
    
    # 讀取用戶資料
    users_data = load_user_data()
    
    # 初始化新用戶
    if user_id not in users_data:
        users_data[user_id] = {"registration_step": "start"}
        save_user_data(users_data)
        
        welcome_message = "歡迎使用熱量計算LINE Bot！請選擇您要執行的操作："
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="歡迎選單",
                template=ButtonsTemplate(
                    title="熱量計算機器人",
                    text=welcome_message,
                    actions=[
                        MessageAction(label="註冊個人資料", text="/註冊"),
                        MessageAction(label="記錄運動", text="/運動"),
                        MessageAction(label="查看報告", text="/報告"),
                        MessageAction(label="幫助", text="/幫助")
                    ]
                )
            )
        )
        return

    # 處理命令
    if text.startswith('/'):
        handle_command(event, text, user_id, users_data)
        return
    
    # 處理註冊流程
    if "registration_step" in users_data[user_id] and users_data[user_id]["registration_step"] != "completed":
        handle_registration(event, text, user_id, users_data)
        return
    
    # 處理運動記錄流程
    if "exercise_step" in users_data[user_id] and users_data[user_id]["exercise_step"] != "completed":
        handle_exercise_record(event, text, user_id, users_data)
        return
    
    # 如果都不是以上情況，提供主選單
    show_main_menu(event)

def handle_command(event, text, user_id, users_data):
    if text == "/註冊":
        # 開始註冊流程
        users_data[user_id]["registration_step"] = "gender"
        save_user_data(users_data)
        
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="選擇性別",
                template=ButtonsTemplate(
                    title="步驟 1: 選擇性別",
                    text="請選擇您的性別：",
                    actions=[
                        MessageAction(label="男", text="男"),
                        MessageAction(label="女", text="女")
                    ]
                )
            )
        )
    
    elif text == "/運動":
        # 確認用戶是否已完成註冊
        if "registration_step" not in users_data[user_id] or users_data[user_id]["registration_step"] != "completed":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請先完成個人資料註冊，輸入 /註冊 開始。")
            )
            return
        
        # 開始運動記錄流程
        users_data[user_id]["exercise_step"] = "type"
        save_user_data(users_data)
        
        # 顯示運動類型選單
        show_exercise_menu(event)
    
    elif text == "/報告":
        # 確認用戶是否已完成註冊
        if "registration_step" not in users_data[user_id] or users_data[user_id]["registration_step"] != "completed":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請先完成個人資料註冊，輸入 /註冊 開始。")
            )
            return
        
        # 顯示報告選單
        line_bot_api.reply_message(
            event.reply_token,
            TemplateSendMessage(
                alt_text="選擇報告類型",
                template=ButtonsTemplate(
                    title="報告類型",
                    text="請選擇您要查看的報告類型：",
                    actions=[
                        MessageAction(label="每週報告", text="/週報告"),
                        MessageAction(label="每月報告", text="/月報告"),
                        MessageAction(label="運動建議", text="/建議")
                    ]
                )
            )
        )
    
    elif text == "/週報告":
        show_weekly_report(event, user_id)
    
    elif text == "/月報告":
        show_monthly_report(event, user_id)
    
    elif text == "/建議":
        show_exercise_recommendation(event, user_id)
    
    elif text == "/幫助":
        help_text = (
            "《熱量計算LINE Bot 使用說明》\n\n"
            "◉ 主要功能：\n"
            "- /註冊：設定身高、體重、性別、年齡等個人資料\n"
            "- /運動：記錄每天的運動項目和時間\n"
            "- /報告：查看每週/每月運動報告和健康建議\n"
            "- /幫助：顯示此幫助訊息\n\n"
            "◉ 報告功能：\n"
            "- /週報告：顯示最近一週的運動熱量消耗\n"
            "- /月報告：顯示本月每天的運動熱量消耗\n"
            "- /建議：根據您的運動量提供建議\n\n"
            "開始使用請輸入 /註冊 完成個人資料設定！"
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=help_text)
        )
    
    else:
        show_main_menu(event)

def handle_registration(event, text, user_id, users_data):
    step = users_data[user_id]["registration_step"]
    
    if step == "gender":
        if text in ["男", "女"]:
            users_data[user_id]["gender"] = text
            users_data[user_id]["registration_step"] = "age"
            save_user_data(users_data)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入您的年齡（整數）：")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請選擇「男」或「女」：")
            )
    
    elif step == "age":
        try:
            age = int(text)
            if 10 <= age <= 120:
                users_data[user_id]["age"] = age
                users_data[user_id]["registration_step"] = "height"
                save_user_data(users_data)
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入您的身高（公分）：")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入有效的年齡（10-120歲）：")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入有效的數字：")
            )
    
    elif step == "height":
        try:
            height = float(text)
            if 100 <= height <= 250:
                users_data[user_id]["height"] = height
                users_data[user_id]["registration_step"] = "weight"
                save_user_data(users_data)
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入您的體重（公斤）：")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入有效的身高（100-250公分）：")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入有效的數字：")
            )
    
    elif step == "weight":
        try:
            weight = float(text)
            if 30 <= weight <= 200:
                users_data[user_id]["weight"] = weight
                users_data[user_id]["registration_step"] = "completed"
                save_user_data(users_data)
                
                # 計算BMR
                bmr = calculate_bmr(
                    users_data[user_id]["gender"],
                    users_data[user_id]["weight"],
                    users_data[user_id]["height"],
                    users_data[user_id]["age"]
                )
                users_data[user_id]["bmr"] = bmr
                save_user_data(users_data)
                
                completion_message = (
                    f"個人資料設定完成！\n\n"
                    f"性別：{users_data[user_id]['gender']}\n"
                    f"年齡：{users_data[user_id]['age']} 歲\n"
                    f"身高：{users_data[user_id]['height']} 公分\n"
                    f"體重：{users_data[user_id]['weight']} 公斤\n"
                    f"基礎代謝率：{round(bmr)} 大卡/天\n\n"
                    f"您現在可以記錄您的運動了！輸入 /運動 開始記錄。"
                )
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=completion_message)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入有效的體重（30-200公斤）：")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入有效的數字：")
            )

def show_exercise_menu(event):
    exercise_categories = [
        {
            "title": "走路/跑步",
            "exercises": ["走路慢", "走路中", "走路快", "慢跑", "跑步"]
        },
        {
            "title": "騎車/水上運動",
            "exercises": ["騎自行車慢", "騎自行車中", "騎自行車快", "游泳"]
        },
        {
            "title": "健身/伸展",
            "exercises": ["健身房輕度", "健身房中度", "健身房重度", "有氧運動", "瑜珈"]
        },
        {
            "title": "球類運動",
            "exercises": ["打籃球", "打羽球", "打桌球"]
        }
    ]
    
    carousel_columns = []
    
    for category in exercise_categories:
        actions = [MessageAction(label=ex, text=ex) for ex in category["exercises"]]
        column = CarouselColumn(
            title=category["title"],
            text="請選擇運動類型",
            actions=actions
        )
        carousel_columns.append(column)
    
    line_bot_api.reply_message(
        event.reply_token,
        TemplateSendMessage(
            alt_text="選擇運動類型",
            template=CarouselTemplate(columns=carousel_columns)
        )
    )

def handle_exercise_record(event, text, user_id, users_data):
    step = users_data[user_id]["exercise_step"]
    
    if step == "type":
        # 檢查是否為有效的運動類型
        exercise_types = [
            "走路慢", "走路中", "走路快", "慢跑", "跑步",
            "騎自行車慢", "騎自行車中", "騎自行車快", "游泳",
            "健身房輕度", "健身房中度", "健身房重度", "有氧運動", "瑜珈",
            "打籃球", "打羽球", "打桌球"
        ]
        
        if text in exercise_types:
            users_data[user_id]["current_exercise"] = text
            users_data[user_id]["exercise_step"] = "duration"
            save_user_data(users_data)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"您選擇了 {text}，請輸入運動時間（分鐘）：")
            )
        else:
            # 如果不是有效運動類型，重新顯示選單
            show_exercise_menu(event)
    
    elif step == "duration":
        try:
            duration = int(text)
            if 1 <= duration <= 600:  # 限制最長10小時
                exercise_type = users_data[user_id]["current_exercise"]
                weight = users_data[user_id]["weight"]
                
                # 計算運動消耗的熱量
                calories = calculate_exercise_calories(exercise_type, weight, duration)
                
                # 保存運動記錄
                exercise_data = load_exercise_data()
                if user_id not in exercise_data:
                    exercise_data[user_id] = []
                
                today = datetime.datetime.now().date().strftime('%Y-%m-%d')
                exercise_record = {
                    "date": today,
                    "type": exercise_type,
                    "duration": duration,
                    "calories": calories
                }
                
                exercise_data[user_id].append(exercise_record)
                save_exercise_data(exercise_data)
                
                # 重置運動記錄步驟
                users_data[user_id]["exercise_step"] = "completed"
                save_user_data(users_data)
                
                # 回覆用戶
                reply_message = (
                    f"運動記錄已保存！\n\n"
                    f"運動類型：{exercise_type}\n"
                    f"運動時間：{duration} 分鐘\n"
                    f"消耗熱量：{calories} 大卡\n\n"
                    f"輸入 /運動 記錄新的運動，或輸入 /報告 查看您的運動報告。"
                )
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_message)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入有效的運動時間（1-600分鐘）：")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入有效的數字：")
            )

def show_weekly_report(event, user_id):
    # 檢查是否有運動記錄
    exercise_data = load_exercise_data()
    if user_id not in exercise_data or not exercise_data[user_id]:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您尚未記錄任何運動。輸入 /運動 開始記錄。")
        )
        return
    
    # 獲取最近7天的日期
    today = datetime.datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    
    # 計算每天的熱量消耗
    daily_calories = {date: 0 for date in dates}
    for record in exercise_data[user_id]:
        record_date = record['date']
        if record_date in daily_calories:
            daily_calories[record_date] += record['calories']
    
    # 計算總熱量和平均熱量
    total_calories = sum(daily_calories.values())
    avg_calories = total_calories / 7 if total_calories > 0 else 0
    
    # 生成圖表
    img_str = generate_weekly_report_image(user_id)
    
    # 生成報告內容
    report_text = f"《最近一週運動報告》\n\n"
    for date in dates:
        report_text += f"{date[5:]} - {daily_calories[date]} 大卡\n"
    
    report_text += f"\n總消耗熱量：{total_calories} 大卡\n"
    report_text += f"每日平均：{round(avg_calories)} 大卡\n"
    
    # 根據用戶資料獲取建議
    users_data = load_user_data()
    if user_id in users_data and "registration_step" in users_data[user_id] and users_data[user_id]["registration_step"] == "completed":
        recommendation = get_exercise_recommendation(users_data[user_id], total_calories)
        report_text += f"\n{recommendation}"
    
    # 發送報告
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=report_text)
    )
    
    # 如果有圖表，另外發送
    if img_str:
        image_message = {
            "type": "image",
            "originalContentUrl": f"data:image/png;base64,{img_str}",
            "previewImageUrl": f"data:image/png;base64,{img_str}"
        }
        line_bot_api.push_message(user_id, [image_message])

def show_monthly_report(event, user_id):
    # 檢查是否有運動記錄
    exercise_data = load_exercise_data()
    if user_id not in exercise_data or not exercise_data[user_id]:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您尚未記錄任何運動。輸入 /運動 開始記錄。")
        )
        return
    
    # 獲取本月的所有日期
    today = datetime.datetime.now().date()
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    
    days_in_month = (next_month - first_day).days
    dates = [(first_day + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days_in_month)]
    
    # 只保留本月的日期（今天及之前）
    dates = [date for date in dates if date <= today.strftime('%Y-%m-%d')]
    
    # 計算每天的熱量消耗
    daily_calories = {date: 0 for date in dates}
    for record in exercise_data[user_id]:
        record_date = record['date']
        if record_date in daily_calories:
            daily_calories[record_date] += record['calories']
    
    # 計算總熱量和平均熱量
    total_calories = sum(daily_calories.values())
    avg_calories = total_calories / len(dates) if total_calories > 0 else 0
    
    # 生成圖表
    img_str = generate_monthly_report_image(user_id)
    
    # 生成報告內容
    report_text = f"《本月運動報告》\n\n"
    
    # 計算每週的熱量消耗
    weeks = {}
    for date in dates:
        date_obj = datetime.datetime.strptime(date, '%Y-%m-%d').date()
        week_num = (date_obj.day - 1) // 7 + 1
        if week_num not in weeks:
            weeks[week_num] = 0
        weeks[week_num] += daily_calories[date]
    
    for week_num, calories in weeks.items():
        report_text += f"第 {week_num} 週：{calories} 大卡\n"
    
    report_text += f"\n總消耗熱量：{total_calories} 大卡\n"
    report_text += f"每日平均：{round(avg_calories)} 大卡\n"
    
    # 根據用戶資料獲取建議
    users_data = load_user_data()
    if user_id in users_data and "registration_step" in users_data[user_id] and users_data[user_id]["registration_step"] == "completed":
        # 計算本月每週平均消耗熱量
        monthly_weekly_avg = total_calories / (len(weeks) if len(weeks) > 0 else 1)
        recommendation = get_exercise_recommendation(users_data[user_id], monthly_weekly_avg)
        report_text += f"\n{recommendation}"
    
    # 發送報告
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=report_text)
    )
    
    # 如果有圖表，另外發送
    if img_str:
        image_message = {
            "type": "image",
            "originalContentUrl": f"data:image/png;base64,{img_str}",
            "previewImageUrl": f"data:image/png;base64,{img_str}"
        }
        line_bot_api.push_message(user_id, [image_message])

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

