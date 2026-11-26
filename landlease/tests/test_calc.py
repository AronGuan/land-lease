"""核算引擎单元测试：锁定经练习集标准答案验证的规则行为。

运行：python -m pytest landlease/tests/test_calc.py -q
（无 pytest 时）python landlease/tests/test_calc.py
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from landlease.app.services.calc import (  # noqa: E402
    Contract, ParcelContext, Payment, Standard, _month_before, allocate_payments,
    cn_amount, compute_due, compute_parcel, months_in_year, round2,
)

STD = [
    Standard('住宅', '三级', date(1998, 1, 1), Decimal('0.60')),
    Standard('住宅', '三级', date(2016, 1, 1), Decimal('1.10')),
    Standard('仓储', '三级', date(2009, 1, 1), Decimal('0.65')),
]


def test_cn_amount():
    cases = {
        '伍拾柒元陆角叁分': '57.63',
        '陆佰捌拾玖元零捌分': '689.08',      # 含「零」分位（LX-036）
        '肆佰叁拾伍元零捌分': '435.08',
        '壹仟叁佰捌拾陆元柒角捌分': '1386.78',
        '伍元叁分': '5.03',
        '叁佰元整': '300.00',
        '壹万贰仟元伍角': '12000.50',
        '壹亿贰仟万元整': '120000000.00',
    }
    for s, exp in cases.items():
        assert abs(cn_amount(s) - Decimal(exp)) < Decimal('0.001'), s


def test_months_in_year():
    # 口径第三条：起租当月与终止当月均计入
    assert months_in_year(date(2016, 1, 1), date(2025, 12, 31), 2016) == 12
    assert months_in_year(date(2010, 4, 1), date(2020, 3, 31), 2010) == 9
    assert months_in_year(date(2017, 4, 1), date(2027, 3, 31), 2017) == 9
    assert months_in_year(date(2015, 6, 1), date(2020, 5, 31), 2015) == 7
    assert months_in_year(date(2016, 3, 1), date(2036, 2, 29), 2036) == 2
    assert months_in_year(date(2001, 1, 1), date(2001, 12, 31), 2002) == 0


def test_month_before():
    assert _month_before(date(2016, 1, 1)) == date(2015, 12, 31)
    assert _month_before(date(2020, 4, 1)) == date(2020, 3, 31)
    assert _month_before(date(2016, 3, 10)) == date(2016, 2, 29)  # 闰年


def test_overlap_supersede():
    """LX-014：期间重叠时旧合同自新合同起始日前终止（问题清单存疑口径）。"""
    old = Contract('A', start_date=date(2010, 4, 1), end_date=date(2020, 3, 31),
                   rent_mode='随标准调整', area=Decimal('2133.51'),
                   land_usage='仓储', land_level='三级')
    new = Contract('B', start_date=date(2016, 1, 1), end_date=date(2025, 12, 31),
                   rent_mode='固定', rent_amount=Decimal('1386.78'),
                   rent_cn=Decimal('1386.78'))
    ctx = ParcelContext('P', [new, old], contract_status='到期未续')
    due = compute_due(ctx, STD)
    assert due[2010]['due'] == Decimal('1040.09')   # 旧合同 9 个月（随标准 0.65）
    assert due[2015]['due'] == Decimal('1386.78')   # 旧合同被截断前最后一年
    assert due[2016]['due'] == Decimal('1386.78')   # 重叠年只按新合同
    assert due[2026]['due'] == Decimal('1386.78')   # 到期未续延续至 2026 全年


def test_abutting_not_clipped():
    """首尾相接（非重叠）不截断：两段同年均计（LX-031/LX-017 型）。"""
    a = Contract('A', start_date=date(2010, 6, 1), end_date=date(2010, 5, 31) if False else date(2015, 5, 31),
                 rent_mode='固定', rent_amount=Decimal('189.78'))
    b = Contract('B', start_date=date(2015, 6, 1), end_date=date(2020, 5, 31),
                 rent_mode='固定', rent_amount=Decimal('189.78'))
    ctx = ParcelContext('P', [a, b])
    due = compute_due(ctx, STD)
    # 2015 = A 的 1-5 月 + B 的 6-12 月 = 189.78×5/12 + 189.78×7/12 = 189.78
    assert due[2015]['due'] == Decimal('189.78')
    assert due[2015]['months'] == 12


def test_gap_year_fallback():
    """空档年沿用已期满合同按全年计收（口径第五条）。"""
    c = Contract('A', start_date=date(2005, 7, 1), end_date=date(2015, 6, 30),
                 rent_mode='随标准调整', area=Decimal('282.45'),
                 land_usage='住宅', land_level='三级')
    ctx = ParcelContext('P', [c], contract_status='到期未续')
    due = compute_due(ctx, STD)
    assert due[2016]['due'] == Decimal('310.69')    # 282.45×1.10，float 链舍入（LX-006）
    assert due[2016]['months'] == 12
    assert due[2005]['due'] == Decimal('84.73')     # 282.45×0.60×6/12（LX-006）


def test_reduction_two_stage_rounding():
    """口径第六条：应缴先舍入到分，再乘（1−比例）后舍入（LX-024）。"""
    c = Contract('A', start_date=date(2016, 3, 1), end_date=date(2036, 2, 29),
                 rent_mode='随标准调整', area=Decimal('222.43'),
                 land_usage='住宅', land_level='三级')
    ctx = ParcelContext('P', [c], reductions=[(2017, 2018, Decimal('0.5'))])
    due = compute_due(ctx, STD)
    assert due[2016]['due'] == Decimal('203.89')    # 10 个月
    assert due[2017]['due'] == Decimal('122.33')    # 244.67 × 0.5 两段式舍入
    assert due[2019]['due'] == Decimal('244.67')


def test_cn_preferred_over_amount():
    """口径四(一)：大小写不一致按大写。"""
    c = Contract('A', start_date=date(2014, 3, 1), end_date=date(2029, 2, 28),
                 rent_mode='固定', rent_amount=Decimal('75.63'), rent_cn=Decimal('57.63'))
    ctx = ParcelContext('P', [c])
    due = compute_due(ctx, STD)
    assert due[2014]['due'] == Decimal('57.63') and False or due[2014]['due'] == round2(57.63 * 10 / 12)


def test_allocate_payments():
    """口径第七条：票据去重、注明年度归该年、未注明冲最早欠缴年。"""
    due_map = {2015: {'due': Decimal('100.00')}, 2016: {'due': Decimal('100.00')}}
    pays = [
        Payment('T1', date(2015, 6, 1), Decimal('60.00')),
        Payment('T1', date(2015, 6, 1), Decimal('60.00')),            # 重复票据
        Payment('T2', date(2016, 3, 1), Decimal('50.00'), note_year=2016),
        Payment('T3', date(2016, 3, 1), Decimal('70.00')),            # 未注明：冲 2015
    ]
    paid = allocate_payments(due_map, pays)
    # T1 去重计 60 冲 2015；T2 注明 2016 归 2016；T3 未注明 70：补足 2015 剩余 40，余 30 冲 2016
    assert paid[2015] == Decimal('100.00')
    assert paid[2016] == Decimal('80.00')


def test_overpay_not_negative():
    """年度多缴不记负欠缴（LX-026 型）。"""
    c = Contract('A', start_date=date(2020, 1, 1), end_date=date(2026, 12, 31),
                 rent_mode='固定', rent_amount=Decimal('100.00'))
    ctx = ParcelContext('P', [c], payments=[Payment('T1', date(2021, 1, 1), Decimal('900.00'))])
    res = compute_parcel(ctx, STD)
    assert all(r['arrears'] >= 0 for r in res['rows'])
    assert res['arrears'] < 0  # 汇总层面体现多缴（负数）


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for fn in fns:
        try:
            fn()
            print('OK  ', fn.__name__)
        except AssertionError as e:
            failed += 1
            print('FAIL', fn.__name__, e)
    print(f'{len(fns) - failed}/{len(fns)} passed')
    sys.exit(1 if failed else 0)
