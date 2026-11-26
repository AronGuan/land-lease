"""归宗比对 + 问题清单：旧地号↔单元号映射 → 多合同归宗打分 → 与登记/缴费比对生成 13 类问题。

PRD 6.3 / 6.4。纯函数模块；落库由 API 层负责。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from .calc import cn_amount, to_date

# 13 类问题清单（PRD 6.4，严格使用不得自创）
ISSUE_TYPES = [
    # 文件层
    '关键字段有涂改', '合同缺页', '缺宗地图', '年租金大小写不一致',
    '证件号码异常', '联系电话缺失或无效', '坐落或宗地号与登记不一致',
    '面积与登记不一致',
    # 宗地层
    '合同到期未续', '承租人已变更未办合同变更', '登记数据中无对应宗地',
    '缴费记录异常',
    # 通用
    '存疑待确认',
]


# ---------- 旧地号 ↔ 单元号映射（口径第十条） ----------

_UNIT_RE = re.compile(r'^(\d{6})(\d{3})(\d{3})([A-Z]{2})(\d{5})([A-Z])(\d{5,8})$')
def unit_no_segments(unit_no: str) -> Optional[tuple]:
    """拆分不动产单元号 → (地籍区/子区/宗地号)，前导零可省略。

    单元号 28 位：行政区划 6 + 地籍区 3 + 子区 3 + GB 2 + 宗地号 5 + F 1 + 附记号 5-8
    口径第十条：归宗取 7-9 / 10-12 / 15-19 位。
    """
    m = _UNIT_RE.match(unit_no or '')
    if not m:
        return None
    area, sub = m.group(2).lstrip('0') or '0', m.group(3).lstrip('0') or '0'
    parcel = m.group(5).lstrip('0') or '0'
    return area, sub, parcel


_PARCEL_OLD_RE = re.compile(r'^(\d+)[-./](\d+)[-./](\d+)$')
def parcel_no_segments(parcel_no: str) -> Optional[tuple]:
    """旧地号 09-05-0106 → (9, 5, 106) 前导零可省略。

    兼容三种写法：旧地号 09-05-0106 / 点号分隔 09-13.0116 / 直接写完整不动产单元号。
    """
    s = (parcel_no or '').strip()
    if not s:
        return None
    # 合同里直接写完整单元号（28 位）的情况
    if _UNIT_RE.match(s):
        return unit_no_segments(s)
    m = _PARCEL_OLD_RE.match(s)
    if not m:
        return None
    return m.group(1).lstrip('0') or '0', m.group(2).lstrip('0') or '0', m.group(3).lstrip('0') or '0'


def parcel_matches_unit(parcel_no: str, unit_no: str) -> bool:
    a, b = parcel_no_segments(parcel_no), unit_no_segments(unit_no)
    return a is not None and b is not None and a == b


# ---------- 归宗打分 ----------

@dataclass
class GroupCandidate:
    """一份合同相比对到已有宗地组的打分。"""
    parcel_key: str
    score: int = 0
    rules: list = field(default_factory=list)        # [(证据, 分)]

    def add(self, rule: str, score: int):
        self.score += score
        self.rules.append((rule, score))


def score_grouping(doc_a: dict, doc_b: dict) -> GroupCandidate:
    """两份合同归宗打分（doc_a 已属某宗地，doc_b 待归入）。

    PRD 6.3：原合同指针+60 / 宗地号+30 / 证件号+15 / 面积+10 / 坐落+10 / 日期接续+10。
    """
    g = GroupCandidate(parcel_key=doc_a.get('parcel_key', ''))
    # A 原合同编号指针
    if doc_a.get('合同编号') and doc_a.get('合同编号') == doc_b.get('原合同编号'):
        g.add('原合同编号指针命中', 60)
    # B 宗地号位段换算一致（含与单元号交叉比对）
    pa, pb = doc_a.get('宗地号'), doc_b.get('宗地号')
    ua, ub = doc_a.get('不动产单元号'), doc_b.get('不动产单元号')
    pair_match = (
        (pa and pb and parcel_no_segments(pa) == parcel_no_segments(pb))
        or (pa and ub and parcel_matches_unit(pa, ub))
        or (pb and ua and parcel_matches_unit(pb, ua))
    )
    if pair_match:
        g.add('宗地号（↔单元号）位段换算一致', 30)
    # C 承租人证件号
    if doc_a.get('证件号码') and doc_a.get('证件号码') == doc_b.get('证件号码'):
        g.add('承租人证件号一致', 15)
    # D 面积一致（容差 ±0.01）
    a_area, b_area = _dec(doc_a.get('土地面积')), _dec(doc_b.get('土地面积'))
    if a_area is not None and b_area is not None and abs(a_area - b_area) < Decimal('0.01'):
        g.add('面积一致', 10)
    # E 坐落归一化一致（去「县/镇」前缀、统一数字）
    if _norm_loc(doc_a.get('坐落')) and _norm_loc(doc_a.get('坐落')) == _norm_loc(doc_b.get('坐落')):
        g.add('坐落归一化一致', 10)
    # F 起租日 = 前份终止日 +1 天
    a_end = to_date(doc_a.get('租赁终止日'))
    b_start = to_date(doc_b.get('租赁起始日'))
    if a_end and b_start and b_start == a_end + timedelta(days=1):
        g.add('起租日接续前份合同', 10)
    return g


GROUP_THRESHOLD = 40


def group_documents(docs: Iterable[dict]) -> tuple[dict, list]:
    """对一批合同执行归宗：返回 {parcel_key: [档案号...]} 与问题清单新增条目。

    docs: 每份 {档案号, 合同编号, 原合同编号, 宗地号, 不动产单元号, 证件号码,
                 土地面积, 坐落, 租赁起始日, 租赁终止日}
    第一份合同开新宗地；后续每份先尝试匹配已有宗地组，≥40 分归入，<40 分开新宗地。
    """
    groups: dict = {}
    issues: list = []
    docs = list(docs)
    if not docs:
        return groups, issues
    # 按起租日排序，最早的先开宗
    docs.sort(key=lambda d: to_date(d.get('租赁起始日')) or date(1, 1, 1))
    groups['LX-001'] = [docs[0]['档案号']]
    docs[0]['parcel_key'] = 'LX-001'
    for d in docs[1:]:
        best = None
        for pk, members in groups.items():
            for arc in members:
                a = next((x for x in docs if x['档案号'] == arc), None)
                if a is None:
                    continue
                a = {**a, 'parcel_key': pk}
                cand = score_grouping(a, d)
                if cand.score >= GROUP_THRESHOLD and (best is None or cand.score > best.score):
                    best = cand
        if best is not None:
            groups[best.parcel_key].append(d['档案号'])
            d['parcel_key'] = best.parcel_key
        else:
            pk = f'LX-{len(groups) + 1:03d}'
            groups[pk] = [d['档案号']]
            d['parcel_key'] = pk
            issues.append({'档案号': d['档案号'], '问题类型': '登记数据中无对应宗地',
                           '说明': '未能与既有宗地归宗（打分 < 40），新开宗地'})
    return groups, issues


# ---------- 与登记/缴费比对（生成宗地层问题） ----------

def compare_with_registry(doc: dict, ledger: dict, payments_for_parcel: list) -> list:
    """生成宗地层问题清单条目（基于已归宗的合同 + 登记台账 + 缴费归集）。"""
    out = []

    # 1. 合同到期未续（最后一份且当前有效/状态栏为空）
    end = to_date(doc.get('租赁终止日'))
    status = (ledger.get('合同状态') or '').strip()
    if end and end < date(2026, 9, 30) and status in ('到期未续', '到期未续签') :
        out.append({'档案号': doc['档案号'], '问题类型': '合同到期未续',
                    '说明': f'合同已于{end.isoformat()}到期，未见续期合同'})

    # 2. 缺宗地图（文件层识别标记 has_map=否）
    if doc.get('有无宗地图') in ('否', '0', 0, False):
        out.append({'档案号': doc['档案号'], '问题类型': '缺宗地图', '说明': '未附宗地图'})

    # 3. 关键字段有涂改
    altered = doc.get('涂改字段')
    if altered and altered not in (None, '', '无'):
        out.append({'档案号': doc['档案号'], '问题类型': '关键字段有涂改',
                    '说明': f'字段「{altered}」处有涂改'
                           + ('，涂改处无签章' if doc.get('涂改处有无签章') in ('否', '0', 0, False) else '')})

    # 4. 年租金大小写不一致
    small = _dec(doc.get('年租金小写'))
    cn = cn_amount(doc.get('年租金大写')) if doc.get('年租金大写') else None
    if small is not None and cn is not None and abs(cn - small) > Decimal('0.005'):
        out.append({'档案号': doc['档案号'], '问题类型': '年租金大小写不一致',
                    '说明': f'小写 {small:.2f} 与大写「{doc["年租金大写"]}」解析 {cn:.2f} 不一致'})

    # 5. 证件号码异常
    if doc.get('证件号码异常'):  # 由识别层填入
        out.append({'档案号': doc['档案号'], '问题类型': '证件号码异常',
                    '说明': doc['证件号码异常']})
    elif doc.get('证件号码') and not _valid_id(doc['证件号码']):
        out.append({'档案号': doc['档案号'], '问题类型': '证件号码异常',
                    '说明': f'证件号码「{doc["证件号码"]}」校验位或格式不合法'})

    # 6. 联系电话缺失或无效
    phone = doc.get('联系电话')
    if not phone or not re.match(r'^1\d{10}$', str(phone)):
        out.append({'档案号': doc['档案号'], '问题类型': '联系电话缺失或无效',
                    '说明': f'联系电话「{phone}」非法'})

    # 7. 坐落或宗地号与登记不一致
    loc_doc = _norm_loc(doc.get('坐落'))
    loc_reg = _norm_loc(ledger.get('登记坐落'))
    if loc_doc and loc_reg and loc_doc != loc_reg:
        out.append({'档案号': doc['档案号'], '问题类型': '坐落或宗地号与登记不一致',
                    '说明': f'合同坐落「{doc.get("坐落")}」与登记「{ledger.get("登记坐落")}」不一致'})
    elif doc.get('不动产单元号') and ledger.get('不动产单元号') and not parcel_matches_unit(
            doc.get('宗地号', ''), ledger['不动产单元号']):
        out.append({'档案号': doc['档案号'], '问题类型': '坐落或宗地号与登记不一致',
                    '说明': '合同宗地号与登记单元号位段不一致'})

    # 8. 面积与登记不一致
    a_area = _dec(doc.get('土地面积'))
    r_area = _dec(ledger.get('登记面积'))
    if a_area is not None and r_area is not None and abs(a_area - r_area) > Decimal('0.01'):
        out.append({'档案号': doc['档案号'], '问题类型': '面积与登记不一致',
                    '说明': f'合同面积 {a_area:.2f}，登记面积 {r_area:.2f}'})

    # 9. 承租人已变更未办合同变更（登记权利人 ≠ 合同承租人）
    if ledger.get('登记权利人') and doc.get('承租人') and ledger['登记权利人'] != doc['承租人']:
        out.append({'档案号': doc['档案号'], '问题类型': '承租人已变更未办合同变更',
                    '说明': f'合同承租人「{doc["承租人"]}」≠ 登记权利人「{ledger["登记权利人"]}」'})

    # 10. 缴费记录异常（缴款人非承租人/登记权利人）
    payers = {str(p.get('缴款人', '')).strip() for p in payments_for_parcel
              if p.get('缴款人')}
    legal = {doc.get('承租人'), ledger.get('登记权利人'), ledger.get('催缴对象')}
    legal.discard(None)
    unknown_payers = payers - legal - {''}
    if unknown_payers and payers:
        out.append({'档案号': doc['档案号'], '问题类型': '缴费记录异常',
                    '说明': f'缴款人「{"、".join(sorted(unknown_payers))}」非承租人/登记权利人'})

    return out


# ---------- 工具 ----------

def _dec(v) -> Optional[Decimal]:
    try:
        return Decimal(str(v).strip()) if v not in (None, '') else None
    except Exception:
        return None


def _norm_loc(s: str) -> str:
    if not s:
        return ''
    s = str(s).strip()
    s = re.sub(r'[×\*xX]+', '', s)          # 脱敏符（×× / xx / XX 等价）
    s = re.sub(r'(县|镇|市|省)', '', s)
    s = re.sub(r'[一二三四五六七八九十百千万零〇]+',
               lambda m: str(_cn_to_arabic(m.group())), s)
    return s


def _cn_to_arabic(s: str) -> int:
    """简单中文数字转阿拉伯：『二五八』→258；『壹佰』→100。"""
    digit = {'零': 0, '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
             '六': 6, '七': 7, '八': 8, '九': 9, '壹': 1, '贰': 2, '叁': 3,
             '肆': 4, '伍': 5, '陆': 6, '柒': 7, '捌': 8, '玖': 9}
    total, cur = 0, 0
    for ch in s:
        if ch in digit:
            cur = cur * 10 + digit[ch]
        elif ch in ('十', '拾'):
            cur = (cur or 1) * 10
        elif ch in ('百', '佰'):
            cur = (cur or 1) * 100
        elif ch in ('千', '仟'):
            cur = (cur or 1) * 1000
    return total + cur


def _valid_id(v: str) -> bool:
    """个人 18 位身份证校验位或单位信用代码格式。"""
    v = (v or '').strip()
    if len(v) != 18:
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check = '10X98765432'
    if v[:17].isdigit():
        return v[17].upper() == check[sum(int(c) * w for c, w in zip(v[:17], weights)) % 11]
    return v.isalnum()