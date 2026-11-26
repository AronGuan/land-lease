"""把练习集合同扫描件按「宗地」切分为 80% 数据集 / 20% 测试集。

设计要点：
1. 按宗地整体切分，同一宗地的多份合同（新签/续期/变更）必须同侧——
   否则测试宗地缺失成员，标准答案的欠缴金额无法比对。
2. 固定随机种子，结果可复现。
3. 只复制、不移动源文件（源文件始终保留）。
4. 同时导出测试集对应的标准答案子集，供 score.py 独立评测。
"""
import os, csv, re, shutil, random, collections

SEED = 20261027
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '国有土地租赁模拟样本包_练习集', '练习集')
SCAN = os.path.join(SRC, '01_合同扫描件')
ANS = os.path.join(SRC, '08_标准答案')
OUT = os.path.join(ROOT, '数据切分')
TRAIN = os.path.join(OUT, 'dataset_80')
TEST = os.path.join(OUT, 'test_20')
TRAIN_RATIO = 0.8


def parcel_groups():
    with open(os.path.join(ANS, '宗地台账.csv'), encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    return {r['宗地键']: [d for d in re.split(r'[;；]', r['档案号列表']) if d] for r in rows}


def pick_parcels(groups, n_target):
    """打乱后贪心挑选宗地，使文件总数最接近目标；同 size 优先，保证稳定。"""
    keys = sorted(groups)
    random.Random(SEED).shuffle(keys)
    chosen, total = [], 0
    for size in (3, 2, 1):
        for k in keys:
            if k in chosen or len(groups[k]) != size:
                continue
            if total + size <= n_target:
                chosen.append(k)
                total += size
    # 补足：挑最小的差额填补
    for k in keys:
        if total >= n_target:
            break
        if k not in chosen and total + len(groups[k]) <= n_target:
            chosen.append(k)
            total += len(groups[k])
    return chosen, total


def write_manifest(path, keys, groups):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['宗地键', '档案号', '页数', '文件名'])
        for k in keys:
            for arch in groups[k]:
                pages = sorted(n for n in os.listdir(SCAN) if n.startswith(arch + '_') and n.endswith('.jpg'))
                w.writerow([k, arch, len(pages), ';'.join(pages)])


def subset_answers(keys, groups, test_arch):
    os.makedirs(os.path.join(TEST, 'standard_answers'), exist_ok=True)
    with open(os.path.join(ANS, '宗地台账.csv'), encoding='utf-8-sig') as f:
        ledger = [r for r in csv.DictReader(f) if r['宗地键'] in set(keys)]
    with open(os.path.join(TEST, 'standard_answers', '宗地台账.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(ledger[0].keys()))
        w.writeheader(); w.writerows(ledger)

    due = [r for r in csv.DictReader(open(os.path.join(ANS, '应缴明细.csv'), encoding='utf-8-sig'))
           if r['宗地键'] in set(keys)]
    with open(os.path.join(TEST, 'standard_answers', '应缴明细.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(due[0].keys())); w.writeheader(); w.writerows(due)

    pay = [r for r in csv.DictReader(open(os.path.join(ANS, '缴费归集.csv'), encoding='utf-8-sig'))
           if r['宗地键'] in set(keys)]
    with open(os.path.join(TEST, 'standard_answers', '缴费归集.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(pay[0].keys())); w.writeheader(); w.writerows(pay)

    for name, col in (('合同要素.csv', '档案号'), ('问题清单.csv', '档案号')):
        rows = [r for r in csv.DictReader(open(os.path.join(ANS, name), encoding='utf-8-sig'))
                if r[col] in test_arch]
        with open(os.path.join(TEST, 'standard_answers', name), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return len(ledger), len(due), len(pay)


def main():
    groups = parcel_groups()
    n_files = sum(len(v) for v in groups.values())
    n_test_files = round(n_files * (1 - TRAIN_RATIO))
    test_keys, test_cnt = pick_parcels(groups, n_test_files)
    test_arch = set(a for k in test_keys for a in groups[k])
    train_keys = [k for k in groups if k not in set(test_keys)]

    for d in (TRAIN, TEST):
        os.makedirs(d, exist_ok=True)
    copied = 0
    for k in groups:
        dst = TEST if k in set(test_keys) else TRAIN
        for arch in groups[k]:
            for n in [x for x in os.listdir(SCAN) if x.startswith(arch + '_') and x.endswith('.jpg')]:
                shutil.copy2(os.path.join(SCAN, n), os.path.join(dst, n))
                copied += 1

    write_manifest(os.path.join(OUT, 'manifest_dataset_80.csv'), train_keys, groups)
    write_manifest(os.path.join(OUT, 'manifest_test_20.csv'), test_keys, groups)
    ln, dn, pn = subset_answers(test_keys, groups, test_arch)

    print(f'源文件 {n_files} 份（{len(groups)} 宗），切分种子 {SEED}')
    print(f'数据集中(dict) : {len(train_keys)} 宗 / {n_files - test_cnt} 份文件  → dataset_80/')
    print(f'测试集(test)   : {len(test_keys)} 宗 / {test_cnt} 份文件  → test_20/')
    print(f'实际占比 {(n_files-test_cnt)/n_files:.0%} : {test_cnt/n_files:.0%}')
    print(f'测试集宗地 {test_keys}')
    print(f'已复制图片 {copied} 张；测试集标准答案子集：宗地台账 {ln} 行 / 应缴明细 {dn} 行 / 缴费归集 {pn} 行')


if __name__ == '__main__':
    main()
