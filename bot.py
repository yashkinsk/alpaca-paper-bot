# ✅ Alpaca Paper Trading Strategy Bot for 6 Stocks (Fixed for 'symbol' and IEX feed)

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import datetime
import time
import pandas as pd

# API credentials
import os

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# Alpaca clients
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# Selected stocks and capital per asset
symbols = ["LEN", "MSFT", "MRNA", "PFE", "NKE", "AMZN"]
per_asset_balance = 100000 / len(symbols)

# Track current positions and entry prices
positions = {symbol: 0 for symbol in symbols}
buy_prices = {symbol: 0 for symbol in symbols}

# Fetch recent minute-level bars for a given stock
def fetch_last_price(symbol):
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(minutes=30)
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=now,
        feed="iex"  # ✅ FREE data source
    )
    bars = data_client.get_stock_bars(request).df
    if bars.empty:
        return pd.DataFrame()
    df = bars.copy()
    df['symbol'] = symbol  # ✅ Add symbol column manually
    return df

# Entry signal based on RSI + volume spike + green candle
def should_buy(df):
    if len(df) < 15:
        return False
    last = df.iloc[-1]
    vol_avg = df['volume'].rolling(12).mean().iloc[-1]
    rsi = compute_rsi(df['close'])
    return (last['close'] > last['open']) and (last['volume'] > 2.5 * vol_avg) and (rsi < 70)

# Exit signal based on overbought RSI, loss or profit targets
def should_sell(df, entry_price):
    last = df.iloc[-1]
    rsi = compute_rsi(df['close'])
    price = last['close']
    profit = (price - entry_price) / entry_price
    return rsi > 75 or profit <= -0.05 or profit >= 0.02

# RSI calculation
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# Main trading loop — runs every 60 seconds
print("📈 Bot started. Monitoring stocks every 60 seconds...")
while True:
    for symbol in symbols:
        df = fetch_last_price(symbol)
        if df.empty:
            continue

        last_price = df['close'].iloc[-1]

        if positions[symbol] == 0 and should_buy(df):
            qty = int(per_asset_balance // last_price)
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )
            trading_client.submit_order(order_data=order)
            positions[symbol] = qty
            buy_prices[symbol] = last_price
            print(f"[BUY] {symbol} at {last_price:.2f}")

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
            print(f"[SELL] {symbol} at {last_price:.2f}")

    time.sleep(60)
