# 🪟 KHẮC PHỤC LỖI BOT TRÊN WINDOWS

## 🔍 CHẨN ĐOÁN LỖI

Bot crash ngay khi khởi động có thể do nhiều nguyên nhân. Làm theo các bước sau:

### BƯỚC 1: Chạy Debug Script

```powershell
python debug_bot.py
```

Script này sẽ kiểm tra:
- ✅ Python version
- ✅ Dependencies (flask, ccxt, python-dotenv)
- ✅ File .env và credentials
- ✅ File bot syntax
- ✅ Kết nối OKX API
- ✅ Bot log

### BƯỚC 2: Chạy Bot Trực Tiếp (Để Xem Lỗi)

```powershell
# KHÔNG chạy qua run_all.py
# Chạy trực tiếp để xem lỗi:

python bot_fixed_clean.py
```

Nếu có lỗi, bạn sẽ thấy error message chi tiết.

### BƯỚC 3: Hoặc Dùng Safe Wrapper

```powershell
python run_bot_safe.py
```

Script này sẽ catch và giải thích lỗi rõ ràng.

---

## 🛠️ CÁC LỖI THƯỜNG GẶP

### ❌ Lỗi 1: ModuleNotFoundError

**Triệu chứng:**
```
ModuleNotFoundError: No module named 'flask'
ModuleNotFoundError: No module named 'ccxt'
ModuleNotFoundError: No module named 'dotenv'
```

**Nguyên nhân:** Thiếu dependencies

**Giải pháp:**
```powershell
# Cài tất cả dependencies
pip install flask ccxt python-dotenv

# Hoặc từng cái:
pip install flask
pip install ccxt
pip install python-dotenv
```

**Verify:**
```powershell
pip list | findstr "flask ccxt dotenv"
```

---

### ❌ Lỗi 2: File .env Không Tồn Tại

**Triệu chứng:**
```
KeyError: 'OKX_API_KEY'
None value in credentials
```

**Nguyên nhân:** Thiếu file `.env` hoặc config sai

**Giải pháp:**

1. Tạo file `.env` trong thư mục bot:
```powershell
# Tạo file .env
notepad .env
```

2. Nội dung file `.env`:
```env
OKX_API_KEY=your_actual_api_key_here
OKX_API_SECRET=your_actual_secret_here
OKX_API_PASSWORD=your_actual_password_here
```

**LƯU Ý QUAN TRỌNG:**
- ⚠️ File phải tên chính xác `.env` (có dấu chấm ở đầu)
- ⚠️ Không có khoảng trắng thừa
- ⚠️ Không có dấu ngoặc kép
- ⚠️ Thay `your_actual_api_key_here` bằng key thật

**Verify:**
```powershell
# Kiểm tra file tồn tại:
dir .env

# Xem nội dung (CẨN THẬN - đừng share):
type .env
```

---

### ❌ Lỗi 3: UnicodeDecodeError / Encoding

**Triệu chứng:**
```
UnicodeDecodeError: 'charmap' codec can't decode byte...
SyntaxError: Non-UTF-8 code starting with '\xe2'...
```

**Nguyên nhân:** File bot không phải UTF-8 encoding

**Giải pháp:**

**Trong VS Code:**
1. Mở file `bot_fixed_clean.py`
2. Nhìn góc dưới bên phải, thấy encoding hiện tại
3. Click vào encoding
4. Chọn "Save with Encoding"
5. Chọn "UTF-8"
6. Save file

**Hoặc dùng PowerShell:**
```powershell
# Đọc và ghi lại với UTF-8
$content = Get-Content bot_fixed_clean.py -Raw
$Utf8NoBomEncoding = New-Object System.Text.UTF8Encoding $False
[System.IO.File]::WriteAllLines("bot_fixed_clean.py", $content, $Utf8NoBomEncoding)
```

---

### ❌ Lỗi 4: Lỗi Xác Thực OKX API

**Triệu chứng:**
```
ccxt.AuthenticationError: okx {"code":"50111","msg":"Invalid API key"}
ccxt.AuthenticationError: okx {"code":"50113","msg":"Invalid sign"}
```

**Nguyên nhân:** 
- API key sai
- Secret sai
- Passphrase sai
- API key đã bị vô hiệu hóa

**Giải pháp:**

1. **Kiểm tra API credentials:**
   - Đăng nhập OKX
   - Vào Account > API Management
   - Kiểm tra API key còn active không

