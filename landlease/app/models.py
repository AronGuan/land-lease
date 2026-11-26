"""ORM 模型：与 docs/schema.sql 一一对应。"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (JSON, BigInteger, Boolean, Date, DateTime, DECIMAL, ForeignKey,
                        Integer, String, Text, UniqueConstraint, Index, func)
from sqlalchemy.orm import Mapped, mapped_column

from .core.db import Base

AMT = DECIMAL(14, 2)


class ImportBatch(Base):
    __tablename__ = 'import_batch'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_no: Mapped[str] = mapped_column(String(64), unique=True)
    batch_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default='processing')
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    doc_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class FileObject(Base):
    __tablename__ = 'file_object'
    __table_args__ = (UniqueConstraint('batch_id', 'rel_path', name='uk_batch_path'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(BigInteger)
    archive_no: Mapped[str] = mapped_column(String(32), index=True)
    page_no: Mapped[int] = mapped_column(Integer, default=1)
    rel_path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime: Mapped[Optional[str]] = mapped_column(String(64))
    size: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContractDoc(Base):
    __tablename__ = 'contract_doc'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment='档案号')
    batch_id: Mapped[int] = mapped_column(BigInteger, index=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    doc_type: Mapped[Optional[str]] = mapped_column(String(16))
    contract_no: Mapped[Optional[str]] = mapped_column(String(128))
    orig_contract_no: Mapped[Optional[str]] = mapped_column(String(128))
    sign_date: Mapped[Optional[date]] = mapped_column(Date)
    lessor: Mapped[Optional[str]] = mapped_column(String(128))
    lessee: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    lessee_type: Mapped[Optional[str]] = mapped_column(String(16))
    id_no: Mapped[Optional[str]] = mapped_column(String(64))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    address: Mapped[Optional[str]] = mapped_column(String(255))
    parcel_no: Mapped[Optional[str]] = mapped_column(String(64))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    area: Mapped[Optional[float]] = mapped_column(DECIMAL(14, 2))
    land_usage: Mapped[Optional[str]] = mapped_column(String(32))
    land_level: Mapped[Optional[str]] = mapped_column(String(16))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    years: Mapped[Optional[int]] = mapped_column(Integer)
    rent_mode: Mapped[Optional[str]] = mapped_column(String(32))
    rate: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 4))
    rent_amount: Mapped[Optional[float]] = mapped_column(AMT)
    rent_amount_cn: Mapped[Optional[str]] = mapped_column(String(128))
    has_map: Mapped[Optional[int]] = mapped_column(Integer)
    altered_field: Mapped[Optional[str]] = mapped_column(String(64))
    altered_before: Mapped[Optional[str]] = mapped_column(String(255))
    altered_seal: Mapped[Optional[int]] = mapped_column(Integer)
    handwritten_note: Mapped[Optional[str]] = mapped_column(String(512))
    process_type: Mapped[str] = mapped_column(String(16), default='自动通过')
    status: Mapped[str] = mapped_column(String(16), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FieldExtraction(Base):
    __tablename__ = 'field_extraction'
    __table_args__ = (UniqueConstraint('doc_id', 'field_name', name='uk_doc_field'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(32), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    ai_value: Mapped[Optional[str]] = mapped_column(Text)
    final_value: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(DECIMAL(4, 3), index=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[Optional[dict]] = mapped_column(JSON)
    is_corrected: Mapped[int] = mapped_column(Integer, default=0)
    corrected_by: Mapped[Optional[str]] = mapped_column(String(64))
    corrected_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class FieldCorrection(Base):
    __tablename__ = 'field_correction'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    extraction_id: Mapped[int] = mapped_column(BigInteger, index=True)
    before_value: Mapped[Optional[str]] = mapped_column(Text)
    after_value: Mapped[Optional[str]] = mapped_column(Text)
    operator: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Parcel(Base):
    __tablename__ = 'parcel'
    parcel_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    unit_no: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    reg_location: Mapped[Optional[str]] = mapped_column(String(255))
    reg_area: Mapped[Optional[float]] = mapped_column(DECIMAL(14, 2))
    contract_area: Mapped[Optional[float]] = mapped_column(DECIMAL(14, 2))
    land_usage: Mapped[Optional[str]] = mapped_column(String(32))
    land_level: Mapped[Optional[str]] = mapped_column(String(16))
    rent_mode: Mapped[Optional[str]] = mapped_column(String(32))
    contract_status: Mapped[Optional[str]] = mapped_column(String(16))
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    contract_lessee: Mapped[Optional[str]] = mapped_column(String(128))
    reg_owner: Mapped[Optional[str]] = mapped_column(String(128))
    dunning_target: Mapped[Optional[str]] = mapped_column(String(128))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    due_2026: Mapped[Optional[float]] = mapped_column(AMT)
    total_due: Mapped[Optional[float]] = mapped_column(AMT)
    total_paid: Mapped[Optional[float]] = mapped_column(AMT)
    arrears: Mapped[Optional[float]] = mapped_column(AMT, index=True)
    arrears_years: Mapped[Optional[str]] = mapped_column(String(512))
    process_type: Mapped[str] = mapped_column(String(16), default='自动通过')
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ParcelDoc(Base):
    __tablename__ = 'parcel_doc'
    __table_args__ = (UniqueConstraint('parcel_key', 'archive_no', name='pk_parcel_doc'),)
    parcel_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    archive_no: Mapped[str] = mapped_column(String(32), primary_key=True)
    role: Mapped[Optional[str]] = mapped_column(String(16))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)


class RegistryParcel(Base):
    __tablename__ = 'registry_parcel'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_no: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    area: Mapped[Optional[float]] = mapped_column(DECIMAL(14, 2))
    owner: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    raw_row: Mapped[Optional[dict]] = mapped_column(JSON)


class RegistryStreetLevel(Base):
    __tablename__ = 'registry_street_level'
    street_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    land_level: Mapped[str] = mapped_column(String(16))


class RentStandard(Base):
    __tablename__ = 'rent_standard'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    land_usage: Mapped[str] = mapped_column(String(32), index=True)
    land_level: Mapped[str] = mapped_column(String(16), index=True)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[float] = mapped_column(DECIMAL(10, 4))


class ReductionRecord(Base):
    __tablename__ = 'reduction_record'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parcel_key: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    from_year: Mapped[Optional[int]] = mapped_column(Integer)
    to_year: Mapped[Optional[int]] = mapped_column(Integer)
    ratio: Mapped[float] = mapped_column(DECIMAL(5, 4))
    doc_no: Mapped[Optional[str]] = mapped_column(String(128))
    #: 原始行（含不动产单元号/坐落/承租人），供更换参考数据后重新归集
    raw_row: Mapped[Optional[dict]] = mapped_column(JSON)


class RentDue(Base):
    __tablename__ = 'rent_due'
    __table_args__ = (UniqueConstraint('parcel_key', 'year', name='uk_parcel_year'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parcel_key: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    months: Mapped[Optional[int]] = mapped_column(Integer)
    applied_rent: Mapped[Optional[float]] = mapped_column(AMT)
    due_amount: Mapped[float] = mapped_column(AMT, default=0)
    paid_amount: Mapped[float] = mapped_column(AMT, default=0)
    arrears: Mapped[float] = mapped_column(AMT, default=0, index=True)


class RentCalcTrace(Base):
    __tablename__ = 'rent_calc_trace'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parcel_key: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[int] = mapped_column(Integer)
    rule_version: Mapped[str] = mapped_column(String(32))
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    formula: Mapped[Optional[str]] = mapped_column(String(512))
    output: Mapped[Optional[float]] = mapped_column(AMT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentRecord(Base):
    __tablename__ = 'payment_record'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_no: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    parcel_key: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    pay_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    amount: Mapped[Optional[float]] = mapped_column(AMT)
    payer: Mapped[Optional[str]] = mapped_column(String(128))
    note_year: Mapped[Optional[int]] = mapped_column(Integer)
    is_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    raw_row: Mapped[Optional[dict]] = mapped_column(JSON)


class PaymentAlloc(Base):
    __tablename__ = 'payment_alloc'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(BigInteger, index=True)
    parcel_key: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[float] = mapped_column(AMT)
    alloc_rule: Mapped[Optional[str]] = mapped_column(String(64))


class Issue(Base):
    __tablename__ = 'issue'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(32), index=True)
    issue_type: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[Optional[str]] = mapped_column(String(1024))
    temp_algorithm: Mapped[Optional[str]] = mapped_column(String(512))
    diff_amount: Mapped[Optional[float]] = mapped_column(AMT)
    status: Mapped[str] = mapped_column(String(16), default='open')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionNotice(Base):
    __tablename__ = 'collection_notice'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parcel_key: Mapped[str] = mapped_column(String(32), index=True)
    arrears: Mapped[Optional[float]] = mapped_column(AMT)
    template_version: Mapped[Optional[str]] = mapped_column(String(32))
    file_path: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default='generated')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SmsTask(Base):
    __tablename__ = 'sms_task'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notice_id: Mapped[int] = mapped_column(BigInteger, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default='模拟发送')
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class PaymentTrack(Base):
    __tablename__ = 'payment_track'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notice_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[Optional[float]] = mapped_column(AMT)
    pay_date: Mapped[Optional[date]] = mapped_column(Date)
    receipt_no: Mapped[Optional[str]] = mapped_column(String(64))


class TaxPush(Base):
    __tablename__ = 'tax_push'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(16))
    year: Mapped[int] = mapped_column(Integer)
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    total_amount: Mapped[Optional[float]] = mapped_column(AMT)
    operator: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaxPushItem(Base):
    __tablename__ = 'tax_push_item'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    push_id: Mapped[int] = mapped_column(BigInteger, index=True)
    parcel_key: Mapped[Optional[str]] = mapped_column(String(32))
    unit_no: Mapped[Optional[str]] = mapped_column(String(64))
    lessee: Mapped[Optional[str]] = mapped_column(String(128))
    id_no: Mapped[Optional[str]] = mapped_column(String(64))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    due_amount: Mapped[Optional[float]] = mapped_column(AMT)
    paid_amount: Mapped[Optional[float]] = mapped_column(AMT)
    arrears: Mapped[Optional[float]] = mapped_column(AMT)


class SysUser(Base):
    __tablename__ = 'sys_user'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[Optional[str]] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default='enabled')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = 'audit_log'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(64))
    target_id: Mapped[Optional[str]] = mapped_column(String(64))
    before_value: Mapped[Optional[str]] = mapped_column(Text)
    after_value: Mapped[Optional[str]] = mapped_column(Text)
    context: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class ModelConfig(Base):
    __tablename__ = 'model_config'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    endpoint: Mapped[Optional[str]] = mapped_column(String(255))
    model_id: Mapped[Optional[str]] = mapped_column(String(128))
    is_active: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[Optional[dict]] = mapped_column(JSON)


class ModelCallLog(Base):
    __tablename__ = 'model_call_log'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(128))
    target: Mapped[Optional[str]] = mapped_column(String(128))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tokens: Mapped[Optional[int]] = mapped_column(Integer)
    avg_confidence: Mapped[Optional[float]] = mapped_column(DECIMAL(4, 3))
    result: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ConfigItem(Base):
    __tablename__ = 'config_item'
    config_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_value: Mapped[Optional[str]] = mapped_column(Text)
    remark: Mapped[Optional[str]] = mapped_column(String(255))


class BackupRecord(Base):
    __tablename__ = 'backup_record'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backup_type: Mapped[Optional[str]] = mapped_column(String(16))
    file_path: Mapped[Optional[str]] = mapped_column(String(512))
    sha256_status: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
