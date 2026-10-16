"""쇼핑커넥트(또는 스마트스토어) 링크에서 상품명, 설명, 이미지를 가져온다.

네이버가 수집을 막는 경우가 있어서, 실패해도 앱이 멈추지 않도록
가져온 만큼만 돌려주고 나머지는 사용자가 직접 붙여넣게 한다.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

MAX_IMAGES = 12


@dataclass
class ProductInfo:
    url: str
    final_url: str = ""
    title: str = ""
    description: str = ""
    price: str = ""
    images: list[str] = field(default_factory=list)
    error: str = ""


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _images_from_preloaded_state(html: str) -> list[str]:
    """스마트스토어 페이지에 들어 있는 상품 이미지 URL을 찾는다."""
    urls = re.findall(r'https?://shop-phinf\.pstatic\.net/[^"\'\\\s]+?\.(?:jpg|jpeg|png|webp)', html, re.I)
    seen, result = set(), []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _price_from_html(html: str) -> str:
    match = re.search(r'"(?:discountedSalePrice|salePrice)"\s*:\s*(\d+)', html)
    return f"{int(match.group(1)):,}원" if match else ""


def fetch_product(url: str, timeout: float = 10.0) -> ProductInfo:
    info = ProductInfo(url=url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        info.final_url = resp.url
        resp.raise_for_status()
    except requests.RequestException as e:
        info.error = f"페이지를 불러오지 못했습니다: {e}"
        return info

    resp.encoding = "utf-8"
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    info.title = _meta(soup, "og:title", "twitter:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    info.description = _meta(soup, "og:description", "description")
    info.price = _price_from_html(html)

    images: list[str] = []
    og_image = _meta(soup, "og:image")
    if og_image:
        images.append(og_image)
    images += _images_from_preloaded_state(html)
    if len(images) < 3:
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if src.startswith("data:") or not src:
                continue
            images.append(urljoin(info.final_url, src))

    seen, deduped = set(), []
    for img in images:
        key = img.split("?")[0]
        if key not in seen:
            seen.add(key)
            deduped.append(img)
    info.images = deduped[:MAX_IMAGES]

    if not info.title and not info.images:
        info.error = "페이지는 열렸지만 상품 정보를 찾지 못했습니다. 상품 설명을 직접 붙여넣어 주세요."
    return info


def download_image(url: str, timeout: float = 10.0) -> bytes | None:
    try:
        resp = requests.get(url, headers={**HEADERS, "Referer": "https://smartstore.naver.com/"}, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="상품 페이지에서 정보와 사진을 가져온다")
    parser.add_argument("url")
    parser.add_argument("--out", required=True, help="결과 폴더 (product.json, photos/ 저장)")
    args = parser.parse_args()

    out = Path(args.out)
    (out / "photos").mkdir(parents=True, exist_ok=True)
    info = fetch_product(args.url)

    saved = []
    for i, img_url in enumerate(info.images, start=1):
        data = download_image(img_url)
        if not data:
            continue
        ext = ".png" if data.startswith(b"\x89PNG") else ".jpg"
        path = out / "photos" / f"photo_{i:02d}{ext}"
        path.write_bytes(data)
        saved.append(str(path))

    result = {**info.__dict__, "saved_photos": saved}
    (out / "product.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if info.error and not saved else 0


if __name__ == "__main__":
    sys.exit(main())
