import requests
import time
import json
import os

PINNACLE_API_URL = "https://api.odds-api.io/v1/odds/updated"
ROOBET_API_URL = "https://api.odds-api.io/v1/odds/"
SPORT = "Football"
BOOKMAKER_PINNACLE = "Pinnacle"
BOOKMAKER_ROOBET = "Roobet"
API_KEY = "1eee82270ec58445c539554165bdaa5d160c5e484b7afaa395d441f790844be0"
ALL_ODDS_FILE = "all_odds.json"
ARBITRAGE_LOG_FILE = "arbitrage_log.txt"
ARBITRAGE_THRESHOLD = 0.30  # 1%

def send_telegram_message(message):
    bot_token = "7264851713:AAHTZkKbxuURTFkXdQmsGh_MzlI6tPGQ_vI"
    chat_id = "8017579888"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Greška pri slanju Telegram poruke: {e}")

def get_since_timestamp():
    return int(time.time()) - 2

def build_pinnacle_url(since):
    return f"{PINNACLE_API_URL}?sport={SPORT}&bookmaker={BOOKMAKER_PINNACLE}&since={since}&apiKey={API_KEY}"

def build_roobet_url(event_id):
    return f"{ROOBET_API_URL}?eventId={event_id}&bookmakers={BOOKMAKER_ROOBET}&apiKey={API_KEY}"

def load_all_odds():
    if os.path.exists(ALL_ODDS_FILE):
        with open(ALL_ODDS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_all_odds(odds_data):
    with open(ALL_ODDS_FILE, "w") as f:
        json.dump(odds_data, f)

def log_arbitrage(event_id, changes):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(ARBITRAGE_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] Arbitraža za meč {event_id}:\n")
        for change in changes:
            f.write(f"   → {change}\n")
        f.write("\n")

def parse_markets(bookmakers, target):
    for market in bookmakers.get(target, []):
        name = market.get("name")
        odds = market.get("odds")
        if name and odds:
            yield name, odds

def compare_arbitrage(pinnacle_odds, roobet_odds, match_id):
    changes = []

    for market_name, pinnacle_market_odds in parse_markets(pinnacle_odds, BOOKMAKER_PINNACLE):
        for roobet_market_name, roobet_market_odds in parse_markets(roobet_odds, BOOKMAKER_ROOBET):
            if market_name != roobet_market_name:
                continue

            if isinstance(pinnacle_market_odds, dict) and isinstance(roobet_market_odds, dict):
                for key in pinnacle_market_odds:
                    if key in roobet_market_odds:
                        try:
                            pin_val = float(pinnacle_market_odds[key])
                            roo_val = float(roobet_market_odds[key])
                            if pin_val == 0:
                                continue
                            diff = abs(pin_val - roo_val) / pin_val
                            if diff >= ARBITRAGE_THRESHOLD:
                                changes.append(f"[{market_name}] {key}: Pinnacle={pin_val} vs Roobet={roo_val} ({round(diff*100,2)}%)")
                        except ValueError:
                            continue

            elif isinstance(pinnacle_market_odds, list) and isinstance(roobet_market_odds, list):
                for p_line in pinnacle_market_odds:
                    for r_line in roobet_market_odds:
                        try:
                            if float(p_line.get("hdp", -999)) == float(r_line.get("hdp", -999)):
                                for side in ["home", "away", "over", "under"]:
                                    if side in p_line and side in r_line:
                                        try:
                                            p_val = float(p_line[side])
                                            r_val = float(r_line[side])
                                            if p_val == 0:
                                                continue
                                            diff = abs(p_val - r_val) / p_val
                                            if diff >= ARBITRAGE_THRESHOLD:
                                                changes.append(f"[{market_name}] hdp {p_line['hdp']} {side}: Pinnacle={p_val} vs Roobet={r_val} ({round(diff*100,2)}%)")
                                        except ValueError:
                                            continue
                        except:
                            continue
    return changes

def main_loop():
    all_odds = load_all_odds()

    while True:
        try:
            since = get_since_timestamp()
            url = build_pinnacle_url(since)
            response = requests.get(url)

            if response.status_code == 200:
                response_json = response.json()
                new_data = response_json if isinstance(response_json, list) else response_json.get("data", [])

                if not new_data:
                    print(f" -")
                else:
                    print(f" -")

                for event in new_data:
                    event_id = str(event.get("id"))
                    pinnacle_bookmakers = event.get("bookmakers", {})

                    roobet_url = build_roobet_url(event_id)
                    roobet_response = requests.get(roobet_url)

                    if roobet_response.status_code == 200:
                        roobet_json = roobet_response.json()

                        roobet_event = None
                        roobet_data = roobet_json.get("data", None)

                        if isinstance(roobet_data, list) and len(roobet_data) > 0:
                            roobet_event = roobet_data[0]
                        elif isinstance(roobet_json, dict) and "bookmakers" in roobet_json:
                            roobet_event = roobet_json
                        else:
                            print(f"⚠️ Roobet nema validnih podataka za {event_id}")
                            continue

                        roobet_bookmakers = roobet_event.get("bookmakers", {})

                        arbitrage_diffs = compare_arbitrage(
                            {"Pinnacle": pinnacle_bookmakers.get("Pinnacle", [])},
                            {"Roobet": roobet_bookmakers.get("Roobet", [])},
                            event_id
                        )

                        if arbitrage_diffs:
                            print(f"🔀 ARBITRAŽA za meč {event_id}:")
                            for diff in arbitrage_diffs:
                                print("   →", diff)
                            log_arbitrage(event_id, arbitrage_diffs)
                            message = f"*Arbitraža otkrivena za meč {event_id}:*\n" + "\n".join(f"→ {d}" for d in arbitrage_diffs)
                            send_telegram_message(message)
                        else:
                            print(f" +")

                    else:
                        print(f"⚠️ Roobet API greška za event {event_id}: {roobet_response.status_code}")

                    for market_name, odds in parse_markets(pinnacle_bookmakers, BOOKMAKER_PINNACLE):
                        if market_name == "ML":
                            if event_id not in all_odds:
                                all_odds[event_id] = odds
                            else:
                                all_odds[event_id].update(odds)

                save_all_odds(all_odds)
            else:
                print(f"⚠️ HTTP greška kod Pinnacle API: {response.status_code}")

        except Exception as e:
            print("❌ Greška:", e)

        time.sleep(2)

if __name__ == "__main__":
    main_loop()
