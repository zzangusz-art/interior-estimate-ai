# -*- coding: utf-8 -*-
"""
Claude AI 기반 견적서 분석 엔진
"""
import json
import anthropic

SYSTEM_PROMPT = """당신은 대한민국 인테리어·시공 견적 전문 분석가입니다.
소비자가 업체로부터 받은 견적서를 분석하여 다음을 제공합니다:

1. 적정 시장가 대비 견적 평가 (과다청구/적정/저가 여부)
2. 항목별 단가 검증 (자재비, 인건비, 부가세, 이윤율 등)
3. 위험 신호(레드플래그) 탐지
4. 소비자 협상 전략 및 스크립트
5. 누락 항목 또는 불분명한 조항 지적
6. 공정 계약서 체크리스트

분석 원칙:
- 소비자 보호를 최우선으로 하되, 업자의 합리적 이윤(통상 15~25%)은 인정
- 구체적인 수치와 근거를 제시 (단순 "비싸다"가 아닌 "시장가 대비 X% 초과")
- 협상 가능한 항목과 고정 비용을 구분하여 안내
- 지역별/시기별 가격 편차를 고려한 현실적 조언 제공
- 전문 용어는 쉽게 풀어서 설명

응답은 반드시 아래 JSON 구조로 반환하세요:
{
  "summary": {
    "total_quoted": 견적총액(숫자, 없으면 null),
    "total_fair": 적정가총액(숫자),
    "overprice_rate": 초과율(%, 숫자),
    "risk_level": "낮음|보통|높음|매우높음",
    "one_line": "한줄 핵심 요약"
  },
  "items": [
    {
      "name": "항목명",
      "quoted_price": 견적가(숫자 또는 null),
      "fair_price_min": 최저 적정가(숫자),
      "fair_price_max": 최대 적정가(숫자),
      "status": "적정|과다|저가|불명확",
      "note": "분석 코멘트"
    }
  ],
  "red_flags": [
    {
      "severity": "경고|주의|정보",
      "title": "항목명",
      "description": "상세 설명",
      "action": "권고 조치"
    }
  ],
  "negotiation": {
    "strategy": "전체 협상 전략 요약",
    "scripts": [
      {
        "topic": "협상 주제",
        "script": "실제 사용할 수 있는 협상 멘트"
      }
    ],
    "target_price": 목표 협상가(숫자),
    "walkaway_price": 거절 기준가(숫자)
  },
  "contract_checklist": [
    {
      "item": "확인 항목",
      "required": true/false,
      "tip": "팁"
    }
  ],
  "missing_items": ["누락된 항목1", "누락된 항목2"],
  "overall_advice": "종합 조언 (3~5문장)"
}"""


def analyze_estimate(parsed_data: dict, user_context: str = "") -> dict:
    """견적서 데이터를 Claude API로 분석"""
    client = anthropic.Anthropic()

    content = []

    if parsed_data.get("image_base64"):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": parsed_data.get("media_type", "image/jpeg"),
                "data": parsed_data["image_base64"],
            },
        })
        content.append({
            "type": "text",
            "text": (
                "위 이미지는 인테리어·시공 견적서입니다.\n\n"
                "다음 순서로 분석하세요:\n"
                "1. 이미지에서 보이는 모든 항목명, 수량, 단가, 소계, 합계금액을 빠짐없이 읽어냅니다.\n"
                "2. 글씨가 흐리거나 기울어져 있어도 최대한 판독합니다. 읽기 어려운 부분은 '불명확'으로 표시합니다.\n"
                "3. 표 형식이 아닌 경우에도 금액 관련 숫자와 항목명을 모두 추출합니다.\n"
                "4. 추출한 내용을 바탕으로 시장가 대비 분석을 수행합니다.\n"
                "5. 반드시 JSON 형식으로만 응답합니다."
            ),
        })
    else:
        text = parsed_data.get("text", "")
        tables_info = ""
        if parsed_data.get("tables"):
            tables_info = "\n\n[테이블 데이터]\n"
            for i, tbl in enumerate(parsed_data["tables"]):
                tables_info += f"\n테이블 {i+1}:\n"
                for row in tbl.get("data", []):
                    tables_info += " | ".join(str(c) for c in row) + "\n"

        content.append({
            "type": "text",
            "text": f"다음은 인테리어/시공 견적서 내용입니다:\n\n{text}{tables_info}",
        })

    if user_context.strip():
        content.append({
            "type": "text",
            "text": f"\n\n[추가 정보 (소비자 입력)]\n{user_context}",
        })

    content.append({
        "type": "text",
        "text": "\n\n위 견적서를 전문가 관점에서 분석하고, 지정된 JSON 형식으로만 응답해주세요. JSON 외 다른 텍스트는 포함하지 마세요.",
    })

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    response_text = message.content[0].text.strip()

    # 코드블록 래핑 제거
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        response_text = "\n".join(lines[1:end])

    # 잘린 JSON 복구 시도
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        fixed = _repair_json(response_text)
        return json.loads(fixed)


def _repair_json(text: str) -> str:
    """잘린 JSON을 최대한 복구"""
    # 마지막 완전한 필드까지만 사용
    # 중괄호/대괄호 닫기 시도
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    # 마지막 쉼표 제거
    text = text.rstrip().rstrip(",")

    # 열린 배열 닫기
    text += "]" * max(0, open_brackets)
    # 열린 객체 닫기
    text += "}" * max(0, open_braces)

    return text
