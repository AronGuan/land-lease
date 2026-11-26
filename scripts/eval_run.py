"""评测集全流程：OCR 识别 → 合同要素.csv → 宗地台账.csv → 问题清单.csv

用法：
    python scripts/eval_run.py ocr        # 仅 OCR（带缓存，可续跑）
    python scripts/eval_run.py csv        # 从缓存生成 3 个 CSV
    python scripts/eval_run.py all        # 先 OCR 再生成 CSV
"""
from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '.')

from landlease.app.services import dataset, grouping
from landlease.app.services.calc import (Contract, ParcelContext, Payment,
                                          Standard, cn_amount, compute_parcel,
                                          to_date)

BASE = Path('数据切分/国有土地租赁模拟样本包_评测集/评测集')
CACHE = BASE / '_ocr_cache'
RESULT = BASE / '结果'
SCAN_DIR = BASE / '01_合同扫描件'

# 合同要素列（与练习集 08_标准答案 一致 + 处理方式）
FIELD_COLS = [
    '档案号', '页数', '合同类型', '合同编号', '原合同编号', '签订日期', '出租人',
    '承租人', '承租人类型', '证件号码', '联系电话', '住所', '宗地号', '坐落',
    '土地面积', '用途', '土地级别', '租赁起始日', '租赁终止日', '租赁年限',
    '计租方式', '年租金标准', '年租金小写', '年租金大写', '有无宗地图',
    '涂改字段', '涂改前内容', '涂改处有无签章', '手写批注', '处理方式',
]
# 宗地台账列
LEDGER_COLS = [
    '宗地键', '档案号列表', '不动产单元号', '登记坐落', '登记面积', '合同面积',
    '用途', '土地级别', '计租方式', '合同状态', '合同终止日', '合同承租人',
    '登记权利人', '催缴对象', '联系电话', '2026年度应缴', '累计应缴', '累计实缴',
    '欠缴金额', '欠缴年度', '处理方式',
]
# 问题清单列
ISSUE_COLS = ['档案号', '问题类型', '说明']

BASELINE = date(2026, 9, 30)


# ────────────────────────── OCR ──────────────────────────

def _load_standards():
    data = dataset.load_eval(BASE)
    return [Standard(s.land_usage, s.land_level, s.effective_from, s.price)
            for s in dataset.parse_standards(data['standards'])]


def _doc_to_json(arc, doc) -> dict:
    return {
        'archive_no': arc,
        'page_count': doc.page_count,
        'process_type': doc.process_type,
        'forced_reasons': doc.forced_reasons,
        'fields': {
            name: {
                'ai_value': f.ai_value,
                'final_value': f.final_value,
                'confidence': f.confidence,
                'evidence': f.evidence,
                'source': f.source,
                'page': f.page,
                'rules': f.rules,
                'issues': f.issues,
                'level': f.level,
            }
            for name, f in doc.fields.items()
        },
    }


def ocr_all():
    CACHE.mkdir(exist_ok=True)
    std_list = _load_standards()
    arcs = sorted({p.stem.rsplit('_', 1)[0]
                   for p in SCAN_DIR.glob('PC-*.jpg')})
    print(f'待识别 {len(arcs)} 份档案')
    done = 0
    for arc in arcs:
        cache_file = CACHE / f'{arc}.json'
        if cache_file.exists():
            done += 1
            print(f'[{done}/{len(arcs)}] {arc}: cached')
            continue
        paths = sorted(SCAN_DIR.glob(f'{arc}_*.jpg'))
        t0 = time.time()
        try:
            from landlease.app.services import recognize
            doc = recognize.recognize_document(arc, [str(p) for p in paths], std_list)
            cache_file.write_text(
                json.dumps(_doc_to_json(arc, doc), ensure_ascii=False, default=str),
                encoding='utf-8')
            done += 1
            print(f'[{done}/{len(arcs)}] {arc}: {time.time()-t0:.0f}s · {doc.process_type}'
                  + (f' · 强制降级({",".join(doc.forced_reasons)})' if doc.forced_reasons else ''))
        except Exception as e:
            print(f'[{done}/{len(arcs)}] {arc}: FAIL {type(e).__name__}: {e}')
    print(f'OCR 完成，已缓存 {done}/{len(arcs)}')


# ────────────────────────── 加载缓存 ──────────────────────────

def load_cached_docs() -> list[dict]:
    docs = []
    for f in sorted(CACHE.glob('PC-*.json')):
        docs.append(json.loads(f.read_text(encoding='utf-8')))
    return docs


# ────────────────────────── 合同要素.csv ──────────────────────────

