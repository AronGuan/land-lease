"""归宗比对单元测试：旧地号↔单元号映射、归宗打分、问题清单生成。"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from landlease.app.services.grouping import (  # noqa: E402
    GROUP_THRESHOLD, compare_with_registry, group_documents, parcel_matches_unit,
    parcel_no_segments, score_grouping, unit_no_segments, ISSUE_TYPES,
)

# ---------- 旧地号 ↔ 单元号 ----------

def test_unit_no_segments():
    # 单元号 000000009005GB00106F00089385 → (9, 5, 106) 前导零可省
    seg = unit_no_segments('000000009005GB00106F00089385')
    assert seg == ('9', '5', '106')
    assert parcel_no_segments('09-05-0106') == ('9', '5', '106')
    assert parcel_matches_unit('09-05-0106', '000000009005GB00106F00089385')
    assert not parcel_matches_unit('09-05-0107', '000000009005GB00106F00089385')


# ---------- 归宗打分（PRD 6.3 实测样例 LX-027/028/048） ----------

def test_chain_grouping_lx027_chain():
    """LX-028(最早) → LX-048 → LX-027 三份同宗：原合同指针链 + 宗地号 + 证件号。"""
    docs = [
        {'档案号': 'LX-028', '合同编号': '××国土租字（2000）第004号', '原合同编号': '',
         '宗地号': '09-05-0106', '不动产单元号': '000000009005GB00106F00089385',
         '证件号码': '990521194505145261', '土地面积': '313.79',
         '坐落': '××镇解放街181号', '租赁起始日': '2000-06-01', '租赁终止日': '2010-05-31'},
        {'档案号': 'LX-048', '合同编号': '××国土资租〔2010〕004号',
         '原合同编号': '××国土租字（2000）第004号',
         '宗地号': '09-05-0106', '不动产单元号': '',
         '证件号码': '990521194505145261', '土地面积': '313.79',
         '坐落': '××镇解放街181号', '租赁起始日': '2010-06-01', '租赁终止日': '2020-05-31'},
        {'档案号': 'LX-027', '合同编号': '××自然资租〔2020〕002号',
         '原合同编号': '××国土资租〔2010〕004号',
         '宗地号': '000000009005GB00106F00089385', '不动产单元号': '',
         '证件号码': '990521194505145261', '土地面积': '313.79',
         '坐落': '××镇解放街181号', '租赁起始日': '2020-06-01', '租赁终止日': '2025-05-31'},
    ]
    groups, issues = group_documents(docs)
    # 三份归同一宗地
    assert len(groups) == 1
    assert sorted(groups[list(groups)[0]]) == ['LX-027', 'LX-028', 'LX-048']
    assert not issues  # 无新开宗地问题


def test_score_grouping():
    a = {'合同编号': 'A', '宗地号': '09-05-0106', '不动产单元号': '',
         '证件号码': 'ID1', '土地面积': '100', '坐落': '××镇解放街181号',
         '租赁终止日': '2010-05-31'}
    # B 原合同命中 + 宗地号 + 证件号 + 面积 + 坐落 + 接续 = 60+30+15+10+10+10 = 135
    b = {'原合同编号': 'A', '宗地号': '09-05-0106', '证件号码': 'ID1',
         '土地面积': '100.00', '坐落': '××县解放街一八一号',
         '租赁起始日': '2010-06-01'}
    g = score_grouping(a, b)
    assert g.score == 135, f'expected 135, got {g.score}, rules={g.rules}'
    # 第二组：a 宗地号空、给单元号；b 宗地号仍为旧地号 → 走交叉比对
    a2 = {'合同编号': 'A', '宗地号': '', '不动产单元号': '000000009005GB00106F00089385',
          '证件号码': 'ID1', '土地面积': '100', '坐落': '××镇解放街181号',
          '租赁终止日': '2010-05-31'}
    g2 = score_grouping(a2, b)
    assert ('宗地号（↔单元号）位段换算一致', 30) in g2.rules, g2.rules


# ---------- 问题清单生成 ----------

def test_compare_typical_issues():
    doc = {'档案号': 'LX-999', '坐落': '××镇繁荣路187号', '宗地号': '09-04-134',
           '土地面积': '222.43', '承租人': '董林', '证件号码': '990523195001216414',
           '联系电话': '10098481514', '租赁终止日': '2036-02-29', '年租金小写': '244.67',
           '年租金大写': '贰佰肆拾肆元陆角柒分', '有无宗地图': '是'}
    led = {'登记坐落': '××镇繁荣路187号', '登记面积': '222.43',
           '登记权利人': '董林', '催缴对象': '董林',
           '不动产单元号': '000000009004GB00134F00092537', '合同状态': '有效'}
    pays = [{'缴款人': '董林'}]
    issues = compare_with_registry(doc, led, pays)
    # 数据合法 + 与登记一致 → 无问题清单条目
    assert issues == []


def test_compare_triggers_issues():
    doc = {'档案号': 'LX-998', '坐落': '××镇建设大街199号', '宗地号': '07-04-0118',
           '土地面积': '207.18', '承租人': '尹伟立', '证件号码': '990524194402011489',
           '联系电话': '10098972321', '租赁终止日': '2027-03-31', '年租金小写': '435.08',
           '年租金大写': '肆佰叁拾伍元零捌分', '有无宗地图': '否',
           '涂改字段': '土地面积', '涂改处有无签章': '否'}
    led = {'登记坐落': '××镇建设大街199号', '登记面积': '187.18',
           '登记权利人': '尹伟立', '催缴对象': '尹伟立',
           '不动产单元号': '000000007004GB00118F00070291', '合同状态': '有效'}
    issues = compare_with_registry(doc, led, [])
    types = {i['问题类型'] for i in issues}
    # 触发：缺宗地图、关键字段有涂改（无签章）、面积与登记不一致
    assert '缺宗地图' in types
    assert '关键字段有涂改' in types
    assert '面积与登记不一致' in types


def test_issue_types_count():
    assert len(ISSUE_TYPES) == 13
    assert '存疑待确认' in ISSUE_TYPES


def test_low_score_new_parcel():
    """< 40 分新开宗地并记问题。"""
    docs = [
        {'档案号': 'X1', '合同编号': 'X1', '原合同编号': '',
         '宗地号': '01-02-003', '不动产单元号': '',
         '证件号码': 'ID1', '土地面积': '50',
         '坐落': '甲街1号', '租赁起始日': '2020-01-01', '租赁终止日': '2025-12-31'},
        {'档案号': 'X2', '合同编号': 'X2', '原合同编号': '',
         '宗地号': '99-88-077', '不动产单元号': '000000009888GB00777F00077777',
         '证件号码': 'ID2', '土地面积': '300',
         '坐落': '乙街9号', '租赁起始日': '2020-06-01', '租赁终止日': '2025-05-31'},
    ]
    groups, issues = group_documents(docs)
    assert len(groups) == 2
    assert any(i['问题类型'] == '登记数据中无对应宗地' for i in issues)


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