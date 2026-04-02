#!/usr/bin/env python
import requests
import json

print("Testing API endpoint...")
try:
    resp = requests.get('http://localhost:8000/api/conversations?limit=50')
    print(f"Status: {resp.status_code}")
    raw_data = resp.json()
    print(f"Raw response type: {type(raw_data)}")
    print(f"Raw response: {json.dumps(raw_data, indent=2)[:500]}")
    
    if isinstance(raw_data, dict):
        print(f"Count from dict: {raw_data.get('count')}")
        conversations = raw_data.get('conversations', [])
    else:
        print(f"Response is a list with {len(raw_data)} items")
        conversations = raw_data
    
    print(f"\nFirst 3 conversations:")
    for c in conversations[:3]:
        print(f"  - Title: {c['title']}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

