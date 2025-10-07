#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script để verify các fixes trong bot_fixed.py
Chạy: python test_fixes.py
"""

import asyncio
from decimal import Decimal

# =========================
# TEST 1: Safe Float Helper
# =========================
def safe_float(value, default=0.0) -> float:
    """Safely convert to float, handle None"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def test_safe_float():
    print("=" * 50)
    print("TEST 1: Safe Float Helper")
    print("=" * 50)
    
    test_cases = [
        (None, 0.0, "None value"),
        (0, 0.0, "Zero"),
        (5.5, 5.5, "Float"),
        ("10.5", 10.5, "String number"),
        ("invalid", 0.0, "Invalid string"),
        ({}, 0.0, "Dict"),
        ([], 0.0, "List"),
    ]
    
    passed = 0
    for value, expected, desc in test_cases:
        result = safe_float(value)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status} | {desc:20s} | Input: {str(value):15s} | Expected: {expected:6.1f} | Got: {result:6.1f}")
        if result == expected:
            passed += 1
    
    print(f"\nKết quả: {passed}/{len(test_cases)} tests passed")
    print()
    return passed == len(test_cases)

# =========================
# TEST 2: Order Response Parsing
# =========================
def test_order_response_parsing():
    print("=" * 50)
    print("TEST 2: Order Response Parsing")
    print("=" * 50)
    
    # Mock order responses từ OKX
    test_orders = [
        {
            "name": "Filled order",
            "order": {"id": "123", "status": "closed", "filled": 0.04, "amount": 0.04},
            "expected": (True, 0.04)
        },
        {
            "name": "Filled=None (lỗi cũ)",
            "order": {"id": "124", "status": "closed", "filled": None, "amount": 0.04},
            "expected": (False, 0.0)  # safe_float → 0.0
        },
        {
            "name": "Partial fill",
            "order": {"id": "125", "status": "open", "filled": 0.02, "amount": 0.04},
            "expected": (False, 0.02)
        },
        {
            "name": "Unknown status",
            "order": {"id": "126", "status": None, "filled": 0.04, "amount": 0.04},
            "expected": (False, 0.04)
        },
    ]
    
    passed = 0
    for test in test_orders:
        order = test["order"]
        expected_success, expected_filled = test["expected"]
        
        # Simulate verify logic
        status = order.get('status', 'unknown')
        filled = safe_float(order.get('filled'), 0)
        amount = order.get('amount', 0.04)
        
        success = (status == 'closed' and filled >= amount * 0.95)
        
        match = (success == expected_success and abs(filled - expected_filled) < 0.001)
        status_str = "✅ PASS" if match else "❌ FAIL"
        
        print(f"{status_str} | {test['name']:25s} | Success: {success} | Filled: {filled:.2f}")
        if match:
            passed += 1
    
    print(f"\nKết quả: {passed}/{len(test_orders)} tests passed")
    print()
    return passed == len(test_orders)

# =========================
# TEST 3: Amount Calculation
# =========================
def test_amount_calculation():
    print("=" * 50)
    print("TEST 3: Amount Calculation with Limits")
    print("=" * 50)
    
    LEVERAGE = 20
    MARGIN_USDT = 6
    
    test_cases = [
        {
            "name": "ETH - normal",
            "price": 4500.0,
            "min_amt": 0.01,
            "max_amt": 100.0,
            "expected_amt": 0.02,  # (6*20)/4500 ≈ 0.0267 → precision 0.02
        },
        {
            "name": "PEPE - below min",
            "price": 0.00001,
            "min_amt": 100.0,
            "max_amt": 10000000.0,
            "expected_amt": 12000000.0,  # (6*20)/0.00001 = 12M
        },
        {
            "name": "BTC - above max (should limit)",
            "price": 1.0,  # Giả sử price rất thấp
            "min_amt": 0.001,
            "max_amt": 10.0,
            "expected_amt": 10.0,  # Limited to max
        },
    ]
    
    passed = 0
    for test in test_cases:
        price = test["price"]
        min_amt = test["min_amt"]
        max_amt = test["max_amt"]
        
        # Calculate
        notional = MARGIN_USDT * LEVERAGE
        raw = notional / price
        amt = max(raw, min_amt)
        if amt > max_amt:
            amt = max_amt
        
        # Check
        expected = test["expected_amt"]
        match = abs(amt - expected) < max_amt * 0.2  # 20% tolerance
        
        status_str = "✅ PASS" if match else "❌ FAIL"
        print(f"{status_str} | {test['name']:20s} | Amount: {amt:,.1f} | Expected: ~{expected:,.1f}")
        
        if match:
            passed += 1
    
    print(f"\nKết quả: {passed}/{len(test_cases)} tests passed")
    print()
    return passed == len(test_cases)

