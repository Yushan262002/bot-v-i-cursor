# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
import ccxt.async_support as ccxt
import asyncio
import os
import threading
from dotenv import load_dotenv
import time
import logging
import winsound

# =========================
# CẤU HÌNH
# =========================
load_dotenv()
api_key = os.getenv("OKX_API_KEY")
secret = os.getenv("OKX_API_SECRET")
password = os.getenv("OKX_API_PASSWORD")

LEVERAGE = 20
MARGIN_USDT = 6  # Điều chỉnh xuống 5-8 USDT/lệnh như yêu cầu
MARGIN_MODE = 'isolated'
TD_MODE = 'isolated'
IDEMPOTENCY_WINDOW_SEC = 60   # chống lệnh trùng trong 10 giây

SL_PCT = 0.002  # 0.2%
TP1_PCT = 0.003  # 0.3%
TP2_PCT = 0.005  # 0.5%

# =========================
# LOGGING setup
# =========================
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

app = Flask(__name__)
exchange = None
loaded_markets = {}
position_lock = asyncio.Lock()
last_signals = {}   # key=(symbol,signal), value=timestamp
active_trades = {}  # market -> {'side', 'entry_price', 'initial_amount', 'tp1_done', 'tp2_done'}

main_loop = asyncio.new_event_loop()
threading.Thread(target=lambda: asyncio.set_event_loop(main_loop) or main_loop.run_forever(), daemon=True).start()

# =========================
# KHỞI TẠO SÀN
# =========================
async def initialize_exchange():
    global exchange, loaded_markets
    exchange = ccxt.okx({
        'apiKey': api_key,
        'secret': secret,
        'password': password,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'hedgeMode': True
        }
    })
    loaded_markets = await exchange.load_markets()
    print(f"✅ Tải {len(loaded_markets)} thị trường.")
    try:
        await exchange.set_position_mode(True)
        print("✅ Đã bật Hedge Mode (long_short_mode).")
    except Exception as e:
        print(f"⚠️ Hedge mode: {e}")

# =========================
# TIỆN ÍCH
# =========================
def beep():
    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass

def find_swap_market(symbol: str) -> str | None:
    base = symbol.upper().replace("USDT", "")
    for m in loaded_markets:
        if loaded_markets[m].get('type') == 'swap' and m.startswith(f"{base}/USDT"):
            return m
    return None

async def calculate_amount(price: float, market: str) -> str:
    notional = MARGIN_USDT * LEVERAGE
    raw = notional / price
    min_amt = loaded_markets[market]['limits']['amount']['min'] or 0
    amt = max(raw, min_amt)
    return exchange.amount_to_precision(market, amt)

async def get_current_pos_info(market: str) -> tuple[str | None, float]:
    """
    Fetch current position side and size.
    Returns (side, size) if size > 0, else (None, 0)
    """
    try:
        positions = await exchange.fetch_positions([market])
        for pos in positions:
            if pos['symbol'] == market:
                size = abs(float(pos['contracts'] or 0))
                if size > 0:
                    return pos['side'], size
        return None, 0
    except Exception as e:
        print(f"⚠️ Lỗi fetch_positions: {e}")
        return None, 0

async def check_balance(required_margin: float) -> bool:
    """
    Check available USDT for margin.
    """
    try:
        balance = await exchange.fetch_balance(params={'type': 'swap'})
        usdt_free = float(balance['USDT']['free']) if 'USDT' in balance else 0
        msg = f"💰 Balance check: Free USDT = {usdt_free:.2f} (cần {required_margin:.2f})"
        print(msg); logging.info(msg)
        
        # Rough estimate used margin (sum from all positions, simplified)
        positions = await exchange.fetch_positions()
        used_margin = sum(abs(float(p['notional'])) / LEVERAGE for p in positions if float(p['contracts']) > 0 and p['symbol'].endswith('/USDT:USDT'))
        available_margin = usdt_free - used_margin
        
        if available_margin >= required_margin:
            return True
        else:
            msg = f"❌ Không đủ margin! Cần {required_margin:.2f} USDT, chỉ có {available_margin:.2f}"
            print(msg); logging.warning(msg)
            beep()  # Cảnh báo
            return False
    except Exception as e:
        print(f"⚠️ Lỗi check_balance: {e}")
        return False