2. **Tạo lại API key:**
   - Delete API key cũ
   - Tạo API key mới
   - **QUAN TRỌNG:** Cấp quyền **Trade**
   - Copy API Key, Secret, Passphrase
   - Update vào `.env`

3. **Kiểm tra IP whitelist:**
   - Nếu bật IP whitelist, phải add IP hiện tại
   - Hoặc tắt IP whitelist (không khuyến khích)

---

### ❌ Lỗi 5: Bot Crash Không Có Error Message

**Triệu chứng:**
Bot chạy rồi tắt ngay, không có error.

**Nguyên nhân:** 
- Exception bị silent
- `run_all.py` không catch error

**Giải pháp:**

1. **KHÔNG chạy qua `run_all.py`**, chạy trực tiếp:
```powershell
python bot_fixed_clean.py
```

2. Hoặc dùng safe wrapper:
```powershell
python run_bot_safe.py
```

3. Kiểm tra bot.log:
```powershell
type bot.log
```

---

### ❌ Lỗi 6: Port 5000 Đã Được Sử Dụng

**Triệu chứng:**
```
OSError: [WinError 10048] Only one usage of each socket address...
```

**Nguyên nhân:** Port 5000 đã được process khác dùng

**Giải pháp:**

**Tìm process đang dùng port 5000:**
```powershell
netstat -ano | findstr :5000
```

**Kill process:**
```powershell
# Giả sử PID = 12345
taskkill /F /PID 12345
```

**Hoặc đổi port trong bot:**
```python
# Trong bot_fixed_clean.py, dòng cuối:
app.run(host='0.0.0.0', port=5001)  # Đổi thành 5001
```

---

## 📋 CHECKLIST TRƯỚC KHI CHẠY BOT

- [ ] Python 3.8+ đã cài
- [ ] Dependencies đã cài (flask, ccxt, python-dotenv)
- [ ] File `.env` tồn tại
- [ ] Credentials trong `.env` đúng
- [ ] File bot là UTF-8 encoding
- [ ] API key có quyền Trade
- [ ] Port 5000 không bị chiếm
- [ ] Internet kết nối tốt

---

## 🚀 CÁC LỆNH HỮU ÍCH

### Kiểm Tra Python
```powershell
python --version
# Cần: Python 3.8 trở lên
```

### Kiểm Tra Dependencies
```powershell
pip list
pip show flask
pip show ccxt
pip show python-dotenv
```

### Cài Dependencies
```powershell
pip install -r requirements.txt

# Hoặc manual:
pip install flask ccxt python-dotenv
```

### Chạy Bot
```powershell
# Debug trước:
python debug_bot.py

# Chạy với safe wrapper:
python run_bot_safe.py

# Hoặc trực tiếp:
python bot_fixed_clean.py
```

### Xem Log
```powershell
# Xem toàn bộ log:
type bot.log

# Xem 50 dòng cuối:
Get-Content bot.log -Tail 50

# Xem realtime:
Get-Content bot.log -Wait -Tail 20
```

---

## 🆘 VẪN KHÔNG ĐƯỢC?

### Bước 1: Chạy Debug
```powershell
python debug_bot.py
```

### Bước 2: Copy Output Debug Script

Gửi cho tôi output của debug script (che API credentials).

### Bước 3: Chạy Bot Với Output Đầy Đủ

```powershell
python bot_fixed_clean.py 2>&1 | Tee-Object -FilePath output.txt
```

Gửi file `output.txt` để tôi xem.

### Bước 4: Kiểm Tra Log Chi Tiết

```powershell
type bot.log
```

---

## 📝 TẠO FILE requirements.txt

Nếu chưa có, tạo file `requirements.txt`:

```txt
flask>=2.0.0
ccxt>=4.0.0
python-dotenv>=0.19.0
```

Cài bằng:
```powershell
pip install -r requirements.txt
```

---

## 🔧 TROUBLESHOOTING NÂNG CAO

### Test Kết Nối OKX Riêng

Tạo file `test_okx.py`:
```python
import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    exchange = ccxt.okx({
        'apiKey': os.getenv('OKX_API_KEY'),
        'secret': os.getenv('OKX_API_SECRET'),
        'password': os.getenv('OKX_API_PASSWORD'),
    })
    
    try:
        balance = await exchange.fetch_balance()
        print("✅ Kết nối thành công!")
        print(f"USDT Balance: {balance.get('USDT', {}).get('free', 0)}")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
    finally:
        await exchange.close()

asyncio.run(test())
```

Chạy:
```powershell
python test_okx.py
```

---

Good luck! 🚀