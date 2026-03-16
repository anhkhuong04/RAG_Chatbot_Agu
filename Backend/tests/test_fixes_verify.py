import requests

BASE_URL = "http://localhost:8000/api/v1/chat"

tests = [
    # Học phí tests
    ("Học phí ngành Công nghệ thông tin bao nhiêu?", "QUERY_FEES"),
    ("So sánh học phí ngành CNTT giữa khóa cũ và khóa mới?", "QUERY_FEES"),
    ("Ngành nào có học phí cao nhất?", "QUERY_FEES"),
    ("Học phí ngành Luật?", "QUERY_FEES"),
    # Điểm chuẩn tests (regression)
    ("Điểm chuẩn ngành CNTT?", "QUERY_SCORES"),
    ("Ngành nào có điểm chuẩn cao nhất?", "QUERY_SCORES"),
    ("Điểm chuẩn ngành mã 7480201?", "QUERY_SCORES"),
]

results = []
for i, (q, expected_intent) in enumerate(tests):
    print(f"\n{'='*70}")
    print(f"Q{i+1}: {q}")
    print(f"Expected: {expected_intent}")
    print(f"{'='*70}")
    r = requests.post(BASE_URL, json={"message": q, "session_id": f"test_fix_{i}"}, timeout=120)
    data = r.json()
    intent = data.get("intent", "N/A")
    resp = data.get("response", "")
    sources = data.get("sources", [])
    ok = intent == expected_intent
    
    print(f"Intent: {intent} {'OK' if ok else 'MISMATCH!'}")
    print(f"Sources: {sources}")
    print(f"\nResponse:\n{resp[:500]}")
    
    results.append({"q": q, "intent": intent, "expected": expected_intent, "ok": ok, "len": len(resp)})

print(f"\n\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
for i, r in enumerate(results):
    icon = "pass" if r["ok"] else "FAIL"
    print(f"  [{icon:4s}] Q{i+1}: [{r['intent']:15s}] ({r['len']:4d}ch) {r['q'][:50]}")
