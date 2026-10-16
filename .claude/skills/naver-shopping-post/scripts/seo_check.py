"""완성된 원고(post.md)를 네이버 블로그 기준으로 점검한다.

네이버는 검색 순위 공식을 공개하지 않는다(C-Rank, D.I.A. 등).
아래 기준은 공개 가이드와 블로거들 사이의 통설을 정리한 것이라 '권장값'이다.

post.md 형식:
    # 제목
    (대가성 문구)
    본문... 소제목은 '## ', 사진 자리는 한 줄에 [사진N]
    ...
    태그: #태그1 #태그2 ...

사용법: python3 seo_check.py post.md --keyword "메인 키워드" --sub "서브1,서브2"
"""

import argparse
import json
import re
import sys
from pathlib import Path

DISCLOSURE_HINTS = ["수수료를 제공받", "쇼핑 커넥트 활동", "쇼핑커넥트 활동"]
AI_PHRASES = [
    "알아보겠습니다", "결론적으로", "요약하자면", "것이 중요합니다", "다양한", "효과적인",
    "완벽한", "혁신적인", "살펴보겠습니다", "마무리하자면", "에 대해 알아", "도움이 되셨기를",
]
PHOTO_RE = re.compile(r"^\[사진\s*(\d+)[^\]]*\]\s*$")
LINK_RE = re.compile(r"^\[상품\s*링크[^\]]*\]\s*$")


def parse(text: str) -> dict:
    lines = text.splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    tag_idx = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("태그")), None)
    tags = re.findall(r"#(\S+)", lines[tag_idx]) if tag_idx is not None else []
    body_lines = [l for i, l in enumerate(lines) if not l.startswith("# ") and i != tag_idx]
    headings = [l for l in body_lines if l.startswith("## ")]
    photos = [l for l in body_lines if PHOTO_RE.match(l.strip())]
    links = [l for l in body_lines if LINK_RE.match(l.strip())]
    prose = "\n".join(
        l for l in body_lines
        if not l.startswith("## ") and not PHOTO_RE.match(l.strip()) and not LINK_RE.match(l.strip())
    )
    return {"title": title, "tags": tags, "headings": headings, "photos": photos, "links": links,
            "prose": prose, "lines": body_lines}


def check(text: str, keyword: str, subs: list[str]) -> list[dict]:
    p = parse(text)
    results = []

    def add(name, ok, detail, level="필수"):
        results.append({"항목": name, "결과": "통과" if ok else ("확인" if level == "권장" else "수정 필요"), "내용": detail})

    title = p["title"]
    add("제목 길이", 20 <= len(title) <= 40, f"{len(title)}자 (권장 20~40자)", "권장")
    kw_pos = title.replace(" ", "").find(keyword.replace(" ", ""))
    add("제목에 메인 키워드", kw_pos >= 0, "포함" if kw_pos >= 0 else "제목에 메인 키워드가 없습니다")
    if kw_pos >= 0:
        add("메인 키워드 위치", kw_pos <= 10, f"앞에서 {kw_pos}번째 글자 (앞쪽일수록 좋음)", "권장")

    head = "\n".join(p["lines"][:6])
    add("대가성 문구(상단)", any(h in head for h in DISCLOSURE_HINTS), "본문 맨 위에 수수료 안내가 있어야 합니다")

    length = len(p["prose"].replace("\n", ""))
    add("본문 길이", 1500 <= length <= 3500, f"공백 포함 {length:,}자 (권장 1,500~3,500자)", "권장")

    count = p["prose"].replace(" ", "").count(keyword.replace(" ", ""))
    add("메인 키워드 반복", 3 <= count <= 8, f"{count}회 (권장 3~8회, 너무 많으면 어뷰징으로 보일 수 있음)", "권장")

    first_para = next((b for b in p["prose"].split("\n\n") if b.strip() and not any(h in b for h in DISCLOSURE_HINTS)), "")
    add("첫 문단에 메인 키워드", keyword.replace(" ", "") in first_para.replace(" ", ""), "도입부에 한 번 넣는 것을 권장", "권장")

    for sub in subs:
        n = p["prose"].replace(" ", "").count(sub.replace(" ", ""))
        add(f"서브 키워드 '{sub}'", n >= 1, f"{n}회", "권장")

    add("소제목 수", 3 <= len(p["headings"]) <= 7, f"{len(p['headings'])}개 (권장 3~7개)", "권장")
    add("사진 수", len(p["photos"]) >= 4, f"{len(p['photos'])}장 (권장 4장 이상, 직접 찍은 사진이 가장 좋음)", "권장")
    add("상품 링크 안내", 2 <= len(p["links"]) <= 4, f"{len(p['links'])}곳 (권장 3곳: 소개 직후, 가격/단점 직후, 마지막)", "권장")
    labels = [LINK_RE.match(l.strip()) and l.strip() for l in p["links"]]
    if len(labels) != len(set(labels)):
        add("링크 안내 문구 중복", False, "같은 문구가 반복됩니다. 위치마다 다르게 써 주세요", "권장")
    add("태그 수", 5 <= len(p["tags"]) <= 30, f"{len(p['tags'])}개 (권장 10개 안팎, 최대 30개)", "권장")

    found = [ph for ph in AI_PHRASES if ph in p["prose"]]
    add("AI 티 나는 표현", not found, ", ".join(found) if found else "없음")

    paras = [b for b in p["prose"].split("\n\n") if b.strip()]
    long_paras = [b for b in paras if len(b) > 250]
    add("긴 문단", not long_paras, f"250자 넘는 문단 {len(long_paras)}개 (모바일에서 읽기 힘듦)", "권장")

    endings = re.findall(r"(니다|요|죠|다)[.!?]", p["prose"])
    if endings:
        formal = endings.count("니다") / len(endings)
        add("말투 다양성", formal < 0.5, f"'~니다' 비율 {formal:.0%} (높으면 딱딱하고 AI처럼 느껴짐)", "권장")

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("post")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--sub", default="")
    args = parser.parse_args()

    text = Path(args.post).read_text(encoding="utf-8")
    subs = [s.strip() for s in args.sub.split(",") if s.strip()]
    results = check(text, args.keyword, subs)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(r["결과"] == "수정 필요" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
