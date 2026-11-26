"""API 冒烟测试：覆盖 9 个 router 的全部读接口 + 关键写接口。

用法：
  python scripts/smoke_api.py                    # 默认打到 127.0.0.1:8001
  BASE=http://127.0.0.1:8000 python scripts/smoke_api.py

退出码 0 = 全通过。
"""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.getenv('BASE', 'http://127.0.0.1:8000')

GET_CASES = [
    ('/api/health', None),
    ('/api/batches?page=1&page_size=5', 'page'),
    ('/api/review/docs?page_size=3', 'page'),
    ('/api/review/docs?process_type=人工复核&page_size=3', 'page'),
    ('/api/review/docs/LX-001', 'doc'),
    ('/api/review/docs/LX-001/pages', 'pages'),
    ('/api/parcels?page_size=3', 'page'),
    ('/api/parcels?land_usage=工业&page_size=3', 'page'),
    ('/api/parcels/LX-001', 'parcel'),
    ('/api/parcels/LX-001/contract-draft?years=10', 'draft'),
    ('/api/issues?page_size=3', 'page'),
    ('/api/issues?issue_type=存疑待确认', 'page'),
    ('/api/issues/types', 'list13'),
    ('/api/dashboard/kpis', 'kpis'),
    ('/api/dashboard/arrears-top', 'list'),
    ('/api/dashboard/distributions', 'dist'),
    ('/api/dashboard/governance-queue', 'queue'),
    ('/api/dunning/notices?page_size=3', 'page'),
    ('/api/dunning/expiry-calendar', 'list'),
    ('/api/tax', 'list'),
    ('/api/system/standards', 'list'),
    ('/api/system/street-levels', 'list'),
    ('/api/system/reductions', 'list'),
    ('/api/system/audit-logs?page_size=3', 'page'),
    ('/api/system/models', 'list'),
]


def check(path: str, kind) -> tuple[bool, str]:
    try:
        r = httpx.get(f'{BASE}{path}', timeout=30)
    except Exception as e:  # noqa: BLE001
        return False, f'连接失败 {e}'
    if r.status_code != 200:
        return False, f'HTTP {r.status_code} {r.text[:160]}'
    if kind is None:
        return True, ''
    data = r.json()
    if kind == 'page':
        if not isinstance(data, dict) or not {'items', 'total', 'page', 'page_size'} <= data.keys():
            return False, f'分页结构不符 {list(data)[:5] if isinstance(data, dict) else type(data)}'
        return True, f'{len(data["items"])}/{data["total"]}'
    if kind == 'list':
        return (True, f'{len(data)} 条') if isinstance(data, list) else (False, '非 list')
    if kind == 'list13':
        ok = isinstance(data, list) and len(data) == 13
        return ok, f'{len(data)} 类'
    if kind == 'kpis':
        need = {'total_parcels', 'total_due', 'total_arrears', 'due_2026', 'pending_review'}
        return (need <= data.keys()), str(data)[:80]
    if kind == 'doc':
        return (data.get('doc', {}).get('id') == 'LX-001'), f'fields={len(data.get("fields", []))}'
    if kind == 'pages':
        ok = data.get('page_count', 0) >= 1 and len(data.get('pages', [])) == data.get('page_count')
        return ok, f"页数={data.get('page_count')} 批次={data.get('batch_no')}"
    if kind == 'parcel':
        return (data.get('parcel', {}).get('parcel_key') == 'LX-001'), \
               f'contracts={len(data.get("contracts", []))} dues={len(data.get("dues", []))}'
    if kind == 'draft':
        ok = data.get('doc_type') == '续期' and data.get('start_date') and data.get('end_date')
        return ok, f"{data.get('start_date')} ~ {data.get('end_date')} 建议{data.get('suggest_rent')}"
    if kind == 'dist':
        return ({'by_year', 'by_usage'} <= data.keys()), ''
    if kind == 'queue':
        return ({'batches_pending', 'docs_pending', 'issues_open'} <= data.keys()), ''
    return True, ''


def main():
    print(f'== GET 冒烟 {BASE}')
    ok = fail = 0
    cases = list(GET_CASES)
    # 批次详情：动态取列表首个 id，避免硬编码
    first_batch = httpx.get(f'{BASE}/api/batches?page=1&page_size=1', timeout=30).json()
    if first_batch.get('items'):
        cases.insert(2, (f"/api/batches/{first_batch['items'][0]['id']}", None))
    for path, kind in cases:
        good, msg = check(path, kind)
        print(('  OK   ' if good else '  FAIL ') + path + ('  ' + msg if msg else ''))
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)

    # 写接口（用真实档案号，幂等或可重复确认）
    print('== POST 冒烟')
    writes = [
        ('/api/batches', {'batch_type': '冒烟测试'}, 'id'),
        ('/api/review/batch-confirm',
         {'archive_nos': ['LX-001'], 'operator': 'smoke', 'sample_inspect_rate': 0.0}, None),
    ]
    for path, body, expect_key in writes:
        r = httpx.post(f'{BASE}{path}', json=body, timeout=30)
        good = r.status_code == 200
        if good and expect_key:
            good = expect_key in r.json()
        print(('  OK   ' if good else '  FAIL ') + f'POST {path}  {r.status_code}'
              + ('' if good else f'  {r.text[:120]}'))
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)

    print(f'\n结果：OK={ok} FAIL={fail}')
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
