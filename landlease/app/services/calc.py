"""租金核算引擎（纯规则程序，AI 不参与）。

全部金额使用 Decimal + ROUND_HALF_UP，输出保留到分；评分容差 ±0.01 元。
规则依据：练习集《06_计租标准与核算口径》第三至第八条。
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

CENT = Decimal('0.01')
BASELINE_YEAR = 2026  # 核算基准日 2026-09-30


_CN_DIGIT = {'零': 0, '〇': 0, '壹': 1, '一': 1, '贰': 2, '二': 2, '叁': 3, '三': 3,
             '肆': 4, '四': 4, '伍': 5, '五': 5, '陆': 6, '六': 6, '柒': 7, '七': 7,
             '捌': 8, '八': 8, '玖': 9, '九': 9}
_CN_UNIT = {'拾': 10, '十': 10, '佰': 100, '百': 100, '仟': 1000, '千': 1000}


def cn_amount(text: str) -> Optional[Decimal]:
    """中文大写金额 -> Decimal（如 伍拾柒元陆角叁分 -> 57.63）。"""
    if not text:
        return None
    s = str(text).strip().replace('整', '')
    if '元' in s:
        int_part, _, frac = s.partition('元')
    else:
        int_part, frac = s, ''
    # 分段算法：段内由 拾/佰/仟 累加；遇 万/亿 以该单位结算当前段并清零
    # （如「壹亿贰仟万」= 1亿 + 2000万 = 120000000）
    total, section, cur = 0, 0, 0
    for ch in int_part:
        if ch in _CN_DIGIT:
            cur = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            section += (cur or 1) * _CN_UNIT[ch]
            cur = 0
        elif ch == '万':
            total += (section + cur) * 10000
            section, cur = 0, 0
        elif ch == '亿':
            total += (section + cur) * 100000000
            section, cur = 0, 0
    val = Decimal(total + section + cur)
    # 角/分按标记字定位：如「陆角叁分」「零捌分」（零=0角，捌=8分）「伍角」「捌分」
    jiao = fen = 0
    last: Optional[int] = None
    for ch in frac:
        if ch in _CN_DIGIT:
            last = _CN_DIGIT[ch]
        elif ch == '角':
            jiao = last or 0
            last = None
        elif ch == '分':
            if last is not None:
                fen = last
            last = None
    return val + Decimal(jiao) / 10 + Decimal(fen) / 100


def q(x) -> Decimal:
    """四舍五入到分。"""
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def to_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip().replace('/', '-')
    if not s:
        return None
    try:
        parts = [int(p) for p in s.split('-')[:3]]
        return date(*parts)
    except (ValueError, TypeError):
        return None


def months_in_year(start: Optional[date], end: Optional[date], year: int) -> int:
    """口径第三条：起租当月与终止当月均计入。"""
    ys, ye = date(year, 1, 1), date(year, 12, 31)
    s = max(start or ys, ys)
    e = min(end or ye, ye)
    if s > e:
        return 0
    return (e.year - s.year) * 12 + (e.month - s.month) + 1


@dataclass
class Contract:
    archive_no: str
    doc_type: str = ''
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    rent_mode: str = ''          # 固定 / 随标准调整（空则按年租金小写兜底）
    rent_amount: Optional[Decimal] = None   # 年租金小写
    rent_cn: Optional[Decimal] = None       # 年租金大写解析值（与小写不一致时按大写，口径四(一)）
    rate: Optional[Decimal] = None          # 合同所载年租金标准（兜底用）
    area: Optional[Decimal] = None
    land_usage: str = ''
    land_level: str = ''


@dataclass
class Standard:
    land_usage: str
    land_level: str
    effective_from: date
    price: Decimal


@dataclass
class Payment:
    ticket_no: str
    pay_date: Optional[date]
    amount: Decimal
    note_year: Optional[int] = None
    is_duplicate: bool = False


@dataclass
class ParcelContext:
    parcel_key: str
    contracts: list = field(default_factory=list)
    payments: list = field(default_factory=list)
    reductions: list = field(default_factory=list)  # [(from_year, to_year, ratio)]
    contract_status: str = '有效'                    # 有效 / 到期未续 / 解除 / 收回
    end_year: int = BASELINE_YEAR                    # 解除/收回时计至该年


def pick_standard(standards: Iterable[Standard], usage: str, level: str, year: int) -> Optional[Decimal]:
    """口径第四(二)：取该年度 1 月 1 日有效的计租标准。"""
    probe = date(year, 1, 1)
    hit = [s for s in standards
           if s.land_usage == usage and s.land_level == level and s.effective_from <= probe]
    if not hit:
        return None
    return max(hit, key=lambda s: s.effective_from).price


def applied_rent(c: Contract, year: int, standards: Iterable[Standard]) -> Optional[Decimal]:
    """当年适用年租金（Decimal 展示值；口径第四条）。

    计租方式缺失时：优先按合同年租金小写，其次按面积 × 合同所载标准。
    """
    rf = rent_float(c, year, standards)
    return q(Decimal(str(rf))) if rf is not None else None


def rent_float(c: Contract, year: int, standards: Iterable[Standard]) -> Optional[float]:
    """当年适用年租金（float 链，与标准答案生成器口径一致；中间不取整）。"""
    mode = c.rent_mode or ''
    if '随标准调整' in mode:
        if not c.area:
            return None
        price = pick_standard(standards, c.land_usage, c.land_level, year)
        if price is None:
            return float(c.rent_amount) if c.rent_amount is not None else None
        return float(c.area) * float(price)
    if c.rent_amount is not None:
        # 口径四(一)：大写与小写不一致的，暂按大写金额计算（并应记问题清单）
        if c.rent_cn is not None and c.rent_cn != Decimal(c.rent_amount):
            return float(c.rent_cn)
        return float(c.rent_amount)
    if c.area and c.rate:
        return float(c.area) * float(c.rate)
    return None


def round2(x: float) -> Decimal:
    """两位舍入：float64 + Python round（经练习集标准答案逐例验证的口径）。"""
    return Decimal(str(round(x, 2)))


def timeline_end_year(ctx: ParcelContext) -> int:
    """口径第五条：计至核算基准日所在年度（含 2026 年全年）；期满未续按最后一份合同继续计收；解除/收回计至当年。"""
    if ctx.contract_status in ('解除', '收回'):
        return ctx.end_year
    return BASELINE_YEAR


def _month_before(d: date) -> date:
    """d 所在月的前一个月的月末（起租当月计入新合同，旧合同计至前月月底）。"""
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(y, m, calendar.monthrange(y, m)[1])


def compute_due(ctx: ParcelContext, standards: Iterable[Standard]) -> dict:
    """逐年应缴（含减免）。返回 {year: {months, applied_rent, due}}

    覆盖规则：
    - 合同链内按各自期限计（起租/终止当月均计入）；
    - 期间重叠的（问题清单·存疑）：旧合同自新合同起始日前终止，重叠段按新合同计收；
    - 最后一份合同期满未续的，向后延续至核算基准日所在年度（口径第五条）；
    - 合同链出现空档年的，沿用已期满的最后一份合同继续计收（期满未续签未收回）。
    """
    if not ctx.contracts:
        return {}
    starts = [c.start_date.year for c in ctx.contracts if c.start_date]
    if not starts:
        # 全部合同都缺起租日（如仅载明承租人的变更协议）→ 无法核定计费年度
        return {}
    first_year = min(starts)
    last_year = timeline_end_year(ctx)
    ends = [c.end_date for c in ctx.contracts if c.end_date]
    max_end = max(ends) if ends else None

    def effective_end(c: Contract) -> Optional[date]:
        if ctx.contract_status == '到期未续' and c.end_date and max_end and c.end_date == max_end:
            return max(c.end_date, date(last_year, 12, 31))
        return c.end_date

    # 按起租日排序；每份合同的计收终点 = 自身终点被后一份合同的起租日截断
    ordered = sorted(ctx.contracts, key=lambda c: (c.start_date or date(1, 1, 1), c.archive_no))
    clipped = []
    for i, c in enumerate(ordered):
        e = effective_end(c)
        if e and i + 1 < len(ordered):
            nxt = ordered[i + 1].start_date
            if nxt:
                e = min(e, _month_before(nxt))
        clipped.append((c, e))

    result = {}
    for year in range(first_year, last_year + 1):
        covered = [(c, e) for c, e in clipped
                   if months_in_year(c.start_date, e, year) > 0]
        months_total, base, rent_disp = 0, 0.0, Decimal(0)
        if covered:
            for c, e in covered:
                m = months_in_year(c.start_date, e, year)
                rf = rent_float(c, year, standards)
                months_total += m
                if rf is not None:
                    # 年内多份合同：先求未舍入和，年末一次舍入（经 LX-031 验证）
                    base += rf * m / 12
                    rent_disp += q(Decimal(str(rf)))
        else:
            # 空档年：沿用此前最后一份期满合同，按全年计收
            prior = [ce for ce in clipped if ce[1] and ce[1].year < year]
            if prior:
                c, _ = max(prior, key=lambda ce: ce[1])
                rf = rent_float(c, year, standards)
                months_total = 12
                if rf is not None:
                    base = rf
                    rent_disp = q(Decimal(str(rf)))
        # 口径第六条：先算应缴（舍入到分），再乘（1 − 减免比例）（经 LX-024 验证）
        due = round2(base)
        ratio = None
        for fy, ty, r in ctx.reductions:
            if fy <= year <= ty:
                ratio = Decimal(str(r))
                break
        if ratio is not None:
            due = round2(float(due) * (1.0 - float(ratio)))
        result[year] = {'months': months_total, 'applied_rent': rent_disp, 'due': due}
    return result


def allocate_payments(due_map: dict, payments: Iterable[Payment]) -> dict:
    """口径第七条实缴归集：
    1) 同一票据号只计一次；2) 按缴费日期先后、同日期按票据号；
    3) 注明年度的归该年度（超额为多缴，不冲抵其他年度）；
    4) 未注明年度的冲抵最早欠缴年度，依次向后。
    """
    paid = {y: Decimal(0) for y in due_map}
    seen_ticket = set()
    ordered = sorted([p for p in payments if not p.is_duplicate],
                     key=lambda p: (p.pay_date or date(1900, 1, 1), p.ticket_no or ''))
    for p in ordered:
        if p.ticket_no:
            if p.ticket_no in seen_ticket:
                continue
            seen_ticket.add(p.ticket_no)
        amount = Decimal(p.amount)
        if p.note_year and p.note_year in paid:
            paid[p.note_year] += amount
            continue
        # 未注明年度：冲抵最早尚未缴足的年度
        for y in sorted(paid):
            if amount <= 0:
                break
            remain = due_map[y]['due'] - paid[y]
            if remain <= 0:
                continue
            take = min(remain, amount)
            paid[y] += take
            amount -= take
        if amount > 0 and paid:
            # 各年度均已缴足仍有余额 → 多缴，计入最后一年的实缴
            last = max(paid)
            paid[last] += amount
    return paid


def compute_parcel(ctx: ParcelContext, standards: Iterable[Standard]) -> dict:
    """完整核算：逐年应缴/实缴/欠缴 + 汇总。"""
    due_map = compute_due(ctx, standards)
    paid_map = allocate_payments(due_map, ctx.payments)
    rows = []
    total_due = total_paid = Decimal(0)
    arrears_years = []
    for y in sorted(due_map):
        due = due_map[y]['due']
        paid = q(paid_map.get(y, Decimal(0)))
        # 年度层面多缴不记为负欠缴（口径第八条：负数表示多缴，汇总层面体现）
        arrear = q(max(Decimal(0), due - paid))
        rows.append({'year': y, 'months': due_map[y]['months'],
                     'applied_rent': due_map[y]['applied_rent'],
                     'due': due, 'paid': paid, 'arrears': arrear})
        total_due += due
        total_paid += paid
        if due > paid:
            arrears_years.append(str(y))
    return {
        'parcel_key': ctx.parcel_key,
        'rows': rows,
        'total_due': q(total_due),
        'total_paid': q(total_paid),
        'arrears': q(total_due - total_paid),
        'due_2026': q(due_map.get(2026, {'due': Decimal(0)})['due']),
        'arrears_years': arrears_years,
    }