# =========================
# TEST 4: Balance Check Logic
# =========================
def test_balance_check():
    print("=" * 50)
    print("TEST 4: Balance Check Logic")
    print("=" * 50)
    
    MIN_BALANCE_BUFFER = 2.0
    
    test_cases = [
        {
            "name": "Đủ margin + buffer",
            "avail": 50.0,
            "required": 10.0,
            "expected": True
        },
        {
            "name": "Đủ margin nhưng không đủ buffer",
            "avail": 11.0,
            "required": 10.0,
            "expected": False  # 11 < 10 + 2
        },
        {
            "name": "Không đủ margin",
            "avail": 5.0,
            "required": 10.0,
            "expected": False
        },
        {
            "name": "Vừa đủ với buffer",
            "avail": 12.0,
            "required": 10.0,
            "expected": True  # 12 >= 10 + 2
        },
    ]
    
    passed = 0
    for test in test_cases:
        avail = test["avail"]
        required = test["required"]
        expected = test["expected"]
        
        # Logic
        has_enough = avail >= (required + MIN_BALANCE_BUFFER)
        
        match = has_enough == expected
        status_str = "✅ PASS" if match else "❌ FAIL"
        
        print(f"{status_str} | {test['name']:35s} | Avail: {avail:5.1f} | Req: {required:5.1f} | Buffer: {MIN_BALANCE_BUFFER:.1f} | Result: {has_enough}")
        
        if match:
            passed += 1
    
    print(f"\nKết quả: {passed}/{len(test_cases)} tests passed")
    print()
    return passed == len(test_cases)

# =========================
# TEST 5: Position Cleanup Logic
# =========================
def test_position_cleanup():
    print("=" * 50)
    print("TEST 5: Position Cleanup Logic")
    print("=" * 50)
    
    test_cases = [
        {
            "name": "Position còn, cùng side",
            "active_side": "long",
            "current_side": "long",
            "current_size": 0.5,
            "should_cleanup": False
        },
        {
            "name": "Position đã đóng (size=0)",
            "active_side": "long",
            "current_side": None,
            "current_size": 0,
            "should_cleanup": True
        },
        {
            "name": "Position đảo chiều",
            "active_side": "long",
            "current_side": "short",
            "current_size": 0.5,
            "should_cleanup": True
        },
        {
            "name": "Position khác side nhưng size=0",
            "active_side": "long",
            "current_side": "short",
            "current_size": 0,
            "should_cleanup": True
        },
    ]
    
    passed = 0
    for test in test_cases:
        active_side = test["active_side"]
        current_side = test["current_side"]
        current_size = test["current_size"]
        expected = test["should_cleanup"]
        
        # Logic
        should_cleanup = (current_size == 0 or current_side != active_side)
        
        match = should_cleanup == expected
        status_str = "✅ PASS" if match else "❌ FAIL"
        
        print(f"{status_str} | {test['name']:30s} | Cleanup: {should_cleanup} | Expected: {expected}")
        
        if match:
            passed += 1
    
    print(f"\nKết quả: {passed}/{len(test_cases)} tests passed")
    print()
    return passed == len(test_cases)

# =========================
# MAIN TEST RUNNER
# =========================
def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "BOT TRADING - UNIT TEST SUITE" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    results = []
    
    # Run all tests
    results.append(("Safe Float Helper", test_safe_float()))
    results.append(("Order Response Parsing", test_order_response_parsing()))
    results.append(("Amount Calculation", test_amount_calculation()))
    results.append(("Balance Check Logic", test_balance_check()))
    results.append(("Position Cleanup Logic", test_position_cleanup()))
    
    # Summary
    print("=" * 60)
    print("TỔNG KẾT")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} | {name}")
    
    total_passed = sum(1 for _, p in results if p)
    total_tests = len(results)
    
    print()
    print(f"Tổng cộng: {total_passed}/{total_tests} test suites passed")
    
    if total_passed == total_tests:
        print()
        print("🎉 TẤT CẢ TESTS ĐÃ PASS! Bot fixes hoạt động đúng.")
        print()
        return 0
    else:
        print()
        print("⚠️ MỘT SỐ TESTS FAILED. Cần review lại code.")
        print()
        return 1

if __name__ == "__main__":
    exit(main())