async def close_position(market: str, pos_side: str, pos_size: float):
    """
    Close position only if size > 0.
    """
    if pos_size <= 0:
        msg = f"⏩ Không có vị thế {pos_side.upper()} để đóng cho {market} (size=0)"
        print(msg); logging.info(msg)
        return

    try:
        close_side = 'sell' if pos_side == 'long' else 'buy'
        close_amount_str = exchange.amount_to_precision(market, pos_size)
        order = await exchange.create_market_order(
            market,
            close_side,
            close_amount_str,
            params={'reduceOnly': True, 'posSide': pos_side, 'tdMode': TD_MODE}
        )
        # Check if order succeeded or specific error
        filled = float(order.get('filled', 0))
        if order.get('status') == 'closed' and filled >= pos_size * 0.9:
            msg = f"✅ Đóng {pos_side.upper()} {close_amount_str} {market}"
            print(msg); logging.info(msg)
            beep()
        else:
            error_msg = order.get('info', {}).get('msg', str(order))
            if '51169' in str(error_msg) or "don't have any positions" in str(error_msg):
                msg = f"⏩ Vị thế {pos_side.upper()} đã đóng trước đó cho {market}"
                print(msg); logging.info(msg)
            else:
                print(f"⚠️ Lệnh đóng partial hoặc fail: filled={filled}/{pos_size}, error={error_msg}")
                logging.warning(f"Lệnh đóng partial hoặc fail: {error_msg}")
    except Exception as e:
        error_str = str(e)
        if '51169' in error_str or "don't have any positions" in error_str:
            msg = f"⏩ Vị thế {pos_side.upper()} đã đóng trước đó cho {market}"
            print(msg); logging.info(msg)
        else:
            print(f"❌ Lỗi đóng vị thế: {e}")
            logging.error(f"Lỗi đóng vị thế: {e}")

# =========================
# MONITOR TP/SL
# =========================
async def monitor_loop():
    while True:
        try:
            for market in list(active_trades.keys()):
                trade_info = active_trades[market]
                side = trade_info['side']
                entry_price = trade_info['entry_price']
                initial_amount = trade_info['initial_amount']
                tp1_done = trade_info['tp1_done']
                tp2_done = trade_info['tp2_done']

                # Fetch position
                positions = await exchange.fetch_positions([market])
                pos = next((p for p in positions if p['symbol'] == market and p.get('side') == side), None)
                if not pos:
                    if market in active_trades:
                        del active_trades[market]
                    continue
                current_size = abs(float(pos['contracts'] or 0))
                if current_size == 0:
                    if market in active_trades:
                        del active_trades[market]
                    continue

                # Fetch current price
                ticker = await exchange.fetch_ticker(market)
                current_price = float(ticker['last'])

                # Calculate profit %
                if side == 'long':
                    profit_pct = (current_price - entry_price) / entry_price
                else:
                    profit_pct = (entry_price - current_price) / entry_price

                # SL: Close all if <= -0.2%
                if profit_pct <= -SL_PCT:
                    await close_position(market, side, current_size)
                    if market in active_trades:
                        del active_trades[market]
                    continue

                min_amt = loaded_markets[market]['limits']['amount']['min'] or 0

                # TP1: Close 50% if >= 0.3%
                if not tp1_done and profit_pct >= TP1_PCT:
                    close_size = current_size * 0.5
                    if close_size >= min_amt:
                        close_size_str = exchange.amount_to_precision(market, close_size)
                        close_side = 'sell' if side == 'long' else 'buy'
                        await exchange.create_market_order(
                            market, close_side, close_size_str,
                            params={'reduceOnly': True, 'posSide': side, 'tdMode': TD_MODE}
                        )
                        trade_info['tp1_done'] = True
                        msg = f"✅ TP1: Chốt 50% {side.upper()} {close_size_str} {market} @ {current_price} (lợi nhuận {profit_pct*100:.2f}%)"
                        print(msg); logging.info(msg)
                        beep()

                # TP2: Close additional 20% of initial if >= 0.5% and TP1 done
                if tp1_done and not tp2_done and profit_pct >= TP2_PCT:
                    close_size = min(initial_amount * 0.2, current_size)
                    if close_size >= min_amt:
                        close_size_str = exchange.amount_to_precision(market, close_size)
                        close_side = 'sell' if side == 'long' else 'buy'
                        await exchange.create_market_order(
                            market, close_side, close_size_str,
                            params={'reduceOnly': True, 'posSide': side, 'tdMode': TD_MODE}
                        )
                        trade_info['tp2_done'] = True
                        msg = f"✅ TP2: Chốt thêm 20% {side.upper()} {close_size_str} {market} @ {current_price} (lợi nhuận {profit_pct*100:.2f}%)"
                        print(msg); logging.info(msg)
                        beep()

            await asyncio.sleep(3)  # Kiểm tra mỗi 3 giây
        except Exception as e:
            print(f"❌ Lỗi monitor: {e}")
            logging.error(f"Lỗi monitor: {e}")
            await asyncio.sleep(10)

