"""练习集数据加载：把 CSV/XLSX 读成核算引擎可直接消费的结构。"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[3]
_ENV_DIR = os.getenv('PRACTICE_DIR', '')
PRACTICE_DIR = Path(_ENV_DIR) if _ENV_DIR else (
    ROOT / '国有土地租赁模拟样本包_练习集' / '练习集')


def _rows_csv(path: Path) -> list:
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def _rows_xlsx(path: Path, sheet: str = None) -> list:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    head = next(it)
    return [dict(zip(head, r)) for r in it if any(v is not None for v in r)]


def load_practice(base: Path = None) -> dict:
    base = Path(base) if base else PRACTICE_DIR
    ans = base / '08_标准答案'
    return {
        'contracts': _rows_csv(ans / '合同要素.csv'),
        'ledger': _rows_csv(ans / '宗地台账.csv'),
        'due': _rows_csv(ans / '应缴明细.csv'),
        'alloc': _rows_csv(ans / '缴费归集.csv'),
        'issues': _rows_csv(ans / '问题清单.csv'),
        'registry': _rows_xlsx(base / '02_不动产登记导出.xlsx'),
        'payments': _rows_xlsx(base / '03_租金缴费记录.xlsx'),
        'reductions': _rows_xlsx(base / '04_租金减免登记.xlsx'),
        'standards': _rows_xlsx(base / '05_计租标准与土地级别.xlsx', '计租标准'),
        'street_level': _rows_xlsx(base / '05_计租标准与土地级别.xlsx', '土地级别范围'),
    }


def load_eval(base: Path) -> dict:
    """评测集加载：只读 02/03/04/05（评测集无 08_标准答案）。"""
    base = Path(base)
    return {
        'registry': _rows_xlsx(base / '02_不动产登记导出.xlsx'),
        'payments': _rows_xlsx(base / '03_租金缴费记录.xlsx'),
        'reductions': _rows_xlsx(base / '04_租金减免登记.xlsx'),
        'standards': _rows_xlsx(base / '05_计租标准与土地级别.xlsx', '计租标准'),
        'street_level': _rows_xlsx(base / '05_计租标准与土地级别.xlsx', '土地级别范围'),
    }


def parse_standards(raw: list) -> list:
    """计租标准表：宽表（一级..四级）转长表。"""
    from .calc import Standard
    out = []
    for r in raw:
        eff = r['执行起始日']
        if isinstance(eff, datetime):
            eff = eff.date()
        elif isinstance(eff, str):
            eff = date(*[int(x) for x in eff.split('-')[:3]])
        for lvl in ('一级', '二级', '三级', '四级'):
            price = r.get(lvl)
            if price is None:
                continue
            out.append(Standard(land_usage=str(r['用途']).replace('用地', ''),
                                land_level=lvl, effective_from=eff,
                                price=Decimal(str(price))))
    return out


def parse_street_level(raw: list) -> dict:
    """土地级别范围：街路 -> 级别。"""
    out = {}
    for r in raw:
        level = str(r.get('土地级别') or '')
        streets = str(r.get('所含街路（××镇）') or '')
        for s in [x.strip() for x in streets.replace('、', ',').split(',') if x.strip()]:
            out[s] = level
    return out


def infer_level(location: str, street_map: dict) -> str:
    """口径第二条：合同未载明级别的，按坐落所在街路确定。"""
    if not location or not street_map:
        return ''
    for street, level in street_map.items():
        if street in str(location):
            return level
    return ''


def parse_reductions(raw: list) -> list:
    """减免登记：返回 {unit_no: [(from,to,ratio)]}"""
    out = {}
    for r in raw:
        ratio = str(r.get('减免比例') or '0').replace('%', '')
        try:
            ratio = Decimal(ratio) / Decimal(100) if Decimal(ratio) > 1 else Decimal(ratio)
        except Exception:
            ratio = Decimal(0)
        key = str(r.get('不动产单元号') or '')
        out.setdefault(key, []).append((int(r['减免起始年度']), int(r['减免终止年度']), ratio))
    return out
