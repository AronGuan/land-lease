"""评分脚本：用标准答案给一份提交打分。
用法：python3 score.py <标准答案目录> <提交目录>
提交目录放 合同要素.csv、宗地台账.csv、问题清单.csv（列名与练习集标准答案相同，UTF-8 编码）。
合同要素.csv 与 宗地台账.csv 各加一列“处理方式”，填“自动通过”（经办人员批量确认即可）或“人工复核”（对照原件逐项核对），不填视为自动通过。
合同要素按份、欠缴金额按宗地：自动通过且正确得 1，送人工复核得 0.5，自动通过但有错扣 1，错的放过去比老实送复核更吃亏。
满分 100：合同要素 30、宗地归集与登记匹配 15、租金核算 30、问题清单 20（其中存疑待确认单算 5）、催缴对象 5。"""
import sys, os, csv, re, itertools, datetime as dt

ans_dir, sub_dir = sys.argv[1], sys.argv[2]

def rcsv(d, name):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

FW = str.maketrans('０１２３４５６７８９（）：，．', '0123456789():,.')
def norm(v):
    return re.sub(r'\s+', '', str(v or '')).translate(FW)

def ndate(v):
    v = norm(v)
    m = re.match(r'(\d{4})\D(\d{1,2})\D(\d{1,2})', v)
    if m:
        return dt.date(*map(int, m.groups())).isoformat()
    return v

def nnum(v):
    try:
        return round(float(norm(v).replace(',', '').rstrip('元').rstrip('平方米')), 2)
    except ValueError:
        return norm(v)

FIELDS = {'合同编号': norm, '合同类型': norm, '签订日期': ndate, '承租人': norm, '证件号码': lambda v: norm(v).upper(), '联系电话': norm,
          '宗地号': norm, '坐落': norm, '土地面积': nnum, '用途': lambda v: norm(v).replace('用地', ''), '租赁起始日': ndate, '租赁终止日': ndate,
          '计租方式': lambda v: '固定' if '固定' in norm(v) else ('随标准调整' if norm(v) else ''), '年租金小写': nnum, '年租金大写': norm}

A = {r['档案号']: r for r in rcsv(ans_dir, '合同要素.csv')}
S = {norm(r.get('档案号')): r for r in (rcsv(sub_dir, '合同要素.csv') or [])}
def review(r):
    return '复核' in norm((r or {}).get('处理方式'))

print('== 合同要素（逐字段准确率仅供诊断）')
accs = []
for f, fn in FIELDS.items():
    ok = n = 0
    for k, a in A.items():
        t = fn(a[f]); s = S.get(k)
        p = fn(s.get(f, '')) if s else None
        if t == '' and (p in (None, '')):
            continue
        n += 1; ok += (p == t)
    acc = ok / n if n else 1.0
    accs.append(acc)
    print(f'  {f:<6} {acc:6.1%}  ({ok}/{n})')
KEY = ['合同编号', '签订日期', '承租人', '证件号码', '宗地号', '坐落', '土地面积', '租赁起始日', '租赁终止日', '计租方式', '年租金小写', '年租金大写']
pts = n_auto = n_auto_ok = 0
for k, a in A.items():
    s_ = S.get(k)
    if review(s_):
        pts += .5; continue
    n_auto += 1
    ok = s_ is not None and all(FIELDS[f](a[f]) == FIELDS[f](s_.get(f, '')) for f in KEY)
    n_auto_ok += ok; pts += 1 if ok else -1
s1 = 30 * max(0, pts) / len(A)
print(f'  自动通过 {n_auto}/{len(A)} 份（{n_auto / len(A):.0%}），其中关键字段全对 {n_auto_ok} 份（{(n_auto_ok / n_auto if n_auto else 0):.0%}）')

AL = rcsv(ans_dir, '宗地台账.csv'); SL = rcsv(sub_dir, '宗地台账.csv') or []
def groups(rows):
    g = {}
    for r in rows:
        for d in re.split(r'[;；,，、\s]+', norm(r['档案号列表'])):
            if d:
                g[d] = r
    return g
ga, gs = groups(AL), groups(SL)
pairs_a = {frozenset(p) for r in AL for p in itertools.combinations(sorted(re.split(r';', r['档案号列表'])), 2)}
pairs_s = set()
for r in SL:
    ds = sorted(d for d in re.split(r'[;；,，、\s]+', norm(r['档案号列表'])) if d)
    pairs_s |= {frozenset(p) for p in itertools.combinations(ds, 2)}