# =========================
# GIAO DỊCH
# =========================
async def trade(market: str, signal: str, price: float):
    async with position_lock:
        try:
            # beep + log
            beep()
            msg = f"▶️ Nhận tín hiệu {signal.upper()} {market} @ {price}"
            print(msg)
            logging.info(msg)

            # leverage
            try:
                await exchange.set_leverage(LEVERAGE, market, {'posSide': 'long', 'mgnMode': MARGIN_MODE})
                await exchange.set_leverage(LEVERAGE, market, {'posSide': 'short', 'mgnMode': MARGIN_MODE})
            except Exception as e:
                print(f"⚠️ set_leverage: {e}")

            amount_str = await calculate_amount(price, market)
            amount = float(amount_str)
            # Tính actual margin cần dựa trên amount thực (xử lý min_amt)
            actual_notional = amount * price
            actual_margin = actual_notional / LEVERAGE
            current_side, current_size = await get_current_pos_info(market)

            # Nếu cùng bên và size >0, bỏ qua mở mới
            if current_side == signal and current_size > 0:
                msg = f"⏩ Đã có vị thế {signal.upper()} {market} (size={current_size}), bỏ qua mở mới."
                print(msg)
                logging.info(msg)
                return

            # đóng ngược nếu có (chỉ nếu size >0)
            if current_side and current_side != signal and current_size > 0:
                msg = f"🔁 Đóng {current_side.upper()} cũ (size={current_size})..."
                print(msg); logging.info(msg)
                await close_position(market, current_side, current_size)
                await asyncio.sleep(1)
            elif current_side and current_side != signal and current_size == 0:
                msg = f"⏩ Vị thế {current_side.upper()} cũ đã đóng trước đó cho {market}"
                print(msg); logging.info(msg)

            # Kiểm tra balance TRƯỚC khi mở mới (dùng actual_margin)
            if not await check_balance(actual_margin):
                msg = f"⏩ Bỏ qua {signal.upper()} {market} do thiếu balance (actual margin cần {actual_margin:.2f})."
                print(msg); logging.warning(msg)
                return

            # mở mới (chỉ nếu không có cùng bên hoặc size=0)
            if current_side != signal or current_size == 0:
                msg = f"✅ Vào {signal.upper()} {amount_str} {market} @ {price} (margin ~{actual_margin:.2f} USDT)"
                print(msg); logging.info(msg)
                order = await exchange.create_market_order(
                    market,
                    side='buy' if signal == 'long' else 'sell',
                    amount=amount_str,
                    params={'posSide': signal, 'tdMode': TD_MODE}
                )
                # Kiểm tra order fill
                filled = float(order.get('filled', 0))
                if order.get('status') != 'closed' or filled < amount * 0.9:
                    msg = f"⚠️ Lệnh partial fill: {filled}/{amount} (error: {order.get('info', {}).get('msg', 'N/A')})"
                    print(msg); logging.warning(msg)
                else:
                    msg = f"✅ Lệnh fill đầy đủ: {filled}/{amount}"
                    print(msg); logging.info(msg)

                # Thêm vào active_trades để monitor TP/SL (chỉ nếu không có active rồi)
                if market not in active_trades or active_trades[market]['side'] != signal:
                    active_trades[market] = {
                        'side': signal,
                        'entry_price': price,
                        'initial_amount': amount,
                        'tp1_done': False,
                        'tp2_done': False
                    }

        except Exception as e:
            print(f"❌ Lỗi trade: {e}")
            logging.error(f"Lỗi trade: {e}")

# =========================
# WEBHOOK
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"JSON error: {e}"}), 400

    signal = str(data.get('signal', '')).lower()
    symbol = str(data.get('symbol', '')).upper()
    price = data.get('price')

    try:
        price = float(price)
    except:
        return jsonify({"error": "Sai giá"}), 400

    # idempotency check
    key = (symbol, signal)
    now = time.time()
    if key in last_signals and now - last_signals[key] < IDEMPOTENCY_WINDOW_SEC:
        msg = f"⏩ Bỏ qua tín hiệu trùng {signal.upper()} {symbol}"
        print(msg); logging.info(msg)
        return jsonify({"status": "skipped"}), 200
    last_signals[key] = now

    market = find_swap_market(symbol)
    if not market:
        return jsonify({"error": f"Không tìm thấy thị trường {symbol}"}), 404

    asyncio.run_coroutine_threadsafe(trade(market, signal, price), main_loop)
    return jsonify({"status": "OK"}), 200

# =========================
# MAIN
# =========================
if __name__ == '__main__':
    future = asyncio.run_coroutine_threadsafe(initialize_exchange(), main_loop)
    future.result()
    
    # Khởi động monitor loop
    main_loop.call_soon_threadsafe(lambda: asyncio.create_task(monitor_loop()))
    
    print("🌐 Bot Limited đang chạy tại http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000)