"""VLM 识别适配器：OpenAI 兼容接口（默认 DashScope）主通道。

职责单一：把一页合同图片变成「字段 -> {value, confidence, evidence}」。
不做反推、不做判定（recognize.py 的职责）。

通道可切换：`base_url` / `api_key` 由 channel.py 按当前主通道给出，
因此换托管商（闭源云端 → 开源可部署）不需要改这里。
"""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from ..core.config import settings

# 抽取字段清单（与 contract_doc 表 / 合同要素.csv 对齐）
FIELDS = [
    '合同类型', '合同编号', '原合同编号', '签订日期', '出租人', '承租人', '承租人类型',
    '证件号码', '联系电话', '住所', '宗地号', '坐落', '土地面积', '用途', '土地级别',
    '租赁起始日', '租赁终止日', '租赁年限', '计租方式', '年租金标准', '年租金小写',
    '年租金大写', '有无宗地图', '涂改字段', '涂改前内容', '涂改处有无签章', '手写批注',
]

_PROMPT = f"""你是国土部门国有土地租赁合同的档案数字化专员。请从这张合同扫描页中抽取以下字段。

要求：
1. 严格按图片原文抽取，禁止推测或编造；页面上没有的字段填 null。
2. 每个字段给出置信度 confidence（0~1 的小数，1 表示完全清晰无歧义）。
3. evidence 给出该字段在图中的原文片段（≤30 字）；无法定位时给空字符串。
4. 「涂改字段」「涂改前内容」「涂改处有无签章」：页面出现数字/文字被划改、覆盖、补写时必须记录；无涂改则涂改字段填 null。
5. 日期统一 YYYY-MM-DD；金额保留原文写法（小写如 1386.78，大写如 壹仟叁佰捌拾陆元柒角捌分）。
6. 只输出 JSON，不要任何其他文字。

输出格式：
{{"字段名": {{"value": ...或null, "confidence": 0.00, "evidence": "..."}}, ...}}

字段清单：{','.join(FIELDS)}"""


def _b64_image(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def _parse_json(text: str) -> dict:
    """从模型输出中稳健解析 JSON（容忍 ```json 围栏与前后杂文）。"""
    text = text.strip()
    m = re.search(r'```(?:json)?\s*(.+?)\s*```', text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find('{'), text.rfind('}')
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def extract_page(image_path, model: Optional[str] = None,
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 retries: int = 2, timeout: float = 120.0) -> dict:
    """单页抽取。返回 {字段: {value, confidence, evidence}}；失败抛异常。

    每字段额外带 _page 便于多页合并溯源。
    `base_url` / `api_key` 留空则走 .env 的闭源主通道（DashScope）。
    """
    model = model or settings.DEFAULT_VL_MODEL
    base_url = (base_url or settings.DASHSCOPE_BASE_URL).rstrip('/')
    api_key = api_key or settings.DASHSCOPE_API_KEY
    if not api_key:
        raise RuntimeError('模型凭据未配置（.env 的 DASHSCOPE_API_KEY / OPENSOURCE_API_KEY）')
    body = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'image_url',
                 'image_url': {'url': f'data:image/jpeg;base64,{_b64_image(image_path)}'}},
                {'type': 'text', 'text': _PROMPT},
            ],
        }],
        'temperature': 0.1,
        'response_format': {'type': 'json_object'},
    }
    headers = {'Authorization': f'Bearer {api_key}'}
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(f'{base_url}/chat/completions',
                              json=body, headers=headers, timeout=timeout)
            # 部分开源托管商不支持 response_format=json_object；prompt 已要求只输出 JSON，
            # 去掉该参数即可继续（解析侧 _parse_json 本身容错）。
            if resp.status_code == 400 and 'response_format' in resp.text:
                body.pop('response_format', None)
                resp = httpx.post(f'{base_url}/chat/completions',
                                  json=body, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content']
            parsed = _parse_json(content)
            out = {}
            for f, v in parsed.items():
                if not isinstance(v, dict):
                    v = {'value': v, 'confidence': 0.5, 'evidence': ''}
                val = v.get('value')
                if val in ('', 'null', 'None', '无', '未见', '未填写'):
                    val = None
                out[f] = {'value': val,
                          'confidence': max(0.0, min(1.0, float(v.get('confidence') or 0))),
                          'evidence': str(v.get('evidence') or '')[:60]}
            return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'VLM 抽取失败（{Path(image_path).name}）: {last_err}')
