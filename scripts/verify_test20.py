"""test_20 盲测：标准答案取测试集，原始表（缴费/减免/计租标准/街路级别）取练习集全量表。

用法：python scripts/verify_test20.py
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from landlease.app.services import dataset  # noqa: E402
from landlease.app.services.calc import compute_parcel  # noqa: E402
from verify_calc import build_contexts  # noqa: E402

TEST_ANS = Path(__file__).resolve().parents[1] / '数据切分' / 'test_20' / 'standard_answers'


def main():
    data = dataset.load_practice()
    # 替换答案表为测试集
    for name in ('ledger', 'contracts', 'due', 'alloc', 'issues'):
        data[name] = dataset._rows_csv(TEST_ANS / f'{ {"ledger": "宗地台账", "contracts": "合同要素", "due": "应缴明细", "alloc": "缴费归集", "issues": "问题清单"}[name] }.csv')

    standards = dataset.parse_standards(data['standards'])
    alloc_map = {}
    for r in data['alloc']:
        alloc_map.setdefault(r['宗地键'], []).append(r['序号'])

    ctxs = build_contexts(data, standards, alloc_map)
    expect_due = {}
    for r in data['due']:
        expect_due.setdefault(r['宗地键'], {})[int(r['年度'])] = r
    expect_led = {r['宗地键']: r for r in data['ledger']}

    ok_years = tot_years = 0
    ok_parcels = 0
    diffs = []
    for key, ctx in ctxs.items():
        res = compute_parcel(ctx, standards)
        exp = expect_due.get(key, {})
        for row in res['rows']:
            y = row['year']
            e = exp.get(y)
            if not e:
                continue
            tot_years += 1
            good = (abs(row['due'] - Decimal(e['应缴'])) <= Decimal('0.01')
                    and abs(row['paid'] - Decimal(e['实缴'])) <= Decimal('0.01')
                    and abs(row['arrears'] - Decimal(e['欠缴'])) <= Decimal('0.01'))
            if good:
                ok_years += 1
            else:
                diffs.append((key, y, str(row['due']), e['应缴'], str(row['paid']), e['实缴']))
        led = expect_led[key]
        p_ok = (abs(res['arrears'] - Decimal(led['欠缴金额'])) <= Decimal('0.01')
                and abs(res['total_due'] - Decimal(led['累计应缴'])) <= Decimal('0.01'))
        if not p_ok:
            diffs.append((key, 'SUM', str(res['total_due']), led['累计应缴'],
                          str(res['arrears']), led['欠缴金额']))
        ok_parcels += 1 if p_ok else 0

    print(f'[test_20 盲测] 宗地数 {len(ctxs)}  汇总级全对 {ok_parcels}/{len(ctxs)}')
    print(f'[test_20 盲测] 年度级全对 {ok_years}/{tot_years}  ({ok_years/max(tot_years,1):.1%})')
    for d in diffs:
        print('  DIFF:', d)


if __name__ == '__main__':
    main()
