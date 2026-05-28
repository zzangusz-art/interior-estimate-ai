# -*- coding: utf-8 -*-
"""
Claude AI 기반 견적서 분석 엔진
"""
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

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
- note, description, tip 등 텍스트 필드는 각 100자 이내로 간결하게 작성

응답은 반드시 아래 JSON 구조로만 반환하세요. JSON 외 다른 텍스트 없이:
{
  "summary": {
    "total_quoted": 견적총액(숫자, 없으면 null),
    "total_fair": 적정가총액(숫자),
    "overprice_rate": 초과율(%, 숫자),
    "risk_level": "낮음|보통|높음|매우높음",
    "one_line": "한줄 핵심 요약 (50자 이내)"
  },
  "items": [
    {
      "name": "항목명",
      "quoted_price": 견적가(숫자 또는 null),
      "fair_price_min": 최저 적정가(숫자),
      "fair_price_max": 최대 적정가(숫자),
      "status": "적정|과다|저가|불명확",
      "note": "분석 코멘트 (100자 이내)"
    }
  ],
  "red_flags": [
    {
      "severity": "경고|주의|정보",
      "title": "항목명 (20자 이내)",
      "description": "상세 설명 (100자 이내)",
      "action": "권고 조치 (80자 이내)"
    }
  ],
  "negotiation": {
    "strategy": "전체 협상 전략 요약 (150자 이내)",
    "scripts": [
      {
        "topic": "협상 주제 (20자 이내)",
        "script": "실제 사용할 협상 멘트 (150자 이내)"
      }
    ],
    "target_price": 목표 협상가(숫자),
    "walkaway_price": 거절 기준가(숫자)
  },
  "contract_checklist": [
    {
      "item": "확인 항목 (30자 이내)",
      "required": true,
      "tip": "팁 (80자 이내)"
    }
  ],
  "missing_items": ["누락항목1", "누락항목2"],
  "overall_advice": "종합 조언 (200자 이내)"
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
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    response_text = message.content[0].text.strip()

    # stop_reason 확인 - max_tokens 도달 여부 로깅
    stop_reason = message.stop_reason
    if stop_reason == "max_tokens":
        logger.warning(f"응답이 max_tokens에 도달하여 잘렸습니다. 복구를 시도합니다.")

    # 코드블록 래핑 제거
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        response_text = "\n".join(lines[1:end]).strip()

    return _safe_parse(response_text)


def _safe_parse(text: str) -> dict:
    """
    JSON 파싱 3단계 전략:
    1. 직접 파싱
    2. _repair_json 후 파싱
    3. 최소 기본값 반환 (사용자에게 에러 노출 방지)
    """
    # 1단계: 직접 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2단계: 복구 후 파싱
    try:
        fixed = _repair_json(text)
        result = json.loads(fixed)
        logger.info("JSON 복구 성공")
        return result
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"JSON 복구 실패: {e}\n원본(앞 300자): {text[:300]}")

    # 3단계: 원본에서 summary만 추출 시도 후 기본값 반환
    partial = _extract_partial_summary(text)
    logger.warning("JSON 파싱 최종 실패 - 부분 결과 반환")
    return partial


def _repair_json(text: str) -> str:
    """
    잘린/손상된 JSON 복구 (스택 기반, 이스케이프 완전 처리).

    처리 순서:
    1. unterminated string → 해당 string 시작 직전의 마지막 구분자(콤마/여는괄호)로 잘라냄
    2. 값 없는 dangling key ("key": 로 끝나는 경우) 제거
    3. 꼬리 콤마 제거
    4. 스택으로 열린 괄호를 역순으로 닫기
    """
    import re

    text = text.strip()

    # ── 헬퍼: 문자열 상태 추적 스캔 ──────────────────────────────
    def scan(s):
        """각 위치에서 in_string 상태, 마지막 comma/open_bracket 위치, str_open_pos 반환"""
        in_str = False
        esc = False
        _str_open = -1
        _last_comma = -1
        _last_open = -1
        for i, ch in enumerate(s):
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                if in_str:
                    in_str = False
                else:
                    in_str = True
                    _str_open = i
                continue
            if in_str:
                continue
            if ch == ',':
                _last_comma = i
            elif ch in ('{', '['):
                _last_open = i
        return in_str, _str_open, _last_comma, _last_open

    # ── 1단계: unterminated string 처리 ──────────────────────────
    in_str, str_open, last_comma, last_open = scan(text)

    if in_str:
        # str_open 직전의 마지막 구분자(콤마 or 여는괄호)를 cut point로
        candidates = [p for p in (last_comma, last_open) if 0 <= p < str_open]
        cut_pos = max(candidates) if candidates else -1

        if cut_pos >= 0:
            if text[cut_pos] == ',':
                text = text[:cut_pos]           # 콤마 포함 이후 제거
            else:
                text = text[:cut_pos + 1]       # 여는괄호는 보존
        else:
            text = text[:str_open]              # 최후 수단

    # ── 2단계: 값 없는 dangling key 제거 ("key": 로 끝남) ─────────
    text = text.rstrip()
    # 예: ,"description":  또는  "title":
    text = re.sub(r',?\s*"(?:[^"\\]|\\.)*"\s*:\s*$', '', text)

    # ── 3단계: 꼬리 콤마 제거 ─────────────────────────────────────
    text = text.rstrip().rstrip(',').rstrip()

    # ── 4단계: 스택으로 열린 괄호를 역순 닫기 ─────────────────────
    stack = []
    in_str = False
    esc = False
    close_of = {'{': '}', '[': ']'}
    matching = {'}': '{', ']': '['}

    for ch in text:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch in ('}', ']'):
            if stack and stack[-1] == matching[ch]:
                stack.pop()

    text += ''.join(close_of[c] for c in reversed(stack))

    return text


def _extract_partial_summary(text: str) -> dict:
    """
    JSON 파싱이 완전히 실패한 경우 정규식으로 숫자 정보만 추출하여
    최소한의 응답 구조를 반환 (사용자에게 에러 대신 partial 결과 표시)
    """
    import re

    def find_num(pattern):
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                return None
        return None

    total_quoted = find_num(r'"total_quoted"\s*:\s*([\d,]+)')
    total_fair   = find_num(r'"total_fair"\s*:\s*([\d,]+)')
    overprice    = find_num(r'"overprice_rate"\s*:\s*([\d.]+)')

    risk_m = re.search(r'"risk_level"\s*:\s*"([^"]+)"', text)
    risk_level = risk_m.group(1) if risk_m else "분석 중 오류"

    one_m = re.search(r'"one_line"\s*:\s*"([^"]+)"', text)
    one_line = one_m.group(1) if one_m else "AI 응답이 길어 일부 내용만 표시됩니다. 다시 시도해 주세요."

    return {
        "summary": {
            "total_quoted": total_quoted,
            "total_fair": total_fair,
            "overprice_rate": overprice,
            "risk_level": risk_level,
            "one_line": one_line,
        },
        "items": [],
        "red_flags": [{
            "severity": "정보",
            "title": "분석 결과 일부 손실",
            "description": "AI 응답이 너무 길어 세부 항목을 불러오지 못했습니다.",
            "action": "파일을 다시 업로드하거나, 추가 정보를 줄여서 다시 시도해 주세요.",
        }],
        "negotiation": {"strategy": "", "scripts": [], "target_price": None, "walkaway_price": None},
        "contract_checklist": [],
        "missing_items": [],
        "overall_advice": "AI 응답 처리 중 오류가 발생했습니다. 동일한 파일로 다시 시도해 주세요.",
    }
