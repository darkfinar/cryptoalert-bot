import os
import json
import requests
import threading
import time
from flask import Flask, request
from telebot import TeleBot, types
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN")
bot = TeleBot(TOKEN)

DATA_FILE = "alerts.json"
USERS_PREMIUM = "premium_users.json"

def load_data(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_data(data, file):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

alerts = load_data(DATA_FILE)
premium_users = load_data(USERS_PREMIUM)

price_cache = {}

def get_price(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        return r.json().get(coin_id, {}).get("usd")
    except:
        return None

def check_alerts():
    for user_id, user_alerts in list(alerts.items()):
        is_premium = int(user_id) in premium_users and premium_users[int(user_id)] > time.time()
        for alert in user_alerts[:]:
            price = get_price(alert["coin"])
            if not price: continue
            price_cache[alert["coin"]] = price

            if (alert["direction"] == "above" and price >= alert["price"]) or \
               (alert["direction"] == "below" and price <= alert["price"]):
                bot.send_message(user_id, f"🚨 ALERTE ! {alert['coin'].upper()} à {price}$ maintenant !")
                user_alerts.remove(alert)
    save_data(alerts, DATA_FILE)
    print("Check alerts done")

scheduler = BackgroundScheduler()
scheduler.add_job(check_alerts, "interval", minutes=5)
scheduler.start()

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Bienvenue ! /setalert bitcoin 65000 above\n/myalerts\n/premium")

@bot.message_handler(commands=["setalert"])
def set_alert(message):
    try:
        _, coin, price_str, direction = message.text.split(maxsplit=3)
        price = float(price_str)
        direction = direction.lower().strip()
        if direction not in ["above", "below"]:
            raise ValueError

        user_id = str(message.from_user.id)
        if user_id not in alerts:
            alerts[user_id] = []

        is_premium = int(message.from_user.id) in premium_users and premium_users[int(message.from_user.id)] > time.time()

        if len(alerts[user_id]) >= 3 and not is_premium:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Passer Premium ⭐ (500 Stars)", callback_data="buy_premium"))
            bot.reply_to(message, "Limite gratuite atteinte (3 alertes).", reply_markup=markup)
            return

        new_id = len(alerts[user_id]) + 1
        alerts[user_id].append({"id": new_id, "coin": coin.lower(), "price": price, "direction": direction})
        save_data(alerts, DATA_FILE)
        bot.reply_to(message, f"Alerte #{new_id} créée.")
    except:
        bot.reply_to(message, "Exemple : /setalert bitcoin 65000 above")

@bot.message_handler(commands=["myalerts"])
def my_alerts(message):
    user_id = str(message.from_user.id)
    if user_id not in alerts or not alerts[user_id]:
        bot.reply_to(message, "Aucune alerte.")
        return
    text = "Alertes :\n" + "\n".join(f"#{a['id']} - {a['coin'].upper()} {a['direction']} {a['price']}$" for a in alerts[user_id])
    bot.reply_to(message, text)

@bot.callback_query_handler(func=lambda call: call.data == "buy_premium")
def buy_premium(call):
    bot.answer_callback_query(call.id, text="Ouverture facture 500 Stars...", show_alert=False)

    prices = [types.LabeledPrice(label="Premium 30 jours", amount=500)]

    bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Premium CryptoAlertBot",
        description="Alertes illimitées + priorité",
        payload="premium_month_v1",
        currency="XTR",
        prices=prices,
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False
    )

@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True, error_message=None)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    if "premium_month" in payload:
        expiration = int(time.time()) + 30 * 86400
        premium_users[user_id] = expiration
        save_data(premium_users, USERS_PREMIUM)
        bot.send_message(message.chat.id, "✅ Premium activé 30 jours ! 🚀")
    else:
        bot.send_message(message.chat.id, "Paiement OK, merci.")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return "OK"

def run_bot():
    bot.remove_webhook()
    bot.infinity_polling(allowed_updates=types.Update.ALL_TYPES)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
