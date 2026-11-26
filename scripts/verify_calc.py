import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from landlease.app.services import dataset  # noqa: E402
from landlease.app.services.calc import (Contract, ParcelContext, Payment, cn_amount, compute_parcel, to_date)  # noqa: E402

# 面积口径：contract=按合同面积（口径四(三)原文），registry=按登记面积（数据校验用）
AREA_RULE = os.getenv('AREA_RULE', 'auto')


def area_of(c: dict, led: dict):
    v = Decimal(c['土地面积']) if c.get('土地面积') else None
    ra = Decimal(led['登记面积']) if led.get('登记面积') else None
    if AREA_RULE == 'registry' and ra is not None:
        return ra
    if AREA_RULE == 'min' and v is not None and ra is not None:
        return min(v, ra)      # 面积不一致属存疑：按对产权人有利（较少应缴）暂算
    if AREA_RULE == 'auto' and v is not None and ra is not None and led.get('_ambiguous'):
        return min(v, ra)      # 仅对被判为存疑的宗地按最少算法暂算
    return v


def build_contexts(data: dict, standards: list, alloc_map: dict) -> dict:
    """按宗地台账分组，构造核算上下文（合同要素与缴费均取标准答案，隔离识别环节）。"""
    contracts = {r['档案号']: r for r in data['contracts']}
    pay_rows = {}
    for r in data['payments']:
        pay_rows.setdefault(str(r['序号']), r)

    street_map = dataset.parse_street_level(data['street_level'])
    # 减免登记 -> 宗地键（按不动产单元号 / 坐落 / 承租人 匹配）
    red_map = {}
    for r in data['reductions']:
        ratio = str(r.get('减免比例') or '0').replace('%', '')
        try:
            ratio = Decimal(ratio) / Decimal(100) if Decimal(ratio) > 1 else Decimal(ratio)
        except Exception:
            ratio = Decimal(0)
        item = (int(r['减免起始年度']), int(r['减免终止年度']), ratio)
        unit = str(r.get('不动产单元号') or '')
        loc = str(r.get('坐落') or '')
        who = str(r.get('承租人') or '')
        for led in data['ledger']:
            hit = (unit and unit == led.get('不动产单元号')) or \
                  (loc and loc in str(led.get('登记坐落') or '')) or \
                  (who and who == led.get('合同承租人'))
            if hit:
                red_map.setdefault(led['宗地键'], []).append(item)

    # 标准答案中判为「存疑待确认」的宗地：按口径十二取最少算法
    ambiguous = {r['档案号'] for r in data['issues'] if r['问题类型'] == '存疑待确认'}

    ctxs = {}
    for led in data['ledger']:
        key = led['宗地键']
        led['_ambiguous'] = key in ambiguous or any(a in ambiguous for a in led['档案号列表'].split(';'))
        archives = [a for a in led['档案号列表'].split(';') if a]
        cons = []
        for a in archives:
            c = contracts.get(a)
            if not c:
                continue
            level = c.get('土地级别') or ''
            if not level:  # 口径第二条：按登记坐落/合同坐落街路定级
                level = dataset.infer_level(led.get('登记坐落') or c.get('坐落') or '', street_map)
            cons.append(Contract(
                archive_no=a,
                doc_type=c.get('合同类型', ''),
                start_date=to_date(c.get('租赁起始日')),
                end_date=to_date(c.get('租赁终止日')),
                rent_mode=c.get('计租方式', ''),
                rent_amount=Decimal(c['年租金小写']) if c.get('年租金小写') else None,
                rent_cn=cn_amount(c.get('年租金大写')),
                rate=Decimal(c['年租金标准']) if c.get('年租金标准') else None,
                area=area_of(c, led),
                land_usage=(c.get('用途') or '').replace('用地', ''),
                land_level=level,
            ))
        payments = []
        for pid in alloc_map.get(key, []):
            row = pay_rows.get(pid)
            if not row:
                continue
            payments.append(Payment(
                ticket_no=str(row.get('票据号') or ''),
                pay_date=to_date(row.get('缴费日期')),
                amount=Decimal(str(row.get('金额（元）') or 0)),
                note_year=int(row['所属年度']) if row.get('所属年度') else None,
            ))
        ctxs[key] = ParcelContext(
            parcel_key=key, contracts=cons, payments=payments,
            reductions=red_map.get(key, []), contract_status=led.get('合同状态', '有效'),
        )
    return ctxs


def main():
    data = dataset.load_practice()
    standards = dataset.parse_standards(data['standards'])
    # 缴费归集标准答案：宗地键 -> 缴费记录序号
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
            elif len(diffs) < 12:
                diffs.append((key, y, str(row['due']), e['应缴'], str(row['paid']), e['实缴']))
        led = expect_led[key]
        p_ok = (abs(res['arrears'] - Decimal(led['欠缴金额'])) <= Decimal('0.01')
                and abs(res['total_due'] - Decimal(led['累计应缴'])) <= Decimal('0.01'))
        ok_parcels += 1 if p_ok else 0

    print(f'宗地数 {len(ctxs)}  汇总级（欠缴+累计应缴）全对 {ok_parcels}/{len(ctxs)}')
    print(f'年度级（应缴+实缴+欠缴）全对 {ok_years}/{tot_years}  ({ok_years/max(tot_years,1):.1%})')
    if diffs:
        print('--- 差异样例（宗地, 年度, 算得应缴, 标准应缴, 算得实缴, 标准实缴）')
        for d in diffs:
            print('  ', d)


if __name__ == '__main__':
    main()
