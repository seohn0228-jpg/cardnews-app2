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


def render_body(lines: list[str], photos_dir: Path, link: str, photo_urls: dict[int, str] | None = None) -> tuple[str, list[str]]:
    """본문 줄들을 HTML로 바꾼다. 빠진 사진 번호 목록도 함께 돌려준다."""
    out, missing = [], []
    para: list[str] = []
    list_items: list[str] = []
    list_tag = ""

    def flush_para():
        if para:
            out.append('<p style="text-align:center">' + "<br>".join(inline(l) for l in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal list_tag
        if list_items:
            out.append(f'<{list_tag} style="text-align:center;list-style-position:inside;padding-left:0">' + "".join(f"<li>{inline(i)}</li>" for i in list_items) + f"</{list_tag}>")
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
            src_attr = f' data-src="{html.escape(photo_urls[n], quote=True)}"' if photo_urls and n in photo_urls else ""
            out.append(f'<figure data-n="{n}"{src_attr} data-caption="{html.escape(caption, quote=True)}"><img src="{uri}" alt="{alt}">{cap}</figure>'
                       f'<button class="save-photo" type="button" data-n="{n}" hidden>사진 {n} 저장</button>')
        elif LINK_RE.match(stripped):
            flush_para(); flush_list()
            label = (LINK_RE.match(stripped).group(1) or "").strip() or "👉 상품 페이지 바로가기"
            safe = html.escape(link, quote=True)
            # 네이버 에디터는 붙여넣을 때 글자에 걸린 링크를 지우는 경우가 많다.
            # 주소를 글자 그대로 한 줄 넣어 두면 에디터가 알아서 링크로 바꿔 준다.
            out.append(f'<p class="product-link" style="text-align:center"><b>{inline(label)}</b><br>'
                       f'<a href="{safe}" target="_blank" rel="noopener">{inline(link)}</a></p>')
        elif stripped.startswith("## "):
            flush_para(); flush_list()
            out.append(f'<h2 style="text-align:center">{inline(stripped[3:])}</h2>')
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
.post-title { text-align: center; font-family: var(--display); font-size: clamp(22px, 5.4vw, 30px); line-height: 1.4; margin: 0 0 22px; text-wrap: balance }
article p { margin: 0 0 1.1em }
article h2 { font-size: 19px; margin: 1.9em 0 .7em; padding-bottom: 6px; border-bottom: 2px solid var(--soft) }
article ul, article ol { margin: 0 0 1.1em; padding-left: 1.3em }
figure { margin: 1.4em 0; text-align: center }
figure img { width: 100%; max-width: 100%; height: auto; border-radius: 6px; display: block }
.save-photo { display: block; margin: -0.6em auto 1.4em; font-size: 14px; padding: 6px 12px }
.copy-stage { position: fixed; left: -9999px; top: 0; width: 600px }
figcaption { font-size: 14px; color: var(--muted); margin-top: 8px }
.disclosure { margin: 0 0 1.6em }
.product-link { margin: 1.4em 0; text-align: center }
.product-link b { color: var(--ink) }
.product-link a { color: var(--accent); word-break: break-all }
.missing { color: #c0392b }
.tags { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin-top: 26px }
.tags span { background: var(--soft); border-radius: 999px; padding: 3px 10px; font-size: 14px }
@media (prefers-reduced-motion: no-preference) { button { transition: filter .15s } button:hover { filter: brightness(1.05) } }
</style>

<div class="wrap">
  <section class="tools" aria-label="발행 도구">
    <h1>발행 준비 · 사진 __PHOTO_COUNT__장 배치 완료</h1>
    <div class="row">
      <button class="primary" id="copy-body" type="button">본문 복사</button>
      <button class="primary" id="save-all" type="button" hidden>사진 __PHOTO_COUNT__장 저장</button>
      <button id="copy-title" type="button">제목 복사</button>
      <button id="copy-tags" type="button">태그 복사</button>
      <button id="copy-link" type="button">상품 링크 복사</button>
    </div>
    <p class="status" id="status" role="status"></p>
    <ol class="steps">
      <li><b>사진 저장</b>: '사진 __PHOTO_COUNT__장 저장'을 눌러 휴대폰에 저장해요(사진마다 저장 창이 떠요). 버튼이 안 보이면 아래 사진을 길게 눌러 저장하세요.</li>
      <li><b>글 붙여넣기</b>: 블로그 글쓰기에서 제목 복사 → 붙여넣기, 본문 복사 → 본문에 붙여넣기.</li>
      <li><b>사진 넣기</b>: 붙여넣은 본문에 <b>📷 [사진 N] 여기에 photo_0N 넣기</b> 줄이 보여요. 그 줄을 지우고 같은 번호 사진을 넣으면 돼요.</li>
      <li>👉 링크 안내 __CTA_COUNT__곳 밑에 상품 주소가 한 줄씩 들어가 있어요. 블로그에 붙여넣으면 주소가 링크로 바뀌는지 확인하고, 글자로만 남아 있으면 주소 끝에 커서를 두고 엔터를 한 번 눌러 주세요.</li>
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
const KEEP_EMBEDDED = false;
const HAS_URLS = KEEP_EMBEDDED || !!document.querySelector("figure[data-src]");
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

// 네이버 에디터는 페이지 안에 들어 있는 사진을 붙여넣지 못한다.
// 그래서 복사본에서는 사진 자리를 '📷 사진 N' 줄로 바꿔, 어디에 넣을지 보이게 한다.
function buildCopyNode() {
  const clone = document.getElementById("post-body").cloneNode(true);
  clone.querySelectorAll(".save-photo").forEach(b => b.remove());
  clone.querySelectorAll("figure").forEach(fig => {
    const cap = fig.dataset.caption || "";
    if (KEEP_EMBEDDED) {
      // 처음 방식: 페이지 안의 사진을 그대로 복사한다 (사용자 확인: 이 방식이 앱에 잘 붙었음)
      fig.setAttribute("style", "text-align:center;margin:16px 0");
      const img = fig.querySelector("img"); if (img) img.setAttribute("style", "max-width:100%");
      return;
    }
    if (fig.dataset.src) {
      // 공개 주소의 사진은 네이버 에디터가 받아서 본문에 넣어 준다.
      const wrap = document.createElement("div");
      const pi = document.createElement("p");
      pi.setAttribute("style", "text-align:center");
      const img = document.createElement("img");
      img.src = fig.dataset.src; img.alt = cap || ("사진 " + fig.dataset.n);
      img.setAttribute("style", "max-width:100%");
      pi.appendChild(img); wrap.appendChild(pi);
      if (cap) {
        const pc = document.createElement("p");
        pc.setAttribute("style", "text-align:center;color:#888888;font-size:14px");
        pc.textContent = cap; wrap.appendChild(pc);
      }
      fig.replaceWith(...wrap.childNodes);
    } else {
      const p = document.createElement("p");
      p.setAttribute("style", "text-align:center;color:#1f7a53;font-weight:700;font-size:17px");
      const nn = String(fig.dataset.n).padStart(2, "0");
      p.textContent = "📷 [사진 " + fig.dataset.n + "] 여기에 photo_" + nn + " 넣기" + (cap ? " · " + cap : "");
      fig.replaceWith(p);
    }
  });
  const stage = document.createElement("div");
  stage.className = "copy-stage"; stage.appendChild(clone);
  document.body.appendChild(stage);
  return stage;
}

document.getElementById("copy-body").addEventListener("click", async () => {
  const stage = buildCopyNode();
  const body = stage.firstChild;
  const htmlText = body.innerHTML;
  const plain = body.innerText;
  try {
    if (!window.ClipboardItem) throw new Error("no ClipboardItem");
    await navigator.clipboard.write([new ClipboardItem({
      "text/html": new Blob([htmlText], { type: "text/html" }),
      "text/plain": new Blob([plain], { type: "text/plain" }),
    })]);
    say(HAS_URLS ? "본문 복사됨 (사진 포함). 블로그 본문에 붙여넣어 보세요." : "본문 복사됨. 붙여넣은 뒤 📷 사진 N 자리에 사진을 넣어 주세요.");
    stage.remove();
  } catch (e) {
    selectNode(body);
    try { if (document.execCommand("copy")) { say("본문 복사됨. 붙여넣은 뒤 📷 사진 N 자리에 사진을 넣어 주세요."); stage.remove(); return; } } catch (_) {}
    stage.remove();
    selectNode(document.getElementById("post-body"));
    say("자동 복사가 막혀 있어요. 원고가 선택돼 있으니 직접 복사해 주세요.");
  }
});

function photoBlob(n) {
  const img = document.querySelector(`figure[data-n="${n}"] img`);
  const b64 = img.src.split(",")[1];
  const bin = atob(b64); const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: "image/jpeg" });
}
const fname = n => "photo_" + String(n).padStart(2, "0") + ".jpg";

let downloads = null;
async function savePhoto(n) {
  try { await downloads.save({ filename: fname(n), data: photoBlob(n) }); return true; }
  catch (e) {
    if (e && e.code === "declined") { say("사진 " + n + " 저장을 취소했어요."); return false; }
    if (e && e.code === "rate_limited") { say("저장 창이 이미 열려 있어요. 잠시 뒤 다시 눌러 주세요."); return false; }
    say("이 화면에서는 저장할 수 없어요. 사진을 길게 눌러 저장해 주세요."); return false;
  }
}
(async () => {
  try { downloads = await window.claude?.use?.("downloads"); } catch (e) { downloads = null; }
  if (!downloads) return;
  document.querySelectorAll(".save-photo").forEach(b => {
    b.hidden = false;
    b.addEventListener("click", async () => { if (await savePhoto(b.dataset.n)) say("사진 " + b.dataset.n + " 저장됨"); });
  });
  const all = document.getElementById("save-all");
  all.hidden = false;
  all.addEventListener("click", async () => {
    const ns = [...document.querySelectorAll("figure[data-n]")].map(f => f.dataset.n);
    let ok = 0;
    for (const n of ns) { say("사진 " + n + " / " + ns.length + " 저장 중..."); if (await savePhoto(n)) ok++; else break; }
    if (ok === ns.length) say("사진 " + ok + "장 모두 저장했어요.");
  });
})();
</script>
"""


def public_photo_urls(post_dir: Path) -> dict[int, str]:
    """푸시된 커밋에 들어 있는 사진의 공개 주소(raw.githubusercontent.com)를 만든다.

    네이버 에디터는 페이지 속 사진(data:)은 버리지만, 공개 주소의 사진은 받아 준다.
    커밋 SHA로 주소를 고정해 두면 브랜치가 지워져도 사진이 남는다.
    """
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=post_dir).stdout.strip()

    remote = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote)
    sha = git("rev-parse", "HEAD")
    if not m or not sha:
        return {}
    # 원격에 올라간 커밋인지 확인 (안 올라갔으면 주소가 열리지 않는다)
    if not git("branch", "-r", "--contains", sha):
        return {}
    top = Path(git("rev-parse", "--show-toplevel"))
    urls = {}
    for f in sorted((post_dir / "photos").glob("photo_*.*")):
        rel = f.resolve().relative_to(top).as_posix()
        if not git("ls-tree", "--full-tree", "--name-only", sha, "--", rel):
            continue
        n = int(re.search(r"photo_(\d+)", f.name).group(1))
        urls[n] = f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{sha}/{rel}"
    return urls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("post_dir")
    parser.add_argument("--link", default="")
    parser.add_argument("--public-photos", action="store_true", help="복사본에 사진 공개 주소를 넣음(실험용)")
    args = parser.parse_args()

    post_dir = Path(args.post_dir)
    lines = (post_dir / "post.md").read_text(encoding="utf-8").splitlines()

    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    tag_idx = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("태그")), None)
    tags = re.findall(r"#(\S+)", lines[tag_idx]) if tag_idx is not None else []
    body_lines = [l for i, l in enumerate(lines) if not l.startswith("# ") and i != tag_idx]

    # 네이버 앱은 복사한 사진을 받지 못한다(사용자 확인). 기본은 사진 자리 표시 + 사진 저장 버튼.
    photo_urls = public_photo_urls(post_dir) if args.public_photos else {}
    body, missing = render_body(body_lines, post_dir / "photos", args.link or "[상품 링크]", photo_urls)
    body = body.replace('<p style="text-align:center">이 포스팅은', '<p class="disclosure" style="margin:0 0 24px;padding:14px 12px;border:2px solid #e8590c;border-radius:4px;color:#e8590c;font-size:18px;font-weight:700;line-height:1.6;text-align:center">이 포스팅은', 1)
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