def build_csv_contracts(docs: list[dict]) -> Path:
    RESULT.mkdir(exist_ok=True)
    out = RESULT / '合同要素.csv'
    rows = []
    for d in docs:
        fv = {n: (d['fields'].get(n) or {}).get('final_value') for n in FIELD_COLS}
        row = {
            '档案号': d['archive_no'],
            '页数': d['page_count'],
            '处理方式': d['process_type'],
        }
        for col in FIELD_COLS:
            if col in ('档案号', '页数', '处理方式'):
                continue
            row[col] = _fmt_val(fv.get(col))
        rows.append(row)
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELD_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f'合同要素.csv: {len(rows)} 行 → {out}')
    return out


def _fmt_val(v) -> str:
    if v is None or v == '':
        return ''
    if isinstance(v, (Decimal,)):
        return str(v)
    return str(v)


# ────────────────────────── 归宗 + 核算 ──────────────────────────

def _build_contracts(docs: list[dict], std_list) -> list[Contract]:
    """DocResult → calc.Contract"""
    out = []
    for d in docs:
        fv = {n: (d['fields'].get(n) or {}).get('final_value') for n in d['fields']}
        def g(k):
            v = (d['fields'].get(k) or {}).get('final_value')
            return v if v not in (None, '') else None
        out.append(Contract(
            archive_no=d['archive_no'],
            doc_type=g('合同类型') or '',
            start_date=to_date(g('租赁起始日')),
            end_date=to_date(g('租赁终止日')),
            rent_mode=g('计租方式') or '',
            rent_amount=_dec(g('年租金小写')),
            rent_cn=cn_amount(g('年租金大写')) if g('年租金大写') else None,
            rate=_dec(g('年租金标准')),
            area=_dec(g('土地面积')),
            land_usage=g('用途') or '',
            land_level=g('土地级别') or '',
        ))
    return out


def _dec(v):
    from decimal import Decimal as D, InvalidOperation
    if v is None or v == '':
        return None
    try:
        return D(str(v))
    except (InvalidOperation, ValueError):
        return None


def _match_payments_to_parcels(payments_raw, parcels_info):
    """将缴费记录归集到宗地（按缴款人 == 承租人；回退按坐落关键词）。"""
    by_payer = {}
    for p in parcels_info:
        if p['lessee']:
            by_payer.setdefault(p['lessee'], []).append(p)
    alloc = {}  # parcel_key -> [Payment]
    unmatched = 0
    seen_ticket = set()
    for r in payments_raw:
        ticket = str(r.get('票据号') or '')
        is_dup = 1 if ticket and ticket in seen_ticket else 0
        if ticket and not is_dup:
            seen_ticket.add(ticket)
        amt = _dec(r.get('金额（元）'))
        if amt is None:
            continue
        year_raw = r.get('所属年度')
        year = int(year_raw) if year_raw and str(year_raw).isdigit() else None
        pay = Payment(ticket_no=ticket or None,
                      pay_date=to_date(r.get('缴费日期')),
                      amount=float(amt), year=year,
                      is_duplicate=bool(is_dup))
        # 匹配宗地
        payer = str(r.get('缴款人') or '').strip()
        loc_text = str(r.get('宗地（收费员录入）') or '').strip()
        pk = None
        # 1) 缴款人 == 承租人
        if payer in by_payer:
            candidates = by_payer[payer]
            pk = candidates[0]['parcel_key'] if len(candidates) == 1 else None
            if pk is None and candidates:
                # 多宗同名 → 用坐落消歧
                for c in candidates:
                    if c['location'] and c['location'][:4] in loc_text:
                        pk = c['parcel_key']; break
                if not pk:
                    pk = candidates[0]['parcel_key']  # 取第一个
        # 2) 坐落关键词
        if not pk:
            for p in parcels_info:
                if p['location'] and p['location'][:6] in loc_text:
                    pk = p['parcel_key']; break
        if pk:
            alloc.setdefault(pk, []).append(pay)
        else:
            unmatched += 1
    print(f'缴费归集: {sum(len(v) for v in alloc.values())} 条匹配, {unmatched} 条未归集')
    return alloc


