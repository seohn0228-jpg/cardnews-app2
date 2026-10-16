"""네이버 검색광고 API의 키워드 도구로 연관 키워드와 월간 검색량을 가져온다.

API 키 발급: https://searchad.naver.com → 도구 → API 사용 관리
필요한 값: API_KEY(액세스 라이선스), SECRET_KEY(비밀키), CUSTOMER_ID
"""

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://api.searchad.naver.com"
KEYWORD_TOOL_URI = "/keywordstool"


@dataclass
class KeywordStat:
    keyword: str
    pc: int
    mobile: int
    competition: str  # 낮음 / 중간 / 높음

    @property
    def total(self) -> int:
        return self.pc + self.mobile


class NaverKeywordError(Exception):
    pass


def _signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _to_int(value) -> int:
    # 검색량이 적으면 "< 10" 같은 문자열로 온다
    if isinstance(value, (int, float)):
        return int(value)
    return 5 if "<" in str(value) else int(str(value).replace(",", "") or 0)


def related_keywords(
    seeds: list[str], api_key: str, secret_key: str, customer_id: str, timeout: float = 10.0
) -> list[KeywordStat]:
    """씨앗 키워드(최대 5개)로 연관 키워드를 조회해 검색량 순으로 돌려준다."""
    # 키워드 도구는 공백이 들어간 키워드를 받지 않는다
    hints = [s.replace(" ", "") for s in seeds if s.strip()][:5]
    if not hints:
        return []

    timestamp = str(int(time.time() * 1000))
    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _signature(timestamp, "GET", KEYWORD_TOOL_URI, secret_key),
    }
    try:
        resp = requests.get(
            BASE_URL + KEYWORD_TOOL_URI,
            params={"hintKeywords": ",".join(hints), "showDetail": "1"},
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise NaverKeywordError(f"네이버 검색광고 API에 연결하지 못했습니다: {e}") from e

    if resp.status_code != 200:
        raise NaverKeywordError(f"네이버 검색광고 API 오류 ({resp.status_code}): {resp.text[:200]}")

    stats = [
        KeywordStat(
            keyword=row["relKeyword"],
            pc=_to_int(row.get("monthlyPcQcCnt", 0)),
            mobile=_to_int(row.get("monthlyMobileQcCnt", 0)),
            competition=row.get("compIdx", ""),
        )
        for row in resp.json().get("keywordList", [])
    ]
    stats.sort(key=lambda s: s.total, reverse=True)
    return stats


def pick_keywords(stats: list[KeywordStat], product_words: list[str], limit: int = 15) -> list[KeywordStat]:
    """상품과 관련 있는 키워드만 남긴다.

    검색량이 너무 큰 대표 키워드는 상위 노출이 어려우므로,
    상품 단어가 들어간 키워드를 앞에 두고 그다음 검색량 순으로 채운다.
    """
    words = [w.replace(" ", "") for w in product_words if len(w.strip()) >= 2]
    related = [s for s in stats if any(w in s.keyword for w in words)]
    others = [s for s in stats if s not in related]
    return (related + others)[:limit]
