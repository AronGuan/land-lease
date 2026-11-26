"""确认入库 → 生成/更新宗地台账（Parcel / ParcelDoc / RentDue）+ 汇总回写。

复核工作台点「确认入库」后的真实落地链路（PRD 第⑤步「复核确认即入库生成台账」）：
1. 定位该合同所属宗地（已有关系 → 宗地号↔登记单元号位段匹配 → 新开宗地）
2. 写入宗地-合同关系（主合同 / 续期）
3. 用主档合同信息 + 不动产登记信息刷新 parcel
4. 按 calc 引擎重算该宗地逐年应缴/实缴/欠缴 → 覆写 rent_due
5. 回写 parcel 汇总（total_due / total_paid / arrears / due_2026 / arrears_years）

这样工作台 KPI、宗地台账、欠缴看板、到期日历都会随确认即时更新。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import (ContractDoc, Issue, Parcel, ParcelDoc, PaymentAlloc,
                      PaymentRecord, ReductionRecord, RegistryParcel,
                      RegistryStreetLevel, RentDue, RentStandard)
from .calc import (Contract, ParcelContext, Payment, Standard, cn_amount,
                   compute_parcel)
from .grouping import parcel_matches_unit

BASELINE = date(2026, 9, 30)


def _standards(db: Session) -> list:
    return [Standard(r.land_usage, r.land_level, r.effective_from, r.price)
            for r in db.scalars(select(RentStandard)).all()]


def _dec(v) -> Optional[Decimal]:
    try:
        return Decimal(str(v)) if v not in (None, '') else None
    except Exception:
        return None


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def level_from_street(db: Session, location: Optional[str]) -> Optional[str]:
    """按坐落中的街路名反查土地级别（口径：合同未载明级别的，取街路级别）。"""
    if not location:
        return None
    loc = str(location)
    best = None
    for r in db.scalars(select(RegistryStreetLevel)).all():
        name = (r.street_name or '').strip()
        if name and name in loc:
            # 取匹配到的最长街路名，避免「繁荣路」与「繁荣」混淆
            if best is None or len(name) > len(best[0]):
                best = (name, r.land_level)
    return best[1] if best else None


def match_registry(db: Session, parcel_no: Optional[str]) -> Optional[RegistryParcel]:
    """按合同宗地号 ↔ 不动产单元号位段匹配登记记录。"""
    if not parcel_no:
        return None
    for r in db.scalars(select(RegistryParcel)).all():
        if r.unit_no and parcel_matches_unit(parcel_no, r.unit_no):
            return r
    return None


_match_registry = match_registry  # 兼容旧调用


def resolve_parcel_key(db: Session, doc: ContractDoc) -> str:
    """定位合同所属宗地键：已有关系优先，其次按宗地号匹配登记单元号，否则以档案号新开宗地。"""
    link = db.scalar(select(ParcelDoc).where(ParcelDoc.archive_no == doc.id))
    if link:
        return link.parcel_key
    reg = _match_registry(db, doc.parcel_no)
    if reg:
        p = db.scalar(select(Parcel).where(Parcel.unit_no == reg.unit_no))
        if p:
            return p.parcel_key
    return doc.id


def confirm_and_land(db: Session, doc: ContractDoc) -> dict:
    """确认入库：状态置 confirmed + 生成/更新宗地台账 + 重算核算 + 消解该档案问题。"""
    doc.status = 'confirmed'
    parcel_key = resolve_parcel_key(db, doc)

    # ── 宗地-合同关系 ──
    link = db.scalar(select(ParcelDoc).where(ParcelDoc.parcel_key == parcel_key,
                                             ParcelDoc.archive_no == doc.id))
    has_main = db.scalar(select(ParcelDoc).where(ParcelDoc.parcel_key == parcel_key,
                                                ParcelDoc.role == '主合同')) is not None
    if link is None:
        db.add(ParcelDoc(parcel_key=parcel_key, archive_no=doc.id,
                         role='续期' if has_main else '主合同',
                         start_date=doc.start_date, end_date=doc.end_date))
    else:
        link.start_date = doc.start_date
        link.end_date = doc.end_date
    db.flush()

    # ── 宗地主档 ──
    parcel = db.get(Parcel, parcel_key)
    if parcel is None:
        parcel = Parcel(parcel_key=parcel_key, process_type=doc.process_type)
        db.add(parcel)

    reg = _match_registry(db, doc.parcel_no)
    if reg:
        parcel.unit_no = parcel.unit_no or reg.unit_no
        parcel.reg_location = reg.location
        parcel.reg_area = reg.area
        parcel.reg_owner = reg.owner
    # 合同未载明土地级别 → 按坐落街路反查（否则「随标准调整」取不到标准价）
    if not parcel.land_level:
        parcel.land_level = (level_from_street(db, parcel.reg_location or doc.location)
                             or doc.land_level)

    members = db.scalars(
        select(ContractDoc).join(ParcelDoc, ParcelDoc.archive_no == ContractDoc.id)
        .where(ParcelDoc.parcel_key == parcel_key,
               ContractDoc.status == 'confirmed')).all()
    if members:
        latest = max(members, key=lambda c: (c.start_date or date(1900, 1, 1), c.id))
        parcel.contract_area = latest.area
        parcel.land_usage = latest.land_usage or parcel.land_usage
        parcel.land_level = latest.land_level or parcel.land_level
        parcel.rent_mode = latest.rent_mode
        ends = [c.end_date for c in members if c.end_date]
        parcel.end_date = max(ends) if ends else parcel.end_date
        parcel.contract_lessee = latest.lessee
        parcel.phone = latest.phone or parcel.phone
        parcel.dunning_target = parcel.reg_owner or latest.lessee
        parcel.process_type = ('自动通过' if all(c.process_type == '自动通过' for c in members)
                               else '人工复核')
    db.flush()

    summary = recompute_parcel(db, parcel_key)
    # 复核确认即视为问题已核对：该档案未消解问题自动置已消解（留痕可追溯，不物理删除）
    db.execute(
        update(Issue)
        .where(Issue.target == doc.id, Issue.status == 'open')
        .values(status='resolved',
                description=func.concat(func.coalesce(Issue.description, ''),
                                        '｜复核入库确认消解')))
    db.flush()
    return {'parcel_key': parcel_key, **summary}


def recompute_parcel(db: Session, parcel_key: str) -> dict:
    """按已确认合同 + 缴费归集 + 减免，重算并覆写 rent_due 与 parcel 汇总。

    若该宗地已无任何「已确认」合同（例如唯一合同被撤回），则整宗移除，
    回到确认入库前的状态；重新确认时会再次生成。
    """
    docs = db.scalars(
        select(ContractDoc).join(ParcelDoc, ParcelDoc.archive_no == ContractDoc.id)
        .where(ParcelDoc.parcel_key == parcel_key,
               ContractDoc.status == 'confirmed')).all()
    if not docs:
        db.execute(delete(RentDue).where(RentDue.parcel_key == parcel_key))
        db.execute(delete(ParcelDoc).where(ParcelDoc.parcel_key == parcel_key))
        db.execute(delete(Parcel).where(Parcel.parcel_key == parcel_key))
        db.flush()
        return {'parcel_key': parcel_key, 'rows': 0, 'removed': True}

    pays = []
    for alloc in db.scalars(select(PaymentAlloc)
                            .where(PaymentAlloc.parcel_key == parcel_key)).all():
        pr = db.get(PaymentRecord, alloc.payment_id)
        pays.append(Payment(ticket_no=(pr.ticket_no if pr else '') or '',
                            pay_date=pr.pay_date if pr else None,
                            amount=Decimal(str(alloc.amount or 0)),
                            note_year=alloc.year,
                            is_duplicate=bool(pr.is_duplicate) if pr else False))
    reds = [(r.from_year, r.to_year, Decimal(str(r.ratio)))
            for r in db.scalars(select(ReductionRecord)
                                .where(ReductionRecord.parcel_key == parcel_key)).all()]

    parcel = db.get(Parcel, parcel_key)
    contract_status = '有效'
    if parcel and parcel.end_date and parcel.end_date < BASELINE:
        contract_status = '到期未续'

    # 合同未载明「用途/级别」时回退宗地台账口径（标准答案的计租依据在宗地表）
    pk_level = parcel.land_level if parcel else None
    pk_usage = parcel.land_usage if parcel else None

    ctx = ParcelContext(
        parcel_key=parcel_key,
        contracts=[Contract(archive_no=c.id, doc_type=c.doc_type or '',
                            start_date=c.start_date, end_date=c.end_date,
                            rent_mode=c.rent_mode or '',
                            rent_amount=_dec(c.rent_amount),
                            rent_cn=cn_amount(c.rent_amount_cn) if c.rent_amount_cn else None,
                            rate=_dec(c.rate), area=_dec(c.area),
                            land_usage=(c.land_usage or pk_usage or ''),
                            land_level=(c.land_level or pk_level
                                        or level_from_street(db, c.location) or ''))
                   for c in docs],
        payments=pays, reductions=reds, contract_status=contract_status)
    res = compute_parcel(ctx, _standards(db))

    db.execute(delete(RentDue).where(RentDue.parcel_key == parcel_key))
    for row in res['rows']:
        db.add(RentDue(parcel_key=parcel_key, year=row['year'], months=row['months'],
                       applied_rent=_f(row['applied_rent']),
                       due_amount=_f(row['due']), paid_amount=_f(row['paid']),
                       arrears=_f(row['arrears'])))
    if parcel is not None:
        # 主档快照同步为「最新合同」信息（改字段后面积/承租人/终止日等随之刷新）
        latest = max(docs, key=lambda c: (c.start_date or date(1900, 1, 1), c.id))
        parcel.contract_area = latest.area
        parcel.land_usage = latest.land_usage or parcel.land_usage
        parcel.land_level = latest.land_level or parcel.land_level
        parcel.rent_mode = latest.rent_mode
        ends = [c.end_date for c in docs if c.end_date]
        if ends:
            parcel.end_date = max(ends)
        parcel.contract_lessee = latest.lessee
        parcel.phone = latest.phone or parcel.phone
        parcel.dunning_target = parcel.reg_owner or latest.lessee
        parcel.contract_status = contract_status
        parcel.total_due = _f(res['total_due'])
        parcel.total_paid = _f(res['total_paid'])
        parcel.arrears = _f(res['arrears'])
        parcel.due_2026 = _f(res['due_2026'])
        parcel.arrears_years = '、'.join(res['arrears_years'])
    db.flush()
    return {'parcel_key': parcel_key, 'rows': len(res['rows']),
            'total_due': float(res['total_due']),
            'total_paid': float(res['total_paid']),
            'arrears': float(res['arrears'])}
