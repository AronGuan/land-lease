"""识别编排单元测试：三级判定 / 反推规则库 / 强制降级（不调 VLM）。"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from landlease.app.services.calc import Standard  # noqa: E402
from landlease.app.services.recognize import (  # noqa: E402
    FieldResult, judge, merge_pages, validate_field, valid_id_no, valid_phone,
)

STD = [Standard('住宅', '一级', date(1998, 1, 1), Decimal('2.10'))]


def _merged(**kw):
    """合成抽取结果：默认高置信，按需覆盖。"""
    base = {}
    for name, v in kw.items():
        val, conf = v if isinstance(v, tuple) else (v, 0.97)
        base[name] = {'value': val, 'confidence': conf, 'evidence': '', 'page': 1}
    return base


def test_validators():
    assert valid_id_no('990524194402011489')   # 样本真值（校验位合法）
    assert not valid_id_no('990524194402011480')
    assert valid_id_no('99C5XQX9LHYTHFU8FW')   # 单位信用代码（格式）
    assert not valid_id_no('12345')
    assert valid_phone('10098972321')
    assert not valid_phone('1234567')
    assert '证件号码格式异常' in validate_field('证件号码', '990524194402011480')
    assert '联系电话格式异常' in validate_field('联系电话', '12345')
    assert validate_field('土地面积', '2133.51') == []
    assert '日期格式异常' in validate_field('签订日期', '2015年12月')


def test_l1_auto_pass():
    m = _merged(承租人='尹伟立', 土地面积='207.18', 证件号码='990524194402011489',
                联系电话='10098972321', 租赁起始日='2017-04-01',
                租赁终止日='2027-03-31', 年租金小写='435.08')
    doc = judge('LX-001', m, STD)
    assert doc.fields['承租人'].level == 'L1'
    assert doc.process_type == '自动通过'


def test_l2_cn_inference():
    """年租金小写缺失 → 大写互推。"""
    m = _merged(年租金大写='伍拾柒元陆角叁分', 土地面积='27.2', 租赁起始日='2014-03-01',
                租赁终止日='2029-02-28', 承租人='张三', 证件号码='990524194402011489',
                联系电话='10098972321')
    doc = judge('LX-002', m, STD)
    f = doc.fields['年租金小写']
    assert f.level == 'L2' and f.source == 'inferred'
    assert f.final_value == '57.63'
    assert any('大写互推' in r for r in f.rules)


def test_l2_date_inference():
    """终止日缺失 → 起始日 + 年限 − 1 天。"""
    m = _merged(租赁起始日='2016-01-01', 租赁年限='10', 承租人='李四',
                证件号码='990524194402011489', 联系电话='10098972321')
    doc = judge('LX-003', m, STD)
    f = doc.fields['租赁终止日']
    assert f.level == 'L2' and f.final_value == '2025-12-31'
    m2 = _merged(租赁起始日='2016-03-01', 租赁年限='20', 承租人='李四',
                 证件号码='990524194402011489', 联系电话='10098972321')
    assert judge('LX-003b', m2, STD).fields['租赁终止日'].final_value == '2036-02-29'


def test_l2_amount_inference():
    """年租金缺失 → 面积 × 标准互推。"""
    m = _merged(土地面积='100.00', 用途='住宅', 土地级别='一级',
                租赁起始日='2015-06-01', 租赁终止日='2025-05-31', 承租人='王五',
                证件号码='990524194402011489', 联系电话='10098972321')
    doc = judge('LX-004', m, STD)
    f = doc.fields['年租金小写']
    assert f.level == 'L2' and f.final_value == '210.00'
    assert any('金额互推' in r for r in f.rules)


def test_l3_blank():
    """推不出且缺失 → 留空记问题。"""
    m = _merged(承租人='赵六', 证件号码='990524194402011489', 联系电话='10098972321')
    doc = judge('LX-005', m, STD)
    f = doc.fields['年租金小写']
    assert f.level == 'L3' and f.final_value is None
    assert '不可识别' in f.issues
    assert doc.process_type == '人工复核'  # 关键字段 L3 强制复核


def test_forced_downgrade_altered():
    """涂改 → 整份人工复核 + 目标字段 L2（LX-001 实测教训）。"""
    m = _merged(承租人='钱七', 土地面积='2133.51', 年租金小写='4018.25',
                证件号码='990524194402011489', 联系电话='10098972321',
                涂改字段=('年租金小写', 0.95), 涂改前内容='3998.25')
    doc = judge('LX-006', m, STD)
    assert doc.process_type == '人工复核'
    assert any('涂改' in r for r in doc.forced_reasons)
    assert doc.fields['年租金小写'].level == 'L2'
    assert '关键字段有涂改' in doc.fields['年租金小写'].issues


def test_cn_small_mismatch():
    """大小写不一致 → 暂按大写 + 记问题（口径四(一)）。"""
    m = _merged(年租金小写='75.63', 年租金大写='伍拾柒元陆角叁分',
                土地面积='27.2', 承租人='孙八',
                证件号码='990524194402011489', 联系电话='10098972321',
                租赁起始日='2014-03-01', 租赁终止日='2029-02-28')
    doc = judge('LX-007', m, STD)
    f = doc.fields['年租金小写']
    assert f.final_value == '57.63' and f.level == 'L2'
    assert '大小写金额不一致' in f.issues


def test_merge_pages():
    p1 = {'承租人': {'value': '张三', 'confidence': 0.98, 'evidence': ''},
          '土地面积': {'value': None, 'confidence': 0.5, 'evidence': ''}}
    p2 = {'承租人': {'value': '张三', 'confidence': 0.9, 'evidence': ''},
          '土地面积': {'value': '88.8', 'confidence': 0.95, 'evidence': '第2页'}}
    m = merge_pages([p1, p2])
    assert m['承租人']['page'] == 1 and m['承租人']['confidence'] == 0.98
    assert m['土地面积']['value'] == '88.8' and m['土地面积']['page'] == 2


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
