"""Pydantic schemas（与 contract_doc / parcel / 等表对齐；服务端分页响应）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar('T')


class Page(BaseModel, Generic[T]):
    """服务端分页响应（参考 AntD Table 「current/pageSize/total」语义）。"""
    items: List[T]
    total: int
    page: int = 1
    page_size: int = 20


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------- 批次 ----------

class BatchCreate(BaseModel):
    batch_type: str = '新签'   # 新签 / 续期 / 变更 / 现场补档


class BatchOut(OrmModel):
    id: int
    batch_no: str
    batch_type: str
    status: str
    file_count: int
    doc_count: int
    created_by: Optional[str] = None
    created_at: datetime


# ---------- 合同档案 ----------

class ContractDocOut(OrmModel):
    id: str
    batch_id: int
    doc_type: Optional[str]
    contract_no: Optional[str]
    sign_date: Optional[date]
    lessor: Optional[str]
    lessee: Optional[str]
    id_no: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    area: Optional[Decimal]
    land_usage: Optional[str]
    land_level: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    years: Optional[int]
    rent_mode: Optional[str]
    rent_amount: Optional[Decimal]
    altered_field: Optional[str] = None
    altered_seal: Optional[int] = None
    has_map: Optional[int] = None
    process_type: str
    status: str
    #: 关键字段最低置信度（列表接口附加，用于判断是否够「自动通过」阈值）
    min_confidence: Optional[float] = None


class FieldExtractionOut(OrmModel):
    id: int
    field_name: str
    ai_value: Optional[str]
    final_value: Optional[str]
    confidence: Optional[Decimal]
    source: str
    reason: Optional[dict]
    level: str = 'L3'        # L1/L2/L3，前端识别黄/红条用


class FieldCorrectionIn(BaseModel):
    field_name: str
    after_value: Optional[str] = None
    before_value: Optional[str] = None
    operator: str = '操作员'


class BatchConfirmIn(BaseModel):
    """批量确认（自动通过 + 强制复核）。"""
    archive_nos: list[str]
    operator: str = '操作员'
    sample_inspect_rate: float = Field(0.0, ge=0, le=1, description='抽检比例，0~1')


class BatchConfirmIn(BaseModel):
    """批量确认（自动通过 + 强制复核）。"""
    archive_nos: List[str]
    operator: str = '操作员'
    sample_inspect_rate: float = Field(0.0, ge=0, le=1, description='抽检比例，0~1')


class ParcelOut(OrmModel):
    parcel_key: str
    unit_no: Optional[str]
    reg_location: Optional[str]
    reg_area: Optional[Decimal]
    contract_area: Optional[Decimal]
    land_usage: Optional[str]
    land_level: Optional[str]
    rent_mode: Optional[str]
    contract_status: Optional[str]
    end_date: Optional[date]
    contract_lessee: Optional[str]
    reg_owner: Optional[str]
    dunning_target: Optional[str]
    phone: Optional[str]
    due_2026: Optional[Decimal]
    total_due: Optional[Decimal]
    total_paid: Optional[Decimal]
    arrears: Optional[Decimal]
    arrears_years: Optional[str]
    process_type: str
    updated_at: datetime
    # 列表页附加列（由接口计算填充，非表字段）
    archives: Optional[str] = None           # 档案号列表（一宗多合同，分号分隔）
    dunning_status: Optional[str] = None     # 未催缴 / 已催缴 / 部分回款 / 已回款
    dunning_notice_id: Optional[int] = None  # 最新通知书 id
    dunning_at: Optional[str] = None         # 最近催缴时间


class RentDueOut(OrmModel):
    parcel_key: str
    year: int
    months: Optional[int]
    applied_rent: Optional[Decimal]
    due: Decimal = Field(alias='due_amount')
    paid: Decimal = Field(alias='paid_amount')
    arrears: Decimal


class IssueOut(OrmModel):
    id: int
    target: str
    issue_type: str
    description: Optional[str]
    temp_algorithm: Optional[str]
    diff_amount: Optional[Decimal]
    status: str
    created_at: datetime


class NoticeOut(OrmModel):
    id: int
    parcel_key: str
    arrears: Optional[Decimal]
    template_version: Optional[str]
    status: str
    created_at: datetime


class TaxPushOut(OrmModel):
    id: int
    period: str
    year: int
    row_count: Optional[int]
    total_amount: Optional[Decimal]
    operator: Optional[str]
    created_at: datetime


class AuditLogOut(OrmModel):
    id: int
    actor: str
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    before_value: Optional[str]
    after_value: Optional[str]
    created_at: datetime


# ---------- 模型通道 ----------

class ModelChannelUpdate(BaseModel):
    """通道配置修改：开源通道换托管商 / 换 vLLM 地址时用。

    凭据只填「环境变量名」，明文 key 走 .env，不进数据库、不进请求体。
    """
    name: Optional[str] = None
    endpoint: Optional[str] = None
    model_id: Optional[str] = None
    api_key_env: Optional[str] = None