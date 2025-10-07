# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
import ccxt.async_support as ccxt
import asyncio
import os
import threading
from dotenv import load_dotenv
import time
import logging
try:
    import winsound  # type: ignore
except Exception:
    winsound = None

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
IDEMPOTENCY_WINDOW_SEC = 60   # chống lệnh trùng trong 60 giây

# Mức SL/TP mới: SL 2%, TP1 3% (đóng 50%), TP2 5% (đóng thêm 20%)
SL_PCT = 0.02
TP1_PCT = 0.03
TP2_PCT = 0.05

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
# Sẽ khởi tạo lock sau khi event loop sẵn sàng
position_lock = None
last_signals = {}   # key=(symbol,signal), value=timestamp
active_trades = {}  # market -> {'side', 'entry_price', 'initial_amount', 'tp1_done', 'tp2_done'}

main_loop = None

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

async def boot():
    global position_lock
    await initialize_exchange()
    # Lock phải được tạo sau khi event loop đã set
    position_lock = asyncio.Lock()
    # Khởi động monitor loop
    asyncio.create_task(monitor_loop())

# =========================
# TIỆN ÍCH
# =========================
def beep():
    try:
        if winsound is not None:
            winsound.MessageBeep(getattr(winsound, 'MB_ICONEXCLAMATION', 0))
        else:
            # Fallback bell trên *nix
            print("\a", end='', flush=True)
    except Exception:
        pass

def to_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

import re

def find_swap_market(symbol: str) -> str | None:
    s = str(symbol).upper()
    # Lấy base: chỉ ký tự A-Z, bỏ USDT
    base = re.sub(r'[^A-Z]', '', s)
    base = base.replace('USDT', '')
    # Alias thường gặp
    aliases = {
        'ASTER': 'ASTR',
    }
    base = aliases.get(base, base)

    # Ưu tiên dạng BASE/USDT:USDT của OKX swap
    for m, meta in loaded_markets.items():
        if meta.get('type') == 'swap' and m.startswith(f"{base}/USDT"):
            return m
    return None

def parse_okx_amount_limits(market_meta):
    limits = (market_meta.get('limits') or {})
    amount_limits = (limits.get('amount') or {})
    min_amt = to_float(amount_limits.get('min')) or 0.0
    max_amt = to_float(amount_limits.get('max'), float('inf'))
    info = (market_meta.get('info') or {})
    max_mkt_sz = to_float(info.get('maxMktSz'))
    min_sz = to_float(info.get('minSz'))
    lot_sz = to_float(info.get('lotSz'))
    if max_mkt_sz:
        max_amt = min(max_amt, max_mkt_sz)
    if min_sz:
        min_amt = max(min_amt, min_sz)
    return min_amt, max_amt, (lot_sz or 0.0)

async def calculate_amount(price: float, market: str) -> str:
    import math
    notional = MARGIN_USDT * LEVERAGE
    meta = loaded_markets[market]
    min_amt, max_amt, lot_sz = parse_okx_amount_limits(meta)
    raw = max(min(notional / price, max_amt), min_amt)
    if lot_sz and lot_sz > 0:
        # Snap theo lot size
        raw = max(min_amt, math.floor(raw / lot_sz) * lot_sz)
    return exchange.amount_to_precision(market, raw)

async def get_current_pos_info(market: str) -> tuple[str | None, float]:
    """
    Fetch current position side and size.
    Returns (side, size) if size > 0, else (None, 0)
    """
    try:
        positions = await exchange.fetch_positions([market])
        for pos in positions:
            if pos['symbol'] == market:
                size = abs(to_float(pos.get('contracts')))
                if size > 0:
                    return pos.get('side'), size
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
        usdt_obj = balance.get('USDT') or {}
        usdt_free = to_float(usdt_obj.get('free'))
        msg = f"💰 Balance check: Free USDT = {usdt_free:.2f} (cần {required_margin:.2f})"
        print(msg); logging.info(msg)
        return usdt_free >= required_margin
    except Exception as e:
        print(f"⚠️ Lỗi check_balance: {e}")
        logging.error(f"⚠️ Lỗi check_balance: {e}")
        return False

