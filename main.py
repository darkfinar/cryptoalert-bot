import os
import json
import requests
import threading
import time
from flask import Flask
from telebot import TeleBot, types
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN")  # sera mis dans Render
bot = TeleBot(TOKEN)

DATA_FILE = "alerts.json"

def load_alerts():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_alerts(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

alerts = load_alerts()

price_cache = {}

def get_price(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        data = r.json()
        return data.get(coin_id, {}).get("usd")
    except:
        return None

def check_alerts():
    global price_cache
    for user_id, user_alerts in list(alerts.items()):
        for alert in user_alerts[:]:
            price = get_price(alert["coin"])
            if not price:
                continue
            price_cache[alert["coin"]] = price
            
            if (alert["direction"] == "above" and price >= alert["price"]) or \
               (alert["direction"] == "below" and price <= alert["price"]):
                bot.send_message(user_id, f"🚨 ALERTE !\n{alert['coin'].upper()} est maintenant à {price}$ !")
                user_alerts.remove(alert)
                save_alerts(alerts)
    print("Vérification terminée")

scheduler = BackgroundScheduler()
scheduler.add_job(check_alerts, "interval", minutes=5)
scheduler.start()

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Bienvenue ! Utilise /setalert pour créer une alerte.\nEx: /setalert bitcoin 65000 above")

@bot.message_handler(commands=["setalert"])
def set_alert(message):
    try:
        _, coin, price_str, direction = message.text.split()
        price = float(price_str)
        direction = direction.lower()
        if direction not in ["above", "below"]:
            raise ValueError
        
        user_id = str(message.chat.id)
        if user_id not in alerts:
            alerts[user_id] = []
        
        if len(alerts[user_id]) >= 3:
            bot.reply_to(message, "Limite gratuite atteinte (3 alertes). /premium pour illimité.")
            return
        
        new_id = len(alerts[user_id]) + 1
        alerts[user_id].append({
            "id": new_id,
            "coin": coin.lower(),
            "price": price,
            "direction": direction
        })
        save_alerts(alerts)
        bot.reply_to(message, f"Alerte #{new_id} créée : {coin.upper()} {direction} {price}$")
    except:
        bot.reply_to(message, "Format : /setalert bitcoin 65000 above")

@bot.message_handler(commands=["myalerts"])
def my_alerts(message):
    user_id = str(message.chat.id)
    if user_id not in alerts or not alerts[user_id]:
        bot.reply_to(message, "Aucune alerte.")
        return
    text = "Tes alertes :\n"
    for a in alerts[user_id]:
        text += f"#{a['id']} - {a['coin'].upper()} {a['direction']} {a['price']}$\n"
    bot.reply_to(message, text)

@app.route("/")
def home():
    return "Bot en ligne"

def run_bot():
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
