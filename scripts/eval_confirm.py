"""评测集：批量确认入库 → 归集 → 重算 → 合并重复宗地。

用法：python scripts/eval_confirm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, '.')

from sqlalchemy import select

from landlease.app.core.db import SessionLocal
from landlease.app.models import ContractDoc
from landlease.app.services import refdata
from landlease.app.services.ledger import confirm_and_land

OPERATOR = '张贯贯'


def main():
    db = SessionLocal()
    try:
        docs = db.scalars(select(ContractDoc)
                          .where(ContractDoc.status != 'confirmed')).all()
        print(f'待确认 {len(docs)} 份')
        ok = fail = 0
        for c in docs:
            try:
                r = confirm_and_land(db, c)
                db.commit()
                ok += 1
                print(f'  {c.id} → 宗地 {r.get("parcel_key")} '
                      f'应缴 {r.get("total_due")} 欠缴 {r.get("arrears")}')
            except Exception as e:                      # noqa: BLE001
                db.rollback()
                fail += 1
                print(f'  {c.id} FAIL {type(e).__name__}: {e}')
        print(f'确认入库：成功 {ok} / 失败 {fail}')

        print('\n--- 重新归集并重算 ---')
        r = refdata.relink(db, OPERATOR)
        print(f'  宗地 {r["parcel_count"]} · 登记重连 {r["registry_relinked"]} · '
              f'缴费 {r["payment_matched"]}/{r["payment_matched"] + r["payment_missed"]} '
              f'· 减免 {r["reduction_matched"]} · 变化 {r["changed_count"]} 宗')
        print(f'  应缴 {r["total_due"]:,.2f} · 实缴 {r["total_paid"]:,.2f} · '
              f'欠缴 {r["total_arrears"]:,.2f}')

        print('\n--- 合并重复宗地 ---')
        m = refdata.merge_duplicates(db, OPERATOR)
        print(f'  合并 {m["merged"]} 宗：'
              + '、'.join(f'{x["from"]}→{x["to"]}' for x in m['groups']))
        print(f'  宗地 {m["parcel_count"]} · 应缴 {m["total_due"]:,.2f} · '
              f'欠缴 {m["total_arrears"]:,.2f}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
