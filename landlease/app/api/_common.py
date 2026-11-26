"""通用分页工具：与 AntD Table 分页协议对齐。"""
from __future__ import annotations

from typing import Any, Sequence, TypeVar

from fastapi import HTTPException, Query
from sqlalchemy import inspect as sa_inspect

T = TypeVar('T')


def orm_to_dict(obj: Any) -> dict:
    """SQLAlchemy 实例 → 纯 dict（Decimal/date 保持原值，由 FastAPI 编码）。

    FastAPI 0.141 + pydantic v2 在无 response_model 时不再自动 jsonable 化 ORM 对象，
    因此所有裸返回 ORM 的端点统一走此函数。
    """
    if obj is None:
        return {}
    mapper = sa_inspect(obj).mapper
    return {c.key: getattr(obj, c.key) for c in mapper.column_attrs}


def page_params(page: int = Query(1, ge=1),
                page_size: int = Query(20, ge=1, le=200)):
    """分页查询依赖：?page=1&page_size=20。"""
    return {'page': page, 'page_size': page_size}


def paginate(items: Sequence[T], total: int, params: dict) -> dict:
    """对已取回的列表做 slice 分页（小数据量场景，简单稳定）。"""
    page, ps = params['page'], params['page_size']
    if (page - 1) * ps > total:
        raise HTTPException(400, 'page 超出范围')
    return {'items': items[(page - 1) * ps: page * ps], 'total': total,
            'page': page, 'page_size': ps}


def apply_pagination(query, params: dict):
    """SQLAlchemy query → slice 分页（避免 SQLAlchemy 2.0 count 警告）。"""
    total = query.count()
    page, ps = params['page'], params['page_size']
    if (page - 1) * ps > total:
        raise HTTPException(400, 'page 超出范围')
    items = query.offset((page - 1) * ps).limit(ps).all()
    return {'items': items, 'total': total, 'page': page, 'page_size': ps}