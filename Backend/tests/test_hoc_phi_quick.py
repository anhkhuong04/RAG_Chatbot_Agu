import requests

BASE_URL = "http://localhost:8000/api/v1/chat"

questions = [
    "Học phí ngành Công nghệ thông tin bao nhiêu?",
    "So sánh học phí ngành CNTT giữa khóa cũ và khóa mới?",
    "Ngành nào có học phí cao nhất?",
]

for i, q in enumerate(questions):
    print(f"\n{'='*70}")
    print(f"Q{i+1}: {q}")
    print(f"{'='*70}")
    r = requests.post(BASE_URL, json={"message": q, "session_id": f"test_hp_{i}"}, timeout=120)
    data = r.json()
    print(f"Intent: {data.get('intent', 'N/A')}")
    print(f"Sources: {data.get('sources', [])}")
    print(f"\nResponse:\n{data.get('response', 'No response')}")

print(f"\n{'='*70}")
print("DONE")
