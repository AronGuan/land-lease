"""把练习集标准数据灌入 MySQL（演示 / 现场初始化）。

用法：python scripts/seed.py [--clear]

数据来源：国有土地租赁模拟样本包_练习集/练习集/
- 05 计租标准与土地级别.xlsx → rent_standard / registry_street_level
- 02 不动产登记导出.xlsx → registry_parcel
- 04 租金减免登记.xlsx → reduction_record
- 08 标准答案/合同要素.csv → contract_doc
- 08 标准答案/宗地台账.csv → parcel / parcel_doc
- 08 标准答案/应缴明细.csv → rent_due
- 08 标准答案/缴费归集.csv + 03_租金缴费记录.xlsx → payment_record / payment_alloc
- 08 标准答案/问题清单.csv → 不灌库（新合同上传时由检测引擎动态生成）
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from landlease.app.core.db import SessionLocal, init_db  # noqa: E402
from landlease.app.models import (AuditLog, ContractDoc, FieldExtraction,  # noqa: E402
                                   ImportBatch, Issue, Parcel, ParcelDoc,
                                   PaymentAlloc, PaymentRecord, ReductionRecord,
                                   RegistryParcel, RegistryStreetLevel, RentDue,
                                   RentStandard, SysUser)
from landlease.app.services import dataset  # noqa: E402
from landlease.app.services.calc import cn_amount, to_date  # noqa: E402


def _d(v) -> date | None:
    return to_date(v)


def _n(v, typ=Decimal):
    if v in (None, ''):
        return None
    try:
        return typ(str(v))
    except Exception:
        return None


def clear_all(db):
    """清空全部业务表（含催缴/税务，避免上次测试的通知书与回款留痕残留）。"""
    from landlease.app.models import (CollectionNotice, FieldCorrection,
                                      FieldExtraction, ModelCallLog, PaymentTrack,
                                      SmsTask, TaxPush, TaxPushItem)
    for m in (PaymentAlloc, PaymentRecord, RentDue, Issue, ParcelDoc, Parcel,
              ContractDoc, FieldCorrection, FieldExtraction, ReductionRecord,
              RegistryParcel, RegistryStreetLevel, RentStandard, ImportBatch,
              PaymentTrack, SmsTask, CollectionNotice, TaxPushItem, TaxPush,
              AuditLog, ModelCallLog):
        db.execute(delete(m))
    db.commit()


def seed(db, data: dict):
    # ── 按 dataset_80 过滤：只灌 26 宗地 + 40 份合同（已入库），
    #    test_20 的 10 份留给用户手动通过合同治理流程导入 ──
    import csv
    manifest = Path(__file__).resolve().parents[1] / '数据切分' / 'manifest_dataset_80.csv'
    if manifest.exists():
        with open(manifest, encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        ds80_parcels = {r['宗地键'] for r in rows}
        ds80_archives = {r['档案号'] for r in rows}
        before = {k: len(v) for k, v in data.items() if isinstance(v, list)}
        data['contracts'] = [r for r in data['contracts'] if r.get('档案号') in ds80_archives]
        data['ledger'] = [r for r in data['ledger'] if r.get('宗地键') in ds80_parcels]
        data['due'] = [r for r in data['due'] if r.get('宗地键') in ds80_parcels]
        data['alloc'] = [r for r in data['alloc'] if r.get('宗地键') in ds80_parcels]
        # 问题清单不灌库（已复核入库的合同不应有预置问题），跳过过滤
        # 缴费记录通过 alloc 的序号间接过滤
        ds80_seqs = {str(a['序号']) for a in data['alloc']}
        data['payments'] = [r for r in data['payments'] if str(r.get('序号')) in ds80_seqs]
        after = {k: len(v) for k, v in data.items() if isinstance(v, list)}
        print(f'按 dataset_80 过滤：合同 {before.get("contracts",0)}→{after.get("contracts",0)}，'
              f'宗地 {before.get("ledger",0)}→{after.get("ledger",0)}，'
              f'应缴 {before.get("due",0)}→{after.get("due",0)}，'
              f'缴费 {before.get("payments",0)}→{after.get("payments",0)}，'
              f'问题 0（不灌库）')

    # 1) 计租标准
    for r in data['standards']:
        eff = r['执行起始日']
        eff = eff.date() if hasattr(eff, 'date') else _d(eff)
        for lvl in ('一级', '二级', '三级', '四级'):
            price = r.get(lvl)
            if price is None:
                continue
            db.add(RentStandard(land_usage=str(r['用途']).replace('用地', ''),
                                land_level=lvl, effective_from=eff,
                                price=Decimal(str(price))))
    # 2) 街路级别
    street_map = dataset.parse_street_level(data['street_level'])
    for street, level in street_map.items():
        db.add(RegistryStreetLevel(street_name=street, land_level=level))

    # 3) 不动产登记
    for r in data['registry']:
        db.add(RegistryParcel(unit_no=str(r.get('不动产单元号') or ''),
                              location=str(r.get('坐落') or ''),
                              area=_n(r.get('土地面积') or r.get('面积')),
                              owner=str(r.get('权利人') or r.get('权利人名称') or ''),
                              phone=str(r.get('联系电话') or ''),
                              raw_row={k: (str(v) if v is not None else None)
                                       for k, v in r.items()}))
    db.flush()

    # 4) 批次（初始导入批次）
    b = ImportBatch(batch_no='SEED-PRACTICE', batch_type='初始导入',
                    status='done', file_count=0,
                    doc_count=len(data['contracts']), created_by='系统')
    db.add(b); db.flush()

    # 5) 合同档案 + 字段级识别记录
    #    dataset_80 的 40 份由标准答案灌入，字段值 100% 准确 → 全部「已复核入库」
    from landlease.app.services.vlm import FIELDS
    docs = data['contracts']
    for idx, r in enumerate(docs):
        has_alter = bool(r.get('涂改字段'))
        db.add(ContractDoc(
            id=r['档案号'], batch_id=b.id, page_count=_n(r.get('页数'), int),
            doc_type=r.get('合同类型'), contract_no=r.get('合同编号'),
            orig_contract_no=r.get('原合同编号') or None,
            sign_date=_d(r.get('签订日期')), lessor=r.get('出租人'),
            lessee=r.get('承租人'), lessee_type=r.get('承租人类型'),
            id_no=r.get('证件号码'), phone=r.get('联系电话'), address=r.get('住所'),
            parcel_no=r.get('宗地号'), location=r.get('坐落'),
            area=_n(r.get('土地面积')), land_usage=r.get('用途'),
            land_level=r.get('土地级别') or None,
            start_date=_d(r.get('租赁起始日')), end_date=_d(r.get('租赁终止日')),
            years=_n(r.get('租赁年限'), int), rent_mode=r.get('计租方式'),
            rate=_n(r.get('年租金标准')), rent_amount=_n(r.get('年租金小写')),
            rent_amount_cn=r.get('年租金大写'),
            has_map=1 if str(r.get('有无宗地图')) == '是' else 0,
            altered_field=r.get('涂改字段') or None,
            altered_before=r.get('涂改前内容') or None,
            altered_seal=1 if str(r.get('涂改处有无签章')) == '是' else 0,
            handwritten_note=r.get('手写批注') or None,
            process_type='自动通过',
            status='confirmed',
        ))
        # 字段级识别记录（27 字段）
        low_conf_fields = {'涂改字段', '涂改前内容', '涂改处有无签章', '手写批注'}
        for name in FIELDS:
            val = r.get(name)
            val = str(val).strip() if val not in (None, '') else None
            if val is None:
                conf, level, source = None, 'L3', 'blank'
            elif name in low_conf_fields:
                conf, level, source = 0.72, 'L2', 'ai'
            elif has_alter and name in ('土地面积', '年租金小写'):
                conf, level, source = 0.82, 'L2', 'ai'
            else:
                conf, level, source = 0.96, 'L1', 'ai'
            db.add(FieldExtraction(
                doc_id=r['档案号'], field_name=name, ai_value=val,
                final_value=val, confidence=conf, source=source,
                reason={'level': level,
                        'rules': ([f'关键字段有涂改：{r["涂改字段"]}'] if has_alter else [])}))
    db.flush()

    # 6) 宗地台账 + 宗地-合同关系
    for r in data['ledger']:
        db.add(Parcel(
            parcel_key=r['宗地键'], unit_no=r.get('不动产单元号'),
            reg_location=r.get('登记坐落'), reg_area=_n(r.get('登记面积')),
            contract_area=_n(r.get('合同面积')), land_usage=r.get('用途'),
            land_level=r.get('土地级别'), rent_mode=r.get('计租方式'),
            contract_status=r.get('合同状态'), end_date=_d(r.get('合同终止日')),
            contract_lessee=r.get('合同承租人'), reg_owner=r.get('登记权利人'),
            dunning_target=r.get('催缴对象'), phone=r.get('联系电话'),
            due_2026=_n(r.get('2026年度应缴')), total_due=_n(r.get('累计应缴')),
            total_paid=_n(r.get('累计实缴')), arrears=_n(r.get('欠缴金额')),
            arrears_years=r.get('欠缴年度') or '', process_type='自动通过',
        ))
        for i, arc in enumerate(a for a in r['档案号列表'].split(';') if a):
            db.add(ParcelDoc(parcel_key=r['宗地键'], archive_no=arc,
                             role='主合同' if i == 0 else '续期'))
    db.flush()

    # 7) 应缴明细
    for r in data['due']:
        db.add(RentDue(parcel_key=r['宗地键'], year=int(r['年度']),
                       months=None, applied_rent=None,
                       due_amount=_n(r['应缴']) or 0,
                       paid_amount=_n(r['实缴']) or 0,
                       arrears=_n(r['欠缴']) or 0))

    # 8) 减免登记（单元号 → 宗地键）
    parcel_by_unit = {p.unit_no: p.parcel_key for p in
                      db.scalars(select(Parcel)).all() if p.unit_no}
    for r in data['reductions']:
        ratio = str(r.get('减免比例') or '0').replace('%', '')
        try:
            ratio = Decimal(ratio) / 100 if Decimal(ratio) > 1 else Decimal(ratio)
        except Exception:
            ratio = Decimal(0)
        unit = str(r.get('不动产单元号') or '')
        pk = parcel_by_unit.get(unit)
        if not pk:
            # 回退：按坐落匹配
            for p in db.scalars(select(Parcel)).all():
                if r.get('坐落') and r['坐落'] in str(p.reg_location or ''):
                    pk = p.parcel_key
                    break
        if pk:
            db.add(ReductionRecord(parcel_key=pk, from_year=int(r['减免起始年度']),
                                   to_year=int(r['减免终止年度']), ratio=ratio,
                                   doc_no=r.get('批准文号')))

    # 9) 缴费记录 + 归集
    pay_by_seq = {str(r['序号']): r for r in data['payments']}
    seen_ticket: dict = {}
    for r in data['payments']:
        tno = str(r.get('票据号') or '')
        is_dup = 1 if tno and tno in seen_ticket else 0
        if tno and not is_dup:
            seen_ticket[tno] = True
        pr = PaymentRecord(ticket_no=tno or None,
                           pay_date=_d(r.get('缴费日期')),
                           amount=_n(r.get('金额（元）')),
                           payer=r.get('缴款人'),
                           note_year=_n(r.get('所属年度'), int),
                           is_duplicate=is_dup,
                           raw_row={k: (str(v) if v is not None else None)
                                    for k, v in r.items()})
        db.add(pr); db.flush()
        # 归集：按标准答案
        for a in data['alloc']:
            if str(a['序号']) == str(r['序号']):
                db.add(PaymentAlloc(payment_id=pr.id, parcel_key=a['宗地键'],
                                    year=int(r.get('所属年度') or 0),
                                    amount=_n(r.get('金额（元）')) or 0,
                                    alloc_rule='标准答案归集'))

    # 10) 问题清单——不预置灌库
    # 40 份标准答案合同已复核入库（confirmed），不应挂"未消解"问题。
    # 问题清单纯由新合同上传时检测引擎动态生成（batch.py run_pipeline →
    # recognize.judge → doc.issues() + grouping.compare_with_registry）。

    # 11) 默认用户
    if not db.scalar(select(SysUser).where(SysUser.username == 'admin')):
        db.add(SysUser(username='admin', password_hash='seed-not-for-prod',
                       real_name='管理员', role='admin'))

    # 11.5) 模型通道（闭源云端 / 开源可部署 / 本地离线），主通道标记随切走
    from landlease.app.models import ModelCallLog, ModelConfig
    from landlease.app.services.channel import default_channels
    if not db.scalar(select(ModelConfig.id).limit(1)):
        for ch in default_channels():
            db.add(ModelConfig(**ch))

    # 12) 模型调用日志（演示样例，对齐原型「模型调用日志」表）
    for r in [
        dict(model_name='qwen3-vl-plus', target='LX-001_1.jpg', duration_ms=6800,
             tokens=2214, avg_confidence=0.95, result='成功'),
        dict(model_name='qwen3-vl-plus', target='LX-046_2.jpg', duration_ms=9100,
             tokens=2460, avg_confidence=0.61, result='低置信转复核'),
        dict(model_name='qwen3-vl-plus', target='LX-047_1.jpg', duration_ms=7400,
             tokens=2318, avg_confidence=0.97, result='成功'),
        # 开源通道标杆：切换后同一批文档由 Qwen3-VL-32B 跑，供现场对比
        dict(model_name='Qwen/Qwen3-VL-32B-Instruct', target='LX-047_1.jpg',
             duration_ms=4900, tokens=2318, avg_confidence=0.96, result='成功'),
    ]:
        db.add(ModelCallLog(**r))

    db.add(AuditLog(actor='系统', action='seed', target_type='database',
                    after_value=f'contracts={len(data["contracts"])}, '
                                f'parcels={len(data["ledger"])}, due={len(data["due"])}'))
    db.commit()


def main():
    init_db()
    db = SessionLocal()
    try:
        data = dataset.load_practice()
        if '--clear' in sys.argv:
            clear_all(db)
            print('已清空业务表')
        # 幂等：已有宗地则跳过
        if db.scalar(select(Parcel).limit(1)) and '--force' not in sys.argv:
            print('库中已有宗地数据，跳过（如需重灌加 --clear --force）')
            return
        seed(db, data)
        from sqlalchemy import func as _f
        print('灌库完成：',
              f'合同 {db.scalar(select(_f.count(ContractDoc.id)))}，',
              f'宗地 {len(data["ledger"])}，',
              f'应缴 {len(data["due"])}，',
              f'缴费 {len(data["payments"])}，',
              f'问题 {db.scalar(select(_f.count(Issue.id)))}（由新合同识别时动态生成）')
    finally:
        db.close()


if __name__ == '__main__':
    main()
