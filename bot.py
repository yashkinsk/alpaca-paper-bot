# ✅ Alpaca Paper Trading Bot — с восстановлением позиций и логами для Render

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import datetime
import time
import pandas as pd
import os
import traceback

# --- API credentials ---
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# --- Alpaca clients ---
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# --- Strategy parameters ---
symbols = ["LEN", "MSFT", "MRNA", "PFE", "NKE", "AMZN"]
portfolio_value = 100000
per_asset_balance = portfolio_value / len(symbols)

positions = {symbol: 0 for symbol in symbols}
buy_prices = {symbol: 0 for symbol in symbols}

# --- Initialize from current positions ---
account_positions = trading_client.get_all_positions()
for pos in account_positions:
    symbol = pos.symbol
    if symbol in symbols:
        positions[symbol] = int(float(pos.qty))
        buy_prices[symbol] = float(pos.avg_entry_price)
        print(f"🔄 Loaded position: {symbol} qty={positions[symbol]} @ {buy_prices[symbol]}", flush=True)

print("📦 Positions loaded:", positions, flush=True)

# --- Fetch historical bars ---
def fetch_last_price(symbol):
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(minutes=30)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=now,
            feed="iex"
        )
        bars = data_client.get_stock_bars(request).df
        if bars.empty:
            print(f"⚠️ No data for {symbol}", flush=True)
            return pd.DataFrame()
        df = bars.copy()
        df["symbol"] = symbol
        return df
    except Exception as e:
        print(f"⚠️ Error fetching data for {symbol}: {e}", flush=True)
        return pd.DataFrame()

# --- RSI calculation ---
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else 50

# --- Entry logic ---
def should_buy(df):
    if len(df) < 15:
        return False
    last = df.iloc[-1]
    vol_avg = df['volume'].rolling(12).mean().iloc[-1]
    rsi = compute_rsi(df['close'])
    return (
        last['close'] > last['open']
        and last['volume'] > 2.5 * vol_avg
        and rsi < 70
    )

# --- Exit logic ---
def should_sell(df, entry_price):
    last = df.iloc[-1]
    rsi = compute_rsi(df['close'])
    price = last['close']
    profit = (price - entry_price) / entry_price
    print(f"📊 {df['symbol'].iloc[-1]} | Price: {price:.2f} | Entry: {entry_price:.2f} | PnL: {profit*100:.2f}% | RSI: {rsi:.1f}", flush=True)
    return rsi > 75 or profit <= -0.05 or profit >= 0.02

# --- Main loop ---
print("📈 Bot started. Monitoring stocks every 60 seconds...", flush=True)

while True:
    try:
        for symbol in symbols:
            print(f"🔍 Checking {symbol}...", flush=True)

            df = fetch_last_price(symbol)
            if df.empty:
                continue

            last_price = df['close'].iloc[-1]

            # BUY
            if positions[symbol] == 0 and should_buy(df):
                qty = int(per_asset_balance // last_price)
                if qty > 0:
                    order = MarketOrderRequest(
                        symbol=symbol,
                        qty=qty,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                    trading_client.submit_order(order_data=order)
                    positions[symbol] = qty
                    buy_prices[symbol] = last_price
                    print(f"[BUY]  {symbol} qty={qty} @ {last_price:.2f}", flush=True)

            # SELL
            elif positions[symbol] > 0 and should_sell(df, buy_prices[symbol]):
                qty = positions[symbol]
                order = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                trading_client.submit_order(order_data=order)
                positions[symbol] = 0
                print(f"[SELL] {symbol} qty={qty} @ {last_price:.2f}", flush=True)

        time.sleep(60)

    except Exception as e:
        print("❌ Unexpected error:", flush=True)
        traceback.print_exc()
        time.sleep(60)
