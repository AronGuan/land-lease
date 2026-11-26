"""把当前 MySQL 数据整体导出成 SQLite 文件，供云端演示链接使用。

用法：
    python scripts/export_to_sqlite.py                 # 输出 dist/cloud_demo/demo.db
    python scripts/export_to_sqlite.py --out xxx.db

说明：
- 以 ORM 模型为准建表（Base.metadata.create_all），与 MySQL 结构一一对应；
- 逐表按外键顺序复制，行数打印出来可与 MySQL 对账；
- 金额列 DECIMAL 在 SQLite 落为 REAL，展示按 2 位小数舍入，与 MySQL 看不出差别。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, insert, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from landlease.app import models  # noqa: E402,F401  注册全部模型
from landlease.app.core.db import Base, engine as src_engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='dist/cloud_demo/demo.db')
    args = ap.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    dst_engine = create_engine(f'sqlite:///{out_path}', future=True)
    Base.metadata.create_all(bind=dst_engine)

    total = 0
    with Session(src_engine) as src, Session(dst_engine) as dst:
        for table in Base.metadata.sorted_tables:
            rows = [dict(r) for r in src.execute(select(table)).mappings()]
            if rows:
                dst.execute(insert(table), rows)
            total += len(rows)
            print(f'  {table.name:<24} {len(rows):>6} 行')
        dst.commit()

    # 对账：两边逐表行数必须一致
    print('\n--- 对账 ---')
    bad = 0
    with Session(src_engine) as src, Session(dst_engine) as dst:
        for table in Base.metadata.sorted_tables:
            a = src.execute(select(func.count()).select_from(table)).scalar()
            b = dst.execute(select(func.count()).select_from(table)).scalar()
            flag = 'OK ' if a == b else '差异'
            if a != b:
                bad += 1
                print(f'  {flag} {table.name:<24} MySQL={a} SQLite={b}')
    print(f'  {"全部一致" if bad == 0 else str(bad) + " 张表不一致"} · 合计 {total} 行')
    print(f'\n输出：{out_path}  ({out_path.stat().st_size / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
