"""Claude로 상품을 분석하고 네이버 블로그 원고를 쓴다."""

import base64
import json

import anthropic

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# 쇼핑커넥트 대가성 문구. 본문 맨 위에 항상 들어간다.
DISCLOSURE = "이 포스팅은 네이버 쇼핑 커넥트 활동의 일환으로, 판매 발생 시 수수료를 제공받습니다."


class WriterError(Exception):
    pass


def _media_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return None


def _image_blocks(images: list[bytes], limit: int = 4) -> list[dict]:
    blocks = []
    for data in images:
        media_type = _media_type(data)
        if not media_type or len(data) > 5 * 1024 * 1024:
            continue
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()},
        })
        if len(blocks) >= limit:
            break
    return blocks


def _call_json(client: anthropic.Anthropic, system: str, content: list[dict], schema: dict, effort: str) -> dict:
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=32000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=system,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise WriterError("AI가 이 요청을 처리하지 않았습니다. 상품 정보를 확인해 주세요.")
    if response.stop_reason == "max_tokens":
        raise WriterError("글이 너무 길어 중간에 끊겼습니다. 다시 시도해 주세요.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise WriterError("AI 응답을 해석하지 못했습니다. 다시 시도해 주세요.") from e


# ---------------------------------------------------------------- 1단계: 상품 분석

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": "string", "description": "브랜드+제품명, 짧게"},
        "category": {"type": "string"},
        "seed_keywords": {
            "type": "array", "items": {"type": "string"},
            "description": "네이버에서 사람들이 이 상품을 찾을 때 검색할 만한 짧은 키워드 5개",
        },
        "benefits": {
            "type": "array", "items": {"type": "string"},
            "description": "상세페이지/사진에서 확인되는 장점. 근거 없는 내용 금지",
        },
        "specs": {"type": "array", "items": {"type": "string"}, "description": "용량, 크기, 소재 등 사실 정보"},
        "target_readers": {"type": "array", "items": {"type": "string"}, "description": "이 상품이 필요한 사람 유형"},
        "cautions": {"type": "array", "items": {"type": "string"}, "description": "구매 전 알아둘 점, 아쉬울 수 있는 점"},
        "photo_notes": {
            "type": "array", "items": {"type": "string"},
            "description": "전달받은 사진 순서대로, 각 사진에 무엇이 보이는지 한 줄씩",
        },
    },
    "required": ["product_name", "category", "seed_keywords", "benefits", "specs", "target_readers", "cautions", "photo_notes"],
    "additionalProperties": False,
}


def analyze_product(client: anthropic.Anthropic, title: str, description: str, price: str, images: list[bytes]) -> dict:
    text = (
        "아래 상품 정보와 사진을 보고 블로그 글을 쓰기 위한 재료를 정리해 줘.\n"
        "사진이나 설명에서 확인되지 않는 장점은 절대 만들어 내지 마.\n\n"
        f"[상품명] {title or '(없음)'}\n[가격] {price or '(없음)'}\n[상품 설명]\n{description or '(없음)'}"
    )
    content = _image_blocks(images) + [{"type": "text", "text": text}]
    return _call_json(
        client,
        system="너는 상세페이지를 꼼꼼하게 읽는 쇼핑 리서처다. 사실만 정리한다.",
        content=content,
        schema=ANALYZE_SCHEMA,
        effort="medium",
    )


# ---------------------------------------------------------------- 2단계: 원고 작성

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {
            "type": "array", "items": {"type": "string"},
            "description": "제목 후보 3개. 메인 키워드를 앞쪽에, 25~35자",
        },
        "body": {
            "type": "string",
            "description": "본문. 소제목은 '## '로 시작, 사진 자리는 따로 한 줄에 [사진N] 형식",
        },
        "photo_guide": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "marker": {"type": "string", "description": "[사진1] 처럼 본문에 쓴 표시"},
                    "photo_number": {"type": "integer", "description": "업로드 사진 번호(1부터)"},
                    "why": {"type": "string", "description": "이 자리에 이 사진을 넣는 이유"},
                    "caption": {"type": "string", "description": "사진 아래 짧은 설명, 키워드 자연스럽게 포함"},
                },
                "required": ["marker", "photo_number", "why", "caption"],
                "additionalProperties": False,
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}, "description": "# 없이 태그 10개"},
    },
    "required": ["titles", "body", "photo_guide", "tags"],
    "additionalProperties": False,
}

