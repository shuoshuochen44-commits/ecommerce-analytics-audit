import pytest


def test_contract_preserves_exact_values_and_rejects_ambiguous_columns():
    from zhishu_inspection.source_types import TableData
    table=TableData('orders',('id','amount'),[('001','10.20')],{'kind':'csv'})
    assert table.rows[0]==('001','10.20')
    with pytest.raises(ValueError):
        TableData('orders',('id','ID'),[('1','2')],{})
    with pytest.raises(ValueError):
        TableData('orders',('id',),[('1','2')],{})


def test_contract_never_silently_truncates_input():
    from zhishu_inspection.source_types import TableData,MAX_ROWS
    with pytest.raises(ValueError,match='行数'):
        TableData('orders',('id',),[('1',)]*(MAX_ROWS+1),{})


def test_contract_enforces_expanded_bytes_not_only_source_file_size():
    from zhishu_inspection.source_types import TableData,MAX_BYTES
    with pytest.raises(ValueError,match='20 MB'):
        TableData('orders',('value',),[('字'*(MAX_BYTES//3+1),)],{})
    with pytest.raises(ValueError,match='展开'):
        TableData('orders',('value',),[({'nested':1},)],{})
