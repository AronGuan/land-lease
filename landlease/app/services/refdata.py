"""参考数据（02 登记 / 03 缴费 / 04 减免 / 05 标准）导入与重算。

把 scripts/eval_seed.py、eval_link.py 的一次性逻辑抽成可复用服务：
上传暂存 → 解析预览 → 落库（替换/追加）→ 重新归集 → 全量重算 → 出差异清单。
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import (AuditLog, ContractDoc, Issue, Parcel, ParcelDoc,
                      PaymentAlloc, PaymentRecord, ReductionRecord,
                      RegistryParcel, RegistryStreetLevel, RentDue, RentStandard)
from . import dataset
from .calc import to_date
from .grouping import parcel_matches_unit

UPLOAD_DIR: Path = settings.STORAGE_DIR / 'refdata'

KINDS: dict = {
    'registry': {
        'label': '不动产登记导出', 'source': '02_不动产登记导出.xlsx', 'icon': '02',
        'required': ['不动产单元号', '坐落'], 'sheet': None,
        'desc': '归宗 · 权利人（催缴对象）· 登记面积/坐落比对',
        'affects': '催缴对象、问题清单',
    },
    'payments': {
        'label': '租金缴费记录', 'source': '03_租金缴费记录.xlsx', 'icon': '03',
        'required': ['票据号', '金额（元）'], 'sheet': None,
        'desc': '实缴归集（票据去重 · 按年度/冲抵最早欠缴年）',
        'affects': '实缴 → 欠缴',
    },
    'reductions': {
        'label': '租金减免登记', 'source': '04_租金减免登记.xlsx', 'icon': '04',
        'required': ['减免起始年度', '减免终止年度', '减免比例'], 'sheet': None,
        'desc': '口径第六条：先算应缴再乘 (1 − 减免比例)',
        'affects': '应缴 → 欠缴',
    },
    'standards': {
        'label': '计租标准与土地级别', 'source': '05_计租标准与土地级别.xlsx', 'icon': '05',
        'required': ['用途', '执行起始日'], 'sheet': '计租标准',
        'desc': '「随标准调整」的年租金 = 面积 × 当年 1/1 有效标准价',
        'affects': '应缴',
    },
}

_DUP_KEY = {'registry': '不动产单元号', 'payments': '票据号',
            'reductions': '批准文号', 'standards': None}


# ---------- 上传暂存 ----------

def save_upload(filename: str, content: bytes) -> str:
    """存上传文件，返回 token（preview / commit 凭 token 取文件）。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    (UPLOAD_DIR / f'{token}{Path(filename).suffix.lower() or ".xlsx"}').write_bytes(content)
    return token


def token_path(token: str) -> Optional[Path]:
    if not re.fullmatch(r'[0-9a-f]{12}', str(token or '')):
        return None
    for p in UPLOAD_DIR.glob(f'{token}.*'):
        return p
    return None


# ---------- 解析与预览 ----------

def parse_file(path: Path, kind: str, sheet: str = None) -> dict:
    """解析 xlsx/csv → {'rows','extra','columns','sheets','warnings'}。"""
    cfg = KINDS[kind]
    warnings: list = []
    extra: dict = {}

    if path.suffix.lower() == '.csv':
        rows = dataset._rows_csv(path)
        sheets = ['(csv)']
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        sheets = list(wb.sheetnames)
        want = sheet or cfg.get('sheet')
        if want and want in sheets:
            rows = dataset._rows_xlsx(path, want)
        else:
            rows = dataset._rows_xlsx(path, sheets[0])
            if want and want not in sheets:
                warnings.append(f'未找到工作表「{want}」，已取「{sheets[0]}」')
        if kind == 'standards' and '土地级别范围' in sheets:
            extra['street_level'] = dataset._rows_xlsx(path, '土地级别范围')
        elif kind == 'standards':
            warnings.append('未找到工作表「土地级别范围」，街路级别不会更新')

    columns = list(rows[0].keys()) if rows else []
    missing = [c for c in cfg['required'] if c not in columns]
    if missing:
        warnings.append(f'缺少必备列：{"、".join(missing)}')
    return {'rows': rows, 'extra': extra, 'columns': columns,
            'sheets': sheets, 'warnings': warnings}


