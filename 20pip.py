import MetaTrader5 as mt5
import pandas as pd
import time
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator

# --- PARAMETERS ---
account = {
    "login": 274179714,
    "server": "Exness-MT5Trial6",
    "password": "1Minesh#"
}
SYMBOLS = ["EURUSDm", "BTCUSDm", "XAUUSDm"]
TIMEFRAME = mt5.TIMEFRAME_M15
LOOKBACK_BARS = 100
RISK_PCT = 0.23  # 23% risk per trade
TP_PIPS = 20
SL_PIPS = 15
VOLUME_MULTIPLIER = 1.0

def connect_mt5():
    if not mt5.initialize(login=account["login"], server=account["server"], password=account["password"]):
        print("MT5 init failed:", mt5.last_error())
        return False
    print("✅ MT5 connected successfully.")
    return True

def activate_symbols():
    for symbol in SYMBOLS:
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"❌ Symbol info not found: {symbol}")
            continue
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                print(f"❌ Failed to activate symbol: {symbol}")
            else:
                print(f"✅ Symbol activated: {symbol}")
        else:
            print(f"✅ Symbol already visible: {symbol}")

def fetch_candles(symbol, n_bars):
    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n_bars)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'], unit='s')
                return df
        print(f"⚠️ No data returned for {symbol}. Retrying ({attempt+1}/3)...")
        time.sleep(3)
    print(f"❌ Failed to fetch data for {symbol}. Ensure chart is open and history is loaded.")
    return None

def indicator_signals(df):
    ema = EMAIndicator(close=df['close'], window=20).ema_indicator()
    ema_signal = 1 if df['close'].iloc[-1] > ema.iloc[-1] else -1

    macd = MACD(close=df['close'])
    macd_signal = 1 if macd.macd_diff().iloc[-1] > 0 else -1

    rsi = RSIIndicator(close=df['close'], window=14).rsi()
    rsi_signal = 1 if rsi.iloc[-1] < 30 else -1 if rsi.iloc[-1] > 70 else 0

    adx_obj = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    adx_signal = 1 if adx_obj.adx().iloc[-1] > 25 else 0

    avg_vol = df['real_volume'].tail(20).mean()
    volume_spike_signal = 1 if df['real_volume'].iloc[-1] > 4 * avg_vol else 0

    return [ema_signal, macd_signal, rsi_signal, adx_signal, volume_spike_signal]

def majority_vote(signals):
    buy_votes = signals.count(1)
    sell_votes = signals.count(-1)
    if buy_votes >= 3:
        return 1
    elif sell_votes >= 3:
        return -1
    return 0

def get_account_info():
    info = mt5.account_info()
    return info.balance if info else 0

def calc_lot_size(balance, symbol, stop_pips, risk_pct):
    pip_value = 0.0001 if "JPY" not in symbol else 0.01
    stop_amount = stop_pips * pip_value
    risk_usd = balance * risk_pct
    lot = risk_usd / (stop_amount * 100000)
    return max(0.01, round(lot * VOLUME_MULTIPLIER, 2))

def open_trade(symbol, order_type, volume, price, sl, tp):
    deviation = 20
    type_ = mt5.ORDER_TYPE_BUY if order_type == "buy" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": type_,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": 123456,
        "comment": "20 Pips Challenge",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    result = mt5.order_send(request)
    print(f"📤 Order sent for {symbol}: {result.retcode}")

def has_open_position():
    positions = mt5.positions_get()
    if positions is None:
        print("⚠️ Could not retrieve positions. Check MT5 connection.")
        return False
    return len(positions) > 0

def main():
    if not connect_mt5():
        return
    activate_symbols()
    while True:
        if has_open_position():
            print("⏳ Trade already open. Waiting...")
            time.sleep(60)
            continue

        signals_summary = []
        for symbol in SYMBOLS:
            df = fetch_candles(symbol, LOOKBACK_BARS)
            if df is None or df.shape[0] < LOOKBACK_BARS:
                continue
            signals = indicator_signals(df)
            vote = majority_vote(signals)
            signals_summary.append({
                "symbol": symbol,
                "signals": signals,
                "vote": vote,
                "strength": signals.count(1) if vote == 1 else signals.count(-1)
            })

        trade_candidates = [s for s in signals_summary if abs(s["vote"]) > 0]
        if trade_candidates:
            best = sorted(trade_candidates, key=lambda x: x["strength"], reverse=True)[0]
            symbol = best["symbol"]
            vote = best["vote"]
            df = fetch_candles(symbol, LOOKBACK_BARS)
            entry_price = df['close'].iloc[-1]
            balance = get_account_info()
            lot = calc_lot_size(balance, symbol, SL_PIPS, RISK_PCT)
            pip_value = 0.0001 if "JPY" not in symbol else 0.01
            sl = entry_price - SL_PIPS * pip_value if vote == 1 else entry_price + SL_PIPS * pip_value
            tp = entry_price + TP_PIPS * pip_value if vote == 1 else entry_price - TP_PIPS * pip_value
            open_trade(symbol, "buy" if vote == 1 else "sell", lot, entry_price, sl, tp)
        else:
            print("🔍 No valid trade signals found.")
        time.sleep(60)

if __name__ == "__main__":
    main()
    mt5.shutdown()
