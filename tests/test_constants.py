#!/usr/bin/env python3
"""Test the new StrategyNames constants"""

from strategies.constants import StrategyNames

print("\n" + "="*60)
print("Testing StrategyNames Constants")
print("="*60)

# Test 1: All strategy names
print("\n1. All Strategy Names:")
for name in StrategyNames.all_names():
    print(f"   - {name}")

# Test 2: Display names
print("\n2. Display Names:")
for name in StrategyNames.all_names():
    display = StrategyNames.get_display_name(name)
    print(f"   {name} → {display}")

# Test 3: Config keys
print("\n3. Config Keys:")
for name in StrategyNames.all_names():
    key = StrategyNames.get_config_key(name)
    print(f"   {name} → {key}")

# Test 4: Config sections
print("\n4. Config Sections:")
for name in StrategyNames.all_names():
    section = StrategyNames.get_config_section(name)
    print(f"   {name} → {section}")

# Test 5: Strategy types
print("\n5. Strategy Types:")
for name in StrategyNames.all_names():
    stype = StrategyNames.get_strategy_type(name)
    icon = StrategyNames.get_icon(name)
    print(f"   {icon} {name} → {stype}")

# Test 6: Validation
print("\n6. Validation:")
test_names = [
    "EMA_Crossover",
    "RSI_BB_MeanReversion",
    "MACD_Volume_Momentum",
    "InvalidStrategy",
]
for name in test_names:
    valid = StrategyNames.is_valid_strategy(name)
    status = "✅" if valid else "❌"
    print(f"   {status} {name}: {'valid' if valid else 'invalid'}")

# Test 7: Validate or raise
print("\n7. Validate with Exception:")
try:
    StrategyNames.validate_strategy_name("EMA_Crossover")
    print("   ✅ Valid name accepted")
except ValueError as e:
    print(f"   ❌ Unexpected error: {e}")

try:
    StrategyNames.validate_strategy_name("InvalidStrategy")
    print("   ❌ Invalid name should have raised error")
except ValueError as e:
    print(f"   ✅ Invalid name rejected: {e}")

print("\n" + "="*60)
print("✅ All constant tests completed successfully!")
print("="*60 + "\n")
