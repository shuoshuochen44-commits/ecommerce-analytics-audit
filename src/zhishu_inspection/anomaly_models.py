"""Versioned, exact configuration for offline statistical anomaly rules."""

from dataclasses import dataclass, field, fields
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


@dataclass(frozen=True)
class AnomalyConfig:
    window_days: int = 28
    min_history: int = 14
    mad_multiplier: Decimal = Decimal('6')
    relative_floor: Decimal = Decimal('0.5')
    absolute_floor: Decimal = Decimal('1.00')

    def __post_init__(self) -> None:
        if type(self.window_days) is not int or not 3 <= self.window_days <= 366:
            raise ValueError('window_days 必须是 3 到 366 的整数')
        if type(self.min_history) is not int or not 3 <= self.min_history <= self.window_days:
            raise ValueError('min_history 必须是 3 到 window_days 的整数')
        for name, maximum, allow_zero in (
            ('mad_multiplier', Decimal('100'), False),
            ('relative_floor', Decimal('10'), True),
            ('absolute_floor', Decimal('999999999.99'), False),
        ):
            value = getattr(self, name)
            if type(value) not in (str, int, Decimal) or (isinstance(value, str) and len(value) > 64):
                raise ValueError(f'{name} 请使用精确十进制文本、整数或 Decimal')
            try:
                number = Decimal(value)
            except InvalidOperation:
                raise ValueError(f'{name} 必须是有限十进制数') from None
            if not number.is_finite() or number < 0 or (not allow_zero and number == 0) or number > maximum:
                raise ValueError(f'{name} 超出允许的有限非负范围')
            if number.as_tuple().exponent < -6:
                raise ValueError(f'{name} 最多支持六位小数，避免配置展开与数值精度超出预算')
            if name == 'absolute_floor' and number < Decimal('0.01'):
                raise ValueError('absolute_floor 至少为 0.01 货币单位')
            object.__setattr__(self, name, number)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'AnomalyConfig':
        if not isinstance(value, dict) or not set(value) <= {field.name for field in fields(cls)}:
            raise ValueError('配置必须为 JSON 对象，且只包含已支持的配置字段')
        return cls(**value)

    def to_dict(self) -> dict[str, int | str]:
        return {
            field.name: format(value, 'f') if isinstance(value, Decimal) else value
            for field in fields(self) for value in (getattr(self, field.name),)
        }


@dataclass(frozen=True)
class AnomalySuiteConfig:
    sales: AnomalyConfig = field(default_factory=AnomalyConfig)
    count_absolute_floor: int = 3
    min_order_history: int = 20
    order_mad_multiplier: Decimal = Decimal('8')
    order_relative_floor: Decimal = Decimal('5')

    def __post_init__(self) -> None:
        if not isinstance(self.sales, AnomalyConfig):
            raise ValueError('sales 必须是 AnomalyConfig')
        if type(self.count_absolute_floor) is not int or not 1 <= self.count_absolute_floor <= 1000000:
            raise ValueError('count_absolute_floor 必须为 1 到 1000000 的整数订单数')
        if type(self.min_order_history) is not int or not 3 <= self.min_order_history <= 20000:
            raise ValueError('min_order_history 必须为 3 到 20000 的整数')
        checked = AnomalyConfig(mad_multiplier=self.order_mad_multiplier,
                                relative_floor=self.order_relative_floor,
                                absolute_floor=self.sales.absolute_floor)
        object.__setattr__(self, 'order_mad_multiplier', checked.mad_multiplier)
        object.__setattr__(self, 'order_relative_floor', checked.relative_floor)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'AnomalySuiteConfig':
        base = {f.name for f in fields(AnomalyConfig)}
        extra = {f.name for f in fields(cls)} - {'sales'}
        if not isinstance(value, dict) or not set(value) <= base | extra:
            raise ValueError('完整检测配置包含不支持的字段')
        return cls(sales=AnomalyConfig.from_mapping({k: v for k, v in value.items() if k in base}),
                   **{k: v for k, v in value.items() if k in extra})

    def to_dict(self) -> dict[str, int | str]:
        return {**self.sales.to_dict(), 'count_absolute_floor': self.count_absolute_floor,
                'min_order_history': self.min_order_history,
                'order_mad_multiplier': format(self.order_mad_multiplier, 'f'),
                'order_relative_floor': format(self.order_relative_floor, 'f')}
