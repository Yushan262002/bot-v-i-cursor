# BÁO CÁO PHÂN TÍCH VÀ KHẮC PHỤC LỖI BOT TRADING

## 📊 TÓM TẮT CÁC LỖI CHÍNH

### 1. **Lỗi NoneType (Xuất hiện ~200+ lần)**
**Triệu chứng:**
```
[ERROR] Lỗi trade: float() argument must be a string or a real number, not 'NoneType'
```

**Nguyên nhân:**
- OKX API trả về `order.filled = None` thay vì `0` trong một số trường hợp
- Code gốc: `filled = float(order.get('filled', 0))` → crash khi `filled = None`

**Giải pháp:**
```python
def safe_float(value, default=0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

# Sử dụng:
filled = safe_float(order.get('filled'), 0)
```

---

### 2. **Lỗi 51008 - Thiếu Balance/Margin (~100+ lần)**
**Triệu chứng:**
```
Order failed. Your available USDT balance is insufficient, and your available margin (in USD) is too low for borrowing
```

**Nguyên nhân:**
- Logic `check_balance()` tính margin sai:
  ```python
  # SAI - Tính toán không chính xác
  used_margin = sum(abs(float(p['notional'])) / LEVERAGE for p in positions ...)
  available_margin = usdt_free - used_margin
  ```
- OKX không dùng `free balance` mà dùng `availBal` (available balance) riêng

**Giải pháp:**
```python
async def check_balance(required_margin: float) -> bool:
    balance = await exchange.fetch_balance(params={'type': 'swap'})
    
    # Lấy availBal từ OKX API
    usdt_info = balance.get('info', {}).get('data', [])
    avail_balance = 0.0
    
    for item in usdt_info:
        details = item.get('details', [])
        for detail in details:
            if detail.get('ccy') == 'USDT':
                avail_balance = safe_float(detail.get('availBal'), 0)
    
    # Thêm buffer để an toàn
    if avail_balance >= (required_margin + MIN_BALANCE_BUFFER):
        return True
```

---

### 3. **Lỗi 51202 - Vượt Max Order Amount (PEPE, DOGE...)**
**Triệu chứng:**
```
Market order amount exceeds the maximum amount. (PEPE: 12031281.3 tokens)
```

**Nguyên nhân:**
- Tokens giá thấp (PEPE ~0.00001$) → amount = 12 triệu tokens
- OKX giới hạn max order amount, code không kiểm tra

**Giải pháp:**
```python
async def calculate_amount(price: float, market: str) -> Tuple[str, float]:
    notional = MARGIN_USDT * LEVERAGE
    raw = notional / price
    
    # Lấy limits từ market info
    limits = loaded_markets[market].get('limits', {})
    amount_limits = limits.get('amount', {})
    
    min_amt = safe_float(amount_limits.get('min'), 0)
    max_amt = safe_float(amount_limits.get('max'), float('inf'))
    
    # Giới hạn amount
    amt = max(raw, min_amt)
    if amt > max_amt:
        amt = max_amt  # Giảm xuống max allowed
    
    return exchange.amount_to_precision(market, amt), actual_margin
```

---

### 4. **Partial Fill / Unknown Status (~50+ lần)**
**Triệu chứng:**
```
⚠️ Lệnh partial fill: filled=0.0/0.04, status=unknown, error=N/A
```

**Nguyên nhân:**
- Order response ngay lập tức có thể chưa có `filled` data
- Code không verify lại order sau khi đặt

**Giải pháp:**
```python
async def verify_order_filled(order_id: str, market: str, expected_amount: float) -> Tuple[bool, float]:
    # Đợi 1 giây cho order fill
    await asyncio.sleep(ORDER_VERIFY_DELAY)
    
    # Fetch lại order để verify
    order = await exchange.fetch_order(order_id, market)
    
    status = order.get('status', 'unknown')
    filled = safe_float(order.get('filled'), 0)
    
    if status == 'closed' and filled >= expected_amount * 0.95:
        return True, filled
    else:
        return False, filled

# Sử dụng khi đặt lệnh:
order = await exchange.create_market_order(...)
order_id = order.get('id')
success, filled = await verify_order_filled(order_id, market, amount)

if success:
    # Add to active_trades
else:
    # Log warning, không add
```

---

### 5. **Monitor Loop Errors (~30+ lần)**
**Triệu chứng:**
```
[ERROR] Lỗi monitor: okx GET https://www.okx.com/api/v5/market/ticker?instId=...
```

**Nguyên nhân:**
- API timeout/rate limit
- Code không handle exceptions trong loop
- Crash 1 market → crash toàn bộ monitor loop

**Giải pháp:**
```python
async def monitor_loop():
    while True:
        try:
            markets_to_remove = []
            
            for market in list(active_trades.keys()):
                try:  # ← Thêm try-catch riêng cho từng market
                    # Monitor logic...
                    
                    # Fetch ticker với error handling
                    try:
                        ticker = await exchange.fetch_ticker(market)
                        current_price = safe_float(ticker.get('last'), 0)
                        if current_price == 0:
                            continue  # Skip nếu price invalid
                    except Exception as e:
                        logging.warning(f"Lỗi fetch ticker {market}: {e}")
                        continue  # Skip market này, monitor tiếp market khác
                    
                except Exception as e:
                    logging.error(f"Lỗi monitor market {market}: {e}")
                    continue  # Không crash toàn bộ loop
            
            # Cleanup
            for market in markets_to_remove:
                if market in active_trades:
                    del active_trades[market]
            
        except Exception as e:
            logging.error(f"Lỗi monitor loop: {e}")
            await asyncio.sleep(10)  # Đợi rồi retry
```

