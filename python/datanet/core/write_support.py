"""节点共用的写入参数检查。"""

def validate_write(key, mode, *, allow_append=False):
    if not isinstance(key, str):
        raise TypeError('写入主键必须是字符串')
    if not key:
        raise ValueError('写入主键不能为空')
    modes = ('insert', 'update', 'upsert', 'append') if allow_append else ('insert', 'update', 'upsert')
    if mode not in modes:
        raise ValueError('写入模式必须为 ' + '、'.join(modes))

def validate_record(key, value, key_column, columns):
    if not isinstance(value, dict):
        raise TypeError('记录必须是字典')
    if any((not isinstance(column, str) or column not in columns for column in value)):
        raise ValueError('记录包含未知字段')
    if key_column in value and value[key_column] != key:
        raise ValueError('记录中的主键与写入主键不一致')
    return {**value, key_column: key}
