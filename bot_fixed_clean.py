# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
import ccxt.async_support as ccxt
import asyncio
import os
import threading
from dotenv import load_dotenv
import time
import logging
from typing import Optional, Tuple
from decimal import Decimal

# =========================
# CẤU HÌNH
# =========================
load_dotenv()
api_key = os.getenv("OKX_API_KEY")
secret = os.getenv("OKX_API_SECRET")
password = os.getenv("OKX_API_PASSWORD")

LEVERAGE = 20
MARGIN_USDT = 6
MARGIN_MODE = 'isolated'
TD_MODE = 'isolated'
IDEMPOTENCY_WINDOW_SEC = 60

SL_PCT = 0.002
TP1_PCT = 0.003
TP2_PCT = 0.005

MAX_RETRIES = 2
ORDER_VERIFY_DELAY = 1.0
MIN_BALANCE_BUFFER = 2.0

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
last_signals = {}
active_trades = {}

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
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except (ImportError, Exception):
        pass

def find_swap_market(symbol: str) -> Optional[str]:
    base = symbol.upper().replace("USDT", "")
    for m in loaded_markets:
        if loaded_markets[m].get('type') == 'swap' and m.startswith(f"{base}/USDT"):
            return m
    return None

def safe_float(value, default=0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

async def calculate_amount(price: float, market: str) -> Tuple[str, float]:
    notional = MARGIN_USDT * LEVERAGE
    raw = notional / price
    
    market_info = loaded_markets[market]
    limits = market_info.get('limits', {})
    amount_limits = limits.get('amount', {})
    cost_limits = limits.get('cost', {})
    
    min_amt = safe_float(amount_limits.get('min'), 0)
    max_amt = safe_float(amount_limits.get('max'), float('inf'))
    
    amt = max(raw, min_amt)
    if amt > max_amt:
        msg = f"⚠️ Amount {amt} vượt max {max_amt} cho {market}, giảm xuống max"
        print(msg)
        logging.warning(msg)
        amt = max_amt
    
    amount_str = exchange.amount_to_precision(market, amt)
    actual_notional = float(amount_str) * price
    actual_margin = actual_notional / LEVERAGE
    
    return amount_str, actual_margin

async def get_current_pos_info(market: str) -> Tuple[Optional[str], float]:
    try:
        positions = await exchange.fetch_positions([market])
        for pos in positions:
            if pos['symbol'] == market:
                contracts = pos.get('contracts')
                size = safe_float(contracts, 0)
                if size > 0:
                    return pos['side'], size
        return None, 0
    except Exception as e:
        msg = f"⚠️ Lỗi fetch_positions cho {market}: {e}"
        print(msg)
        logging.error(msg)
        return None, 0

async def check_balance(required_margin: float) -> bool:
    try:
        balance = await exchange.fetch_balance(params={'type': 'swap'})
        
        usdt_info = balance.get('info', {}).get('data', [])
        avail_balance = 0.0
        
        for item in usdt_info:
            if isinstance(item, dict):
                details = item.get('details', [])
                for detail in details:
                    if detail.get('ccy') == 'USDT':
                        avail_balance = safe_float(detail.get('availBal'), 0)
                        break
        
        if avail_balance == 0:
            avail_balance = safe_float(balance.get('USDT', {}).get('free'), 0)
        
        msg = f"💰 Balance check: Available USDT = {avail_balance:.2f} (cần {required_margin:.2f})"
        print(msg)
        logging.info(msg)
        
        if avail_balance >= (required_margin + MIN_BALANCE_BUFFER):
            return True
        else:
            msg = f"❌ Không đủ margin! Cần {required_margin:.2f} USDT, chỉ có {avail_balance:.2f}"
            print(msg)
            logging.warning(msg)
            beep()
            return False
    except Exception as e:
        msg = f"⚠️ Lỗi check_balance: {e}"
        print(msg)
        logging.error(msg)
        return False

async def verify_order_filled(order_id: str, market: str, expected_amount: float, max_wait: float = 3.0) -> Tuple[bool, float]:
    try:
        await asyncio.sleep(ORDER_VERIFY_DELAY)
        order = await exchange.fetch_order(order_id, market)
        
        status = order.get('status', 'unknown')
        filled = safe_float(order.get('filled'), 0)
        
        if status == 'closed' and filled >= expected_amount * 0.95:
            return True, filled
        else:
            msg = f"⚠️ Order {order_id} status={status}, filled={filled}/{expected_amount}"
            print(msg)
            logging.warning(msg)
            return False, filled
    except Exception as e:
        msg = f"⚠️ Lỗi verify order {order_id}: {e}"
        print(msg)
        logging.error(msg)
        return False, 0.0

async def close_position(market: str, pos_side: str, pos_size: float) -> bool:
    if pos_size <= 0:
        msg = f"⏩ Không có vị thế {pos_side.upper()} để đóng cho {market} (size=0)"
        print(msg)
        logging.info(msg)
        return True

    try:
        close_side = 'sell' if pos_side == 'long' else 'buy'
        close_amount_str = exchange.amount_to_precision(market, pos_size)
        
        order = await exchange.create_market_order(
            market,
            close_side,
            close_amount_str,
            params={'reduceOnly': True, 'posSide': pos_side, 'tdMode': TD_MODE}
        )
        
        order_id = order.get('id')
        if not order_id:
            msg = f"❌ Không nhận được order ID khi đóng {pos_side} {market}"
            print(msg)
            logging.error(msg)
            return False
        
        success, filled = await verify_order_filled(order_id, market, pos_size)
        
        if success:
            msg = f"✅ Đóng {pos_side.upper()} {filled} {market}"
            print(msg)
            logging.info(msg)
            beep()
            return True
        else:
            return False
            
    except Exception as e:
        error_str = str(e)
        if '51169' in error_str or "don't have any positions" in error_str or "Position does not exist" in error_str:
            msg = f"⏩ Vị thế {pos_side.upper()} đã đóng trước đó cho {market}"
            print(msg)
            logging.info(msg)
            return True
        else:
            msg = f"❌ Lỗi đóng vị thế {pos_side} {market}: {e}"
            print(msg)
            logging.error(msg)
            return False

# =========================
# MONITOR TP/SL
# =========================
async def monitor_loop():
    while True:
        try:
            markets_to_remove = []
            
            for market in list(active_trades.keys()):
                try:
                    trade_info = active_trades[market]
                    side = trade_info['side']
                    entry_price = trade_info['entry_price']
                    initial_amount = trade_info['initial_amount']
                    tp1_done = trade_info['tp1_done']
                    tp2_done = trade_info['tp2_done']

                    current_side, current_size = await get_current_pos_info(market)
                    
                    if current_size == 0 or current_side != side:
                        markets_to_remove.append(market)
                        continue

                    try:
                        ticker = await exchange.fetch_ticker(market)
                        current_price = safe_float(ticker.get('last'), 0)
                        if current_price == 0:
                            continue
                    except Exception as e:
                        msg = f"⚠️ Lỗi fetch ticker {market}: {e}"
                        logging.warning(msg)
                        continue

                    if side == 'long':
                        profit_pct = (current_price - entry_price) / entry_price
                    else:
                        profit_pct = (entry_price - current_price) / entry_price

                    if profit_pct <= -SL_PCT:
                        success = await close_position(market, side, current_size)
                        if success:
                            markets_to_remove.append(market)
                        continue

                    market_info = loaded_markets.get(market, {})
                    min_amt = safe_float(market_info.get('limits', {}).get('amount', {}).get('min'), 0)

                    if not tp1_done and profit_pct >= TP1_PCT:
                        close_size = current_size * 0.5
                        if close_size >= min_amt:
                            close_size_str = exchange.amount_to_precision(market, close_size)
                            close_side = 'sell' if side == 'long' else 'buy'
                            try:
                                order = await exchange.create_market_order(
                                    market, close_side, close_size_str,
                                    params={'reduceOnly': True, 'posSide': side, 'tdMode': TD_MODE}
                                )
                                order_id = order.get('id')
                                if order_id:
                                    success, _ = await verify_order_filled(order_id, market, float(close_size_str))
                                    if success:
                                        trade_info['tp1_done'] = True
                                        msg = f"✅ TP1: Chốt 50% {side.upper()} {close_size_str} {market} @ {current_price} (lợi nhuận {profit_pct*100:.2f}%)"
                                        print(msg)
                                        logging.info(msg)
                                        beep()
                            except Exception as e:
                                logging.error(f"Lỗi TP1 {market}: {e}")

                    if tp1_done and not tp2_done and profit_pct >= TP2_PCT:
                        close_size = min(initial_amount * 0.2, current_size)
                        if close_size >= min_amt:
                            close_size_str = exchange.amount_to_precision(market, close_size)
                            close_side = 'sell' if side == 'long' else 'buy'
                            try:
                                order = await exchange.create_market_order(
                                    market, close_side, close_size_str,
                                    params={'reduceOnly': True, 'posSide': side, 'tdMode': TD_MODE}
                                )
                                order_id = order.get('id')
                                if order_id:
                                    success, _ = await verify_order_filled(order_id, market, float(close_size_str))
                                    if success:
                                        trade_info['tp2_done'] = True
                                        msg = f"✅ TP2: Chốt thêm 20% {side.upper()} {close_size_str} {market} @ {current_price} (lợi nhuận {profit_pct*100:.2f}%)"
                                        print(msg)
                                        logging.info(msg)
                                        beep()
                            except Exception as e:
                                logging.error(f"Lỗi TP2 {market}: {e}")
                
                except Exception as e:
                    msg = f"❌ Lỗi monitor market {market}: {e}"
                    logging.error(msg)
                    continue
            
            for market in markets_to_remove:
                if market in active_trades:
                    del active_trades[market]
                    msg = f"🗑️ Cleanup active_trades cho {market}"
                    logging.info(msg)

            await asyncio.sleep(3)
        except Exception as e:
            msg = f"❌ Lỗi monitor loop: {e}"
            print(msg)
            logging.error(msg)
            await asyncio.sleep(10)

# =========================
# GIAO DỊCH
# =========================
async def trade(market: str, signal: str, price: float):
    async with position_lock:
        try:
            beep()
            msg = f"▶️ Nhận tín hiệu {signal.upper()} {market} @ {price}"
            print(msg)
            logging.info(msg)

            try:
                await exchange.set_leverage(LEVERAGE, market, {'posSide': 'long', 'mgnMode': MARGIN_MODE})
                await exchange.set_leverage(LEVERAGE, market, {'posSide': 'short', 'mgnMode': MARGIN_MODE})
            except Exception as e:
                logging.warning(f"set_leverage: {e}")

            amount_str, actual_margin = await calculate_amount(price, market)
            amount = float(amount_str)
            
            current_side, current_size = await get_current_pos_info(market)

            if current_side == signal and current_size > 0:
                msg = f"⏩ Đã có vị thế {signal.upper()} {market} (size={current_size}), bỏ qua mở mới."
                print(msg)
                logging.info(msg)
                return

            if current_side and current_side != signal and current_size > 0:
                msg = f"🔁 Đóng {current_side.upper()} cũ (size={current_size})..."
                print(msg)
                logging.info(msg)
                
                success = await close_position(market, current_side, current_size)
                if not success:
                    msg = f"⚠️ Không thể đóng {current_side.upper()}, hủy lệnh mới"
                    print(msg)
                    logging.warning(msg)
                    return
                
                await asyncio.sleep(1.5)
                
                verify_side, verify_size = await get_current_pos_info(market)
                if verify_size > 0 and verify_side == current_side:
                    msg = f"⚠️ Position {current_side.upper()} vẫn còn sau khi đóng, hủy lệnh mới"
                    print(msg)
                    logging.warning(msg)
                    return

            if not await check_balance(actual_margin):
                msg = f"⏩ Bỏ qua {signal.upper()} {market} do thiếu balance (cần {actual_margin:.2f})."
                print(msg)
                logging.warning(msg)
                return

            msg = f"✅ Vào {signal.upper()} {amount_str} {market} @ {price} (margin ~{actual_margin:.2f} USDT)"
            print(msg)
            logging.info(msg)
            
            order = await exchange.create_market_order(
                market,
                side='buy' if signal == 'long' else 'sell',
                amount=amount_str,
                params={'posSide': signal, 'tdMode': TD_MODE}
            )
            
            order_id = order.get('id')
            if not order_id:
                msg = f"❌ Không nhận được order ID cho {signal.upper()} {market}"
                print(msg)
                logging.error(msg)
                return
            
            success, filled = await verify_order_filled(order_id, market, amount)
            
            if success:
                msg = f"✅ Lệnh fill đầy đủ: {filled}/{amount}"
                print(msg)
                logging.info(msg)
                
                active_trades[market] = {
                    'side': signal,
                    'entry_price': price,
                    'initial_amount': filled,
                    'tp1_done': False,
                    'tp2_done': False
                }
            else:
                msg = f"⚠️ Lệnh fill không đầy đủ: {filled}/{amount}, không add vào active_trades"
                print(msg)
                logging.warning(msg)

        except Exception as e:
            msg = f"❌ Lỗi trade {market}: {e}"
            print(msg)
            logging.error(msg, exc_info=True)

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

    key = (symbol, signal)
    now = time.time()
    if key in last_signals and now - last_signals[key] < IDEMPOTENCY_WINDOW_SEC:
        msg = f"⏩ Bỏ qua tín hiệu trùng {signal.upper()} {symbol}"
        print(msg)
        logging.info(msg)
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
    
    main_loop.call_soon_threadsafe(lambda: asyncio.create_task(monitor_loop()))
    
    print("🌐 Bot Fixed đang chạy tại http://127.0.0.1:5000")
    print("📋 Các cải tiến:")
    print("  ✓ Fix lỗi NoneType khi check filled")
    print("  ✓ Balance check chính xác với OKX API")
    print("  ✓ Verify order sau khi đặt")
    print("  ✓ Cleanup active_trades đúng cách")
    print("  ✓ Better error handling trong monitor loop")
    print("  ✓ Check max order amount để tránh lỗi 51202")
    print("  ✓ Verify position đã đóng trước khi mở mới")
    
    app.run(host='0.0.0.0', port=5000)