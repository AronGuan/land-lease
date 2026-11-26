"""评测集阶段 2：合同入库后归集缴费与减免，并重算全部宗地台账。

前提：合同已通过批次识别并「确认入库」（parcel / parcel_doc 已生成）。
用法：python scripts/eval_link.py
"""
from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '.')

from sqlalchemy import select

from landlease.app.core.db import SessionLocal
from landlease.app.models import (Parcel, PaymentAlloc, PaymentRecord,
                                  ReductionRecord)
from landlease.app.services import dataset
from landlease.app.services.ledger import recompute_parcel

BASE = Path('数据切分/国有土地租赁模拟样本包_评测集/评测集')


def _door(loc: str) -> str:
    """提取门牌号，如 '××镇河东街232号' → '232'。"""
    m = re.search(r'(\d+)\s*号', str(loc or ''))
    return m.group(1) if m else ''


def _street(loc: str) -> str:
    """提取街路名，如 '××镇河东街232号' → '河东街'。"""
    m = re.search(r'(?:镇|街道)?([\u4e00-\u9fa5]{2,4}(?:街|路|道|巷))', str(loc or ''))
    return m.group(1) if m else ''


def main():
    db = SessionLocal()
    try:
        parcels = db.scalars(select(Parcel)).all()
        if not parcels:
            print('无宗地，请先完成合同识别与确认入库'); return
        print(f'当前宗地 {len(parcels)} 个')

        # 索引
        by_lessee: dict = {}
        by_owner: dict = {}
        for p in parcels:
            if p.contract_lessee:
                by_lessee.setdefault(p.contract_lessee, []).append(p)
            if p.reg_owner:
                by_owner.setdefault(p.reg_owner, []).append(p)

        def match(payer: str, loc_text: str):
            """返回 parcel_key：先按门牌号+街路，再按缴款人。"""
            d = _door(loc_text)
            s = _street(loc_text)
            if d:
                best = None
                for p in parcels:
                    for loc in (p.reg_location,):
                        if not loc:
                            continue
                        if _door(loc) == d and (not s or s == _street(loc)):
                            best = p; break
                    if best:
                        break
                if best:
                    return best.parcel_key
            if payer:
                cands = by_lessee.get(payer) or by_owner.get(payer)
                if cands:
                    return cands[0].parcel_key
            return None

        # 1) 缴费归集
        pays = db.scalars(select(PaymentRecord)).all()
        hit = miss = 0
        for pr in pays:
            raw = pr.raw_row or {}
            loc_text = str(raw.get('宗地（收费员录入）') or '')
            pk = match(str(pr.payer or ''), loc_text)
            if not pk:
                miss += 1
                continue
            hit += 1
            pr.parcel_key = pk
            exists = db.scalar(select(PaymentAlloc)
                               .where(PaymentAlloc.payment_id == pr.id))
            if not exists:
                db.add(PaymentAlloc(payment_id=pr.id, parcel_key=pk,
                                    year=pr.note_year or 0,
                                    amount=float(pr.amount or 0)))
        db.commit()
        print(f'缴费归集: 匹配 {hit} 条 / 未匹配 {miss} 条')

        # 2) 减免归集
        data = dataset.load_eval(BASE)
        by_unit = {p.unit_no: p.parcel_key for p in parcels if p.unit_no}
        red_hit = 0
        for r in data['reductions']:
            unit = str(r.get('不动产单元号') or '')
            pk = by_unit.get(unit)
            if not pk:
                loc = str(r.get('坐落') or '')
                d, s = _door(loc), _street(loc)
                for p in parcels:
                    if d and _door(p.reg_location) == d and (not s or s == _street(p.reg_location)):
                        pk = p.parcel_key; break
            if not pk:
                print(f'  减免未匹配: {r.get("批准文号")} {r.get("坐落")}')
                continue
            ratio = Decimal(str(r.get('减免比例') or 0).replace('%', ''))
            if ratio > 1:
                ratio = ratio / 100
            db.add(ReductionRecord(parcel_key=pk,
                                   from_year=int(r.get('减免起始年度') or 0),
                                   to_year=int(r.get('减免终止年度') or 0),
                                   ratio=float(ratio), doc_no=r.get('批准文号')))
            red_hit += 1
        db.commit()
        print(f'减免归集: {red_hit} 条')

        # 3) 重算全部宗地
        total_due = total_paid = total_arr = 0.0
        for p in parcels:
            res = recompute_parcel(db, p.parcel_key)
            total_due += float(res.get('total_due') or 0)
            total_paid += float(res.get('total_paid') or 0)
            total_arr += float(res.get('arrears') or 0)
        db.commit()
        print(f'重算完成：{len(parcels)} 宗 / 应缴 {total_due:,.2f} / '
              f'实缴 {total_paid:,.2f} / 欠缴 {total_arr:,.2f}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
