"""现场预检：一键确认「服务在跑 / 数据在位 / 接口全绿 / 核算全对」。

用法：python scripts/drill_check.py [BASE]
默认 BASE=http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
PY = sys.executable

OK, FAIL = '\u2713', '\u2717'
failures = []


def step(title: str, fn):
    try:
        detail = fn()
        print(f'  {OK} {title}' + (f'  {detail}' if detail else ''))
    except Exception as e:  # noqa: BLE001
        failures.append(title)
        print(f'  {FAIL} {title}  {e}')


def check_health():
    d = httpx.get(f'{BASE}/api/health', timeout=10).json()
    assert d['status'] == 'ok', f"status={d['status']} db={d['database']}"
    assert d['table_count'] == 27, f"table_count={d['table_count']}"
    assert d['api_key_configured'], 'API Key 未配置'
    return f"27 表 / 模型 {d['model']} / 口径 {d['rule_version']}"


def check_data():
    k = httpx.get(f'{BASE}/api/dashboard/kpis', timeout=15).json()
    assert k['total_parcels'] == 26, f"宗地数 {k['total_parcels']}（期望 26，需先跑 seed.py）"
    assert abs(k['total_arrears'] - 108600.93) < 0.01, f"累计欠缴 {k['total_arrears']}（期望 108600.93）"
    return f"26 宗地 / 应缴 {k['total_due']:,.2f} / 欠缴 {k['total_arrears']:,.2f}"


def check_issues():
    n = httpx.get(f'{BASE}/api/issues/types', timeout=10).json()
    assert len(n) == 13, f'问题类型 {len(n)} 类（期望 13）'
    return '13 类问题清单'


def run_script(rel: str, expect: str):
    env = {**os.environ, 'BASE': BASE}   # 子脚本沿用同一后端地址
    out = subprocess.run([PY, str(ROOT / rel)], capture_output=True, text=True,
                         timeout=600, env=env)
    text = (out.stdout or '') + (out.stderr or '')
    assert out.returncode == 0, f'{rel} 退出码 {out.returncode}\n{text[-400:]}'
    assert expect in text, f'{rel} 未达预期'
    tail = [l for l in text.strip().splitlines() if l.strip()][-1]
    return tail[:110]


def main():
    print(f'== 现场预检 {BASE}\n')
    step('后端健康检查', check_health)
    step('演示数据在位', check_data)
    step('问题清单 13 类', check_issues)
    step('接口冒烟 28 项', lambda: run_script('scripts/smoke_api.py', 'FAIL=0'))
    step('练习集核算验证', lambda: run_script('scripts/verify_calc.py', '30/30'))
    step('盲测核算验证', lambda: run_script('scripts/verify_test20.py', '4/4'))
    step('核算单测 10 项', lambda: run_script('landlease/tests/test_calc.py', '10/10'))
    step('识别单测 9 项', lambda: run_script('landlease/tests/test_recognize.py', '9/9'))
    step('归宗单测 7 项', lambda: run_script('landlease/tests/test_grouping.py', '7/7'))

    print()
    if failures:
        print(f'{FAIL} 预检未通过 {len(failures)} 项：' + '、'.join(failures))
        print('   处理建议见 docs/04_部署说明.md 第五节「常见排障」')
        return 1
    print(f'{OK} 全部通过，可以开始演示。')
    print('   演示脚本：docs/05_现场补档演练脚本.md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
