"""催缴：生成通知书 + 模拟短信任务 + 催缴台账（回款留痕）+ 通知书 PDF。"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import (AuditLog, CollectionNotice, ContractDoc, PaymentTrack,
                      Parcel, SmsTask)
from ..schemas import NoticeOut, Page
from ._common import apply_pagination, page_params

router = APIRouter(prefix='/api/dunning', tags=['dunning'])

BASELINE = date(2026, 9, 30)


@router.post('/notices', response_model=dict)
def generate_notices(parcel_keys: list[str], operator: str = '系统',
                       db: Session = Depends(get_db)):
    """对欠缴宗地生成催缴通知书（幂等）。

    - 该宗地已有「未回款/部分回款」的通知书 → **复用并刷新欠缴金额**，不新建、不重复发短信；
    - 否则新建通知书 + 模拟短信任务。
    返回值区分 created（新建）与 reused（复用），供前端提示并直接下载 PDF。
    """
    rows = db.scalars(select(Parcel).where(Parcel.parcel_key.in_(parcel_keys))).all()
    if not rows:
        raise HTTPException(400, '无对应宗地')
    created, reused, notice_ids, skipped = [], [], [], []
    for p in rows:
        if not p.arrears or p.arrears <= 0:
            skipped.append(p.parcel_key)
            continue
        exist = db.scalar(
            select(CollectionNotice)
            .where(CollectionNotice.parcel_key == p.parcel_key,
                   CollectionNotice.status.in_(('generated', '部分回款')))
            .order_by(desc(CollectionNotice.id)).limit(1))
        if exist:
            exist.arrears = p.arrears          # 金额随最新台账刷新
            db.flush()
            reused.append(exist.id)
            notice_ids.append(exist.id)
        else:
            n = CollectionNotice(parcel_key=p.parcel_key, arrears=p.arrears,
                                 template_version='v1.0',
                                 file_path=f'notices/{p.parcel_key}.pdf')
            db.add(n)
            db.flush()
            db.add(SmsTask(notice_id=n.id, phone=p.phone, status='模拟发送',
                           sent_at=datetime.now()))
            created.append(n.id)
            notice_ids.append(n.id)
    db.add(AuditLog(actor=operator, action='dunning_generate',
                    target_type='notice', target_id=','.join(map(str, notice_ids)) or '-',
                    after_value=f'created={created}, reused={reused}, skipped={skipped}'))
    db.commit()
    return {'created_count': len(created), 'reused_count': len(reused),
            'skipped': skipped, 'created': created, 'reused': reused,
            'notice_ids': notice_ids}


@router.get('/notices/pdf-batch')
def notices_pdf_batch(ids: str, db: Session = Depends(get_db)):
    """批量下载通知书：单份直接返回 PDF，多份打包 zip。"""
    import zipfile

    try:
        id_list = [int(x) for x in ids.split(',') if x.strip()]
    except ValueError:
        raise HTTPException(400, 'ids 参数非法')
    if not id_list:
        raise HTTPException(400, '未指定通知书')
    notices = db.scalars(select(CollectionNotice)
                         .where(CollectionNotice.id.in_(id_list))
                         .order_by(CollectionNotice.id)).all()
    if not notices:
        raise HTTPException(404, '通知书不存在')

    if len(notices) == 1:
        n = notices[0]
        buf = _render_notice_pdf(n, db.get(Parcel, n.parcel_key))
        return StreamingResponse(
            buf, media_type='application/pdf',
            headers={'Content-Disposition':
                     f'attachment; filename="notice_{n.parcel_key}_{n.id}.pdf"'})

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in notices:
            pdf = _render_notice_pdf(n, db.get(Parcel, n.parcel_key))
            z.writestr(f'催缴通知书_{n.parcel_key}_{n.id:03d}.pdf', pdf.getvalue())
    zbuf.seek(0)
    stamp = datetime.now().strftime('%Y%m%d%H%M')
    return StreamingResponse(
        zbuf, media_type='application/zip',
        headers={'Content-Disposition':
                 f'attachment; filename="notices_{stamp}.zip"'})


@router.get('/notices', response_model=Page[NoticeOut])
def list_notices(parcel_key: Optional[str] = Query(None),
                    latest_only: bool = Query(True),
                    db: Session = Depends(get_db), params: dict = Depends(page_params)):
    """通知书列表。默认每个宗地只返回**最新一份**（催缴对象视角，避免重复行）；
    查某宗地历史时传 parcel_key（自动返回该宗地全部历史）。"""
    q = db.query(CollectionNotice).order_by(desc(CollectionNotice.created_at))
    if parcel_key:
        q = q.where(CollectionNotice.parcel_key == parcel_key)
    elif latest_only:
        latest_ids = (select(func.max(CollectionNotice.id))
                      .group_by(CollectionNotice.parcel_key))
        q = q.where(CollectionNotice.id.in_(latest_ids))
    return apply_pagination(q, params)


# ---------- 到期提醒（到期日历 + 工作台共用） ----------

@router.get('/expiry-alerts', response_model=dict)
def expiry_alerts(days: int = 90, db: Session = Depends(get_db)):
    """到期提醒：已到期未续（全部）+ 未来 N 天内到期（默认 90 天）。

    分级口径（对齐原型「分级提醒规则」）：
      红 紧急 — 30 天内到期，或已到期未续，或欠缴超 3 年；
      橙 重要 — 60 天内到期，或欠缴 1–3 年；
      蓝 一般 — 90 天内到期。
    """
    from ..services.calc import to_date

    items = []
    for p in db.scalars(select(Parcel).where(Parcel.end_date.isnot(None))).all():
        end = to_date(p.end_date)
        if end is None:
            continue
        remain = (end - BASELINE).days
        if remain < 0:
            status = '已到期未续'
        elif remain <= days:
            status = '即将到期'
        else:
            continue
        years = len([x for x in (p.arrears_years or '').split('、') if x.strip()])
        if status == '已到期未续' or remain <= 30 or years > 3:
            level, level_name = 'red', '紧急'
        elif remain <= 60 or years >= 1:
            level, level_name = 'orange', '重要'
        else:
            level, level_name = 'blue', '一般'
        items.append({
            'parcel_key': p.parcel_key, 'lessee': p.contract_lessee,
            'owner': p.reg_owner, 'location': p.reg_location,
            'end_date': end.isoformat(), 'remain_days': remain,
            'status': status, 'level': level, 'level_name': level_name,
            'arrears': float(p.arrears or 0), 'arrears_years': p.arrears_years,
            'contract_status': p.contract_status,
        })
    # 待办直觉：按「距基准日远近」升序（越接近今天越靠前），已过期同样按超期天数从小到大
    items.sort(key=lambda x: (abs(x['remain_days']), -x['arrears']))
    summary = {
        'overdue': sum(1 for x in items if x['status'] == '已到期未续'),
        'within_30': sum(1 for x in items if 0 <= x['remain_days'] <= 30),
        'within_60': sum(1 for x in items if 30 < x['remain_days'] <= 60),
        'within_90': sum(1 for x in items if 60 < x['remain_days'] <= days),
        'total': len(items),
        'levels': {
            'red': sum(1 for x in items if x['level'] == 'red'),
            'orange': sum(1 for x in items if x['level'] == 'orange'),
            'blue': sum(1 for x in items if x['level'] == 'blue'),
        },
    }
    return {'base_date': BASELINE.isoformat(), 'window_days': days,
            'summary': summary, 'items': items}


@router.get('/expiry-calendar', response_model=list)
def expiry_calendar(year: int = 2026, db: Session = Depends(get_db)):
    """到期日历：未来一年内到期的合同（PRD 五）。"""
    from ..models import ContractDoc
    from datetime import date
    end = date(year, 12, 31)
    rows = db.scalars(select(ContractDoc)
                        .where(ContractDoc.end_date.isnot(None),
                                  ContractDoc.end_date <= end)
                        .order_by(ContractDoc.end_date).limit(200)).all()
    return [{'archive_no': c.id, 'lessee': c.lessee, 'end_date': c.end_date.isoformat()}
            for c in rows if c.end_date]


# ---------- 催缴台账（催缴记录） ----------

@router.get('/notices/{notice_id}/tracks', response_model=dict)
def notice_tracks(notice_id: int, db: Session = Depends(get_db)):
    """催缴台账：通知书 → 短信发送 → 回款登记的全部留痕。"""
    n = db.get(CollectionNotice, notice_id) or _404('通知书')
    p = db.get(Parcel, n.parcel_key)
    sms = db.scalars(select(SmsTask).where(SmsTask.notice_id == notice_id)
                     .order_by(SmsTask.id)).all()
    tracks = db.scalars(select(PaymentTrack).where(PaymentTrack.notice_id == notice_id)
                        .order_by(PaymentTrack.id)).all()
    recovered = sum(float(t.amount or 0) for t in tracks)
    arrears = float(n.arrears or 0)
    return {
        'notice': {'id': n.id, 'parcel_key': n.parcel_key, 'arrears': arrears,
                   'template_version': n.template_version, 'status': n.status,
                   'created_at': n.created_at.isoformat() if n.created_at else None},
        'parcel': ({'parcel_key': p.parcel_key, 'lessee': p.contract_lessee,
                    'owner': p.reg_owner, 'location': p.reg_location,
                    'phone': p.phone, 'arrears_years': p.arrears_years,
                    'arrears': float(p.arrears or 0)} if p else None),
        'timeline': ([{'type': 'notice', 'at': n.created_at.isoformat() if n.created_at else None,
                       'title': '生成催缴通知书',
                       'detail': f'欠缴 ¥{arrears:,.2f} · 模板 {n.template_version or "v1.0"}'}]
                     + [{'type': 'sms',
                         'at': (s.sent_at or n.created_at).isoformat() if (s.sent_at or n.created_at) else None,
                         'title': f'短信{s.status}',
                         'detail': f'接收号码 {s.phone or "—"}（演示占位，不真实下发）'}
                        for s in sms]
                     + [{'type': 'payment', 'at': (t.pay_date.isoformat() if t.pay_date else None),
                         'title': f'回款登记 ¥{float(t.amount or 0):,.2f}',
                         'detail': f'票据号 {t.receipt_no or "—"}'} for t in tracks]),
        'sms': [{'phone': s.phone, 'status': s.status,
                 'sent_at': s.sent_at.isoformat() if s.sent_at else None} for s in sms],
        'tracks': [{'id': t.id, 'amount': float(t.amount or 0),
                    'pay_date': t.pay_date.isoformat() if t.pay_date else None,
                    'receipt_no': t.receipt_no} for t in tracks],
        'recovered': recovered,
        'remain': max(0.0, arrears - recovered),
        'note': '回款登记仅写入催缴台账留痕；正式入账以缴费归集（payment_record/alloc）为准。',
    }


@router.post('/notices/{notice_id}/tracks', response_model=dict)
def add_track(notice_id: int, amount: float, pay_date: Optional[str] = None,
              receipt_no: Optional[str] = None, operator: str = '操作员',
              db: Session = Depends(get_db)):
    """登记一笔回款（催缴台账留痕；不改账，入账以缴费归集为准）。"""
    n = db.get(CollectionNotice, notice_id) or _404('通知书')
    if amount is None or amount <= 0:
        raise HTTPException(400, '回款金额须大于 0')
    d = None
    if pay_date:
        from ..services.calc import to_date
        d = to_date(pay_date)
    t = PaymentTrack(notice_id=n.id, amount=amount,
                     pay_date=d or date.today(), receipt_no=receipt_no or None)
    db.add(t)
    total = sum(float(x.amount or 0) for x in
                db.scalars(select(PaymentTrack).where(PaymentTrack.notice_id == n.id)).all())
    total += amount
    n.status = '已回款' if total >= float(n.arrears or 0) else '部分回款'
    db.add(AuditLog(actor=operator, action='dunning_payment_track',
                    target_type='notice', target_id=str(notice_id),
                    after_value=f'amount={amount}, receipt={receipt_no}'))
    db.commit()
    return {'ok': True, 'notice_id': notice_id, 'amount': amount,
            'recovered': total, 'status': n.status}


# ---------- 通知书 PDF ----------

@router.get('/notices/{notice_id}/pdf')
def notice_pdf(notice_id: int, db: Session = Depends(get_db)):
    """生成催缴通知书 PDF（A4 制式模板，内置中文 CID 字体，无需外部字体文件）。"""
    n = db.get(CollectionNotice, notice_id) or _404('通知书')
    p = db.get(Parcel, n.parcel_key)
    buf = _render_notice_pdf(n, p)
    fname = f'notice_{n.parcel_key}_{notice_id}.pdf'
    return StreamingResponse(
        buf, media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'})


def _cjk_font() -> str:
    """优先注册并内嵌系统中文字体（保证任意阅读器都能显示），退化到内置 CID 字体。"""
    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        ('MicrosoftYaHei', 'C:/Windows/Fonts/msyh.ttc', 0),
        ('MicrosoftYaHei', 'C:/Windows/Fonts/msyh.ttf', None),
        ('SimSun', 'C:/Windows/Fonts/simsun.ttc', 0),
        ('SimHei', 'C:/Windows/Fonts/simhei.ttf', None),
        ('NotoSansCJK', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 0),
        ('NotoSansCJK', '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf', None),
    ]
    for name, path, idx in candidates:
        if not Path(path).exists():
            continue
        try:
            if name in pdfmetrics.getRegisteredFontNames():
                return name
            if idx is None:
                pdfmetrics.registerFont(TTFont(name, path))
            else:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
            return name
        except Exception:              # noqa: BLE001  换下一个候选
            continue
    try:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        return 'STSong-Light'
    except Exception:                  # noqa: BLE001
        return 'Helvetica'


def _render_notice_pdf(n: CollectionNotice, p: Optional[Parcel]) -> io.BytesIO:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font = _cjk_font()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=25 * mm, rightMargin=25 * mm,
                            topMargin=25 * mm, bottomMargin=20 * mm)
    title = ParagraphStyle('t', fontName=font, fontSize=18, leading=26, alignment=1)
    sub = ParagraphStyle('s', fontName=font, fontSize=10.5, leading=16, alignment=1,
                         textColor='#666666')
    body = ParagraphStyle('b', fontName=font, fontSize=12, leading=24, firstLineIndent=24)
    flat = ParagraphStyle('f', fontName=font, fontSize=12, leading=24)
    right = ParagraphStyle('r', fontName=font, fontSize=12, leading=22, alignment=2)

    lessee = (p.contract_lessee or p.reg_owner or p.dunning_target) if p else '（催缴对象）'
    loc = (p.reg_location if p else '') or '（坐落）'
    area = float(p.reg_area or p.contract_area or 0) if p else 0
    years = (p.arrears_years or '') if p else ''
    arrears = float(n.arrears or 0)

    story = [
        Paragraph('国有土地租金催缴通知书', title),
        Paragraph(f'×土租催〔{BASELINE.year}〕第 {n.id:03d} 号', sub),
        Spacer(1, 10 * mm),
        Paragraph(f'{lessee}：', flat),
        Spacer(1, 3 * mm),
        Paragraph(
            f'你单位承租的位于 <b>{loc}</b> 的国有土地（宗地面积 {area:,.2f} ㎡，宗地键 {n.parcel_key}），'
            f'截至 {BASELINE.isoformat()} 累计欠缴土地租金 <b>¥{arrears:,.2f}</b>'
            f'（欠缴年度：{years or "见附页"}）。', body),
        Spacer(1, 3 * mm),
        Paragraph('请于收到本通知之日起 30 日内，按原缴费渠道补缴上述租金。'
                  '逾期未缴的，将依照合同约定及有关规定处理。', body),
        Spacer(1, 3 * mm),
        Paragraph('特此通知。', body),
        Spacer(1, 18 * mm),
        Paragraph('××县自然资源和规划局（模拟）', right),
        Paragraph(f'{BASELINE.year} 年 {BASELINE.month} 月 {BASELINE.day} 日', right),
        Spacer(1, 12 * mm),
        Paragraph(f'模板版本：{n.template_version or "v1.0"} · 生成时间 '
                  f'{datetime.now():%Y-%m-%d %H:%M} · 演示环境文书', sub),
    ]
    doc.build(story)
    buf.seek(0)
    return buf


def _404(msg: str):
    raise HTTPException(404, f'{msg}不存在')