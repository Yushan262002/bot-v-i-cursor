# -*- coding: utf-8 -*-
"""
Safe wrapper để chạy bot và catch errors
Chạy: python run_bot_safe.py
"""

import sys
import os
import traceback

def main():
    print("=" * 60)
    print("BOT SAFE LAUNCHER")
    print("=" * 60)
    print()
    
    # Tìm bot file
    bot_files = ['bot.py', 'bot_fixed_clean.py', 'bot_fixed.py']
    bot_file = None
    
    for bf in bot_files:
        if os.path.exists(bf):
            bot_file = bf
            print(f"✅ Tìm thấy {bf}")
            break
    
    if not bot_file:
        print("❌ Không tìm thấy file bot!")
        print("   Các file cần có: bot.py hoặc bot_fixed_clean.py")
        input("Press Enter to exit...")
        return 1
    
    print(f"▶️  Đang chạy {bot_file}...")
    print("=" * 60)
    print()
    
    try:
        # Import và chạy bot
        with open(bot_file, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Execute bot code
        exec(code, {'__name__': '__main__'})
        
    except KeyboardInterrupt:
        print()
        print("=" * 60)
        print("⏹️  Bot đã dừng (Ctrl+C)")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ BOT CRASH - CHI TIẾT LỖI:")
        print("=" * 60)
        print()
        
        # Print error type
        print(f"Loại lỗi: {type(e).__name__}")
        print(f"Message: {str(e)}")
        print()
        
        # Print full traceback
        print("Traceback:")
        print("-" * 60)
        traceback.print_exc()
        print("-" * 60)
        print()
        
        # Suggestions
        print("=" * 60)
        print("💡 HƯỚNG GIẢI QUYẾT:")
        print("=" * 60)
        
        error_msg = str(e).lower()
        
        if 'modulenotfounderror' in str(type(e)).lower() or 'no module' in error_msg:
            missing_module = str(e).split("'")[1] if "'" in str(e) else "unknown"
            print(f"❌ Thiếu module: {missing_module}")
            print()
            print("Giải pháp:")
            if missing_module == 'dotenv':
                print("   pip install python-dotenv")
            elif missing_module in ['flask', 'ccxt']:
                print(f"   pip install {missing_module}")
            else:
                print(f"   pip install {missing_module}")
        
        elif 'keyerror' in str(type(e)).lower():
            print("❌ Thiếu key trong config")
            print()
            print("Giải pháp:")
            print("   - Kiểm tra file .env có đầy đủ:")
            print("     OKX_API_KEY=...")
            print("     OKX_API_SECRET=...")
            print("     OKX_API_PASSWORD=...")
        
        elif 'authentication' in error_msg or 'invalid' in error_msg:
            print("❌ Lỗi xác thực OKX API")
            print()
            print("Giải pháp:")
            print("   - Kiểm tra lại API credentials trong .env")
            print("   - Đảm bảo API key còn hiệu lực")
            print("   - Kiểm tra quyền API (cần Trading permission)")
        
        elif 'connection' in error_msg or 'timeout' in error_msg:
            print("❌ Lỗi kết nối mạng")
            print()
            print("Giải pháp:")
            print("   - Kiểm tra kết nối internet")
            print("   - Thử lại sau vài giây")
            print("   - Kiểm tra firewall/antivirus")
        
        elif 'unicodedecodeerror' in str(type(e)).lower():
            print("❌ Lỗi encoding")
            print()
            print("Giải pháp:")
            print("   - File bot cần lưu với UTF-8 encoding")
            print("   - Trong VS Code: File > Save with Encoding > UTF-8")
        
        else:
            print("Lỗi không xác định.")
            print()
            print("Giải pháp:")
            print("   1. Chạy debug script:")
            print("      python debug_bot.py")
            print()
            print("   2. Kiểm tra bot.log")
            print()
            print("   3. Copy lỗi trên và search Google")
        
        print()
        input("Press Enter to exit...")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)