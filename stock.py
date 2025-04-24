import os
from dotenv import load_dotenv
load_dotenv()
import twstock
import re
import cloudinary
import cloudinary.uploader
import matplotlib
matplotlib.use('Agg')  # For server compatibility
import matplotlib.pyplot as plt
import pandas as pd

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def upload_to_cloudinary(file_path) -> str:
    """Upload an image to Cloudinary and return its URL."""
    try:
        response = cloudinary.uploader.upload(file_path)
        return response['secure_url']
    except Exception as e:
        print(f"Image upload failed: {e}")
        return None

def txt_to_img_url() -> str:
    try:
        sid = '2330'
        stock = twstock.Stock(sid)
        file_name = f'{sid}.png'

        # Prepare stock data for plotting
        stock_data = {
            'close': stock.close,
            'date': stock.date,
            'high': stock.high,
            'low': stock.low,
            'open': stock.open
        }
        df = pd.DataFrame.from_dict(stock_data)

            # Plot stock data
        df.plot(x='date', y='close')
        plt.title(f'{sid} stock price')
        plt.savefig(file_name)
        plt.close()

            # Upload the image to Cloudinary
        image_url = upload_to_cloudinary(file_name)

        if image_url:
            os.remove(file_name)
            return image_url
        else:
            return None

    except Exception as e:
        print(f"Error generating stock trend chart: {e}")
        return None
