# -*- coding: utf-8 -*-
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
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print_header("BOT QUICK FIX TOOL")
    print("\nTool nay se tu dong:")
    print("  1. Kiem tra dependencies")
    print("  2. Cai dependencies thieu")
    print("  3. Kiem tra file .env")
    print("  4. Kiem tra file bot")
    print("  5. Verify bot syntax")
    
    input("\nNhan Enter de bat dau...")
    
    total_steps = 5
    fixes_applied = []
    
    print_step(1, total_steps, "Kiem tra Python version")
    print(f"   Python: {sys.version}")
    
    if sys.version_info < (3, 8):
        print("   [X] Can Python 3.8 tro len!")
        print("   Download: https://www.python.org/downloads/")
        return 1
    else:
        print("   [OK] Python version OK")
    
    print_step(2, total_steps, "Kiem tra dependencies")
    
    required = ['flask', 'ccxt', 'python-dotenv']
    missing = []
    
    for package in required:
        try:
            if package == 'python-dotenv':
                __import__('dotenv')
                print(f"   [OK] {package}")
            else:
                __import__(package)
                print(f"   [OK] {package}")
        except ImportError:
            print(f"   [X] {package} - THIEU")
            missing.append(package)
    
    if missing:
        print(f"\n   Dang cai {len(missing)} package thieu...")
        
        for package in missing:
            print(f"   Installing {package}...")
            success, stdout, stderr = run_command(f"pip install {package}")
            
            if success:
                print(f"   [OK] Cai {package} thanh cong")
                fixes_applied.append(f"Cai {package}")
            else:
                print(f"   [X] Loi cai {package}: {stderr}")
    
    print_step(3, total_steps, "Kiem tra file .env")
    
    if not os.path.exists('.env'):
        print("   [X] File .env khong ton tai")
        print("\n   Tao file .env mau...")
        
        env_content = """OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_secret_here
OKX_API_PASSWORD=your_password_here"""
        
        try:
            with open('.env', 'w', encoding='utf-8') as f:
                f.write(env_content)
            
            print("   [OK] Da tao file .env mau")
            print("\n   [!] QUAN TRONG: Mo file .env va dien API credentials!")
            fixes_applied.append("Tao file .env mau")
        except Exception as e:
            print(f"   [X] Loi tao .env: {e}")
    else:
        print("   [OK] File .env ton tai")
        
        try:
            with open('.env', 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'your_api_key_here' in content:
                print("   [!] Canh bao: Van dung credentials mau!")
                print("   Can update file .env voi API that")
            else:
                print("   [OK] Credentials da duoc cap nhat")
        except Exception as e:
            print(f"   [!] Khong doc duoc .env: {e}")
    
    print_step(4, total_steps, "Kiem tra file bot")
    
    bot_files = ['bot_fixed_clean.py', 'bot.py', 'bot_fixed.py']
    found = None
    
    for bf in bot_files:
        if os.path.exists(bf):
            print(f"   [OK] Tim thay {bf}")
            found = bf
            break
    
    if not found:
        print("   [X] Khong tim thay file bot!")
        print("   Can co file bot_fixed_clean.py hoac bot.py")
        return 1
    
    print_step(5, total_steps, "Kiem tra syntax bot")
    
    try:
        with open(found, 'r', encoding='utf-8') as f:
            code = f.read()
        
        compile(code, found, 'exec')
        print(f"   [OK] Syntax OK")
    except SyntaxError as e:
        print(f"   [X] Loi syntax:")
        print(f"      File: {e.filename}")
        print(f"      Dong {e.lineno}: {e.text}")
        print(f"      Loi: {e.msg}")
        return 1
    except UnicodeDecodeError:
        print(f"   [X] Loi encoding!")
        print(f"   File {found} can luu voi UTF-8 encoding")
        print("\n   Dang thu fix encoding...")
        
        try:
            with open(found, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            with open(found, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("   [OK] Da sua encoding")
            fixes_applied.append(f"Sua encoding {found}")
        except Exception as e:
            print(f"   [X] Khong the sua: {e}")
    except Exception as e:
        print(f"   [X] Loi khac: {e}")
    
    print_header("KET QUA")
    
    if fixes_applied:
        print("\n[OK] Da ap dung cac fixes:")
        for i, fix in enumerate(fixes_applied, 1):
            print(f"   {i}. {fix}")
    else:
        print("\n[OK] Khong can fix gi (moi thu OK)")
    
    print("\n" + "=" * 60)
    print("BUOC TIEP THEO:")
    print("=" * 60)
    
    print("\n1. Kiem tra file .env co credentials dung:")
    print("   notepad .env")
    
    print("\n2. Chay bot:")
    print(f"   python {found}")
    
    print("\n3. Hoac dung safe wrapper:")
    print("   python run_bot_safe.py")
    
    print("\n4. Hoac chay debug de test:")
    print("   python debug_bot.py")
    
    print("\n" + "=" * 60)
    
    input("\nNhan Enter de thoat...")
    return 0

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nDa huy")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nLoi: {e}")
        import traceback
        traceback.print_exc()
        input("\nNhan Enter de thoat...")
        sys.exit(1)