async def confirm_fill(order, market: str, expected_amount: float, retries: int = 4, delay: float = 0.25):
    order_id = order.get('id') or ((order.get('info') or {}).get('ordId'))
    status = order.get('status')
    filled = to_float(order.get('filled'))
    if (status == 'closed') or (filled >= expected_amount * 0.9):
        return filled, (status or 'closed')
    for _ in range(retries):
        await asyncio.sleep(delay)
        try:
            fresh = await exchange.fetch_order(order_id, market)
            status = fresh.get('status') or status
            filled = max(filled, to_float(fresh.get('filled')))
            if (status == 'closed') or (filled >= expected_amount * 0.9):
                break
        except Exception as _:
            await asyncio.sleep(delay)
    return filled, (status or 'unknown')

async def place_market_with_backoff(market: str, side: str, amount_float: float, params: dict, max_attempts: int = 5):
    meta = loaded_markets[market]
    min_amt, _, _ = parse_okx_amount_limits(meta)
    amt = amount_float
    last_exc = None
    for _ in range(max_attempts):
        try:
            amt_str = exchange.amount_to_precision(market, amt)
            return await exchange.create_market_order(market, side, amt_str, params), amt
        except Exception as e:
            es = str(e)
            last_exc = e
            # Tự giảm size nếu dính hạn mức hoặc thiếu margin
            if '51202' in es:      # Market order amount exceeds the maximum amount
                amt *= 0.5
            elif '51008' in es:    # Available balance / margin insufficient
                amt *= 0.7
            else:
                break
            if amt < max(min_amt, 1e-18):
                break
    if last_exc:
        raise last_exc
    raise RuntimeError('place_market_with_backoff failed')

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
        order, used_amt = await place_market_with_backoff(
            market,
            close_side,
            amount_float=pos_size,
            params={'reduceOnly': True, 'posSide': pos_side, 'tdMode': TD_MODE},
        )
        filled, status = await confirm_fill(order, market, expected_amount=used_amt)
        if status == 'closed' and filled >= pos_size * 0.9:
            msg = f"✅ Đóng {pos_side.upper()} {exchange.amount_to_precision(market, pos_size)} {market}"
            print(msg); logging.info(msg)
            beep()
        else:
            error_msg = (order.get('info') or {}).get('msg', str(order))
            if '51169' in str(error_msg) or "don't have any positions" in str(error_msg):
                msg = f"⏩ Vị thế {pos_side.upper()} đã đóng trước đó cho {market}"
                print(msg); logging.info(msg)
            else:
                print(f"⚠️ Lệnh đóng partial hoặc fail: filled={filled}/{pos_size}, status={status}, error={error_msg}")
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
    backoff = 1.0
    while True:
        try:
            # Lấy tất cả positions 1 lần/vòng
            positions = await exchange.fetch_positions()
            by_key = {(p.get('symbol'), p.get('side')): p for p in positions}

            for market in list(active_trades.keys()):
                trade_info = active_trades[market]
                side = trade_info['side']
                entry_price = to_float(trade_info['entry_price'])
                initial_amount = to_float(trade_info['initial_amount'])
                tp1_done = trade_info['tp1_done']
                tp2_done = trade_info['tp2_done']

                pos = by_key.get((market, side))
                if not pos:
                    # Không còn position bên này -> dừng monitor
                    active_trades.pop(market, None)
                    continue

                current_size = abs(to_float(pos.get('contracts')))
                if current_size <= 0:
                    active_trades.pop(market, None)
                    continue

                info = pos.get('info') or {}
                mark_px = to_float(info.get('markPx'))
                current_price = mark_px
                if not current_price:
                    try:
                        ticker = await exchange.fetch_ticker(market)
                        current_price = to_float(ticker.get('last'))
                    except Exception:
                        current_price = 0.0
                if not current_price or not entry_price:
                    # Không đủ dữ liệu giá -> bỏ qua vòng này
                    continue

                # Tính % lời/lỗ theo mark price nếu có
                if side == 'long':
                    profit_pct = (current_price - entry_price) / entry_price
                else:
                    profit_pct = (entry_price - current_price) / entry_price

                # SL: đóng hết nếu lỗ >= 2%
                if profit_pct <= -SL_PCT:
                    await close_position(market, side, current_size)
                    active_trades.pop(market, None)
                    continue

                # TP theo phần trăm của initial_amount
                min_amt = (loaded_markets[market].get('limits') or {}).get('amount', {}).get('min') or 0
                min_amt = to_float(min_amt)

                # TP1: 3% -> đóng 50% initial
                if not tp1_done and profit_pct >= TP1_PCT:
                    close_size = min(initial_amount * 0.5, current_size)
                    if close_size >= min_amt and close_size > 0:
                        side_close = 'sell' if side == 'long' else 'buy'
                        order, used = await place_market_with_backoff(
                            market, side_close, close_size, params={'reduceOnly': True, 'posSide': side, 'tdMode': TD_MODE}
                        )
                        await confirm_fill(order, market, expected_amount=used)
                        trade_info['tp1_done'] = True
                        msg = f"✅ TP1: Chốt 50% {side.upper()} {exchange.amount_to_precision(market, close_size)} {market} @ {current_price} (lợi nhuận {profit_pct*100:.2f}%)"
                        print(msg); logging.info(msg)
                        beep()

                # TP2: 5% -> đóng thêm 20% initial
                if tp1_done and not tp2_done and profit_pct >= TP2_PCT:
                    close_size = min(initial_amount * 0.2, current_size)
                    if close_size >= min_amt and close_size > 0:
                        side_close = 'sell' if side == 'long' else 'buy'
                        order, used = await place_market_with_backoff(
                            market, side_close, close_size, params={'reduceOnly': True, 'posSide': side, 'tdMode': TD_MODE}
                        )
                        await confirm_fill(order, market, expected_amount=used)
                        trade_info['tp2_done'] = True
                        msg = f"✅ TP2: Chốt thêm 20% {side.upper()} {exchange.amount_to_precision(market, close_size)} {market} @ {current_price} (lợi nhuận {profit_pct*100:.2f}%)"
                        print(msg); logging.info(msg)
                        beep()

            await asyncio.sleep(8)
            backoff = 1.0
        except Exception as e:
            print(f"❌ Lỗi monitor: {e}")
            logging.error(f"Lỗi monitor: {e}")
            await asyncio.sleep(min(30, backoff))
            backoff *= 1.8