def summarize(kind: str, parsed: dict, token: str = None) -> dict:
    """预览摘要：行数 / 必备列空值 / 重复键 / 样例 / 警告。"""
    rows = parsed['rows']
    cfg = KINDS[kind]
    dup_key = _DUP_KEY[kind]
    seen: set = set()
    dup = 0
    blank = {c: 0 for c in cfg['required']}
    for r in rows:
        for c in cfg['required']:
            if r.get(c) in (None, ''):
                blank[c] += 1
        if dup_key:
            v = str(r.get(dup_key) or '')
            if v:
                if v in seen:
                    dup += 1
                else:
                    seen.add(v)
    sample = [{k: (v.isoformat() if isinstance(v, (datetime, date)) else v)
               for k, v in list(r.items())[:6]} for r in rows[:5]]
    out = {
        'token': token, 'kind': kind, 'label': cfg['label'], 'desc': cfg['desc'],
        'affects': cfg['affects'], 'source': cfg['source'],
        'row_count': len(rows), 'columns': parsed['columns'],
        'sheets': parsed.get('sheets') or [],
        'duplicate_key': dup_key, 'duplicate_count': dup,
        'blank_required': {k: v for k, v in blank.items() if v},
        'warnings': parsed['warnings'], 'sample': sample,
    }
    if kind == 'standards':
        out['street_level_count'] = len(parsed['extra'].get('street_level') or [])
    return out


# ---------- 落库 ----------

def _dec(v):
    if v is None or v == '':
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _count(db: Session, kind: str) -> int:
    m = {'registry': RegistryParcel, 'payments': PaymentRecord,
         'reductions': ReductionRecord, 'standards': RentStandard}[kind]
    return int(db.scalar(select(func.count(m.id))) or 0)


def _clear(db: Session, kind: str):
    if kind == 'registry':
        db.execute(delete(RegistryParcel))
    elif kind == 'payments':
        db.execute(delete(PaymentAlloc))
        db.execute(delete(PaymentRecord))
    elif kind == 'reductions':
        db.execute(delete(ReductionRecord))
    elif kind == 'standards':
        db.execute(delete(RentStandard))
        db.execute(delete(RegistryStreetLevel))
    db.flush()


def status(db: Session) -> dict:
    """各类参考数据当前行数与最近一次导入时间。"""
    out = {}
    for kind, cfg in KINDS.items():
        log = db.scalar(select(AuditLog).where(AuditLog.action == 'refdata_import',
                                                AuditLog.target_type == kind)
                        .order_by(desc(AuditLog.id)))
        out[kind] = {
            'label': cfg['label'], 'source': cfg['source'], 'desc': cfg['desc'],
            'affects': cfg['affects'], 'row_count': _count(db, kind),
            'last_import_at': log.created_at.isoformat() if log and log.created_at else None,
            'last_import_by': log.actor if log else None,
            'last_import_rows': log.after_value if log else None,
        }
    if out.get('standards'):
        out['standards']['street_level_count'] = int(
            db.scalar(select(func.count(RegistryStreetLevel.street_name))) or 0)
    return out


def commit(db: Session, kind: str, parsed: dict, mode: str = 'replace',
           operator: str = '系统') -> dict:
    """落库。replace 先清空该类型再写入；append 直接追加。"""
    rows = parsed['rows']
    before = _count(db, kind)
    if mode == 'replace':
        _clear(db, kind)
    inserted = 0

    if kind == 'registry':
        for r in rows:
            db.add(RegistryParcel(
                unit_no=str(r.get('不动产单元号') or '') or None,
                location=r.get('坐落'),
                area=float(_dec(r.get('宗地面积（㎡）')) or 0) or None,
                owner=r.get('权利人'), phone=r.get('联系电话'),
                raw_row={k: (str(v) if v is not None else None) for k, v in r.items()}))
            inserted += 1

    elif kind == 'payments':
        seen: set = set()
        dup = 0
        if mode == 'append':
            seen = {str(x) for x in db.scalars(
                select(PaymentRecord.ticket_no)
                .where(PaymentRecord.ticket_no.isnot(None))).all()}
        for r in rows:
            tno = str(r.get('票据号') or '').strip()
            is_dup = 0
            if tno:
                if tno in seen:
                    is_dup = 1
                    dup += 1
                else:
                    seen.add(tno)
            y = r.get('所属年度')
            db.add(PaymentRecord(
                ticket_no=tno or None, parcel_key=None,
                pay_date=to_date(r.get('缴费日期')),
                amount=float(_dec(r.get('金额（元）')) or 0),
                payer=r.get('缴款人'),
                note_year=int(y) if y and str(y).isdigit() else None,
                is_duplicate=is_dup,
                raw_row={k: (str(v) if v is not None else None) for k, v in r.items()}))
            inserted += 1

    elif kind == 'reductions':
        idx = build_parcel_index(db)
        for r in rows:
            ratio = _dec(str(r.get('减免比例') or '0').replace('%', '')) or Decimal(0)
            if ratio > 1:
                ratio = ratio / 100
            db.add(ReductionRecord(
                parcel_key=match_reduction(idx, r) or '',
                from_year=int(r.get('减免起始年度') or 0),
                to_year=int(r.get('减免终止年度') or 0),
                ratio=float(ratio), doc_no=r.get('批准文号'),
                raw_row={k: (str(v) if isinstance(v, (datetime, date)) else v)
                         for k, v in r.items()}))
            inserted += 1

    elif kind == 'standards':
        stds = dataset.parse_standards(rows)
        for s in stds:
            db.add(RentStandard(land_usage=s.land_usage, land_level=s.land_level,
                                effective_from=s.effective_from, price=s.price))
        inserted = len(stds)
        sl = parsed['extra'].get('street_level')
        if sl is not None:
            for name, level in dataset.parse_street_level(sl).items():
                db.add(RegistryStreetLevel(street_name=name, land_level=level))
    db.flush()
    db.add(AuditLog(actor=operator, action='refdata_import', target_type=kind,
                    before_value=f'{before} rows',
                    after_value=f'{inserted} rows, mode={mode}'))
    db.commit()
    return {'kind': kind, 'mode': mode, 'rows_before': before,
            'inserted': inserted, 'rows_after': _count(db, kind)}


