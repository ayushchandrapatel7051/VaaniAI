#!/usr/bin/env python3
"""Test command routing for both voice/text inputs"""

from commands import detect_command, route_command

# Test commands
test_cases = [
    "youtube python tutorials",
    "google search machine learning",
    "set timer for 5 minutes",
    "what's the weather",
    "save note buy groceries",
    "remind me in 10 minutes to test",
    "export conversation",
    "favorite this conversation",
    "schedule meeting tomorrow at 2pm",
    "show notes",
]

print("=" * 60)
print("TESTING COMMAND DETECTION & ROUTING")
print("=" * 60)

for test_input in test_cases:
    print(f"\n📝 Input: '{test_input}'")
    
    # Test detection
    is_cmd, cmd_type, params = detect_command(test_input)
    print(f"   Detected: {is_cmd} | Type: {cmd_type}")
    
    # Test routing
    is_direct, response = route_command(test_input, "test-conv-id", [])
    
    if is_direct and response:
        print(f"   ✅ COMMAND ROUTED: {response.get('type')}")
        print(f"      Response: {response.get('text', response.get('title', 'N/A'))}")
    else:
        print(f"   ⚠️  NOT A COMMAND - Would go to LLM")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
