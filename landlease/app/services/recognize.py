"""识别编排：多页合并 → 规则预校验 → 反推规则库 → 三级判定（PRD 6.1/6.2）。

纯函数模块，不落库；API 层负责写 field_extraction / contract_doc / 问题清单。
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

from ..core.config import settings
from .calc import Standard, cn_amount, pick_standard, to_date
from .vlm import FIELDS, extract_page

# ---------- 数据结构 ----------

# 可选字段：合同本来就可能不载明，为空属正常，不应记「不可识别」问题
OPTIONAL_FIELDS = {
    '原合同编号', '承租人类型', '涂改字段', '涂改前内容',
    '涂改处有无签章', '手写批注', '合同编号', '住所', '有无宗地图',
    '土地级别',   # 合同多不载明，按街路级别推导

}

# 字段级校验问题 → 13 类标准问题类型（PRD 6.4，不得自创）
ISSUE_TYPE_MAP = {
    '证件号码格式异常': '证件号码异常',
    '联系电话格式异常': '联系电话缺失或无效',
    '大小写金额不一致': '年租金大小写不一致',
    '关键字段有涂改': '关键字段有涂改',
    '终止日早于起始日': '存疑待确认',
}
DEFAULT_ISSUE_TYPE = '存疑待确认'

# 数值类字段：VLM 常带单位（'5年' / '542.79元' / '1.40元/m²·年'），校验前须去单位
_NUMERIC_FIELDS = {'土地面积', '年租金小写', '年租金标准', '租赁年限'}
_NUM_PREFIX = re.compile(r'^\s*[-+]?\d+(?:\.\d+)?')


def normalize_value(name: str, value):
    """VLM 原文归一化：数值去单位、计租方式映射标准值、用途去「用地」后缀。

    在规则校验之前执行，避免「5年」「542.79元」这类带单位原文被误判为异常。
    """
    if value in (None, ''):
        return value
    s = str(value).strip()
    if name in _NUMERIC_FIELDS:
        m = _NUM_PREFIX.match(s)
        return m.group().strip() if m else s
    if name == '计租方式':
        if '随' in s and ('标准' in s or '基准地价' in s):
            return '随标准调整'
        if '固定' in s:
            return '固定'
        return s
    if name == '用途':
        return s.replace('用地', '')
    return s


@dataclass
class FieldResult:
    name: str
    ai_value: Optional[str] = None
    final_value: Optional[str] = None
    confidence: float = 0.0
    evidence: str = ''
    page: Optional[int] = None
    source: str = 'ai'            # ai / inferred / blank
    level: str = 'L3'             # L1 直接识别 / L2 反推 / L3 不可识别
    rules: list = field(default_factory=list)   # 反推链路（推导规则名列表）
    issues: list = field(default_factory=list)  # 该字段触发的问题类型


@dataclass
class DocResult:
    archive_no: str
    fields: dict                       # name -> FieldResult
    process_type: str = '自动通过'      # 自动通过 / 人工复核
    forced_reasons: list = field(default_factory=list)  # 强制降级原因
    page_count: int = 0

    def issues(self) -> list:
        """汇总问题清单：映射到 13 类标准类型，剔除可选字段空值等误报。

        返回 [(issue_type, description)]，issue_type 严格取自 grouping.ISSUE_TYPES。
        """
        out, seen = [], set()
        for f in self.fields.values():
            for t in f.issues:
                # 可选字段为空 → 不算问题（这些字段本来就允许缺失）
                if t == '不可识别' and f.name in OPTIONAL_FIELDS:
                    continue
                mapped = ISSUE_TYPE_MAP.get(t, DEFAULT_ISSUE_TYPE)
                key = (mapped, f.name, t)
                if key in seen:
                    continue
                seen.add(key)
                desc = (f'关键字段「{f.name}」不可识别' if t == '不可识别'
                        else f'字段「{f.name}」{t}')
                out.append((mapped, desc))
        return out


# ---------- 规则预校验 ----------

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK = '10X98765432'


def valid_id_no(v: str) -> bool:
    """个人 18 位身份证（含校验位）或单位统一社会信用代码（18 位格式）。"""
    v = (v or '').strip()
    if len(v) != 18:
        return False
    if v[:-1].isdigit():  # 个人：校验位
        s = sum(int(c) * w for c, w in zip(v[:17], _ID_WEIGHTS))
        return v[17].upper() == _ID_CHECK[s % 11]
    return v.isalnum()  # 单位信用代码（格式校验）


def valid_phone(v: str) -> bool:
    v = (v or '').strip().replace('-', '').replace(' ', '')
    return v.isdigit() and len(v) == 11


def to_dec(v) -> Optional[Decimal]:
    try:
        return Decimal(str(v).strip()) if v not in (None, '') else None
    except (InvalidOperation, ValueError):
        return None


def validate_field(name: str, value: Optional[str]) -> list:
    """规则预校验：返回问题类型列表（空 = 通过）。"""
    if value in (None, ''):
        return []
    issues = []
    if name == '证件号码' and not valid_id_no(value):
        issues.append('证件号码格式异常')
    elif name == '联系电话' and not valid_phone(value):
        issues.append('联系电话格式异常')
    elif name in ('签订日期', '租赁起始日', '租赁终止日') and to_date(value) is None:
        issues.append('日期格式异常')
    elif name == '土地面积':
        d = to_dec(value)
        if d is None or not (Decimal('0.01') <= d <= Decimal('1000000')):
            issues.append('土地面积异常')
    elif name == '租赁年限':
        d = to_dec(value)
        if d is None or d != d.to_integral_value() or not (1 <= int(d) <= 50):
            issues.append('租赁年限异常')
    elif name in ('年租金小写', '年租金标准'):
        d = to_dec(value)
        if d is None or d <= 0:
            issues.append('金额异常')
    elif name == '年租金大写' and cn_amount(value) is None:
        issues.append('大写金额解析失败')
    return issues


# ---------- 反推规则库（PRD 6.2） ----------

def _year_from(fr: dict, name: str) -> Optional[int]:
    d = to_date(fr[name].final_value) if name in fr else None
    return d.year if d else None


def apply_inference(fr: dict, standards: Iterable[Standard]) -> None:
    """对缺失/低置信字段做反推（就地填 L2 结果）。"""
    conf_th = settings.AUTO_PASS_CONFIDENCE

    def weak(name):
        f = fr.get(name)
        return f is None or f.final_value in (None, '') or f.confidence < conf_th

    # 规则1 大写互推：年租金小写 ← 大写
    if weak('年租金小写'):
        cn = fr['年租金大写'].final_value if '年租金大写' in fr else None
        amt = cn_amount(cn) if cn else None
        if amt is not None:
            _fill(fr, '年租金小写', f'{amt:.2f}', ['大写互推: 年租金小写 ← 年租金大写解析'],
                  f'原文大写「{cn}」')

    # 规则2 金额互推：年租金小写 ← 面积 × 计租标准（签约年度适用标准）
    if weak('年租金小写'):
        area = to_dec(fr['土地面积'].final_value) if '土地面积' in fr else None
        usage = (fr['用途'].final_value or '').replace('用地', '') if '用途' in fr else ''
        level = (fr['土地级别'].final_value or '') if '土地级别' in fr else ''
        year = _year_from(fr, '租赁起始日') or _year_from(fr, '签订日期')
        price = pick_standard(standards, usage, level, year) if (area and usage and level and year) else None
        if price is not None and area:
            _fill(fr, '年租金小写', f'{float(area) * float(price):.2f}',
                  [f'金额互推: 面积{area} × {year}年度标准{price}（{usage}/{level}）'],
                  f'标准表执行起始日 ≤ {year}-01-01 的最新一档')

    # 规则3 日期互推：终止日 = 起始日 + 租赁年限 − 1 天
    # （对齐样本：2016-01-01+10年=2025-12-31；2010-04-01+10年=2020-03-31；2016-03-01+20年=2036-02-29）
    if weak('租赁终止日'):
        s = to_date(fr['租赁起始日'].final_value) if '租赁起始日' in fr else None
        y = to_dec(fr['租赁年限'].final_value) if '租赁年限' in fr else None
        if s and y and y == y.to_integral_value():
            months = int(y) * 12
            ey = s.year + (s.month - 1 + months) // 12
            em = (s.month - 1 + months) % 12 + 1
            end = date(ey, em, min(s.day, calendar.monthrange(ey, em)[1])) - timedelta(days=1)
            _fill(fr, '租赁终止日', end.isoformat(),
                  [f'日期互推: 起始日{s} + 租赁年限{int(y)}年 − 1天'], '')

    # 规则4 年限互推：租赁年限 ← 终止日 − 起始日
    if weak('租赁年限'):
        s = to_date(fr['租赁起始日'].final_value) if '租赁起始日' in fr else None
        e = to_date(fr['租赁终止日'].final_value) if '租赁终止日' in fr else None
        if s and e and e > s:
            months = (e.year - s.year) * 12 + (e.month - s.month) + (1 if e.day >= s.day - 1 else 0)
            _fill(fr, '租赁年限', str(round(months / 12)),
                  ['年限互推: 由终止日 − 起始日折算'], '')


def _fill(fr: dict, name: str, value: str, rules: list, evidence: str) -> None:
    f = fr.setdefault(name, FieldResult(name=name))
    f.final_value = value
    f.source = 'inferred'
    f.level = 'L2'
    f.rules = rules
    f.evidence = f.evidence or evidence


# ---------- 多页合并 ----------

def merge_pages(pages: list) -> dict:
    """多页抽取结果合并：每字段取最高置信度的非空值；同字段两页高置信且不一致 → 记冲突。"""
    merged: dict = {}
    for page_no, page in enumerate(pages, 1):
        for name, v in page.items():
            if name not in FIELDS:
                continue
            val = v.get('value') if isinstance(v, dict) else v
            conf = float(v.get('confidence', 0)) if isinstance(v, dict) else 0.5
            ev = str(v.get('evidence', '')) if isinstance(v, dict) else ''
            cur = merged.get(name)
            if cur is None or (val and (not cur['value'] or conf > cur['confidence'])):
                if val or cur is None:
                    merged[name] = {'value': val, 'confidence': conf,
                                    'evidence': ev, 'page': page_no}
    return merged


# ---------- 主入口 ----------

def judge(archive_no: str, merged: dict, standards: Iterable[Standard] = (),
          page_count: int = 1) -> DocResult:
    """对「已合并的抽取结果」执行 校验 → 反推 → 三级判定（不调 VLM，可单测）。"""
    fr: dict = {}
    for name in FIELDS:
        m = merged.get(name) or {}
        # ai_value 保留模型原文，final_value 为归一化值（去单位/映射标准取值）
        f = FieldResult(name=name, ai_value=m.get('value'),
                        final_value=normalize_value(name, m.get('value')),
                        confidence=float(m.get('confidence') or 0.0),
                        evidence=m.get('evidence', ''), page=m.get('page'))
        f.issues = validate_field(name, f.final_value)
        fr[name] = f

    # 交叉校验：大小写不一致（口径四(一) 暂按大写，记问题）
    small = to_dec(fr['年租金小写'].final_value)
    cn_val = cn_amount(fr['年租金大写'].final_value) if fr['年租金大写'].final_value else None
    if small is not None and cn_val is not None and abs(cn_val - small) > Decimal('0.005'):
        fr['年租金小写'].issues.append('大小写金额不一致')
        fr['年租金小写'].final_value = f'{cn_val:.2f}'
        fr['年租金小写'].rules = [f'口径四(一): 大写{cn_val} 与小写{small}不一致，暂按大写']
        fr['年租金小写'].level = 'L2'
        fr['年租金小写'].source = 'inferred'
    # 交叉校验：终止日早于起始日
    s, e = to_date(fr['租赁起始日'].final_value), to_date(fr['租赁终止日'].final_value)
    if s and e and e < s:
        fr['租赁终止日'].issues.append('终止日早于起始日')

    # 反推（只对仍缺失/低置信者生效）
    apply_inference(fr, standards)

    # 三级判定
    conf_th = settings.AUTO_PASS_CONFIDENCE
    for f in fr.values():
        if f.final_value in (None, ''):
            f.level, f.source = 'L3', 'blank'
        elif f.level == 'L2':
            pass  # 反推/大小写覆盖已定级
        elif f.confidence >= conf_th and not f.issues:
            f.level = 'L1'
        else:
            f.level = 'L2'  # 低置信或校验未过 → 人工复核档
    # L3 关键字段记问题清单
    for f in fr.values():
        if f.level == 'L3':
            f.issues.append('不可识别')

    doc = DocResult(archive_no=archive_no, fields=fr, page_count=page_count)

    # 强制降级四情形（PRD 6.1）：字段有涂改 → 整份人工复核
    altered = fr.get('涂改字段')
    if altered and altered.final_value not in (None, ''):
        doc.process_type = '人工复核'
        doc.forced_reasons.append(f'字段有涂改：{altered.final_value}')
        tgt = fr.get(str(altered.final_value))
        if tgt is not None:
            tgt.level = 'L2'
            tgt.issues.append('关键字段有涂改')
    # 关键字段低置信 / 校验未过 → 整份人工复核
    key_fields = ('承租人', '证件号码', '土地面积', '租赁起始日', '租赁终止日', '年租金小写')
    for k in key_fields:
        f = fr.get(k)
        if f is None:
            continue
        if f.final_value not in (None, '') and (f.confidence < conf_th or f.issues):
            doc.process_type = '人工复核'
            doc.forced_reasons.append(f'关键字段异常：{k}（置信度{f.confidence:.2f}'
                                      + ('，' + '、'.join(f.issues) if f.issues else '') + '）')
        if f.level == 'L3':
            doc.process_type = '人工复核'
            doc.forced_reasons.append(f'关键字段不可识别：{k}')
    return doc


def recognize_document(archive_no: str, image_paths: list,
                       standards: Iterable[Standard] = (),
                       model: Optional[str] = None,
                       channel=None) -> DocResult:
    """整份文档识别：逐页 VLM 抽取 → 合并 → 校验 → 反推 → 三级判定。

    `channel`（channel.Channel）非空时按该通道的端点/凭据/模型调用，
    用于「闭源云端 ↔ 开源可部署」现场切换；为空则沿用 `model` + .env 默认端点。
    """
    if channel is not None:
        pages = [extract_page(p, model=channel.model_id, base_url=channel.base_url,
                              api_key=channel.api_key) for p in image_paths]
    else:
        pages = [extract_page(p, model=model) for p in image_paths]
    merged = merge_pages(pages)
    return judge(archive_no, merged, standards, page_count=len(pages))
