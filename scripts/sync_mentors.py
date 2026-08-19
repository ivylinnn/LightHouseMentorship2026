#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Airtable 同步导师数据到网站。

用法:
    python3 scripts/sync_mentors.py            # 增量:已有照片不重新下载
    python3 scripts/sync_mentors.py --force    # 重新下载所有照片

流程:
    1. 拉取「网页显示=✓ 且 12期=yes」的导师记录
    2. 组别映射到网站四组,映射不上的(西雅图组等)列出来跳过
    3. 下载头像 → 压成 webp 存 web_assets/mentors/airtable/
    4. 生成 web_assets/mentors-data.js (页面直接引用)
    5. 之后 git diff 人工确认,再 commit + push

token 存放: ~/.config/lighthouse/airtable_token (不进 Git,绝不能写进网页代码)
区域: Airtable 暂无区域字段,先全部记为美西 west;
      若表里新增「区域」单选列(美西/美东),脚本会自动使用。
"""
import io, json, os, re, sys, urllib.request, urllib.parse

BASE_ID  = "applYF5qXUMI7nTpC"
TABLE_ID = "tbl0xkyhbCVN2b3g3"
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(ROOT, "web_assets", "mentors", "airtable")
OUT_JS    = os.path.join(ROOT, "web_assets", "mentors-data.js")

GROUP_MAP = {  # Airtable「组别」→ 网站 group id;初创员工并入资深职业(网页上是一个组)
    "新星职业组": "rising",
    "资深职业组": "senior",
    "初创员工组": "senior",
    "创始人组":   "founder",
    "西雅图组":   "seattle",
}
VIEW_ID = "viwHMIrIFbGSLuId7"   # 「导师完整信息」视图:网页展示顺序 = 此视图中的行顺序
REGION_MAP = {"美西": "west", "美东": "east"}
PHOTO_MAX = 480          # 头像最长边(px),卡片显示用足够
FORCE = "--force" in sys.argv


def token():
    p = os.path.expanduser("~/.config/lighthouse/airtable_token")
    t = os.environ.get("AIRTABLE_TOKEN") or (open(p).read().strip() if os.path.exists(p) else "")
    if not t:
        sys.exit("找不到 Airtable token:请放在 ~/.config/lighthouse/airtable_token 或环境变量 AIRTABLE_TOKEN")
    return t


def fetch_all(tok):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    recs, offset = [], None
    while True:
        q = {"filterByFormula": "AND({网页显示}=TRUE(),{12期}='yes')", "pageSize": "100",
             "view": VIEW_ID}   # 指定视图后,返回顺序即视图行顺序
        if offset:
            q["offset"] = offset
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q),
                                     headers={"Authorization": "Bearer " + tok})
        d = json.load(urllib.request.urlopen(req))
        recs += d["records"]
        offset = d.get("offset")
        if not offset:
            return recs


def clean(s):
    """多行/多余空白压成单行"""
    return re.sub(r"\s+", " ", (s or "")).strip()


def safe_name(s):
    """姓名转文件名:去掉路径分隔等危险字符"""
    return re.sub(r"[/\\:*?\"<>|]+", " ", clean(s)).strip() or "unnamed"


def save_photo(att, fname):
    """下载最大附件并压成 webp;返回是否新写入"""
    path = os.path.join(PHOTO_DIR, fname)
    if os.path.exists(path) and not FORCE:
        return False
    url = (att.get("thumbnails", {}).get("full", {}) or {}).get("url") or att["url"]
    data = urllib.request.urlopen(url).read()
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((PHOTO_MAX, PHOTO_MAX))
    img.save(path, "WEBP", quality=85, method=6)
    return True


def main():
    os.makedirs(PHOTO_DIR, exist_ok=True)
    recs = fetch_all(token())
    print(f"拉取到 网页显示✓ 且 12期=yes 的记录: {len(recs)}")

    mentors, skipped, warns, downloaded = [], [], [], 0
    for r in recs:                     # 不排序:保持 Airtable 视图中的行顺序
        f = r["fields"]
        name = clean(f.get("Name", ""))
        groups = list(dict.fromkeys(GROUP_MAP[g] for g in f.get("组别", []) if g in GROUP_MAP))
        if not groups:
            skipped.append((name, f.get("组别", [])))
            continue
        region = REGION_MAP.get(clean(f.get("区域", "")), "west")

        photo = ""
        atts = f.get("Photo", [])
        if atts:
            photo = safe_name(name) + ".webp"
            if save_photo(atts[0], photo):
                downloaded += 1
        else:
            warns.append(f"{name}: 无照片")
        if not f.get("简介"):
            warns.append(f"{name}: 无中文简介")

        for g in groups:  # 目前无人多组;若将来有,同一导师在每组各出现一次
            m = {"region": region, "group": g, "name": name,
                 "position": clean(f.get("Current position", ""))}
            if photo:            m["photo"] = photo
            if f.get("简介"):        m["bio"]    = f["简介"].strip()
            if f.get("English Bio"): m["bio_en"] = f["English Bio"].strip()
            mentors.append(m)

    js = ("/* 本文件由 scripts/sync_mentors.py 自动生成,请勿手改 —— 改 Airtable 后重新运行脚本 */\n"
          "const MENTORS = " + json.dumps(mentors, ensure_ascii=False, indent=1) + ";\n")
    with open(OUT_JS, "w", encoding="utf-8") as fp:
        fp.write(js)

    print(f"写入 {len(mentors)} 位导师 → web_assets/mentors-data.js;新下载照片 {downloaded} 张")
    if skipped:
        print(f"\n跳过 {len(skipped)} 位(组别不在网站四组内,待确认):")
        for n, g in skipped:
            print(f"  - {n}  {g}")
    if warns:
        print("\n提醒:")
        for w in warns:
            print("  -", w)


if __name__ == "__main__":
    main()