# ---------- 归集匹配 ----------

def _door(loc) -> str:
    m = re.search(r'(\d+)\s*号', str(loc or ''))
    return m.group(1) if m else ''


def _street(loc) -> str:
    m = re.search(r'(?:镇|街道)?([\u4e00-\u9fa5]{2,4}(?:街|路|道|巷))', str(loc or ''))
    return m.group(1) if m else ''


def build_parcel_index(db: Session) -> list:
    """每个宗地的可用匹配线索：宗地键 / 登记单元号 / 坐落（登记 + 合同）/ 人（承租 + 权利）。"""
    parcels = db.scalars(select(Parcel)).all()
    idx = []
    for p in parcels:
        locs = [p.reg_location]
        names = [p.contract_lessee, p.reg_owner, p.dunning_target]
        for link in db.scalars(select(ParcelDoc)
                               .where(ParcelDoc.parcel_key == p.parcel_key)).all():
            c = db.get(ContractDoc, link.archive_no)
            if c:
                locs.append(c.location)
                names.append(c.lessee)
        idx.append({
            'parcel_key': p.parcel_key,
            'unit_no': p.unit_no,
            'locations': [x for x in locs if x],
            'names': [str(x) for x in names if x],
            'doors': {_door(x) for x in locs if x} - {''},
            'streets': {_street(x) for x in locs if x} - {''},
        })
    return idx


def _loc_hit(idx: list, text: str):
    """按「门牌号 + 街路」定位宗地；门牌号唯一时街路可缺省。"""
    d, s = _door(text), _street(text)
    if not d:
        return None
    for it in idx:
        if d in it['doors'] and (not s or s in it['streets']):
            return it['parcel_key']
    return None


def match_payment(idx: list, payer: str, loc_text: str) -> Optional[str]:
    """缴费归集：门牌+街路 → 缴款人姓名。"""
    pk = _loc_hit(idx, loc_text)
    if pk:
        return pk
    payer = str(payer or '').strip()
    if payer:
        for it in idx:
            if any(payer == n or payer in n for n in it['names']):
                return it['parcel_key']
    return None


def match_reduction(idx: list, row: dict) -> Optional[str]:
    """减免归集：不动产单元号 → 门牌+街路 → 承租人/权利人。"""
    unit = str(row.get('不动产单元号') or '').strip()
    if unit:
        for it in idx:
            if it['unit_no'] and parcel_matches_unit(unit, it['unit_no']):
                return it['parcel_key']
    pk = _loc_hit(idx, row.get('坐落'))
    if pk:
        return pk
    who = str(row.get('承租人') or '').strip()
    if who:
        for it in idx:
            if any(who == n for n in it['names']):
                return it['parcel_key']
    return None


