import json

from datanet.core.module_protocol import ComponentResult


WRITE_OPERATIONS = {'put', 'remove', 'restore'}
READ_OPERATIONS = {'get', 'search', 'history'}


class BusinessError(Exception):
    """可安全返回给调用者的业务错误。"""


def _config(ctx, activation):
    for holder in (ctx, activation):
        for name in ('config', 'module_config'):
            value = getattr(holder, name, None)
            if value is not None:
                return value
    return {}


def _setting(config, key, default):
    value = config.get(key, default)
    return default if value is None else value


def _documents(ctx):
    documents = ctx.state.get('documents')
    if not isinstance(documents, dict):
        documents = {}
        ctx.state['documents'] = documents
    return documents


def _idempotency(ctx):
    records = ctx.state.get('idempotency')
    if not isinstance(records, dict):
        records = {}
        ctx.state['idempotency'] = records
    return records


def _requester(ctx):
    value = getattr(ctx, 'requester_id', None)
    if value is None:
        value = getattr(ctx, 'caller_id', None)
    return str(value) if value is not None else 'system'


def _snapshot(document):
    return {
        'revision': document['revision'],
        'title': document['title'],
        'text': document['text'],
        'tags': list(document['tags']),
        'deleted': bool(document['deleted']),
    }


def _append_history(document, history_limit):
    document['history'].append(_snapshot(document))
    if len(document['history']) > history_limit:
        document['history'] = document['history'][-history_limit:]


