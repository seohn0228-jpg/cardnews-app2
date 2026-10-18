"""글마다 구성·도입·마무리·말투를 다르게 고른다.

최근 글(posts/*/style.json)에서 쓴 조합은 피해서 고르고, 고른 결과를 $P/style.json에 저장한다.
어떤 구성을 고르든 SEO 규칙(제목 키워드, 소제목 수, 장단점, 링크 안내 3곳, 사진 4~5장)은 그대로 지킨다.

사용법: python3 pick_style.py posts/<폴더>
"""

import json
import random
import sys
from pathlib import Path

STRUCTURES = {
    "문제해결형": {
        "흐름": "독자의 불편/고민 → 왜 그런지 → 이 상품이 그걸 푸는 방식(2~3개) → 그래도 남는 한계 → 누구에게 맞는지",
        "소제목 예": ["~때문에 고민이었다면", "원인은 의외로 ~", "이 제품이 다른 점", "그래도 이건 감안해야 해요", "결국 이런 분께"],
    },
    "비교기준형": {
        "흐름": "이 종류 고를 때 봐야 할 기준 3~4개를 먼저 제시 → 기준마다 이 상품은 어떤지 → 다른 선택지가 나은 경우",
        "소제목 예": ["~ 고를 때 이 3가지만 보세요", "기준 1. ~", "기준 2. ~", "기준 3. ~", "이런 경우엔 다른 제품이 나아요"],
    },
    "질문답변형": {
        "흐름": "소제목을 사람들이 실제로 검색할 질문으로 쓴다(4~6개). 각 질문에 짧고 분명하게 답한다. 단점도 질문 하나로 다룬다",
        "소제목 예": ["~ 진짜 ~할까?", "~는 얼마나 들어요?", "~ 단점은 없나요?", "~ 세탁/관리는 어떻게?", "누가 사면 후회 안 할까?"],
    },
    "체크리스트형": {
        "흐름": "사기 전에 확인할 것 N가지를 번호 소제목으로. 항목마다 이 상품의 답을 붙인다. 마지막 항목은 아쉬운 점",
        "소제목 예": ["사기 전 체크 1. ~", "체크 2. ~", "체크 3. ~", "체크 4. 아쉬운 점", "체크 결과 정리"],
    },
    "장면스토리형": {
        "흐름": "쓰는 장면 순서로(예: 퇴근 후 → 잠들기 전 → 아침, 또는 집 → 캠핑). 장면마다 관련 기능을 자연스럽게 녹인다. 아쉬운 장면도 하나",
        "소제목 예": ["퇴근하고 소파에 앉았을 때", "잠들기 전 10분", "다음 날 아침 정리", "이 장면에선 아쉬웠어요", "이런 하루라면 잘 맞아요"],
    },
    "요약먼저형": {
        "흐름": "첫 소제목에 3줄 핵심 요약(장점 2 + 아쉬운 점 1)을 먼저 보여 주고, 아래에서 하나씩 자세히 풀기",
        "소제목 예": ["바쁜 분들을 위한 3줄 요약", "장점 1 자세히", "장점 2 자세히", "아쉬운 점 자세히", "총평"],
    },
}

INTROS = {
    "질문으로 시작": "독자에게 바로 묻는 질문 한 줄로 시작 (예: '~할 때 제일 짜증나는 게 뭐세요?')",
    "장면 묘사": "구체적인 순간을 그림처럼 묘사하며 시작 (시간, 장소, 몸의 느낌)",
    "숫자로 시작": "상품 자료에 있는 숫자(가격, 크기, 시간, 전기료 등) 하나로 첫 줄을 연다",
    "흔한 오해 깨기": "'~하면 다 똑같다고 생각했는데' 처럼 흔한 생각을 뒤집으며 시작",
    "결론 먼저": "첫 문단에서 이 글의 결론(누구에게 맞는지)을 먼저 말하고 이유를 풀어 간다",
}

CLOSINGS = {
    "한 줄 총평": "마지막에 한 문장으로 딱 정리 (예: '~만 괜찮다면 충분히 값어치 하는 선택')",
    "추천/비추천 정리": "'이런 분은 사세요 / 이런 분은 다시 생각해 보세요'를 두세 줄씩",
    "구매 팁": "언제·어떤 옵션으로 사면 좋은지 실용 팁으로 마무리 (사이즈, 색상, 할인 타이밍 등 자료 범위 안에서)",
    "구체적 질문 던지기": "독자에게 구체적 질문을 하나 던지며 끝 (예: '여러분은 ~파세요, ~파세요?'). '궁금한 점은 댓글로' 같은 상투구는 금지",
}

TONES = {
    "친근 수다형": "친구한테 말하듯, 감탄과 구어체를 조금 더",
    "차분 정보형": "존댓말 기본, 감탄 적게, 정보 밀도 높게",
    "짧고 단호형": "짧은 문장 위주, 결론을 분명하게, 군더더기 없이",
}


def recent_styles(posts_root: Path, current: Path, n: int = 3) -> list[dict]:
    found = []
    for d in sorted(posts_root.iterdir(), reverse=True):
        if d.resolve() == current.resolve() or not (d / "style.json").exists():
            continue
        found.append(json.loads((d / "style.json").read_text(encoding="utf-8")))
        if len(found) >= n:
            break
    return found


def pick(options: dict, avoid: set, rng: random.Random) -> str:
    keys = [k for k in options if k not in avoid] or list(options)
    return rng.choice(keys)


def main() -> int:
    post_dir = Path(sys.argv[1])
    post_dir.mkdir(parents=True, exist_ok=True)
    recent = recent_styles(post_dir.parent, post_dir)
    rng = random.Random()
    style = {
        "구성": pick(STRUCTURES, {r.get("구성") for r in recent}, rng),
        "도입": pick(INTROS, {r.get("도입") for r in recent}, rng),
        "마무리": pick(CLOSINGS, {r.get("마무리") for r in recent[:2]}, rng),
        "말투": pick(TONES, {r.get("말투") for r in recent[:1]}, rng),
    }
    (post_dir / "style.json").write_text(json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8")
    guide = {
        **style,
        "구성 흐름": STRUCTURES[style["구성"]]["흐름"],
        "소제목 예(그대로 쓰지 말고 상품에 맞게 새로)": STRUCTURES[style["구성"]]["소제목 예"],
        "도입 방법": INTROS[style["도입"]],
        "마무리 방법": CLOSINGS[style["마무리"]],
        "말투 방법": TONES[style["말투"]],
        "최근 글에서 쓴 조합(피함)": recent,
    }
    print(json.dumps(guide, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
