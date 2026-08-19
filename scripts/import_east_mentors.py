#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性迁移工具:从旧官网 (linghangmentorship.com/mentors-east/) 抓取美东导师,
导入 Airtable 美东 base(表结构与美西一致)。

- 组别保留网站原始组名(纽约DC创业组 等 7 组),选项由 typecast 自动创建
- 照片传公开 URL,由 Airtable 拉取永久存档
- 已存在同名记录会跳过,可安全重跑

用法: python3 scripts/import_east_mentors.py
token: ~/.config/lighthouse/airtable_token_east (需 data.records:write)
"""
import html, json, os, re, sys, time, urllib.request

PAGE = "https://www.linghangmentorship.com/mentors-east/"
BASE = "https://api.airtable.com/v0/app76ckvYz8QRdx17/tbl0xkyhbCVN2b3g3"
GROUPS = ["纽约DC创业组", "波士顿创业组", "纽约DC职业组进阶班", "波士顿职业组进阶班",
          "纽约DC职业组成长班", "波士顿职业组成长班", "荣誉顾问"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

token = open(os.path.expanduser("~/.config/lighthouse/airtable_token_east")).read().strip()
clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def api(url, payload=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST" if payload else "GET")
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        e.detail = e.read().decode("utf-8", errors="ignore")[:500]
        raise


def parse_page():
    req = urllib.request.Request(PAGE, headers={"User-Agent": UA})
    h = urllib.request.urlopen(req).read().decode("utf-8", errors="ignore")

    # 组别标题出现位置。标题标记方式不统一(h4/div 混用),所以取组名的所有出现位置,
    # 仅排除简介正文里的引用;按"最近一次出现"归组——页首目录都在第一节之前,不影响。
    heads = [(m.start(), g) for g in GROUPS for m in re.finditer(re.escape(g), h)
             if "sqsrte-small" not in h[max(0, m.start() - 300):m.start()]]
    heads.sort()

    # 逐个 image-block 提取
    blocks = [m.start() for m in re.finditer(r'class="sqs-block image-block', h)]
    mentors = []
    for i, s in enumerate(blocks):
        seg = h[s: blocks[i + 1] if i + 1 < len(blocks) else s + 12000]
        tm = re.search(r'class="image-title[^"]*"[^>]*>(.*?)</div>', seg, flags=re.S)
        if not tm:
            continue
        # 标题区可能混入简介段(如 康岚),只取第一个 h 标签里的文字作姓名
        hm = re.search(r"<h\d[^>]*>(.*?)</h\d>", tm.group(1), flags=re.S)
        name = clean(hm.group(1) if hm else tm.group(1))
        if not name or name in GROUPS or len(name) > 40:
            continue
        im = re.search(r'src="(https://images\.squarespace-cdn\.com[^"]*)"', seg)
        img = html.unescape(im.group(1)).split("?")[0] if im else ""
        paras = [clean(p) for p in
                 re.findall(r'<p class="sqsrte-small"[^>]*>(.*?)</p>', seg, flags=re.S)]
        paras = [p for p in paras if p]
        group = ""
        for pos, g in heads:
            if pos < s:
                group = g
        mentors.append({"name": name, "img": img, "paras": paras, "group": group})

    # 部分组(如 波士顿职业组成长班)用"照片块+独立文字块"版式,figcaption 里没有姓名,
    # 上面的解析拿不到 —— 对这些组按区间做备用解析。
    got = {m["group"] for m in mentors}
    starts = {}
    for pos, g in heads:
        starts[g] = pos                       # 各组正文标题取最后一次出现
    bounds = sorted(starts.values()) + [len(h)]
    for g, pos in starts.items():
        if g in got:
            continue
        end = min(b for b in bounds if b > pos)
        mentors += parse_plain_section(h[pos:end], g)
    return mentors


def parse_plain_section(seg, group):
    """照片块与文字块分离的版式:短段落=姓名,其后段落=简介,照片取姓名前最近的图块"""
    imgs = []
    for m in re.finditer(r'class="sqs-block image-block', seg):
        im = re.search(r'src="(https://images\.squarespace-cdn\.com[^"]*)"', seg[m.start():m.start() + 9000])
        if im:
            imgs.append((m.start(), html.unescape(im.group(1)).split("?")[0]))
    paras = [(m.start(), clean(m.group(2)))
             for m in re.finditer(r"<(p|h[1-4])[^>]*>(.*?)</\1>", seg, flags=re.S)]
    paras = [(p, t) for p, t in paras if t]

    is_name = lambda t: (len(t) <= 20 and not re.search(r"[，,。.:：;；]", t)
                         and not t.startswith("美东领航") and t not in GROUPS)
    names = [i for i, (p, t) in enumerate(paras) if is_name(t)]
    out = []
    for k, i in enumerate(names):
        pos, name = paras[i]
        stop = names[k + 1] if k + 1 < len(names) else len(paras)
        bio = [t for p, t in paras[i + 1:stop]]
        prev = [u for p, u in imgs if p < pos]
        out.append({"name": name, "img": prev[-1] if prev else "",
                    "paras": bio, "group": group})
    return out


def split_name(name):
    """中英文拆分:中文进 中文姓名,拉丁进 English Name"""
    cn = "".join(re.findall(r"[一-鿿·]+", name)).strip("·")
    en = re.sub(r"[一-鿿·]+", " ", name)
    en = re.sub(r"\s+", " ", en).strip()
    return cn, en


def to_fields(m):
    cn, en = split_name(m["name"])
    f = {"组别": [m["group"]] if m["group"] else [], "网页显示": True, "12期": "yes"}
    if cn: f["中文姓名"] = cn
    if en: f["English Name"] = en
    if m["paras"]:
        first = m["paras"][0]
        # 职位 = 首段去掉开头的姓名与分隔符;结果仍太长(首段就是大段简介)则取首句
        pos = re.sub(r"^(%s|%s)\s*[,，:：、]?\s*" % (re.escape(m["name"]), re.escape(cn or m["name"])),
                     "", first).strip().rstrip("。")
        if len(pos) > 60:
            if re.search(r"[一-鿿]", pos):
                pos = pos.split("。")[0].strip()
            else:  # 英文按句点拆,但跳过 Dr./Mr./Inc. 等缩写
                sp = re.split(r"(?<!\b[DMS]r)(?<!\bMs)(?<!\bProf)(?<!\bInc)(?<!\bCo)\.\s", pos)
                pos = sp[0].strip()
        f["Current position"] = pos
        f["简介"] = "\n".join(m["paras"])
    if m["img"]:
        ext = os.path.splitext(m["img"])[1] or ".jpg"
        f["Photo"] = [{"url": m["img"], "filename": (cn or en) + ext}]
    return f


def main():
    mentors = parse_page()
    print(f"网站解析到 {len(mentors)} 位导师")
    from collections import Counter
    for g, n in Counter(m["group"] for m in mentors).items():
        print(f"  {g or '<未归组>'}: {n}")

    # 已有记录按 Name 去重(李明试验记录等)
    existing, offset = set(), None
    while True:
        url = BASE + "?pageSize=100" + (f"&offset={offset}" if offset else "")
        d = api(url)
        existing |= {r["fields"].get("Name", "").strip() for r in d["records"]}
        offset = d.get("offset")
        if not offset:
            break
    todo = [m for m in mentors if m["name"] not in existing
            and (split_name(m["name"])[0] or m["name"]) not in existing]
    print(f"已在表中 {len(mentors) - len(todo)} 位,待写入 {len(todo)} 位")

    warns = [m["name"] for m in todo if not m["paras"]]
    failed = []
    for i in range(0, len(todo), 10):   # Airtable 每次最多 10 条
        batch = todo[i:i + 10]
        try:
            api(BASE, {"records": [{"fields": to_fields(m)} for m in batch], "typecast": True})
        except urllib.error.HTTPError:
            for m in batch:             # 批量失败 → 逐条定位问题记录
                try:
                    api(BASE, {"records": [{"fields": to_fields(m)}], "typecast": True})
                except urllib.error.HTTPError as e:
                    failed.append((m["name"], getattr(e, "detail", str(e))))
                time.sleep(0.25)
        print(f"  写入 {min(i + 10, len(todo))}/{len(todo)}")
        time.sleep(0.25)
    for name, err in failed:
        print(f"  ✗ {name}: {err}")

    if warns:
        print("\n提醒(无简介,需人工补):", ", ".join(warns))


if __name__ == "__main__":
    main()
