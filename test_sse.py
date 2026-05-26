# -*- coding: utf-8 -*-
import requests
import json
import sys

PDF_PATH = r"C:\Users\user\Desktop\인프　템플릿（인테리어）.pdf"

print("SSE 분석 요청 전송 중...")
with open(PDF_PATH, "rb") as f:
    resp = requests.post(
        "http://localhost:5000/analyze",
        files={"file": ("estimate.pdf", f, "application/pdf")},
        data={"context": "서울 마포구 32평 아파트 화장실 리모델링"},
        timeout=180,
        stream=True,
    )

result = None
evt = ""
for line in resp.iter_lines(decode_unicode=True):
    if not line:
        continue
    if line.startswith("event:"):
        evt = line[6:].strip()
    elif line.startswith("data:"):
        data = json.loads(line[5:].strip())
        if evt == "progress":
            print(f"  진행: step={data['step']} - {data['message']}")
        elif evt == "done":
            result = data["result"]
            print("분석 완료!")
        elif evt == "error":
            print("오류:", data["message"])
            sys.exit(1)

if result:
    s = result["summary"]
    print()
    print("=== 분석 결과 ===")
    print("한줄:", s.get("one_line"))
    print("위험도:", s.get("risk_level"))
    print("견적 총액:", s.get("total_quoted"))
    print("적정가:", s.get("total_fair"))
    print("과다청구율:", str(s.get("overprice_rate")) + "%")
    print("레드플래그:", len(result.get("red_flags", [])), "개")
    print("항목수:", len(result.get("items", [])), "개")
    print("스크립트:", len(result.get("negotiation", {}).get("scripts", [])), "개")
    print("체크리스트:", len(result.get("contract_checklist", [])), "개")
    print("\n종합 조언:", result.get("overall_advice", "")[:200])
