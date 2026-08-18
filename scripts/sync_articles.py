#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从微信公众号文章链接同步「领航文章」到网站。

链接来源(二选一,Sheet 优先):
    1. SHEET_CSV_URL —— Google Sheet 发布的 CSV 链接(第一列=文章链接,
       可选「显示」列填 y/yes;暂未配置时留空)
    2. scripts/article_urls.txt —— 一行一个链接,# 开头为注释

用法:
    python3 scripts/sync_articles.py            # 已抓过的文章不重抓
    python3 scripts/sync_articles.py --force    # 全部重抓(标题封面有改动时)

产出:
    web_assets/posts/<hash>.webp   封面图(本地化,微信图链外站无法直接引用)
    web_assets/articles-data.js    首页「领航文章」区数据
"""
import csv, hashlib, html, io, json, os, re, sys, urllib.request

SHEET_CSV_URL = ""   # ← 之后接 Google Sheet:File → Share → Publish to web → CSV 的链接

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL_FILE = os.path.join(ROOT, "scripts", "article_urls.txt")
IMG_DIR  = os.path.join(ROOT, "web_assets", "posts")
OUT_JS   = os.path.join(ROOT, "web_assets", "articles-data.js")
CACHE    = os.path.join(ROOT, "web_assets", "articles-cache.json")  # 已抓文章的元信息
UA       = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
FORCE = "--force" in sys.argv


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read()


def load_urls():
    if SHEET_CSV_URL:
        rows = list(csv.reader(io.StringIO(get(SHEET_CSV_URL).decode("utf-8"))))
        urls = []
        for row in rows:
            if not row or "mp.weixin.qq.com" not in row[0]:
                continue  # 跳过表头/空行
            show = row[1].strip().lower() if len(row) > 1 else ""
            if show in ("", "y", "yes", "true", "1"):
                urls.append(row[0].strip())
        return urls
    if os.path.exists(URL_FILE):
        return [l.strip() for l in open(URL_FILE, encoding="utf-8")
                if l.strip() and not l.startswith("#") and "mp.weixin.qq.com" in l]
    sys.exit("没有文章来源:请配置 SHEET_CSV_URL 或创建 scripts/article_urls.txt")


def meta(page, prop):
    m = re.search(r'<meta property="%s" content="([^"]*)"' % re.escape(prop), page)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch_article(url):
    page = get(url).decode("utf-8", errors="ignore")
    title = meta(page, "og:title")
    if not title:
        raise RuntimeError("抓不到标题(可能被微信拦截,稍后重试)")
    ts = re.search(r'var ct = "?(\d+)"?', page)
    ts = int(ts.group(1)) if ts else 0
    return {"url": url, "h": title, "p": meta(page, "og:description"),
            "cover": meta(page, "og:image"), "ts": ts}


def save_cover(cover_url, slug):
    fname = slug + ".webp"
    path = os.path.join(IMG_DIR, fname)
    if os.path.exists(path) and not FORCE:
        return fname
    from PIL import Image
    img = Image.open(io.BytesIO(get(cover_url))).convert("RGB")
    img.thumbnail((800, 800))
    img.save(path, "WEBP", quality=82, method=6)
    return fname


def main():
    os.makedirs(IMG_DIR, exist_ok=True)
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) and not FORCE else {}
    urls = load_urls()
    print(f"文章链接 {len(urls)} 条")

    posts, errors = [], []
    from datetime import datetime, timezone
    for url in urls:
        slug = hashlib.md5(url.encode()).hexdigest()[:10]
        try:
            art = cache.get(slug) or fetch_article(url)
            img = save_cover(art["cover"], slug) if art.get("cover") else ""
            cache[slug] = art
            d = datetime.fromtimestamp(art["ts"], tz=timezone.utc).strftime("%Y · %m") if art["ts"] else ""
            posts.append({"d": d, "h": art["h"], "p": art["p"], "img": img,
                          "url": url, "ts": art["ts"]})
            print(f"  ✓ {art['h'][:40]}")
        except Exception as e:
            errors.append(f"{url}: {e}")

    posts.sort(key=lambda x: -x["ts"])
    for p in posts:
        p.pop("ts")
    with open(OUT_JS, "w", encoding="utf-8") as fp:
        fp.write("/* 本文件由 scripts/sync_articles.py 自动生成,请勿手改 */\n"
                 "const POSTS = " + json.dumps(posts, ensure_ascii=False, indent=1) + ";\n")
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    print(f"写入 {len(posts)} 篇 → web_assets/articles-data.js")
    for e in errors:
        print("  ✗", e)


if __name__ == "__main__":
    main()
