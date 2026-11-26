"""评测集参考数据灌库（弃用练习集）

只灌 02 登记 / 03 缴费 / 04 减免 / 05 计租标准+街路级别；
合同不灌（走批次 OCR 识别），宗地与台账在合同确认入库时由 ledger 引擎生成。

用法：python scripts/eval_seed.py
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '.')

from sqlalchemy import delete, select

from landlease.app.core.db import SessionLocal
from landlease.app.models import (AuditLog, CollectionNotice, ContractDoc,
                                   FieldCorrection, FieldExtraction,
                                   ImportBatch, Issue, ModelCallLog, Parcel,
                                   ParcelDoc, PaymentAlloc, PaymentRecord,
                                   ReductionRecord, RegistryParcel,
                                   RegistryStreetLevel, RentDue, RentStandard,
                                   SmsTask, TaxPush, TaxPushItem)
from landlease.app.services import dataset
from landlease.app.services.calc import to_date

BASE = Path('数据切分/国有土地租赁模拟样本包_评测集/评测集')


def _n(v):
    if v is None or v == '':
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def clear_all(db):
    for m in (PaymentAlloc, PaymentRecord, RentDue, Issue, ParcelDoc, Parcel,
              ContractDoc, FieldCorrection, FieldExtraction, ReductionRecord,
              RegistryParcel, RegistryStreetLevel, RentStandard, ImportBatch,
              PaymentTrack_, SmsTask, CollectionNotice, TaxPushItem, TaxPush,
              AuditLog, ModelCallLog):
        db.execute(delete(m))
    db.commit()
    print('已清空业务表（练习集数据已弃用）')


def seed(db, data: dict):
    # 1) 计租标准
    stds = dataset.parse_standards(data['standards'])
    for s in stds:
        db.add(RentStandard(land_usage=s.land_usage, land_level=s.land_level,
                            effective_from=s.effective_from, price=s.price))
    print(f'计租标准: {len(stds)} 条')

    # 2) 街路 → 土地级别
    street = dataset.parse_street_level(data['street_level'])
    for name, level in street.items():
        db.add(RegistryStreetLevel(street_name=name, land_level=level))
    print(f'街路级别: {len(street)} 条')

    # 3) 不动产登记
    for r in data['registry']:
        db.add(RegistryParcel(
            unit_no=str(r.get('不动产单元号') or '') or None,
            location=r.get('坐落'),
            area=float(_n(r.get('宗地面积（㎡）')) or 0) or None,
            owner=r.get('权利人'),
            phone=r.get('联系电话'),
            raw_row={k: (str(v) if v is not None else None) for k, v in r.items()},
        ))
    print(f'不动产登记: {len(data["registry"])} 条')

    # 4) 缴费记录（原样入库，parcel_key 待合同入库后归集）
    seen = {}
    dup = 0
    for r in data['payments']:
        tno = str(r.get('票据号') or '').strip()
        is_dup = 0
        if tno:
            if tno in seen:
                is_dup = 1
                dup += 1
            else:
                seen[tno] = True
        year_raw = r.get('所属年度')
        note_year = int(year_raw) if year_raw and str(year_raw).isdigit() else None
        db.add(PaymentRecord(
            ticket_no=tno or None,
            parcel_key=None,
            pay_date=to_date(r.get('缴费日期')),
            amount=float(_n(r.get('金额（元）')) or 0),
            payer=r.get('缴款人'),
            note_year=note_year,
            is_duplicate=is_dup,
            raw_row={k: (str(v) if v is not None else None) for k, v in r.items()},
        ))
    print(f'缴费记录: {len(data["payments"])} 条（重复票据标记 {dup} 条）')

    # 5) 减免登记暂不灌（需 parcel_key，入库后由 eval_link 处理）
    print(f'减免登记: {len(data["reductions"])} 条待合同入库后归集')
    db.commit()


if __name__ == '__main__':
    from landlease.app.models import PaymentTrack as PaymentTrack_

    data = dataset.load_eval(BASE)
    print(f'评测集数据: 登记 {len(data["registry"])} / 缴费 {len(data["payments"])} '
          f'/ 减免 {len(data["reductions"])} / 标准 {len(data["standards"])} 行')
    db = SessionLocal()
    try:
        clear_all(db)
        seed(db, data)
        print('\n参考数据灌库完成，合同请走批次导入识别')
    finally:
        db.close()