singles_a = {r['档案号列表'] for r in AL if ';' not in r['档案号列表']}
tp = len(pairs_a & pairs_s); prec = tp / len(pairs_s) if pairs_s else (1.0 if not pairs_a else 0)
rec = tp / len(pairs_a) if pairs_a else 1.0
f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
# 只有单份文件的宗地：看是否被单独成行
single_ok = sum(1 for d in singles_a if d in gs and len([x for x in re.split(r'[;；,，、\s]+', norm(gs[d]['档案号列表'])) if x]) == 1) / max(1, len(singles_a))
unit_ok = 0
for r in AL:
    s = gs.get(r['宗地键'])
    unit_ok += bool(s) and norm(s.get('不动产单元号')) == norm(r['不动产单元号'])
unit_acc = unit_ok / len(AL)
s2 = 15 * (0.5 * (f1 * 0.7 + single_ok * 0.3) + 0.5 * unit_acc)
print(f'== 宗地归集与登记匹配\n  多份文件归集 F1 {f1:.1%}（精确 {prec:.1%}，召回 {rec:.1%}）  单份文件成行 {single_ok:.1%}  不动产单元号 {unit_acc:.1%}')

def close(a, b):
    try:
        return abs(float(norm(a)) - float(norm(b))) <= 0.011
    except ValueError:
        return False
c_arr = c_tot = c_26 = c_who = 0
p_arr = l_auto = l_auto_ok = 0
for r in AL:
    s = gs.get(r['宗地键']) or {}
    ok = close(s.get('欠缴金额'), r['欠缴金额'])
    if review(s):
        p_arr += .5
    else:
        l_auto += 1; l_auto_ok += ok; p_arr += 1 if ok else -1
    c_arr += ok
    c_tot += close(s.get('累计应缴'), r['累计应缴'])
    c_26 += close(s.get('2026年度应缴'), r['2026年度应缴'])
    c_who += norm(s.get('催缴对象')) == norm(r['催缴对象'])
n = len(AL)
s3 = 30 * (0.5 * max(0, p_arr) + 0.25 * c_tot + 0.25 * c_26) / n
s5 = 5 * c_who / n
print(f'== 租金核算（误差 0.01 元以内算对）\n  欠缴金额 {c_arr}/{n}  累计应缴 {c_tot}/{n}  2026年度应缴 {c_26}/{n}')
print(f'  自动通过 {l_auto}/{n} 宗（{l_auto / n:.0%}），其中欠缴金额正确 {l_auto_ok} 宗（{(l_auto_ok / l_auto if l_auto else 0):.0%}）')
print(f'== 催缴对象 {c_who}/{n}')

AP = {(r['档案号'], r['问题类型']) for r in rcsv(ans_dir, '问题清单.csv')}
SP = {(norm(r.get('档案号')), norm(r.get('问题类型'))) for r in (rcsv(sub_dir, '问题清单.csv') or [])}
def f1(a, s):
    tp = len(a & s); pp = tp / len(s) if s else (1.0 if not a else 0); rr = tp / len(a) if a else 1.0
    return (2 * pp * rr / (pp + rr) if pp + rr else 0), pp, rr
AMB = '存疑待确认'
pf1, pp, rr = f1({x for x in AP if x[1] != AMB}, {x for x in SP if x[1] != AMB})
af1, ap, ar = f1({x for x in AP if x[1] == AMB}, {x for x in SP if x[1] == AMB})
s4 = 15 * pf1 + 5 * af1
print(f'== 问题清单  F1 {pf1:.1%}（精确 {pp:.1%}，召回 {rr:.1%}）；存疑待确认单算 F1 {af1:.1%}（精确 {ap:.1%}，召回 {ar:.1%}）')
for t in sorted({t for _, t in AP}):
    a = {x for x in AP if x[1] == t}
    print(f'  {t:<14} 召回 {len(a & SP)}/{len(a)}')
print(f'\n总分 {s1 + s2 + s3 + s4 + s5:.1f} / 100  （合同要素 {s1:.1f}/30，归集与匹配 {s2:.1f}/15，核算 {s3:.1f}/30，问题清单 {s4:.1f}/20，催缴对象 {s5:.1f}/5）')
