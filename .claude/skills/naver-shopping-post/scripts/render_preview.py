"""post.md와 photos/를 합쳐 사진이 본문 제자리에 들어간 미리보기 페이지(preview.html)를 만든다.

- [사진N] 또는 [사진N: 캡션] 자리에 photos/photo_NN.* 파일을 넣는다.
- 사진은 폭 900px JPEG로 줄여 페이지 안에 넣는다(외부 파일 없이 한 파일로 동작).
- 페이지에서 '본문 복사(사진 포함)'를 누르면 글과 사진이 서식 그대로 클립보드에 담긴다.

사용법: python3 render_preview.py posts/<폴더> --link https://naver.me/xxxx
"""

import argparse
import base64
import html
import io
import re
import sys
from pathlib import Path

from PIL import Image

PHOTO_RE = re.compile(r"^\[사진\s*(\d+)\s*(?::\s*(.*?))?\]\s*$")
LINK_RE = re.compile(r"^\[상품\s*링크\s*(?::\s*(.*?))?\]\s*$")
MAX_WIDTH = 900


def photo_data_uri(photos_dir: Path, n: int) -> str | None:
    matches = sorted(photos_dir.glob(f"photo_{n:02d}.*"))
    if not matches:
        return None
    im = Image.open(matches[0])
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, "white")
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def inline(text: str) -> str:
    return html.escape(text)


