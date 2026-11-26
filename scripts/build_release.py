"""生成离线部署包 zip。

用法：
    python scripts/build_release.py                 # 产出 dist/国有土地租赁智能管理系统_vX.Y_离线部署包.zip
    python scripts/build_release.py --with-wheels   # 同时下载离线 wheel（需可访问 PyPI）

打包内容：后端源码、前端构建产物（web/）、部署与运维脚本、文档、requirements、schema.sql。
不含：.env（含密钥）、storage（业务数据）、__pycache__、虚拟环境。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0'

INCLUDE_DIRS = ['landlease', 'scripts', 'docs', 'deploy']
INCLUDE_FILES = ['requirements.txt', 'README.md', '.env.example']

EXCLUDE_SUFFIX = {'.pyc', '.pyo', '.log', '.pid'}
EXCLUDE_NAMES = {'__pycache__', '.venv', 'venv', 'node_modules', '.git',
                 '.pytest_cache', '.idea', '.vscode', 'storage', '_ocr_cache'}
EXCLUDE_GLOB_DIRS = {'国有土地租赁模拟样本包_练习集', '数据切分', 'frontend'}


def _should_skip(rel: Path) -> bool:
    if any(p in EXCLUDE_NAMES for p in rel.parts):
        return True
    if any(p in EXCLUDE_GLOB_DIRS for p in rel.parts):
        return True
    if rel.name in EXCLUDE_NAMES:
        return True
    return rel.suffix in EXCLUDE_SUFFIX


def download_wheels(dest: Path):
    """把依赖下载为离线 wheel，供目标机 --no-index 安装。"""
    dest.mkdir(parents=True, exist_ok=True)
    print('下载离线依赖到', dest)
    subprocess.check_call([sys.executable, '-m', 'pip', 'download',
                           '-r', str(ROOT / 'requirements.txt'), '-d', str(dest)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--with-wheels', action='store_true', help='同时下载离线 wheel')
    ap.add_argument('--out', default=None, help='输出 zip 路径')
    args = ap.parse_args()

    web = ROOT / 'web'
    if not web.is_dir():
        raise SystemExit('缺少 web/（前端构建产物）。请先执行：cd frontend && npx vite build，'
                         '然后把 frontend/dist 复制为 web/')

    if args.with_wheels:
        download_wheels(ROOT / 'wheels')

    out_dir = ROOT / 'dist'
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d')
    out = Path(args.out) if args.out else out_dir / f'国有土地租赁智能管理系统_v{VERSION}_离线部署包_{stamp}.zip'

    tmp = out_dir / '_pkg'
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / 'web').mkdir(parents=True)

    # 前端构建产物
    for f in web.rglob('*'):
        if f.is_file():
            dst = tmp / 'web' / f.relative_to(web)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

    # 代码与文档
    for d in INCLUDE_DIRS:
        src = ROOT / d
        if not src.is_dir():
            continue
        for f in src.rglob('*'):
            rel = f.relative_to(ROOT)
            if _should_skip(rel):
                continue
            if f.is_dir():
                (tmp / rel).mkdir(parents=True, exist_ok=True)
            else:
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, tmp / rel)

    for name in INCLUDE_FILES:
        src = ROOT / name
        if not src.exists():
            src = ROOT / 'deploy' / name
        if src.exists():
            shutil.copy2(src, tmp / name)

    schema = ROOT / 'docs' / 'schema.sql'
    if schema.exists():
        shutil.copy2(schema, tmp / 'schema.sql')

    wheels = ROOT / 'wheels'
    if wheels.is_dir():
        print('包含离线 wheels ...')
        for f in wheels.rglob('*.whl'):
            (tmp / 'wheels').mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, tmp / 'wheels' / f.name)

    # 包内安装说明
    readme = tmp / '安装说明.md'
    if not readme.exists() and (tmp / 'docs' / '04_部署说明.md').exists():
        shutil.copy2(tmp / 'docs' / '04_部署说明.md', readme)

    # 打包
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(tmp.rglob('*')):
            if f.is_file():
                z.write(f, f.relative_to(tmp))

    shutil.rmtree(tmp)
    size_mb = out.stat().st_size / 1024 / 1024
    print(f'\n部署包已生成：{out}')
    print(f'大小：{size_mb:.1f} MB')
    print('\n包含：')
    with zipfile.ZipFile(out) as z:
        tops = sorted({n.split('/')[0] for n in z.namelist()})
        for t in tops:
            n = sum(1 for x in z.namelist() if x.split('/')[0] == t)
            print(f'  {t}/  ({n} 个文件)')


if __name__ == '__main__':
    main()