STYLE_GUIDE = """너는 10년 동안 네이버 블로그를 운영해 온 생활형 블로거다. 이웃에게 말하듯 쓴다.

[사람 냄새 나는 글 규칙]
- 문장 길이를 섞는다. 짧게 끊는 문장 사이에 가끔 긴 문장.
- 블로그 구어체: "~더라고요", "~거든요", "솔직히", "이게 은근", "저만 그런 거 아니죠?" 같은 표현을 과하지 않게.
- 첫 문단은 공감되는 상황이나 고민으로 시작한다. 상품 이름부터 들이밀지 않는다.
- 장점만 늘어놓지 말고 아쉬운 점이나 이런 분께는 안 맞는다는 이야기를 하나 이상 넣는다. 그래야 믿음이 간다.
- 숫자, 용량, 크기 같은 구체적인 정보를 섞는다(받은 자료에 있는 것만).
- 문단은 2~4줄로 짧게. 모바일에서 읽기 편하게 줄바꿈을 자주 한다.
- 이모티콘은 글 전체에서 3~5개 정도만.

[절대 쓰지 말 것 - AI 티 나는 표현]
- "오늘은 ~에 대해 알아보겠습니다", "결론적으로", "요약하자면", "~하는 것이 중요합니다", "다양한", "효과적인", "완벽한", "혁신적인"
- 모든 문단이 같은 길이, 같은 구조
- 번호 목록이나 글머리표만으로 채운 본문 (스펙 정리 한 군데 정도만 허용)
- 과장된 감탄사 남발, "강력 추천" 반복

[정직하게 쓰기 - 반드시 지킬 것]
- 사용 후기 메모가 주어지면 그 경험을 중심으로 1인칭으로 쓴다. 메모에 없는 경험은 지어내지 않는다.
- 메모가 없으면 "직접 써본 척"을 하지 않는다. 대신 "알아보고 비교해 본 사람" 시점으로 쓴다
  (예: "상세페이지를 꼼꼼히 봤는데", "후기들 보니까 공통적으로", "제가 이걸 고른 이유는").
- 자료에 없는 효능, 수치, 수상 경력, 판매량은 만들지 않는다. 의학적 효과를 단정하지 않는다.

[네이버 검색 노출 규칙]
- 메인 키워드는 제목 앞쪽에 1번, 첫 문단에 1번, 본문 전체에 4~6번 자연스럽게. 억지 반복 금지.
- 서브 키워드는 소제목과 본문에 1~2번씩 나눠서.
- 본문은 공백 포함 1,800~2,500자. 소제목(## ) 4~6개.
- 사진은 본문 사이사이에 고르게. 소제목 바로 아래나 설명하는 내용 바로 옆에 둔다.
- 제목은 후킹되게: 궁금증, 비교, 숫자, 솔직함 중 하나를 쓴다. 낚시성 거짓 제목은 금지.
- 마지막은 부담 없이 마무리하고 상품 링크 위치를 [상품 링크] 한 줄로 표시한다.
"""


def write_post(
    client: anthropic.Anthropic,
    analysis: dict,
    main_keyword: str,
    sub_keywords: list[str],
    photo_count: int,
    experience_memo: str,
    tone: str,
) -> dict:
    memo = experience_memo.strip() or "(없음 - 직접 써본 척 하지 말고 '알아본 사람' 시점으로)"
    text = f"""아래 재료로 네이버 블로그 쇼핑 글을 써 줘.

[상품 분석]
{json.dumps(analysis, ensure_ascii=False, indent=2)}

[메인 키워드] {main_keyword}
[서브 키워드] {", ".join(sub_keywords) or "(없음)"}
[사용할 수 있는 사진 수] {photo_count}장 (사진 번호는 1~{photo_count}, 사진 설명은 분석의 photo_notes 순서와 같음)
[글 분위기] {tone}
[내 사용 후기 메모]
{memo}

대가성 문구는 프로그램이 따로 넣으니 본문에 쓰지 마."""
    return _call_json(
        client,
        system=STYLE_GUIDE,
        content=[{"type": "text", "text": text}],
        schema=POST_SCHEMA,
        effort="high",
    )


def make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
