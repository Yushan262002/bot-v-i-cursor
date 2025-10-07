# -*- coding: utf-8 -*-
"""
Quick Fix Script - Tự động kiểm tra và sửa các lỗi phổ biến
Chạy: python quick_fix.py
"""

import os
import sys
import subprocess

def print_header(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)

def print_step(num, total, text):
    print(f"\n[{num}/{total}] {text}")

def run_command(cmd):
    """Chạy command và return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print_header("🔧 BOT QUICK FIX TOOL")
    print("\nTool này sẽ tự động:")
    print("  1. Kiểm tra dependencies")
    print("  2. Cài dependencies thiếu")
    print("  3. Kiểm tra file .env")
    print("  4. Kiểm tra file bot")
    print("  5. Verify bot syntax")
    
    input("\nNhấn Enter để bắt đầu...")
    
    total_steps = 5
    fixes_applied = []
    
    # Step 1: Check Python version
    print_step(1, total_steps, "Kiểm tra Python version")
    print(f"   Python: {sys.version}")
    
    if sys.version_info < (3, 8):
        print("   ❌ Cần Python 3.8 trở lên!")
        print("   Download: https://www.python.org/downloads/")
        return 1
    else:
        print("   ✅ Python version OK")
    
    # Step 2: Check and install dependencies
    print_step(2, total_steps, "Kiểm tra dependencies")
    
    required = ['flask', 'ccxt', 'python-dotenv']
    missing = []
    
    for package in required:
        try:
            if package == 'python-dotenv':
                __import__('dotenv')
                print(f"   ✅ {package}")
            else:
                __import__(package)
                print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} - THIẾU")
            missing.append(package)
    
    if missing:
        print(f"\n   📦 Đang cài {len(missing)} package thiếu...")
        
        for package in missing:
            print(f"   Installing {package}...")
            success, stdout, stderr = run_command(f"pip install {package}")
            
            if success:
                print(f"   ✅ Cài {package} thành công")
                fixes_applied.append(f"Cài {package}")
            else:
                print(f"   ❌ Lỗi cài {package}: {stderr}")
    
    # Step 3: Check .env file
    print_step(3, total_steps, "Kiểm tra file .env")
    
    if not os.path.exists('.env'):
        print("   ❌ File .env không tồn tại")
        print("\n   Tạo file .env mẫu...")
        
        env_content = """OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_secret_here
OKX_API_PASSWORD=your_password_here"""
        
        try:
            with open('.env', 'w', encoding='utf-8') as f:
                f.write(env_content)
            
            print("   ✅ Đã tạo file .env mẫu")
            print("\n   ⚠️  QUAN TRỌNG: Mở file .env và điền API credentials!")
            fixes_applied.append("Tạo file .env mẫu")
        except Exception as e:
            print(f"   ❌ Lỗi tạo .env: {e}")
    else:
        print("   ✅ File .env tồn tại")
        
        # Check content
        try:
            with open('.env', 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'your_api_key_here' in content:
                print("   ⚠️  Cảnh báo: Vẫn dùng credentials mẫu!")
                print("   👉 Cần update file .env với API thật")
            else:
                print("   ✅ Credentials đã được cập nhật")
        except Exception as e:
            print(f"   ⚠️  Không đọc được .env: {e}")
    
    # Step 4: Check bot files
    print_step(4, total_steps, "Kiểm tra file bot")
    
    bot_files = ['bot_fixed_clean.py', 'bot.py', 'bot_fixed.py']
    found = None
    
    for bf in bot_files:
        if os.path.exists(bf):
            print(f"   ✅ Tìm thấy {bf}")
            found = bf
            break
    
    if not found:
        print("   ❌ Không tìm thấy file bot!")
        print("   👉 Cần có file bot_fixed_clean.py hoặc bot.py")
        return 1
    
    # Step 5: Verify bot syntax
    print_step(5, total_steps, "Kiểm tra syntax bot")
    
    try:
        with open(found, 'r', encoding='utf-8') as f:
            code = f.read()
        
        compile(code, found, 'exec')
        print(f"   ✅ Syntax OK")
    except SyntaxError as e:
        print(f"   ❌ Lỗi syntax:")
        print(f"      File: {e.filename}")
        print(f"      Dòng {e.lineno}: {e.text}")
        print(f"      Lỗi: {e.msg}")
        return 1
    except UnicodeDecodeError:
        print(f"   ❌ Lỗi encoding!")
        print(f"   👉 File {found} cần lưu với UTF-8 encoding")
        print("\n   Đang thử fix encoding...")
        
        try:
            # Re-save with UTF-8
            with open(found, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            with open(found, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("   ✅ Đã sửa encoding")
            fixes_applied.append(f"Sửa encoding {found}")
        except Exception as e:
            print(f"   ❌ Không thể sửa: {e}")
    except Exception as e:
        print(f"   ❌ Lỗi khác: {e}")
    
    # Summary
    print_header("📊 KẾT QUẢ")
    
    if fixes_applied:
        print("\n✅ Đã áp dụng các fixes:")
        for i, fix in enumerate(fixes_applied, 1):
            print(f"   {i}. {fix}")
    else:
        print("\n✅ Không cần fix gì (mọi thứ OK)")
    
    print("\n" + "=" * 60)
    print("📌 BƯỚC TIẾP THEO:")
    print("=" * 60)
    
    print("\n1. Kiểm tra file .env có credentials đúng:")
    print("   notepad .env")
    
    print("\n2. Chạy bot:")
    print(f"   python {found}")
    
    print("\n3. Hoặc dùng safe wrapper:")
    print("   python run_bot_safe.py")
    
    print("\n4. Hoặc chạy debug để test:")
    print("   python debug_bot.py")
    
    print("\n" + "=" * 60)
    
    input("\nNhấn Enter để thoát...")
    return 0

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Đã hủy")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        input("\nNhấn Enter để thoát...")
        sys.exit(1)