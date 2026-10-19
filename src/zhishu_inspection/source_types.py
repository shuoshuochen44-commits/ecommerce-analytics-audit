"""Shared, bounded tabular contract for independently implemented adapters."""

from dataclasses import dataclass

MAX_ROWS=20000
MAX_COLUMNS=200
MAX_BYTES=20*1024*1024


@dataclass
class TableData:
    name: str
    columns: tuple[str,...]
    rows: list[tuple]
    origin: dict
    # Actual physical file/worksheet lines, when the adapter can identify them.
    # Other tables retain virtual header + record ordinals for diagnostics.
    row_numbers: list[int] | None = None

    def __post_init__(self):
        if self.row_numbers is not None:
            if (len(self.row_numbers)!=len(self.rows)
                    or any(type(number) is not int or number<1 for number in self.row_numbers)
                    or any(left>=right for left,right in zip(self.row_numbers,self.row_numbers[1:]))):
                raise ValueError('来源行号必须与数据记录一一对应且严格递增')
        if not 0<len(self.columns)<=MAX_COLUMNS:
            raise ValueError('表格列数必须在 1 到 200 之间')
        if any(not isinstance(c,str) or not c.strip() or len(c)>200 or any(ord(x)<32 for x in c) for c in self.columns):
            raise ValueError('表头为空、过长或含控制字符')
        if len({c.casefold() for c in self.columns})!=len(self.columns):
            raise ValueError('表头重复，无法确定字段映射')
        if len(self.rows)>MAX_ROWS:
            raise ValueError('数据行数超过 20,000；请缩小范围，未截断分析数据')
        if any(len(row)!=len(self.columns) for row in self.rows):
            raise ValueError('表格记录列数与表头不一致')
        expanded=0
        for row in self.rows:
            expanded+=8*len(row)
            for value in row:
                if isinstance(value,(dict,list,tuple)):
                    raise ValueError('嵌套字段需先展开为平面表格')
                expanded+=len(value if isinstance(value,bytes) else ('' if value is None else str(value)).encode('utf-8'))
                if expanded>MAX_BYTES:
                    raise ValueError('数据展开后大小超过 20 MB，请缩小范围')
