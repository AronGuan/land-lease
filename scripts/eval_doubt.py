"""第四条落地：涂改处无签章的，按口径第十二条"对产权人有利（应缴最少）"暂算。

对每份「涂改字段非空且涂改处无签章」的档案：
  1) 方案A = 现台账（按涂改后内容）
  2) 方案B = 按涂改前内容重算
  3) 取应缴较少者为暂算口径并落到台账，问题清单记「存疑待确认」+ 两算法金额与差额

用法：python scripts/eval_doubt.py
"""
from __future__ import annotations

import sys
from decimal import Decimal

sys.path.insert(0, '.')

from sqlalchemy import select

from landlease.app.core.db import SessionLocal
from landlease.app.models import ContractDoc, Issue, Parcel, ParcelDoc
from landlease.app.services.calc import to_date
from landlease.app.services.ledger import recompute_parcel

# 涂改字段名 → 合同主表列
FIELD_MAP = {
    '土地面积': ('area', 'num'),
    '租赁终止日': ('end_date', 'date'),
    '租赁起始日': ('start_date', 'date'),
    '年租金小写': ('rent_amount', 'num'),
    '年租金（小写）': ('rent_amount', 'num'),
    '年租金大写': ('rent_amount_cn', 'text'),
    '年租金标准': ('rate', 'num'),
    '计租方式': ('rent_mode', 'mode'),
    '租赁年限': ('years', 'year'),
    '联系电话': ('phone', 'text'),
}


def _conv(kind: str, raw):
    if raw is None or str(raw).strip() == '':
        return None
    s = str(raw).strip()
    if kind == 'num':
        import re
        m = re.match(r'^\s*[-+]?\d+(?:\.\d+)?', s)
        return float(m.group()) if m else None
    if kind == 'date':
        d = to_date(s)
        return d
    if kind == 'year':
        import re
        m = re.match(r'^\s*(\d+)', s)
        return int(m.group(1)) if m else None
    if kind == 'mode':
        # 原文含未勾选框（□ / 口）→ 该选项未被选中，无法确定
        if '□' in s or '口' in s:
            return None
        if '随' in s and ('标准' in s or '基准地价' in s):
            return '随标准调整'
        if '固定' in s:
            return '固定'
        return None          # 原文未勾选 → 无法确定，按另一方案试算
    return s


def main():
    db = SessionLocal()
    try:
        docs = db.scalars(select(ContractDoc)
                          .where(ContractDoc.altered_field.isnot(None))).all()
        targets = []
        for c in docs:
            f = (c.altered_field or '').strip()
            if not f or f not in FIELD_MAP:
                continue
            # 有签章 → 以涂改后为准，不存疑
            if c.altered_seal == 1:
                continue
            targets.append(c)
        print(f'需按第四条暂算的档案: {[c.id for c in targets]}')

        for c in targets:
            link = db.scalar(select(ParcelDoc).where(ParcelDoc.archive_no == c.id))
            if not link:
                print(f'  {c.id}: 未入库，跳过')
                continue
            pk = link.parcel_key
            parcel = db.get(Parcel, pk)
            due_a = float(parcel.total_due or 0)

            col, kind = FIELD_MAP[(c.altered_field or '').strip()]
            current = getattr(c, col)
            before_raw = c.altered_before
            alt = _conv(kind, before_raw)
            if alt is None:
                # 计租方式未勾选 → 取与当前相反的方案试算
                if col == 'rent_mode':
                    alt = '固定' if (c.rent_mode or '') != '固定' else '随标准调整'
                else:
                    print(f'  {c.id}: 涂改前内容「{before_raw}」无法解析，跳过')
                    continue

            # 方案B：临时替换 → 重算
            setattr(c, col, alt)
            db.flush()
            res = recompute_parcel(db, pk)
            db.flush()
            due_b = float(res.get('total_due') or 0)

            # 取应缴较少者（对产权人有利）
            if due_b < due_a - 0.005:
                chosen, chosen_name = 'B', '涂改前'
                # 保留 B（已写入）
                keep_alt = True
            else:
                setattr(c, col, current)      # 还原为 A
                db.flush()
                res = recompute_parcel(db, pk)
                db.flush()
                chosen, chosen_name = 'A', '涂改后'
                keep_alt = False

            diff = abs(due_a - due_b)
            desc = (f'「{c.altered_field}」处涂改且涂改处无签章：'
                    f'按涂改后（{current}）应缴 {due_a:,.2f} 元；'
                    f'按涂改前（{before_raw}）应缴 {due_b:,.2f} 元，差额 {diff:,.2f} 元。'
                    f'按第十二条暂取对产权人有利（应缴较少）的「{chosen_name}」口径，待主管部门确认')

            exist = db.scalar(select(Issue).where(Issue.target == c.id,
                                                  Issue.issue_type == '存疑待确认',
                                                  Issue.description.like('%涂改%')))
            if exist:
                exist.description = desc
            else:
                db.add(Issue(target=c.id, issue_type='存疑待确认',
                             description=desc, status='open'))
            db.commit()
            print(f'  {c.id} {c.altered_field}: A={due_a:,.2f} / B={due_b:,.2f} '
                  f'差额={diff:,.2f} → 暂用{chosen_name}（{  "保留B" if keep_alt else "还原A"}）')

        # 汇总
        rows = db.scalars(select(Parcel)).all()
        print(f'\n重算后：{len(rows)} 宗 / 应缴 {sum(float(p.total_due or 0) for p in rows):,.2f}'
              f' / 实缴 {sum(float(p.total_paid or 0) for p in rows):,.2f}'
              f' / 欠缴 {sum(float(p.arrears or 0) for p in rows):,.2f}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
