"""
把 複習講義.html(學生版，權威內容) 的知識點內容回補進 index.html(老師版)。

index.html 的 DATA 不是 JSON，是 JS 物件 literal（key 不加引號、6 個 diagram 欄位用單引號
多行字串接續），所以要先做前處理才能 json.loads：diagram 區塊先換成佔位字串保留原文、
常見 key 補雙引號。

流程：①分別解析兩份 DATA ②依分類/子主題「位置」對齊，逐個知識點用 label 比對：
同 label → 整點覆蓋內容；label 已改名(見 OLD_TO_NEW_LABEL) → 比照改名後比對，避免
被誤判成新知識點插入、留下孤兒重複；找不到對應 → 視為新增，插入該子主題末尾
③序列化寫回時手刻 pretty-printer 比照原本縮排規格，diagram 區塊直接還原成原始文字。

用法：改好 OLD_TO_NEW_LABEL（把這輪所有「點的label本身也改了」的項目都列進去，
不只是內容變、標籤沒變的不用列)，執行 `python3 backport_index.py`，會先印出異動報告，
不會直接覆蓋 index.html —— 檢查報告沒問題後，再手動把印出的 `index.html.new` 換成正式檔，
並記得檢查 index.html 的 desc-tech 那行有沒有 `<b>` 白名單渲染（見 HANDBOOK 2026-09-24 節）。
"""
import re, json

STUDENT = "/Users/jc/Qsync/01. Jill /02. 工作/04. 基金會oa備份/本地端CLI/備課大綱/專案管理概論V3備課大綱/複習講義.html"
TEACHER = "/Users/jc/Qsync/01. Jill /02. 工作/04. 基金會oa備份/本地端CLI/備課大綱/專案管理概論V3備課大綱/index.html"

# 每輪套用「內容錯誤/自創詞/新增」批次時，只要改到「知識點標籤本身」（不只是內容），
# 就要把 舊標籤→新標籤 補進這裡，不然 backport 會把新標籤當成全新知識點插入，
# 舊標籤留在 index.html 變孤兒重複。
OLD_TO_NEW_LABEL = {
    "各流程群組的關聯性考點": "流程群組間的關聯性",
    "Project／Program／Portfolio 三層級": "專案／計畫／專案組合的範圍層級",
    "五種組織結構光譜": "組織結構類型比較",
    "三種財務評估方法": "常見的專案財務評估方法",
    "成本估算的三種技術": "成本估算常見工具與技術",
    "企業環境因素 EEF": "企業環境因素 EEF（Enterprise Environmental Factors）",
    "專案管理辦公室 PMO": "專案管理辦公室 PMO（Project Management Office）",
}


def load_student():
    shtml = open(STUDENT, encoding="utf-8").read()
    m = re.search(r'var DATA = (\[.*?\]);\n', shtml, re.S)
    return json.loads(m.group(1))


def load_teacher():
    text = open(TEACHER, encoding="utf-8").read()
    d_start = text.index("var DATA = [")
    d_end = text.index("\n  ];", d_start) + len("\n  ];")
    prefix = text[:d_start]
    block = text[d_start + len("var DATA = "):d_end - 1]
    suffix = text[d_end:]

    diagram_store = []

    def replace_diagram(m2):
        idx = len(diagram_store)
        diagram_store.append(m2.group(0))
        return f'"diagram": "__DIAGRAM_PLACEHOLDER_{idx}__"'

    diagram_pat = re.compile(
        r"diagram:\s*(?:'(?:[^'\\]|\\.)*'\s*\+\s*)*'(?:[^'\\]|\\.)*'", re.S
    )
    block2 = diagram_pat.sub(replace_diagram, block)
    for key in ["name", "short", "count", "key", "subtopics", "points"]:
        block2 = re.sub(rf'(?<!")\b{key}\b\s*:', f'"{key}":', block2)

    teacher_data = json.loads(block2)
    return teacher_data, diagram_store, prefix, suffix


