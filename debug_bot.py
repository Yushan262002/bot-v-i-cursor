# -*- coding: utf-8 -*-
"""
Debug script để tìm lỗi khi bot crash
Chạy: python debug_bot.py
"""

import sys
import os

print("=" * 60)
print("BOT DEBUG - KIỂM TRA LỖI")
print("=" * 60)
print()

# 1. Check Python version
print("[1/7] Kiểm tra Python version...")
print(f"   Python {sys.version}")
if sys.version_info < (3, 8):
    print("   ❌ CẢNH BÁO: Cần Python 3.8 trở lên")
else:
    print("   ✅ OK")
print()

# 2. Check dependencies
print("[2/7] Kiểm tra dependencies...")
required_packages = {
    'flask': 'Flask',
    'ccxt': 'ccxt',
    'dotenv': 'python-dotenv',
    'asyncio': 'asyncio (built-in)'
}

missing = []
for module, package in required_packages.items():
    try:
        if module == 'dotenv':
            __import__('dotenv')
        else:
            __import__(module)
        print(f"   ✅ {package}")
    except ImportError:
        print(f"   ❌ {package} - THIẾU!")
        missing.append(package)

if missing:
    print()
    print("   Cài đặt các package thiếu:")
    print(f"   pip install {' '.join(missing)}")
    print()
else:
    print("   ✅ Tất cả dependencies OK")
print()

# 3. Check .env file
print("[3/7] Kiểm tra file .env...")
if os.path.exists('.env'):
    print("   ✅ File .env tồn tại")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("OKX_API_KEY")
    secret = os.getenv("OKX_API_SECRET")
    password = os.getenv("OKX_API_PASSWORD")
    
    if api_key and secret and password:
        print(f"   ✅ OKX_API_KEY: {api_key[:10]}...")
        print(f"   ✅ OKX_API_SECRET: {secret[:10]}...")
        print(f"   ✅ OKX_API_PASSWORD: ***")
    else:
        print("   ❌ Thiếu credentials trong .env")
        print("   Cần có:")
        print("     OKX_API_KEY=your_key")
        print("     OKX_API_SECRET=your_secret")
        print("     OKX_API_PASSWORD=your_password")
else:
    print("   ❌ File .env KHÔNG TỒN TẠI!")
    print("   Tạo file .env với nội dung:")
    print("     OKX_API_KEY=your_key")
    print("     OKX_API_SECRET=your_secret")
    print("     OKX_API_PASSWORD=your_password")
print()

# 4. Check bot file
print("[4/7] Kiểm tra file bot...")
bot_files = ['bot.py', 'bot_fixed.py', 'bot_fixed_clean.py']
found_bot = None

for bf in bot_files:
    if os.path.exists(bf):
        print(f"   ✅ Tìm thấy {bf}")
        found_bot = bf
        break

if not found_bot:
    print("   ❌ Không tìm thấy file bot.py")
else:
    # Check encoding
    try:
        with open(found_bot, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"   ✅ File {found_bot} đọc được (UTF-8)")
        
        # Check syntax
        try:
            compile(content, found_bot, 'exec')
            print(f"   ✅ Syntax OK")
        except SyntaxError as e:
            print(f"   ❌ Lỗi syntax: {e}")
            print(f"      Dòng {e.lineno}: {e.text}")
    except Exception as e:
        print(f"   ❌ Lỗi đọc file: {e}")
print()

# 5. Test import bot
print("[5/7] Thử import bot...")
if found_bot and not missing:
    try:
        # Remove .py extension
        module_name = found_bot.replace('.py', '')
        
        # Try import
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_name, found_bot)
        if spec and spec.loader:
            print("   ✅ Import spec OK")
        else:
            print("   ❌ Không thể tạo import spec")
    except Exception as e:
        print(f"   ❌ Lỗi import: {e}")
        import traceback
        print()
        print("   Chi tiết lỗi:")
        traceback.print_exc()
else:
    print("   ⏩ Bỏ qua (thiếu bot file hoặc dependencies)")
print()

# 6. Test OKX connection
print("[6/7] Test kết nối OKX API...")
if not missing and api_key and secret and password:
    try:
        import asyncio
        import ccxt.async_support as ccxt
        
        async def test_okx():
            exchange = ccxt.okx({
                'apiKey': api_key,
                'secret': secret,
                'password': password,
                'enableRateLimit': True,
            })
            
            try:
                # Test fetch balance
                balance = await exchange.fetch_balance()
                print("   ✅ Kết nối OKX thành công")
                
                usdt_balance = balance.get('USDT', {})
                free = usdt_balance.get('free', 0)
                print(f"   ✅ USDT Balance: {free:.2f}")
                
                return True
            except Exception as e:
                print(f"   ❌ Lỗi kết nối OKX: {e}")
                return False
            finally:
                await exchange.close()
        
        result = asyncio.run(test_okx())
        
    except Exception as e:
        print(f"   ❌ Lỗi test OKX: {e}")
else:
    print("   ⏩ Bỏ qua (thiếu dependencies hoặc credentials)")
print()

# 7. Check bot log
print("[7/7] Kiểm tra bot log...")
if os.path.exists('bot.log'):
    print("   ✅ File bot.log tồn tại")
    
    # Read last 20 lines
    try:
        with open('bot.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-20:] if len(lines) > 20 else lines
            
        print("   📋 20 dòng log cuối:")
        print("   " + "-" * 56)
        for line in last_lines:
            print("   " + line.rstrip())
        print("   " + "-" * 56)
    except Exception as e:
        print(f"   ⚠️ Không đọc được log: {e}")
else:
    print("   ⏩ Chưa có file bot.log (chưa chạy lần nào)")
print()

# Summary
print("=" * 60)
print("KẾT LUẬN")
print("=" * 60)

if missing:
    print("❌ THIẾU DEPENDENCIES - Cài đặt trước:")
    print(f"   pip install {' '.join(missing)}")
elif not os.path.exists('.env'):
    print("❌ THIẾU FILE .ENV - Tạo file .env với credentials")
elif not (api_key and secret and password):
    print("❌ THIẾU CREDENTIALS trong .env")
elif not found_bot:
    print("❌ THIẾU FILE BOT")
else:
    print("✅ CÁC ĐIỀU KIỆN CƠ BẢN OK")
    print()
    print("📌 HƯỚNG DẪN TIẾP THEO:")
    print("   1. Chạy bot trực tiếp để xem lỗi chi tiết:")
    print(f"      python {found_bot}")
    print()
    print("   2. Nếu vẫn crash, check bot.log:")
    print("      type bot.log  (Windows)")
    print("      cat bot.log   (Linux/Mac)")
    print()
    print("   3. Hoặc chạy với debug mode:")
    print(f"      python -u {found_bot}")

print("=" * 60)