def render_body(lines: list[str], photos_dir: Path, link: str) -> tuple[str, list[str]]:
    """본문 줄들을 HTML로 바꾼다. 빠진 사진 번호 목록도 함께 돌려준다."""
    out, missing = [], []
    para: list[str] = []
    list_items: list[str] = []
    list_tag = ""

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(inline(l) for l in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal list_tag
        if list_items:
            out.append(f"<{list_tag}>" + "".join(f"<li>{inline(i)}</li>" for i in list_items) + f"</{list_tag}>")
            list_items.clear()
            list_tag = ""

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        photo = PHOTO_RE.match(stripped)
        ul = re.match(r"^[-*]\s+(.*)", stripped)
        ol = re.match(r"^\d+\.\s+(.*)", stripped)

        if not stripped:
            flush_para(); flush_list()
        elif photo:
            flush_para(); flush_list()
            n, caption = int(photo.group(1)), (photo.group(2) or "").strip()
            uri = photo_data_uri(photos_dir, n)
            if uri is None:
                missing.append(n)
                out.append(f'<p class="missing">[사진{n}] 파일이 없습니다</p>')
                continue
            cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
            alt = inline(caption or f"사진 {n}")
            out.append(f'<figure data-n="{n}"><img src="{uri}" alt="{alt}">{cap}</figure>')
        elif LINK_RE.match(stripped):
            flush_para(); flush_list()
            label = (LINK_RE.match(stripped).group(1) or "").strip() or "👉 상품 페이지 바로가기"
            safe = html.escape(link, quote=True)
            out.append(f'<p class="product-link"><a href="{safe}" target="_blank" rel="noopener"><b>{inline(label)}</b></a></p>')
        elif stripped.startswith("## "):
            flush_para(); flush_list()
            out.append(f"<h2>{inline(stripped[3:])}</h2>")
        elif ul or ol:
            flush_para()
            tag = "ul" if ul else "ol"
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag
            list_items.append((ul or ol).group(1))
        else:
            flush_list()
            para.append(stripped)
    flush_para(); flush_list()
    return "\n".join(out), missing


PAGE = """<title>__TITLE_SHORT__</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&family=Gowun+Batang:wght@700&display=swap">
<style>
/* 레이아웃: 위에는 발행 도구(복사 버튼, 순서), 아래에는 실제 블로그처럼 보이는 원고 한 단 */
:root {
  --bg: #f3f5f2; --paper: #ffffff; --ink: #1d2320; --muted: #5f6b65;
  --line: #dde3df; --accent: #1f7a53; --accent-ink: #ffffff; --soft: #e6f1eb;
  --display: "Gowun Batang", "Nanum Myeongjo", serif;
  --body: "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121614; --paper: #1a1f1c; --ink: #e8ece9; --muted: #9aa8a0;
  --line: #2c3530; --accent: #4cc08a; --accent-ink: #0d1a13; --soft: #1f2d26; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #121614; --paper: #1a1f1c; --ink: #e8ece9; --muted: #9aa8a0;
  --line: #2c3530; --accent: #4cc08a; --accent-ink: #0d1a13; --soft: #1f2d26; color-scheme: dark }
* { box-sizing: border-box }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.75;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 20px 48px }
.wrap { max-width: 720px; margin: 0 auto; display: grid; gap: 20px }
.tools { background: var(--paper); border: 1px solid var(--line); border-radius: 12px; padding: 18px; display: grid; gap: 14px }
.tools h1 { font-size: 15px; margin: 0; color: var(--muted); font-weight: 500; letter-spacing: .02em }
.row { display: flex; flex-wrap: wrap; gap: 8px }
button { font: inherit; font-size: 15px; border-radius: 8px; padding: 10px 14px; cursor: pointer; border: 1px solid var(--line); background: var(--paper); color: var(--ink) }
button.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 700 }
button:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px }
.status { min-height: 1.5em; font-size: 14px; color: var(--accent); margin: 0 }
.steps { margin: 0; padding-left: 1.3em; color: var(--muted); font-size: 14px; line-height: 1.7 }
.steps b { color: var(--ink) }
article { background: var(--paper); border: 1px solid var(--line); border-radius: 12px; padding: 28px clamp(16px, 5vw, 44px) 36px; min-width: 0 }
.post-title { font-family: var(--display); font-size: clamp(22px, 5.4vw, 30px); line-height: 1.4; margin: 0 0 22px; text-wrap: balance }
article p { margin: 0 0 1.1em }
article h2 { font-size: 19px; margin: 1.9em 0 .7em; padding-bottom: 6px; border-bottom: 2px solid var(--soft) }
article ul, article ol { margin: 0 0 1.1em; padding-left: 1.3em }
figure { margin: 1.4em 0; text-align: center }
figure img { width: 100%; max-width: 100%; height: auto; border-radius: 6px; display: block }
figcaption { font-size: 14px; color: var(--muted); margin-top: 8px }
.disclosure { font-size: 14px; color: var(--muted); background: var(--soft); border-radius: 8px; padding: 10px 12px }
.product-link { margin: 1.4em 0; text-align: center }
.product-link a { display: inline-block; color: var(--accent); background: var(--soft); border-radius: 8px; padding: 10px 16px; text-decoration: none; word-break: keep-all }
.missing { color: #c0392b }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 26px }
.tags span { background: var(--soft); border-radius: 999px; padding: 3px 10px; font-size: 14px }
@media (prefers-reduced-motion: no-preference) { button { transition: filter .15s } button:hover { filter: brightness(1.05) } }
</style>

<div class="wrap">
  <section class="tools" aria-label="발행 도구">
    <h1>발행 준비 · 사진 __PHOTO_COUNT__장 배치 완료</h1>
    <div class="row">
      <button class="primary" id="copy-body" type="button">본문 복사 (사진 포함)</button>
      <button id="copy-title" type="button">제목 복사</button>
      <button id="copy-tags" type="button">태그 복사</button>
      <button id="copy-link" type="button">상품 링크 복사</button>
    </div>
    <p class="status" id="status" role="status"></p>
    <ol class="steps">
      <li><b>PC</b>: 블로그 글쓰기를 열고 제목 복사 → 붙여넣기, 본문 복사 → 본문에 붙여넣기. 사진이 같이 들어가는지 확인하세요.</li>
      <li><b>사진이 빠지면</b>: 아래 원고의 사진을 길게 누르거나 우클릭해 저장한 뒤, 같은 자리에 넣으면 됩니다.</li>
      <li>본문의 👉 링크 안내 __CTA_COUNT__곳에 상품 링크가 걸렸는지 확인하세요. 안 걸렸으면 문구를 선택하고 '상품 링크 복사'로 링크를 넣으면 돼요.</li>
      <li>태그를 붙여넣고 <b>발행은 직접</b> 눌러 주세요.</li>
    </ol>
  </section>

  <article id="post">
    <h1 class="post-title" id="post-title">__TITLE__</h1>
    <div id="post-body">
__BODY__
    </div>
    <div class="tags" aria-label="태그">__TAG_CHIPS__</div>
  </article>
</div>

<script>
const TAGS = __TAGS_JSON__;
const LINK = __LINK_JSON__;
const statusEl = document.getElementById("status");
function say(msg) { statusEl.textContent = msg; }

async function copyText(text, label) {
  try { await navigator.clipboard.writeText(text); say(label + " 복사됨"); }
  catch (e) { selectNode(null, text); say("자동 복사가 막혀 있어요. 선택된 글자를 직접 복사해 주세요."); }
}
function selectNode(node, text) {
  const sel = window.getSelection(); sel.removeAllRanges();
  let target = node;
  if (!target) { target = document.createElement("textarea"); target.value = text; document.body.appendChild(target); target.select(); return; }
  const range = document.createRange(); range.selectNodeContents(target); sel.addRange(range);
}

document.getElementById("copy-title").addEventListener("click", () => copyText(document.getElementById("post-title").textContent, "제목"));
document.getElementById("copy-tags").addEventListener("click", () => copyText(TAGS.map(t => "#" + t).join(" "), "태그"));
document.getElementById("copy-link").addEventListener("click", () => copyText(LINK, "상품 링크"));

document.getElementById("copy-body").addEventListener("click", async () => {
  const body = document.getElementById("post-body");
  const htmlText = body.innerHTML;
  const plain = body.innerText;
  try {
    if (!window.ClipboardItem) throw new Error("no ClipboardItem");
    await navigator.clipboard.write([new ClipboardItem({
      "text/html": new Blob([htmlText], { type: "text/html" }),
      "text/plain": new Blob([plain], { type: "text/plain" }),
    })]);
    say("본문 복사됨 (사진 포함). 블로그 본문에 붙여넣어 보세요.");
  } catch (e) {
    selectNode(body);
    try { if (document.execCommand("copy")) { say("본문 복사됨 (사진 포함). 블로그 본문에 붙여넣어 보세요."); return; } } catch (_) {}
    say("자동 복사가 막혀 있어요. 원고가 선택돼 있으니 직접 복사해 주세요.");
  }
});
</script>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("post_dir")
    parser.add_argument("--link", default="")
    args = parser.parse_args()

    post_dir = Path(args.post_dir)
    lines = (post_dir / "post.md").read_text(encoding="utf-8").splitlines()

    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    tag_idx = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("태그")), None)
    tags = re.findall(r"#(\S+)", lines[tag_idx]) if tag_idx is not None else []
    body_lines = [l for i, l in enumerate(lines) if not l.startswith("# ") and i != tag_idx]

    body, missing = render_body(body_lines, post_dir / "photos", args.link or "[상품 링크]")
    body = body.replace("<p>이 포스팅은", '<p class="disclosure">이 포스팅은', 1)
    photo_count = body.count("<figure")
    cta_count = body.count('class="product-link"')

    import json
    page = (PAGE
            .replace("__TITLE_SHORT__", html.escape(title.split(",")[0][:30] or "블로그 원고"))
            .replace("__TITLE__", html.escape(title))
            .replace("__PHOTO_COUNT__", str(photo_count))
            .replace("__CTA_COUNT__", str(cta_count))
            .replace("__TAG_CHIPS__", "".join(f"<span>#{html.escape(t)}</span>" for t in tags))
            .replace("__TAGS_JSON__", json.dumps(tags, ensure_ascii=False))
            .replace("__LINK_JSON__", json.dumps(args.link, ensure_ascii=False))
            .replace("__BODY__", body))
    out = post_dir / "preview.html"
    out.write_text(page, encoding="utf-8")
    print(f"{out} ({out.stat().st_size / 1024 / 1024:.1f}MB, 사진 {photo_count}장)")
    if missing:
        print(f"빠진 사진 번호: {missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