---

### 6. **Active Trades Cleanup Sai (~20+ lần)**
**Triệu chứng:**
- Bot monitor position đã đóng
- Cố đóng position không tồn tại → lỗi 51169

**Nguyên nhân:**
- `active_trades` dict không được cleanup khi position đóng thành công
- Chỉ cleanup khi size = 0, nhưng có thể đã đóng thủ công

**Giải pháp:**
```python
async def monitor_loop():
    for market in list(active_trades.keys()):
        current_side, current_size = await get_current_pos_info(market)
        
        # Cleanup nếu:
        # 1. Size = 0 (đã đóng)
        # 2. Side khác (đã đảo chiều)
        if current_size == 0 or current_side != trade_info['side']:
            markets_to_remove.append(market)
            continue

async def close_position(...) -> bool:
    # Return True nếu đóng thành công
    # Caller có thể cleanup active_trades dựa vào return value
```

---

### 7. **Race Condition - Đóng/Mở Position**
**Triệu chứng:**
- Đóng LONG nhưng vẫn có LONG position
- Mở SHORT mới nhưng còn LONG cũ

**Nguyên nhân:**
- Close order chưa hoàn thành → đã mở order mới
- Không verify position đã đóng

**Giải pháp:**
```python
async def trade(market: str, signal: str, price: float):
    # Đóng position ngược nếu có
    if current_side and current_side != signal and current_size > 0:
        success = await close_position(market, current_side, current_size)
        if not success:
            # Không đóng được → hủy lệnh mới
            return
        
        await asyncio.sleep(1.5)  # Đợi position clear
        
        # Verify đã đóng
        verify_side, verify_size = await get_current_pos_info(market)
        if verify_size > 0 and verify_side == current_side:
            # Vẫn còn → hủy lệnh mới
            return
    
    # Bây giờ mới mở mới
```

---

## 🛠️ CÁC CẢI TIẾN THÊM

### 1. **Safe Float Helper**
- Xử lý tất cả `None` values từ API
- Tránh crash khi parse số

### 2. **Min Balance Buffer**
```python
MIN_BALANCE_BUFFER = 2.0  # USDT
# Check: available >= (required + buffer)
```
- Tránh lỗi margin do biến động nhỏ

### 3. **Order Verify Delay**
```python
ORDER_VERIFY_DELAY = 1.0  # seconds
```
- Đợi order fill rồi mới verify

### 4. **Max Retries (Future)**
```python
MAX_RETRIES = 2
# Có thể dùng để retry failed orders
```

### 5. **Beep Safe on Linux**
```python
def beep():
    try:
        import winsound
        winsound.MessageBeep(...)
    except (ImportError, Exception):
        pass  # Không crash trên Linux
```

---

## 📈 KẾT QUẢ DỰ KIẾN

| Lỗi | Trước | Sau |
|------|-------|-----|
| NoneType errors | ~200 lần | 0 |
| 51008 (thiếu margin) | ~100 lần | <5 (chỉ khi thực sự hết tiền) |
| 51202 (vượt max) | ~20 lần | 0 |
| Partial fill warnings | ~50 lần | <5 (verify tự động) |
| Monitor errors | ~30 lần | <3 (handle gracefully) |
| Race conditions | ~10 lần | 0 (verify trước khi mở) |

**Tổng lỗi giảm: ~90%**

---

## 🚀 HƯỚNG DẪN SỬ DỤNG

1. **Backup bot cũ:**
```bash
cp bot.py bot_old.py
```

2. **Thay thế bằng bot fixed:**
```bash
cp bot_fixed.py bot.py
```

3. **Test với amount nhỏ:**
- Giảm `MARGIN_USDT = 3` để test
- Monitor log xem còn lỗi không

4. **Chạy bot:**
```bash
python bot.py
```

5. **Monitor log:**
```bash
tail -f bot.log | grep -E "(ERROR|WARNING|✅)"
```

---

## ⚠️ LƯU Ý QUAN TRỌNG

1. **Không thể fix 100% lỗi:**
   - API timeout vẫn có thể xảy ra
   - Network issues không thể tránh
   - ⇒ Bot đã handle gracefully thay vì crash

2. **Balance check vẫn có thể sai nếu:**
   - Có pending orders
   - Có positions ở exchange khác
   - ⇒ Luôn giữ buffer 10-20% USDT

3. **PEPE và tokens nhỏ:**
   - Vẫn có thể bị reject nếu min > max
   - ⇒ Tránh trade tokens quá nhỏ

4. **Monitor 404 errors:**
   - Các symbol không tồn tại trên OKX
   - ⇒ Check symbol name trong webhook

---

## 📞 HỖ TRỢ

Nếu vẫn gặp lỗi, check:
1. Log file `bot.log`
2. Balance thực tế trên OKX
3. Position đang mở
4. API rate limit (max 20 requests/2s)

Good luck! 🚀