def _fingerprint(doc_id, title, text, tags):
    payload = {
        'id': doc_id,
        'title': title,
        'text': text,
        'tags': sorted(tags),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _public_document(document):
    return {
        'id': document['id'],
        'title': document['title'],
        'text': document['text'],
        'tags': list(document['tags']),
        'key': document.get('key'),
        'revision': document['revision'],
        'deleted': bool(document['deleted']),
    }


def _active_count(documents):
    return sum(1 for document in documents.values() if not document.get('deleted'))


def _handle_put(ctx, activation, config):
    parameters = activation.parameters or {}
    doc_id = parameters['id']
    title = parameters['title']
    text = parameters['text']
    tags = list(parameters['tags'])
    key = parameters.get('key')

    documents = _documents(ctx)
    records = _idempotency(ctx)
    requester = _requester(ctx)
    fingerprint = None
    record_key = None
    if key is not None:
        fingerprint = _fingerprint(doc_id, title, text, tags)
        record_key = requester + '\u241f' + key
        record = records.get(record_key)
        if record is not None:
            existing = documents.get(record.get('id'))
            if existing is None:
                records.pop(record_key, None)
            elif record.get('fingerprint') != fingerprint:
                raise BusinessError('同一请求者使用相同 key 提交了不同内容，已拒绝')
            else:
                return {
                    'id': existing['id'],
                    'revision': existing['revision'],
                    'deleted': bool(existing['deleted']),
                    'created': False,
                    'idempotent': True,
                }

    existing = documents.get(doc_id)
    max_entries = int(_setting(config, 'max_entries', 1000))
    history_limit = int(_setting(config, 'history_limit', 20))
    if existing is None:
        if _active_count(documents) >= max_entries:
            raise BusinessError('知识集合已达到最大文档数，无法新增')
        document = {
            'id': doc_id,
            'title': title,
            'text': text,
            'tags': tags,
            'key': key,
            'revision': 1,
            'deleted': False,
            'history': [],
        }
        _append_history(document, history_limit)
        documents[doc_id] = document
        created = True
    else:
        if existing.get('deleted') and _active_count(documents) >= max_entries:
            raise BusinessError('知识集合已达到最大文档数，无法恢复该文档')
        existing['title'] = title
        existing['text'] = text
        existing['tags'] = tags
        if key is not None:
            existing['key'] = key
        existing['revision'] = int(existing['revision']) + 1
        existing['deleted'] = False
        _append_history(existing, history_limit)
        document = existing
        created = False

    if record_key is not None:
        records[record_key] = {
            'requester': requester,
            'key': key,
            'id': doc_id,
            'fingerprint': fingerprint,
        }
    return {
        'id': document['id'],
        'revision': document['revision'],
        'deleted': bool(document['deleted']),
        'created': created,
        'idempotent': False,
    }


def _handle_get(ctx, activation):
    parameters = activation.parameters or {}
    document = _documents(ctx).get(parameters['id'])
    if document is None:
        raise BusinessError('文档不存在')
    return {'document': _public_document(document)}


def _handle_search(ctx, activation, config):
    parameters = activation.parameters or {}
    query = parameters.get('query', '') or ''
    tags = list(parameters.get('tags', []) or [])
    limit = int(parameters.get('limit', 10))
    query_lower = query.lower()
    matches = []
    for document in _documents(ctx).values():
        if document.get('deleted'):
            continue
        haystack = (str(document.get('title', '')) + '\n' + str(document.get('text', ''))).lower()
        if query_lower and query_lower not in haystack:
            continue
        document_tags = list(document.get('tags', []))
        if any(tag not in document_tags for tag in tags):
            continue
        text = str(document.get('text', ''))
        excerpt = text if len(text) <= 120 else text[:120] + '…'
        matches.append({
            'id': document['id'],
            'title': document['title'],
            'revision': document['revision'],
            'tags': document_tags,
            'excerpt': excerpt,
        })
    matches.sort(key=lambda item: item['id'])
    total = len(matches)
    return {
        'query': query,
        'tags': tags,
        'items': matches[:limit],
        'total': total,
    }


def _handle_remove(ctx, activation, config):
    parameters = activation.parameters or {}
    doc_id = parameters['id']
    documents = _documents(ctx)
    document = documents.get(doc_id)
    if document is None:
        raise BusinessError('文档不存在')
    if document.get('deleted'):
        return {'id': doc_id, 'revision': document['revision'], 'deleted': True}
    history_limit = int(_setting(config, 'history_limit', 20))
    document['revision'] = int(document['revision']) + 1
    document['deleted'] = True
    _append_history(document, history_limit)
    return {'id': doc_id, 'revision': document['revision'], 'deleted': True}


def _handle_history(ctx, activation):
    parameters = activation.parameters or {}
    document = _documents(ctx).get(parameters['id'])
    if document is None:
        raise BusinessError('文档不存在')
    items = [
        {
            'revision': int(item['revision']),
            'title': item['title'],
            'deleted': bool(item['deleted']),
        }
        for item in document.get('history', [])
    ]
    items.sort(key=lambda item: item['revision'])
    return {'id': document['id'], 'items': items, 'total': len(items)}


def _handle_restore(ctx, activation, config):
    parameters = activation.parameters or {}
    doc_id = parameters['id']
    revision = int(parameters['revision'])
    documents = _documents(ctx)
    document = documents.get(doc_id)
    if document is None:
        raise BusinessError('文档不存在')
    target = next(
        (item for item in document.get('history', []) if int(item['revision']) == revision),
        None,
    )
    if target is None:
        raise BusinessError('指定修订不在保留的历史中')
    max_entries = int(_setting(config, 'max_entries', 1000))
    if document.get('deleted') and _active_count(documents) >= max_entries:
        raise BusinessError('知识集合已达到最大文档数，无法恢复该文档')
    history_limit = int(_setting(config, 'history_limit', 20))
    document['title'] = target['title']
    document['text'] = target['text']
    document['tags'] = list(target['tags'])
    document['deleted'] = bool(target['deleted'])
    document['revision'] = int(document['revision']) + 1
    _append_history(document, history_limit)
    return {
        'id': document['id'],
        'revision': document['revision'],
        'restored_from': revision,
        'deleted': bool(document['deleted']),
    }


async def execute(ctx, activation):
    if activation.kind != 'access':
        return ComponentResult(status='error', error='不支持的请求类型')
    operation = activation.operation
    config = _config(ctx, activation)
    try:
        if operation in WRITE_OPERATIONS and bool(_setting(config, 'read_only', False)):
            raise BusinessError('知识集合处于只读模式，拒绝修改')
        if operation in WRITE_OPERATIONS:
            async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
                if operation == 'put':
                    data = _handle_put(ctx, activation, config)
                elif operation == 'remove':
                    data = _handle_remove(ctx, activation, config)
                else:
                    data = _handle_restore(ctx, activation, config)
        elif operation == 'get':
            data = _handle_get(ctx, activation)
        elif operation == 'search':
            data = _handle_search(ctx, activation, config)
        elif operation == 'history':
            data = _handle_history(ctx, activation)
        else:
            raise BusinessError('不支持的请求')
    except BusinessError as error:
        return ComponentResult(status='error', error=str(error))
    except Exception as error:
        return ComponentResult(status='error', error=str(error))
    return ComponentResult(data=data)