def duplicate_groups(db: Session) -> list:
    """按「宗地号段位」找出指向同一宗地的重复宗地键。

    同一宗地在不同合同里可能写旧地号（07-14-0164）也可能写完整单元号
    （000000007014GB00164…），段位相同即为同一宗地；此前因解析缺失被拆成多宗。
    """
    from .grouping import parcel_no_segments

    parcels = db.scalars(select(Parcel)).all()
    parent = {p.parcel_key: p.parcel_key for p in parcels}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)   # 以档案号较小者为主宗地键

    seg_keys: dict = {}
    for p in parcels:
        for link in db.scalars(select(ParcelDoc)
                               .where(ParcelDoc.parcel_key == p.parcel_key)).all():
            c = db.get(ContractDoc, link.archive_no)
            if not c:
                continue
            seg = parcel_no_segments(c.parcel_no)
            if seg:
                seg_keys.setdefault(seg, set()).add(p.parcel_key)
    for keys in seg_keys.values():
        ks = sorted(keys)
        for k in ks[1:]:
            union(ks[0], k)

    groups: dict = {}
    for pk in parent:
        root = find(pk)
        if root != pk or sum(1 for x in parent if find(x) == root) > 1:
            groups.setdefault(root, set()).add(pk)
    out = []
    for root, keys in sorted(groups.items()):
        if len(keys) < 2:
            continue
        ks = sorted(keys)
        out.append({
            'keep': ks[0], 'merge': ks[1:],
            'parcel_keys': ks,
            'contracts': [l.archive_no for k in ks
                          for l in db.scalars(select(ParcelDoc)
                                              .where(ParcelDoc.parcel_key == k)).all()],
        })
    return out


def merge_duplicates(db: Session, operator: str = '系统') -> dict:
    """合并重复宗地键（保留档案号最小者），迁移关联数据后重算。"""
    from .ledger import recompute_parcel

    groups = duplicate_groups(db)
    if not groups:
        return {'merged': 0, 'groups': [], 'diff': []}
    before = {p.parcel_key: (float(p.total_due or 0), float(p.arrears or 0))
              for p in db.scalars(select(Parcel)).all()}
    merged = []
    for g in groups:
        keep, drops = g['keep'], g['merge']
        for d in drops:
            for link in db.scalars(select(ParcelDoc)
                                   .where(ParcelDoc.parcel_key == d)).all():
                link.parcel_key = keep
            for pr in db.scalars(select(PaymentRecord)
                                 .where(PaymentRecord.parcel_key == d)).all():
                pr.parcel_key = keep
            for a in db.scalars(select(PaymentAlloc)
                                .where(PaymentAlloc.parcel_key == d)).all():
                a.parcel_key = keep
            for r in db.scalars(select(ReductionRecord)
                                .where(ReductionRecord.parcel_key == d)).all():
                r.parcel_key = keep
            for i in db.scalars(select(Issue).where(Issue.target == d)).all():
                i.target = keep
            db.execute(delete(RentDue).where(RentDue.parcel_key == d))
            p = db.get(Parcel, d)
            if p:
                db.delete(p)
            merged.append({'from': d, 'to': keep})
        db.flush()
    # 重算受影响的宗地
    for g in groups:
        recompute_parcel(db, g['keep'])
    db.flush()
    parcels = db.scalars(select(Parcel)).all()
    diff = []
    for p in parcels:
        b = before.get(p.parcel_key)
        if b is None:
            continue
        a = (float(p.total_due or 0), float(p.arrears or 0))
        if any(abs(x - y) > 0.005 for x, y in zip(a, b)):
            diff.append({'parcel_key': p.parcel_key,
                         'due_before': round(b[0], 2), 'due_after': round(a[0], 2),
                         'arrears_before': round(b[1], 2), 'arrears_after': round(a[1], 2),
                         'delta_due': round(a[0] - b[0], 2),
                         'delta_arrears': round(a[1] - b[1], 2)})
    db.add(AuditLog(actor=operator, action='parcel_merge', target_type='parcel',
                    after_value=f'{merged}'))
    db.commit()
    return {
        'merged': len(merged), 'groups': merged, 'diff': diff,
        'parcel_count': len(parcels),
        'total_due': round(sum(float(p.total_due or 0) for p in parcels), 2),
        'total_arrears': round(sum(float(p.arrears or 0) for p in parcels), 2),
    }