def _match_reductions(reductions_raw, parcels_info):
    """减免登记 → 宗地（按不动产单元号或坐落）。"""
    by_unit = {p['unit_no']: p['parcel_key'] for p in parcels_info if p['unit_no']}
    alloc = {}
    for r in reductions_raw:
        unit = str(r.get('不动产单元号') or '')
        pk = by_unit.get(unit)
        if not pk:
            loc = str(r.get('坐落') or '')
            for p in parcels_info:
                if loc and p['location'] and loc[:4] in p['location']:
                    pk = p['parcel_key']; break
        if pk:
            ratio = _dec(r.get('减免比例'))
            if ratio and ratio > 1:
                ratio = ratio / 100
            alloc.setdefault(pk, []).append({
                'from_year': int(r.get('减免起始年度') or 0),
                'to_year': int(r.get('减免终止年度') or 0),
                'ratio': float(ratio) if ratio else 0,
                'doc_no': r.get('批准文号') or '',
            })
    return alloc


def compute_parcels(docs: list[dict], data: dict, std_list):
    """归宗 + 核算：返回 (parcels_out, conflicts, doc_dicts)。"""
    contracts = _build_contracts(docs, std_list)
    by_arc = {d['archive_no']: d for d in docs}

    def fv(arc, key):
        return (by_arc[arc]['fields'].get(key) or {}).get('final_value')

    # 归宗输入
    doc_dicts = [{
        '档案号': d['archive_no'],
        '合同类型': fv(d['archive_no'], '合同类型') or '',
        '合同编号': fv(d['archive_no'], '合同编号') or '',
        '原合同编号': fv(d['archive_no'], '原合同编号') or '',
        '宗地号': fv(d['archive_no'], '宗地号') or '',
        '坐落': fv(d['archive_no'], '坐落') or '',
        '承租人': fv(d['archive_no'], '承租人') or '',
        '证件号码': fv(d['archive_no'], '证件号码') or '',
        '联系电话': fv(d['archive_no'], '联系电话') or '',
        '签订日期': fv(d['archive_no'], '签订日期') or '',
        '租赁起始日': fv(d['archive_no'], '租赁起始日') or '',
        '租赁终止日': fv(d['archive_no'], '租赁终止日') or '',
        '土地面积': fv(d['archive_no'], '土地面积') or '',
        '用途': fv(d['archive_no'], '用途') or '',
        '土地级别': fv(d['archive_no'], '土地级别') or '',
        '计租方式': fv(d['archive_no'], '计租方式') or '',
        '年租金小写': fv(d['archive_no'], '年租金小写') or '',
        '年租金大写': fv(d['archive_no'], '年租金大写') or '',
        '涂改字段': fv(d['archive_no'], '涂改字段') or '',
        '涂改前内容': fv(d['archive_no'], '涂改前内容') or '',
        '涂改处有无签章': fv(d['archive_no'], '涂改处有无签章') or '',
        '有无宗地图': fv(d['archive_no'], '有无宗地图') or '',
    } for d in docs]

    raw_groups, conflicts = grouping.group_documents(doc_dicts)

    # 宗地键 = 该宗地「最新一份新签或续期合同」的档案号（使用说明）
    street_map = dataset.parse_street_level(data['street_level'])
    registry = data['registry']
    parcels_info = []
    for tmp_key, members in raw_groups.items():
        # 按起租日排序，最新在后
        members = sorted(members, key=lambda a: (
            to_date(fv(a, '租赁起始日')) or date(1, 1, 1), a))
        # 新签/续期里取最晚的一份作为宗地键
        main_candidates = [a for a in members
                           if str(fv(a, '合同类型') or '') in ('新签', '续期', '续期合同')]
        parcel_key = (main_candidates or members)[-1]
        # 合同链：同宗档案按起租日升序
        latest = members[-1]
        doc_no = fv(latest, '宗地号') or fv(members[0], '宗地号') or ''
        loc = fv(latest, '坐落') or fv(members[0], '坐落') or ''
        # 登记匹配
        reg = None
        for r in registry:
            unit = str(r.get('不动产单元号') or '')
            if unit and doc_no and grouping.parcel_matches_unit(str(doc_no), unit):
                reg = r; break
        # 土地级别：合同 → 街路级别
        level = fv(latest, '土地级别') or fv(members[0], '土地级别') or ''
        if not level:
            level = dataset.infer_level(loc, street_map) or ''
        parcels_info.append({
            'parcel_key': parcel_key,
            'members': members,
            'reg': reg,
            'level': level,
            'lessee': fv(latest, '承租人') or '',
            'location': (reg or {}).get('坐落') or loc,
            'unit_no': (reg or {}).get('不动产单元号') or '',
        })

    # 缴费/减免归集
    pay_alloc = _match_payments_to_parcels(data['payments'], parcels_info)
    red_alloc = _match_reductions(data['reductions'], parcels_info)

    # 核算
    parcels_out = []
    arc_index = {c.archive_no: c for c in contracts}
    for info in parcels_info:
        pk = info['parcel_key']
        members = info['members']
        p_contracts = [arc_index[a] for a in members if a in arc_index]
        latest_end = max((c.end_date for c in p_contracts if c.end_date), default=None)
        status = '到期未续' if (latest_end and latest_end < BASELINE) else '有效'

        # 用途/级别回退（合同未载明时按宗地口径）
        for c in p_contracts:
            if not c.land_level:
                c.land_level = info['level']
            if not c.land_usage:
                c.land_usage = fv(members[-1], '用途') or ''

        ctx = ParcelContext(parcel_key=pk, contracts=p_contracts,
                            payments=pay_alloc.get(pk, []),
                            reductions=[], contract_status=status)
        result = compute_parcel(ctx, std_list)

        reg = info['reg']
        owner = (reg or {}).get('权利人') or info['lessee']
        phone = (reg or {}).get('联系电话') or ''
        if not phone:
            for a in reversed(members):
                ph = fv(a, '联系电话')
                if ph:
                    phone = str(ph); break

        arrears_years = '、'.join(str(y) for y, v in result['due'].items()
                                   if float(v.get('arrears', 0)) > 0)
        parcels_out.append({
            'parcel_key': pk, 'members': members, 'reg': reg, 'info': info,
            'result': result, 'owner': owner, 'phone': phone,
            'status': status, 'arrears_years': arrears_years, 'level': info['level'],
        })
    return parcels_out, conflicts, doc_dicts


