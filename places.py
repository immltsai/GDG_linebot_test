import requests
from dotenv import load_dotenv
import os

# 加載 .env 文件中的變數
load_dotenv()

# 你的 Google Places API Key
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

def get_nearby_restaurants():
    """ 查詢附近的餐廳資訊 """
    latitude, longitude, radius = 25.033964, 121.564472, 1000  # 台北101
    url = (f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
           f"?location={latitude},{longitude}&radius={radius}&type=restaurant&key={API_KEY}&language=zh-TW")

    response = requests.get(url).json()
    results = []

    if "results" in response:
        for place in response["results"][:5]:
            name = place["name"]
            rating = place.get("rating", "N/A")
            address = place.get("vicinity", "未知地址")
            place_id = place["place_id"]
            map_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            results.append(f"🍽 {name} | ⭐ {rating}\n📍 {address}\n🔗 {map_url}")

    return "\n\n".join(results) if results else "找不到餐廳資訊 😢"

