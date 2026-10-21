"""Actionable validation errors, without echoing complete schemas and input data."""
from jsonschema.exceptions import ValidationError,SchemaError

def error_message(error):
    if isinstance(error,(ValidationError,SchemaError)):
        path=getattr(error,'json_path','$')
        message=error.message
        if len(message)>1000:message='违反 '+str(error.validator)+' 约束；请按字段路径核对输入与声明。'
        return f'参数校验失败 {path}: {message}'
    return str(error) or type(error).__name__