# ────────────────────────── 宗地台账.csv ──────────────────────────

def build_csv_ledger(parcels_out, docs) -> Path:
    RESULT.mkdir(exist_ok=True)
    out = RESULT / '宗地台账.csv'
    by_arc = {d['archive_no']: d for d in docs}
    rows = []
    for p in parcels_out:
        r = p['result']
        reg = p['reg'] or {}
        members = p['members']
        latest = by_arc[members[-1]]

        def fv(key):
            return (latest['fields'].get(key) or {}).get('final_value')

        process = latest.get('process_type', '自动通过')
        if any(by_arc[a].get('process_type') == '人工复核' for a in members):
            process = '人工复核'

        rows.append({
            '宗地键': p['parcel_key'],
            '档案号列表': ';'.join(members),
            '不动产单元号': reg.get('不动产单元号') or '',
            '登记坐落': reg.get('坐落') or fv('坐落') or '',
            '登记面积': _fmt_val(reg.get('宗地面积（㎡）')),
            '合同面积': _fmt_val(fv('土地面积')),
            '用途': fv('用途') or '',
            '土地级别': p['level'],
            '计租方式': fv('计租方式') or '',
            '合同状态': p['status'],
            '合同终止日': _fmt_val(fv('租赁终止日')),
            '合同承租人': fv('承租人') or '',
            '登记权利人': reg.get('权利人') or '',
            '催缴对象': p['owner'],
            '联系电话': p['phone'],
            '2026年度应缴': _fmt_val(r['due'].get(2026, {}).get('due', 0)),
            '累计应缴': _fmt_val(r['total_due']),
            '累计实缴': _fmt_val(r['total_paid']),
            '欠缴金额': _fmt_val(r['arrears']),
            '欠缴年度': p['arrears_years'],
            '处理方式': process,
        })
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f'宗地台账.csv: {len(rows)} 行 → {out}')
    return out


# ────────────────────────── 问题清单.csv ──────────────────────────

