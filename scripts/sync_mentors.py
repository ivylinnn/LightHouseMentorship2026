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

token 存放: ~/.config/lighthouse/airtable_token       (美西 base)
           ~/.config/lighthouse/airtable_token_east  (美东 base)
           两个都不进 Git,绝不能写进网页代码
区域: 美西 base 读「区域」字段(缺省 west);美东 base 整表记为 east。
      两个 base 表结构一致,只有「组别」取值不同,见 WEST_GROUPS / EAST_GROUPS。
"""
import io, json, os, re, sys, urllib.request, urllib.parse, urllib.error

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(ROOT, "web_assets", "mentors", "airtable")
OUT_JS    = os.path.join(ROOT, "web_assets", "mentors-data.js")

TABLE_ID = "tbl0xkyhbCVN2b3g3"          # 两个 base 的表结构一致,表 id 也相同
VIEW_ID  = "viwHMIrIFbGSLuId7"          # 「导师完整信息」视图:网页展示顺序 = 此视图行顺序

# 美西组别 → 网站 group id(资深职业组和初创员工组各自独立成组)
WEST_GROUPS = {
    "新星职业组": "rising",
    "资深职业组": "senior",
    "初创员工组": "startup",
    "创始人组":   "founder",
    "西雅图组":   "seattle",
}
# 美东保留自己的 7 个组别(城市 + 赛道),不并入美西的分组。
EAST_GROUPS = {
    "纽约DC创业组":       "east-nydc-founder",
    "波士顿创业组":       "east-bos-founder",
    "纽约DC职业组进阶班": "east-nydc-senior",
    "波士顿职业组进阶班": "east-bos-senior",
    "纽约DC职业组成长班": "east-nydc-rising",
    "波士顿职业组成长班": "east-bos-rising",
    "荣誉顾问":           "east-advisor",
}

# 每个 base 一套配置。region=None 表示读 Airtable 的「区域」字段(美西表用)。
BASES = [
    {"id": "applYF5qXUMI7nTpC", "region": None,   "groups": WEST_GROUPS,
     "token": "~/.config/lighthouse/airtable_token",      "env": "AIRTABLE_TOKEN"},
    {"id": "app76ckvYz8QRdx17", "region": "east", "groups": EAST_GROUPS,
     "token": "~/.config/lighthouse/airtable_token_east", "env": "AIRTABLE_TOKEN_EAST"},
]
REGION_MAP = {"美西": "west", "美东": "east"}

# 英文版名字的兜底表(Airtable 的 English Name / 拼音 都为空时才用)。
# 以 _ 开头的键是注释,不参与匹配。
PINYIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "name_pinyin.json")
CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf·]+")


def normalize_en_name(en, zh):
    """Airtable 的「拼音」列有的填「姓 名」(Bao Shenghua),有的填「名 姓」(Shenghua Bao)。
    网站上要统一成英文习惯的「名 姓」,否则和 David Feng 这类英文名排在一起会很乱。
    判断方法:name_pinyin.json 里的写法是「名 姓」,取它的姓(最后一个词);
    如果 Airtable 那串的第一个词就是这个姓,说明是「姓 名」,调换过来。"""
    words = en.split()
    if len(words) == 2:
        words = [w[:1].upper() + w[1:] for w in words]      # 顺手修掉 "Liu xingchu" 这类小写
        ref = PINYIN.get(zh, "").split()
        if len(ref) == 2 and words[0].lower() == ref[-1].lower():
            words = [words[1], words[0]]
        return " ".join(words)
    return en


def strip_cjk(name):
    """"David Feng 冯大为" -> "David Feng"。只在名字里中英混排时用。"""
    return re.sub(r"\s+", " ", CJK.sub(" ", name)).strip()


PINYIN = {k: v for k, v in
          (json.load(open(PINYIN_FILE, encoding="utf-8")).items() if os.path.exists(PINYIN_FILE) else [])
          if not k.startswith("_")}
PHOTO_MAX = 480          # 头像最长边(px),卡片显示用足够
FORCE = "--force" in sys.argv


def token(base):
    """先找本 base 专属的 token,没有就回落到通用 token —— 一个 PAT 同时授权两个 base
    时只需配一份。"""
    for env, path in [(base["env"], base["token"]),
                      ("AIRTABLE_TOKEN", "~/.config/lighthouse/airtable_token")]:
        t = os.environ.get(env)
        if t:
            return t.strip()
        f = os.path.expanduser(path)
        if os.path.exists(f):
            return open(f).read().strip()
    sys.exit(
        f"找不到 {base['id']} 的 Airtable token。\n"
        f"  方式一(推荐):建一个同时授权两个 base、含 data.records:read 的 PAT,存到\n"
        f"      ~/.config/lighthouse/airtable_token\n"
        f"  方式二:单独给这个 base 配,存到 {base['token']} 或环境变量 {base['env']}\n"
        f"  建 token: https://airtable.com/create/tokens")


def fetch_all(base, tok):
    url = f"https://api.airtable.com/v0/{base['id']}/{TABLE_ID}"
    recs, offset = [], None
    while True:
        q = {"filterByFormula": "AND({网页显示}=TRUE(),{12期}='yes')", "pageSize": "100",
             "view": VIEW_ID}   # 指定视图后,返回顺序即视图行顺序
        if offset:
            q["offset"] = offset
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q),
                                     headers={"Authorization": "Bearer " + tok})
        try:
            d = json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")[:300]
            hint = {
                401: "token 无效,或没有 data.records:read 权限",
                403: f"token 有效,但没有被授权访问 base {base['id']}"
                     "(在 token 设置里把这个 base 加进 Access 列表)",
                404: f"base {base['id']} 或表 {TABLE_ID} 不存在 / 视图 {VIEW_ID} 不可见",
                422: "筛选公式或视图 id 有问题",
            }.get(e.code, "")
            sys.exit(f"\n拉取 base {base['id']} 失败:HTTP {e.code}"
                     + (f"\n  可能原因:{hint}" if hint else "")
                     + f"\n  Airtable 返回:{body}"
                     + f"\n  用的 token 来自:{base['token']} 或 {base['env']} / 通用 token")
        recs += d["records"]
        offset = d.get("offset")
        if not offset:
            return recs


def clean(s):
    """多行/多余空白压成单行"""
    return re.sub(r"\s+", " ", (s or "")).strip()


UNVERIFIED = re.compile(r"^[❓？?]+\s*")
# Airtable 里用「待更新」「待补」「TBD」占位的简介,不应该原样出现在网站上
PLACEHOLDER_BIO = {"待更新", "待补", "待补充", "暂无", "tbd", "n/a", "na", "-", "—"}


def is_placeholder(v):
    t = clean(v or "")
    return (not t) or t.lower() in PLACEHOLDER_BIO


def strip_marker(pos):
    """Airtable 里用 ❓ 前缀标「待核实」,是内部标记,不能出现在网站上。
    去掉后返回 (职位, 是否带过标记),带标记的人会进提醒列表。"""
    p = clean(pos)
    return (UNVERIFIED.sub("", p), bool(UNVERIFIED.match(p)))


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
    mentors, skipped, warns, downloaded = [], [], [], 0
    fallbacks = []
    seen = {}

    for base in BASES:                 # 美西在前、美东在后:网站上区域是并列的两套名单
        recs = fetch_all(base, token(base))
        print(f"{base['id']}: 拉取到 网页显示✓ 且 12期=yes 的记录 {len(recs)}")

        for r in recs:                 # 不排序:保持 Airtable 视图中的行顺序
            f = r["fields"]
            name = clean(f.get("Name", ""))
            gmap = base["groups"]
            groups = list(dict.fromkeys(gmap[g] for g in f.get("组别", []) if g in gmap))
            if not groups:
                skipped.append((base["id"], name, f.get("组别", [])))
                continue
            region = base["region"] or REGION_MAP.get(clean(f.get("区域", "")), "west")

            # 同名导师照片会互相覆盖,按区域分目录避免串号
            key = (region, name)
            if key in seen:
                warns.append(f"{name}: {region} 区域内重名,已跳过第二条")
                continue
            seen[key] = True

            photo = ""
            atts = f.get("Photo", [])
            if atts:
                photo = f"{region}-{safe_name(name)}.webp" if region != "west" \
                        else safe_name(name) + ".webp"
                if save_photo(atts[0], photo):
                    downloaded += 1
            else:
                warns.append(f"{name}: 无照片")
            if not f.get("简介"):
                warns.append(f"{name}: 无中文简介")

            position, unverified = strip_marker(f.get("Current position", ""))
            if unverified:
                warns.append(f"{name}: 职位带 ❓ 待核实标记(已从网站去掉,请在 Airtable 里确认)")

            # 英文版显示用的名字:优先 Airtable 的 English Name,其次拼音;
            # 两个都没有就退回中文名(页面上会原样显示中文)
            name_en = clean(f.get("English Name", "")) or clean(f.get("拼音", ""))
            if name_en and not re.search(r"[A-Za-z]", name):   # 纯中文名才需要统一姓名顺序
                name_en = normalize_en_name(name_en, name)
            if not name_en and CJK.search(name) and re.search(r"[A-Za-z]", name):
                name_en = strip_cjk(name)          # 中英混排,英文版只留英文部分
            if not name_en:
                name_en = PINYIN.get(name, "")
                if name_en:
                    fallbacks.append(name)
            if not name_en and re.search(r"[\u4e00-\u9fff]", name):
                warns.append(f"{name}: 没有 English Name / 拼音,英文版仍显示中文名")

            for g in groups:  # 目前无人多组;若将来有,同一导师在每组各出现一次
                m = {"region": region, "group": g, "name": name,
                     "position": position}
                if name_en and name_en != name: m["name_en"] = name_en
                if photo:            m["photo"] = photo
                if not is_placeholder(f.get("简介")):        m["bio"]    = f["简介"].strip()
                if not is_placeholder(f.get("English Bio")): m["bio_en"] = f["English Bio"].strip()
                mentors.append(m)

    js = ("/* 本文件由 scripts/sync_mentors.py 自动生成,请勿手改 —— 改 Airtable 后重新运行脚本 */\n"
          "const MENTORS = " + json.dumps(mentors, ensure_ascii=False, indent=1) + ";\n")
    with open(OUT_JS, "w", encoding="utf-8") as fp:
        fp.write(js)

    from collections import Counter
    tally = Counter((m["region"], m["group"]) for m in mentors)
    print(f"\n写入 {len(mentors)} 位导师 → web_assets/mentors-data.js;新下载照片 {downloaded} 张")
    for (r, g), n in sorted(tally.items()):
        print(f"  {r}/{g}: {n}")
    if skipped:
        print(f"\n跳过 {len(skipped)} 位(组别不在映射表内,待确认):")
        for b, n, g in skipped:
            print(f"  - [{b}] {n}  {g}")
    if fallbacks:
        print(f"\n{len(fallbacks)} 位导师的英文名来自 scripts/name_pinyin.json 兜底表"
              "(Airtable 的 English Name / 拼音 为空),建议回填 Airtable:")
        print("  " + "、".join(fallbacks))
    if warns:
        print("\n提醒:")
        for w in warns:
            print("  -", w)


if __name__ == "__main__":
    main()