def relink(db: Session, operator: str = '系统') -> dict:
    """重新匹配登记 + 归集缴费/减免 + 全量重算，返回差异清单。"""
    from .ledger import recompute_parcel

    idx = build_parcel_index(db)
    parcels = db.scalars(select(Parcel)).all()
    before = {p.parcel_key: (float(p.total_due or 0), float(p.total_paid or 0),
                             float(p.arrears or 0)) for p in parcels}

    # 1) 重新匹配登记（登记数据可能已更新）
    reg_rows = db.scalars(select(RegistryParcel)).all()
    relinked = 0
    for p in parcels:
        hit = None
        for link in db.scalars(select(ParcelDoc)
                               .where(ParcelDoc.parcel_key == p.parcel_key)).all():
            c = db.get(ContractDoc, link.archive_no)
            if not c or not c.parcel_no:
                continue
            for r in reg_rows:
                if r.unit_no and parcel_matches_unit(str(c.parcel_no), r.unit_no):
                    hit = r
                    break
            if hit:
                break
        if hit is None:
            for it in idx:
                if it['parcel_key'] != p.parcel_key:
                    continue
                for r in reg_rows:
                    if not r.location:
                        continue
                    if _door(r.location) and _door(r.location) in it['doors'] \
                            and _street(r.location) in it['streets']:
                        hit = r
                        break
                if hit:
                    break
        if hit:
            changed = (p.unit_no != hit.unit_no)
            p.unit_no = hit.unit_no or p.unit_no
            p.reg_location = hit.location or p.reg_location
            p.reg_area = hit.area or p.reg_area
            p.reg_owner = hit.owner or p.reg_owner
            if hit.phone:
                p.phone = hit.phone
            relinked += int(changed)
    db.flush()

    # 2) 缴费归集（重建 alloc，保证与 record 一致）
    db.execute(delete(PaymentAlloc))
    db.flush()
    hit = miss = 0
    for pr in db.scalars(select(PaymentRecord)).all():
        raw = pr.raw_row or {}
        pk = match_payment(idx, str(pr.payer or ''),
                           str(raw.get('宗地（收费员录入）') or ''))
        if not pk:
            pr.parcel_key = None
            miss += 1
            continue
        hit += 1
        pr.parcel_key = pk
        db.add(PaymentAlloc(payment_id=pr.id, parcel_key=pk,
                            year=pr.note_year or 0, amount=float(pr.amount or 0)))
    db.flush()

    # 3) 减免归集
    red_hit = 0
    for r in db.scalars(select(ReductionRecord)).all():
        pk = match_reduction(idx, _reduction_row(r))
        if pk:
            r.parcel_key = pk          # 重新匹配成功则覆盖
            red_hit += 1
        elif r.parcel_key:
            red_hit += 1               # 匹配不到时保留原有归集，不丢数据
    db.flush()

    # 4) 全量重算
    for p in parcels:
        recompute_parcel(db, p.parcel_key)
    db.flush()

    # 差异清单
    diff = []
    for p in parcels:
        b = before.get(p.parcel_key, (0, 0, 0))
        a = (float(p.total_due or 0), float(p.total_paid or 0), float(p.arrears or 0))
        if any(abs(x - y) > 0.005 for x, y in zip(a, b)):
            diff.append({'parcel_key': p.parcel_key,
                         'due_before': round(b[0], 2), 'due_after': round(a[0], 2),
                         'paid_before': round(b[1], 2), 'paid_after': round(a[1], 2),
                         'arrears_before': round(b[2], 2), 'arrears_after': round(a[2], 2),
                         'delta_due': round(a[0] - b[0], 2),
                         'delta_arrears': round(a[2] - b[2], 2)})
    db.add(AuditLog(actor=operator, action='refdata_relink', target_type='parcel',
                    after_value=f'parcels={len(parcels)}, changed={len(diff)}, '
                                f'payments={hit}/{hit + miss}, reductions={red_hit}'))
    db.commit()
    return {
        'parcel_count': len(parcels), 'registry_relinked': relinked,
        'payment_matched': hit, 'payment_missed': miss,
        'reduction_matched': red_hit,
        'changed_count': len(diff), 'diff': diff,
        'total_due': round(sum(float(p.total_due or 0) for p in parcels), 2),
        'total_paid': round(sum(float(p.total_paid or 0) for p in parcels), 2),
        'total_arrears': round(sum(float(p.arrears or 0) for p in parcels), 2),
        'duplicate_groups': duplicate_groups(db),
    }


def _reduction_row(r: ReductionRecord) -> dict:
    """从已入库的减免记录还原匹配所需字段（raw_row 缺失时退回空，匹配不到即跳过）。"""
    raw = r.raw_row or {}
    return {'不动产单元号': raw.get('不动产单元号'), '坐落': raw.get('坐落'),
            '承租人': raw.get('承租人'), '批准文号': r.doc_no}