def reconcile(teacher_data, source):
    report = {"subtopic_rename": [], "point_replace": [], "point_insert": [],
              "point_relabel": [], "warnings": []}
    for t_cat, s_cat in zip(teacher_data, source):
        if len(t_cat["subtopics"]) != len(s_cat["subtopics"]):
            report["warnings"].append(
                f"分類「{t_cat['name']}」子主題數不一致 teacher={len(t_cat['subtopics'])} "
                f"student={len(s_cat['subtopics'])}")
            continue
        for t_sub, s_sub in zip(t_cat["subtopics"], s_cat["subtopics"]):
            if t_sub["name"] != s_sub["name"]:
                report["subtopic_rename"].append((t_cat["name"], t_sub["name"], s_sub["name"]))
                t_sub["name"] = s_sub["name"]

            label_to_idx = {p[0]: i for i, p in enumerate(t_sub["points"])}
            for s_point in s_sub["points"]:
                label = s_point[0]
                match_idx = label_to_idx.get(label)
                if match_idx is None:
                    old_label = next((o for o, n in OLD_TO_NEW_LABEL.items() if n == label), None)
                    if old_label and old_label in label_to_idx:
                        match_idx = label_to_idx[old_label]
                        report["point_relabel"].append((t_cat["name"], t_sub["name"], old_label, label))
                if match_idx is not None:
                    if t_sub["points"][match_idx] != s_point:
                        t_sub["points"][match_idx] = s_point
                        report["point_replace"].append((t_cat["name"], t_sub["name"], label))
                else:
                    t_sub["points"].append(s_point)
                    report["point_insert"].append((t_cat["name"], t_sub["name"], label))
    return report


def ser_str(x):
    return json.dumps(x, ensure_ascii=False)


def ser_point(p, indent, is_last):
    p = list(p) + [None] * (5 - len(p))
    label, text, hot, terms, metaphor = p
    comma = "" if is_last else ","
    meta_part = ser_str(metaphor) if metaphor is not None else "null"
    if terms is None:
        return f'{indent}[{ser_str(label)}, {ser_str(text)}, {hot}, null, {meta_part}]{comma}'
    lines = [f'{indent}[{ser_str(label)}, {ser_str(text)}, {hot}, [']
    n = len(terms)
    for i, t in enumerate(terms):
        tcomma = "," if i < n - 1 else ""
        lines.append(f'{indent}  [{ser_str(t[0])}, {ser_str(t[1])}]{tcomma}')
    lines.append(f'{indent}], {meta_part}]{comma}')
    return "\n".join(lines)


DIAG_RE = re.compile(r'__DIAGRAM_PLACEHOLDER_(\d+)__')


def ser_subtopic(st, diagram_store, is_last):
    header_comma = "" if is_last else ","
    diagram_val = st.get("diagram")
    lines = []
    if diagram_val:
        n = int(DIAG_RE.match(diagram_val).group(1))
        raw = diagram_store[n]
        lines.append(f'        {{ name: {ser_str(st["name"])},')
        lines.append(f'          {raw},')
        lines.append('          points: [')
    else:
        lines.append(f'        {{ name: {ser_str(st["name"])}, points: [')
    pts = st["points"]
    for i, p in enumerate(pts):
        lines.append(ser_point(p, "          ", i == len(pts) - 1))
    lines.append(f'        ]}}{header_comma}')
    return "\n".join(lines)


def ser_category(cat, diagram_store, is_last):
    header_comma = "" if is_last else ","
    lines = ['    {',
             f'      name: {ser_str(cat["name"])}, short: {ser_str(cat["short"])}, '
             f'count: {cat["count"]}, key: {ser_str(cat["key"])},',
             '      subtopics: [']
    subs = cat["subtopics"]
    for i, st in enumerate(subs):
        lines.append(ser_subtopic(st, diagram_store, i == len(subs) - 1))
    lines.append('      ]')
    lines.append(f'    }}{header_comma}')
    return "\n".join(lines)


def main():
    source = load_student()
    teacher_data, diagram_store, prefix, suffix = load_teacher()
    assert [c["name"] for c in teacher_data] == [c["name"] for c in source], "分類順序或名稱不一致"

    report = reconcile(teacher_data, source)

    print("=== 警告 ===")
    for w in report["warnings"]:
        print(" ", w)
    print(f"\n子主題改名: {len(report['subtopic_rename'])}")
    for x in report["subtopic_rename"]:
        print(" ", x)
    print(f"\n標籤改名比對成功: {len(report['point_relabel'])}")
    for x in report["point_relabel"]:
        print(" ", x)
    print(f"\n內容更新: {len(report['point_replace'])}")
    print(f"新增知識點: {len(report['point_insert'])}")
    for x in report["point_insert"]:
        print(" ", x)

    body_lines = ['var DATA = [']
    for i, cat in enumerate(teacher_data):
        body_lines.append(ser_category(cat, diagram_store, i == len(teacher_data) - 1))
    body_lines.append('  ];')
    new_text = prefix + "\n".join(body_lines) + suffix

    out_path = TEACHER + ".new"
    open(out_path, "w", encoding="utf-8").write(new_text)
    print(f"\n已寫到 {out_path}，檢查報告沒問題後手動覆蓋 index.html。")
    print("別忘了檢查 index.html 的 desc-tech 那行有沒有 <b> 白名單渲染（HANDBOOK 2026-09-24節）。")


if __name__ == "__main__":
    main()
