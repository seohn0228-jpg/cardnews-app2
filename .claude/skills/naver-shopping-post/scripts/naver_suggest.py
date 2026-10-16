"""네이버 자동완성 검색어로 키워드 후보를 모은다 (API 키 불필요).

공식 API가 아니어서 네이버가 막으면 동작하지 않을 수 있다.
그럴 때는 SKILL.md의 '키워드를 못 가져올 때' 절차를 따른다.

사용법: python3 naver_suggest.py 전동칫솔 "전동칫솔 추천"
"""

import json
import sys

import requests

AC_URL = "https://ac.search.naver.com/nx/ac"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.naver.com/",
}
# 씨앗 키워드 뒤에 붙여서 롱테일 키워드를 더 끌어낸다
SUFFIXES = ["", " 추천", " 후기", " 단점", " 비교", " 가성비"]


def suggest(query: str, timeout: float = 5.0) -> list[str]:
    params = {
        "q": query, "con": "1", "frm": "nv", "ans": "2", "r_format": "json",
        "r_enc": "UTF-8", "r_unicode": "0", "t_koreng": "1", "run": "2", "rev": "4",
        "q_enc": "UTF-8", "st": "100",
    }
    resp = requests.get(AC_URL, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [row[0] for group in items for row in group if row]


def collect(seeds: list[str]) -> dict:
    """키워드별 등장 횟수와 가장 앞선 순위를 기록한다.

    여러 질의의 자동완성에 자주, 앞쪽에 나오는 키워드일수록
    사람들이 실제로 많이 치는 키워드로 본다.
    """
    stats: dict[str, dict] = {}
    errors = []
    for seed in seeds:
        for suffix in SUFFIXES:
            query = seed + suffix
            try:
                results = suggest(query)
            except requests.RequestException as e:
                errors.append(f"{query}: {e}")
                continue
            for rank, kw in enumerate(results, start=1):
                s = stats.setdefault(kw, {"keyword": kw, "hits": 0, "best_rank": rank})
                s["hits"] += 1
                s["best_rank"] = min(s["best_rank"], rank)

    ranked = sorted(stats.values(), key=lambda s: (-s["hits"], s["best_rank"]))
    return {"keywords": ranked[:40], "errors": errors}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    result = collect(sys.argv[1:])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if not result["keywords"] else 0)