def build_csv_issues(docs, parcels_out, doc_dicts, conflicts) -> Path:
    RESULT.mkdir(exist_ok=True)
    out = RESULT / '问题清单.csv'
    issues = []
    seen = set()  # (档案号, 问题类型) dedupe

    def add(target, itype, desc):
        key = (target, itype)
        if key in seen:
            return
        seen.add(key)
        issues.append({'档案号': target, '问题类型': itype, '说明': desc})

    for d in docs:
        arc = d['archive_no']
        # 字段层问题（来自 recognize.DocResult.issues，已映射到 13 类）
        # 重建 issues：从 fields 的 issues 字段
        for name, fdata in d['fields'].items():
            field_issues = fdata.get('issues') or []
            for fi in field_issues:
                if fi == '不可识别':
                    from landlease.app.services.recognize import OPTIONAL_FIELDS, ISSUE_TYPE_MAP, DEFAULT_ISSUE_TYPE
                    if name in OPTIONAL_FIELDS:
                        continue
                    mapped = DEFAULT_ISSUE_TYPE
                    desc = f'关键字段「{name}」不可识别'
                else:
                    from landlease.app.services.recognize import ISSUE_TYPE_MAP, DEFAULT_ISSUE_TYPE
                    mapped = ISSUE_TYPE_MAP.get(fi, DEFAULT_ISSUE_TYPE)
                    desc = f'字段「{name}」{fi}'
                add(arc, mapped, desc)

        # 涂改字段 → 关键字段有涂改
        altered = (d['fields'].get('涂改字段') or {}).get('final_value')
        altered_seal = (d['fields'].get('涂改处有无签章') or {}).get('final_value')
        if altered and str(altered).strip():
            seal_desc = '涂改处有签章' if str(altered_seal or '').strip() in ('是', '有', '1') else '涂改处无签章'
            add(arc, '关键字段有涂改', f'原件「{altered}」处有涂改，{seal_desc}')

    # 宗地层问题（与登记比对）
    for p in parcels_out:
        pk = p['parcel_key']
        reg = p['reg']
        if reg is None:
            if any((d['fields'].get('宗地号') or {}).get('final_value') for d in [docs[i] for i in p['members']]):
                add(pk, '登记数据中无对应宗地',
                    f'不动产登记导出中查无该宗地（宗地号 {(docs[p["members"][0]]["fields"].get("宗地号") or {}).get("final_value")}）')
        else:
            # 面积不一致
            for i in p['members']:
                area_val = _dec((docs[i]['fields'].get('土地面积') or {}).get('final_value'))
                reg_area = _dec(reg.get('宗地面积（㎡）'))
                if area_val and reg_area and abs(float(area_val) - float(reg_area)) > 0.5:
                    add(pk, '面积与登记不一致',
                        f'合同面积 {area_val} ㎡ 与登记面积 {reg_area} ㎡ 不一致（暂按合同面积计算）')
                    break
            # 坐落不一致
            for i in p['members']:
                loc = (docs[i]['fields'].get('坐落') or {}).get('final_value') or ''
                reg_loc = str(reg.get('坐落') or '')
                if loc and reg_loc and grouping._norm_loc(loc) != grouping._norm_loc(reg_loc):
                    add(pk, '坐落或宗地号与登记不一致',
                        f'合同坐落「{loc}」与登记「{reg_loc}」不一致')
                    break
        # 合同到期未续
        if p['status'] == '到期未续':
            latest_end = max(
                (to_date((docs[i]['fields'].get('租赁终止日') or {}).get('final_value'))
                 for i in p['members']
                 if (docs[i]['fields'].get('租赁终止日') or {}).get('final_value')),
                default=None)
            add(pk, '合同到期未续',
                f'合同已于{latest_end.isoformat() if latest_end else "—"}到期，'
                f'未见续期合同（按最后合同继续计收至 2026）')

    # 缴费异常：重复票据
    from collections import Counter
    data = dataset.load_eval(BASE)
    tickets = [str(r.get('票据号') or '') for r in data['payments'] if r.get('票据号')]
    dups = {t for t, c in Counter(tickets).items() if c > 1}
    if dups:
        # 按宗地匹配（简化：归到第一次出现的宗地）
        for t in dups:
            for r in data['payments']:
                if str(r.get('票据号') or '') == t:
                    # 尝试匹配宗地
                    payer = str(r.get('缴款人') or '')
                    for p in parcels_out:
                        if p['owner'] == payer or any(
                                (docs[i]['fields'].get('承租人') or {}).get('final_value') == payer
                                for i in p['members']):
                            add(p['parcel_key'], '缴费记录异常',
                                f'票据号「{t}」重复登记 {Counter(tickets)[t]} 次，只计一次')
                            break
                    break

    # 归宗冲突
    for c in conflicts:
        add(c.get('parcel_key', '?'), '存疑待确认', c.get('reason', '归宗存在歧义'))

    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ISSUE_COLS)
        w.writeheader()
        w.writerows(issues)
    print(f'问题清单.csv: {len(issues)} 行 → {out}')
    return out


# ────────────────────────── 主入口 ──────────────────────────

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode in ('ocr', 'all'):
        ocr_all()
    if mode in ('csv', 'all'):
        docs = load_cached_docs()
        if not docs:
            print('无缓存，请先运行 ocr'); return
        print(f'\n=== 生成 CSV（{len(docs)} 份档案）===')
        build_csv_contracts(docs)
        data = dataset.load_eval(BASE)
        std_list = _load_standards()
        parcels_out, conflicts, doc_dicts = compute_parcels(docs, data, std_list)
        build_csv_ledger(parcels_out, docs)
        build_csv_issues(docs, parcels_out, doc_dicts, conflicts)
        print(f'\n=== 完成，结果在 {RESULT} ===')


if __name__ == '__main__':
    main()