# =========================
# GIAO DỊCH
# =========================
async def trade(market: str, signal: str, price: float):
    # Phòng khi lock chưa tạo vì lỗi khởi động, vẫn giữ an toàn bằng lock cục bộ
    lock = position_lock or asyncio.Lock()
    async with lock:
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
            amount = to_float(amount_str)
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
                order, used_amt = await place_market_with_backoff(
                    market,
                    side='buy' if signal == 'long' else 'sell',
                    amount_float=amount,
                    params={'posSide': signal, 'tdMode': TD_MODE}
                )
                filled, status = await confirm_fill(order, market, expected_amount=used_amt)
                if status != 'closed' or filled < amount * 0.9:
                    msg = f"⚠️ Lệnh partial/unknown: {filled}/{amount} (status={status}, error: {(order.get('info') or {}).get('msg', 'N/A')})"
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
    # Tạo event loop nền
    main_loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: asyncio.set_event_loop(main_loop) or main_loop.run_forever(), daemon=True).start()

    # Khởi động exchange + lock + monitor
    future = asyncio.run_coroutine_threadsafe(boot(), main_loop)
    future.result()

    print("🌐 Bot Limited đang chạy tại http://127.0.0.1:5000")
    # Tắt reloader và threading để tránh tạo multi-process / multi-thread ngoài ý muốn
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=False)