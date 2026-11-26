"""从数据库导出评测集三份成果 CSV（合同要素 / 宗地台账 / 问题清单）。

列名与练习集 08_标准答案 一致，末列「处理方式」。
用法：python scripts/eval_export.py
"""
from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '.')

from sqlalchemy import select

from landlease.app.core.db import SessionLocal
from landlease.app.models import (ContractDoc, FieldExtraction, Issue, Parcel,
                                  ParcelDoc)

OUT = Path('数据切分/国有土地租赁模拟样本包_评测集/评测集/结果')

FIELD_COLS = [
    '档案号', '页数', '合同类型', '合同编号', '原合同编号', '签订日期', '出租人',
    '承租人', '承租人类型', '证件号码', '联系电话', '住所', '宗地号', '坐落',
    '土地面积', '用途', '土地级别', '租赁起始日', '租赁终止日', '租赁年限',
    '计租方式', '年租金标准', '年租金小写', '年租金大写', '有无宗地图',
    '涂改字段', '涂改前内容', '涂改处有无签章', '手写批注', '处理方式',
]
LEDGER_COLS = [
    '宗地键', '档案号列表', '不动产单元号', '登记坐落', '登记面积', '合同面积',
    '用途', '土地级别', '计租方式', '合同状态', '合同终止日', '合同承租人',
    '登记权利人', '催缴对象', '联系电话', '2026年度应缴', '累计应缴', '累计实缴',
    '欠缴金额', '欠缴年度', '处理方式',
]
ISSUE_COLS = ['档案号', '问题类型', '说明']


def _s(v) -> str:
    if v is None:
        return ''
    if isinstance(v, Decimal):
        return f'{v:.2f}'.rstrip('0').rstrip('.')
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    return str(v)


def export_contracts(db) -> Path:
    docs = db.scalars(select(ContractDoc).order_by(ContractDoc.id)).all()
    rows = []
    for c in docs:
        ext = {f.field_name: f.final_value for f in
               db.scalars(select(FieldExtraction)
                          .where(FieldExtraction.doc_id == c.id)).all()}
        row = {'档案号': c.id, '页数': c.page_count or '', '处理方式': c.process_type}
        for col in FIELD_COLS:
            if col in row:
                continue
            if col in ext:
                row[col] = _s(ext[col])
            else:
                row[col] = ''
        # 无抽取记录时回退合同主表
        fallback = {
            '合同类型': c.doc_type, '合同编号': c.contract_no, '原合同编号': c.orig_contract_no,
            '签订日期': c.sign_date, '出租人': c.lessor, '承租人': c.lessee,
            '承租人类型': c.lessee_type, '证件号码': c.id_no, '联系电话': c.phone,
            '住所': c.address, '宗地号': c.parcel_no, '坐落': c.location,
            '土地面积': c.area, '用途': c.land_usage, '土地级别': c.land_level,
            '租赁起始日': c.start_date, '租赁终止日': c.end_date, '租赁年限': c.years,
            '计租方式': c.rent_mode, '年租金标准': c.rate, '年租金小写': c.rent_amount,
            '年租金大写': c.rent_amount_cn,
            '有无宗地图': '有' if c.has_map == 1 else ('无' if c.has_map == 0 else ''),
            '涂改字段': c.altered_field, '涂改前内容': c.altered_before,
            '涂改处有无签章': '有' if c.altered_seal == 1 else ('无' if c.altered_seal == 0 else ''),
        }
        for k, v in fallback.items():
            if not row.get(k):
                row[k] = _s(v)
        rows.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / '合同要素.csv'
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELD_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f'合同要素.csv: {len(rows)} 行')
    return p


def export_ledger(db) -> Path:
    parcels = db.scalars(select(Parcel).order_by(Parcel.parcel_key)).all()
    rows = []
    for p in parcels:
        links = db.scalars(select(ParcelDoc).where(ParcelDoc.parcel_key == p.parcel_key)
                           .order_by(ParcelDoc.start_date)).all()
        archives = [lk.archive_no for lk in links]
        latest = db.get(ContractDoc, archives[-1]) if archives else None
        process = '自动通过'
        for a in archives:
            d = db.get(ContractDoc, a)
            if d and d.process_type == '人工复核':
                process = '人工复核'
                break
        rows.append({
            '宗地键': p.parcel_key,
            '档案号列表': ';'.join(archives),
            '不动产单元号': _s(p.unit_no),
            '登记坐落': _s(p.reg_location),
            '登记面积': _s(p.reg_area),
            '合同面积': _s(p.contract_area),
            '用途': _s(p.land_usage),
            '土地级别': _s(p.land_level),
            '计租方式': _s(p.rent_mode),
            '合同状态': _s(p.contract_status),
            '合同终止日': _s(p.end_date),
            '合同承租人': _s(p.contract_lessee),
            '登记权利人': _s(p.reg_owner),
            '催缴对象': _s(p.dunning_target),
            '联系电话': _s(p.phone),
            '2026年度应缴': _s(p.due_2026),
            '累计应缴': _s(p.total_due),
            '累计实缴': _s(p.total_paid),
            '欠缴金额': _s(p.arrears),
            '欠缴年度': _s(p.arrears_years),
            '处理方式': process,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / '宗地台账.csv'
    try:
        f = open(p, 'w', encoding='utf-8-sig', newline='')
    except PermissionError:
        # 目标文件被 Excel 等占用时，改写到带时间戳的副本
        from datetime import datetime
        p = OUT / f'宗地台账_{datetime.now():%Y%m%d_%H%M%S}.csv'
        print(f'  （宗地台账.csv 被占用，改写入 {p.name}）')
        f = open(p, 'w', encoding='utf-8-sig', newline='')
    with f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f'宗地台账.csv: {len(rows)} 行')
    return p


def export_issues(db) -> Path:
    issues = db.scalars(select(Issue).order_by(Issue.target, Issue.issue_type)).all()
    rows = [{'档案号': i.target, '问题类型': i.issue_type,
             '说明': (i.description or '').replace('｜复核入库确认消解', '')}
            for i in issues]
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / '问题清单.csv'
    try:
        f = open(p, 'w', encoding='utf-8-sig', newline='')
    except PermissionError:
        from datetime import datetime
        p = OUT / f'问题清单_{datetime.now():%Y%m%d_%H%M%S}.csv'
        print(f'  （问题清单.csv 被占用，改写入 {p.name}）')
        f = open(p, 'w', encoding='utf-8-sig', newline='')
    with f:
        w = csv.DictWriter(f, fieldnames=ISSUE_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f'问题清单.csv: {len(rows)} 行')
    return p


if __name__ == '__main__':
    db = SessionLocal()
    try:
        export_contracts(db)
        export_ledger(db)
        export_issues(db)
        print(f'\n输出目录: {OUT.resolve()}')
    finally:
        db.close()
