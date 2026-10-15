from datanet.core.component_registry import resource_directory
"""Local model attribution for parser-produced blocks; exports candidate units."""
import argparse
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path
ROLES = ['statement', 'definition', 'proof', 'example', 'exercise', 'remark', 'discussion', 'heading', 'uncertain']
PROMPT_PATH = resource_directory(__file__) / 'prompts' / 'paragraph_attribution.md'
SCHEMA = {'type': 'object', 'properties': {'labels': {'type': 'array', 'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'role': {'type': 'string', 'enum': ROLES}, 'unit_id': {'type': 'string'}, 'needs_review': {'type': 'boolean'}}, 'required': ['id', 'role', 'unit_id', 'needs_review'], 'additionalProperties': False}}}, 'required': ['labels'], 'additionalProperties': False}
NUMBERED_OPENER = re.compile('^(Theorem|Proposition|Lemma|Corollary|Definition|Example|Remark|Exercise)\\s+\\d', re.I)

def read_blocks(path):
    blocks = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    seen = set()
    for block in blocks:
        if not isinstance(block.get('id'), str) or not block['id'] or block['id'] in seen:
            raise ValueError('Block IDs must be nonempty unique strings')
        if not isinstance(block.get('text'), str) or not block['text'].strip():
            raise ValueError('Each block requires nonempty text')
        seen.add(block['id'])
    if not blocks:
        raise ValueError('No blocks provided')
    return blocks

def validate_labels(labels, targets, previous):
    if not isinstance(labels, list) or len(labels) != len(targets):
        raise ValueError('Labels must cover every target block exactly once')
    known = {label['id']: label['unit_id'] for label in previous}
    for label, block in zip(labels, targets):
        if not isinstance(label, dict) or label.get('id') != block['id']:
            raise ValueError('Missing, duplicate or out-of-order block ID')
        if label.get('role') not in ROLES or type(label.get('needs_review')) is not bool:
            raise ValueError('Invalid role or review flag')
        unit = label.get('unit_id')
        if NUMBERED_OPENER.match(block['text']) and unit != block['id']:
            raise ValueError('Each explicit numbered opener must start its own unit at its own ID')
        if unit != block['id'] and (unit not in known or known[unit] != unit):
            raise ValueError('Unit ID must be an existing unit anchor, never a future block')
        if label['role'] == 'uncertain':
            label['needs_review'] = True
        known[block['id']] = unit
    return labels

class OllamaAnnotator:

    def __init__(self, model='qwen3.5:4b', base_url='http://127.0.0.1:11434', timeout=180):
        self.model, self.base_url, self.timeout = (model, base_url.rstrip('/'), timeout)
        self.prompt = PROMPT_PATH.read_text(encoding='utf-8')

    def label(self, targets, context, lookahead, previous, correction=None):
        visible = context + targets + lookahead
        ids = list(dict.fromkeys((block['id'] for block in visible)))
        aliases = {value: f'b{index}' for index, value in enumerate(ids)}
        inverse = {value: key for key, value in aliases.items()}

        def compact(block):
            item = {'id': aliases[block['id']], 'text': block['text'], 'page': block.get('metadata', {}).get('pdf_page')}
            item['section_kind'] = block.get('metadata', {}).get('section_kind', 'unknown')
            item['chapter'] = block.get('metadata', {}).get('chapter')
            item['section'] = block.get('metadata', {}).get('section')
            opener = NUMBERED_OPENER.match(block['text'])
            if opener:
                item['explicit_opener'] = opener.group(1).lower()
                item['required_unit_id'] = item['id']
            if 'label' in block:
                label = block['label']
                item['label'] = {**label, 'id': aliases[label['id']], 'unit_id': aliases.get(label['unit_id'], label['unit_id'])}
            return item
        schema = json.loads(json.dumps(SCHEMA))
        schema['properties']['labels']['minItems'] = len(targets)
        schema['properties']['labels']['maxItems'] = len(targets)
        properties = schema['properties']['labels']['items']['properties']
        properties['id']['enum'] = [aliases[block['id']] for block in targets]
        properties['unit_id']['enum'] = [aliases[block['id']] for block in context if block['label']['unit_id'] == block['id']] + [aliases[block['id']] for block in targets]
        payload = {'model': self.model, 'stream': False, 'think': False, 'format': schema, 'messages': [{'role': 'system', 'content': self.prompt}, {'role': 'user', 'content': json.dumps({'context': [compact(b) for b in context], 'targets': [compact(b) for b in targets], 'lookahead': [compact(b) for b in lookahead]}, ensure_ascii=False)}], 'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2200}, 'keep_alive': '5m'}
        if correction:
            payload['messages'].extend([{'role': 'assistant', 'content': getattr(self, 'last_response', '{}')}, {'role': 'user', 'content': 'That output failed validation: ' + correction + '. Re-read every target text. Correct all labels, preserving target IDs and order. The first block of each new unit must use its own ID. No future unit ID.'}])
        request = urllib.request.Request(self.base_url + '/api/chat', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.load(response)
        if result.get('done_reason') == 'length':
            raise ValueError('Model output was truncated')
        if result.get('prompt_eval_count', 0) >= 8000:
            raise ValueError('Input is too close to the context limit; split parser blocks or reduce batch size')
        self.last_response = result['message']['content']
        labels = json.loads(self.last_response)['labels']
        for label in labels:
            label['id'] = inverse[label['id']]
            label['unit_id'] = inverse[label['unit_id']]
        return (validate_labels(labels, targets, previous), {key: result.get(key) for key in ('prompt_eval_count', 'eval_count', 'total_duration')})

def annotate(blocks, annotator, output_dir, *, batch_size=3):
    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    signature = hashlib.sha256(json.dumps({'blocks': blocks, 'model': annotator.model, 'prompt': annotator.prompt, 'batch_size': batch_size, 'schema': SCHEMA, 'version': 6}, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    checkpoint = output_dir / 'annotation_checkpoint.json'
    labels, batches = ([], [])
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding='utf-8'))
        if state['signature'] != signature:
            raise ValueError('Output directory contains a different run; choose another directory')
        labels, batches = (state['labels'], state['batches'])
        validate_labels(labels, blocks[:len(labels)], [])
    started = time.monotonic()
    by_id = {block['id']: block for block in blocks}

    def group(block):
        return block.get('metadata', {}).get('context_group')

    def make_context(history, target):
        eligible = [label for label in history if group(by_id[label['id']]) == group(target)]
        recent = eligible[-4:]
        provable = [label for label in eligible if label['id'] == label['unit_id'] and label['role'] in ('statement', 'example', 'exercise')][-3:]
        wanted = {label['unit_id'] for label in recent + provable}
        selected = [label for label in eligible if label['id'] in wanted and label not in recent] + recent
        return [{**by_id[label['id']], 'label': label} for label in selected]
    while len(labels) < len(blocks):
        offset = len(labels)
        targets = []
        size = 0
        for block in blocks[offset:offset + batch_size]:
            if group(block) != group(blocks[offset]):
                break
            if targets and size + len(block['text']) > 6500:
                break
            targets.append(block)
            size += len(block['text'])
        context = make_context(labels, targets[0])
        lookahead = [b for b in blocks[offset + len(targets):offset + len(targets) + 2] if group(b) == group(targets[0])]
        error = None
        for attempt in range(2):
            try:
                fresh, stats = annotator.label(targets, context, lookahead, labels, correction=str(error) if error else None)
                error = None
                break
            except (ValueError, KeyError, TypeError) as exc:
                (output_dir / 'last_invalid_response.json').write_text(json.dumps({'target_ids': [block['id'] for block in targets], 'error': str(exc), 'raw': getattr(annotator, 'last_response', None)}, ensure_ascii=False, indent=2), encoding='utf-8')
                error = exc
        if error is not None and len(targets) > 1:
            fresh = []
            single_stats = []
            for index, target in enumerate(targets):
                history = labels + fresh
                single_context = make_context(history, target)
                following = [b for b in blocks[offset + index + 1:offset + index + 3] if group(b) == group(target)]
                single_error = None
                for attempt in range(2):
                    try:
                        labelled, measured = annotator.label([target], single_context, following, history, correction=str(single_error) if single_error else None)
                        single_error = None
                        break
                    except (ValueError, KeyError, TypeError) as exc:
                        single_error = exc
                if single_error:
                    raise ValueError(f"Invalid single-block output at {target['id']}: {single_error}")
                fresh.extend(labelled)
                single_stats.append(measured)
            stats = {'fallback_singletons': len(targets), 'single_stats': single_stats}
            error = None
        if error is not None:
            raise ValueError(f"Invalid model output at {targets[0]['id']}: {error}")
        labels.extend(fresh)
        batches.append({'first_id': targets[0]['id'], 'last_id': targets[-1]['id'], **stats})
        temporary = output_dir / 'annotation_checkpoint.tmp'
        temporary.write_text(json.dumps({'signature': signature, 'labels': labels, 'batches': batches}, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(checkpoint)
        print(f'标注 {len(labels)}/{len(blocks)} 块，{time.monotonic() - started:.1f} 秒', flush=True)
    role_by_opener = {'theorem': 'statement', 'proposition': 'statement', 'lemma': 'statement', 'corollary': 'statement', 'definition': 'definition', 'example': 'example', 'remark': 'remark', 'exercise': 'exercise'}
    for block, label in zip(blocks, labels):
        opener = NUMBERED_OPENER.match(block['text'])
        explicit_role = role_by_opener[opener.group(1).lower()] if opener else None
        if block.get('metadata', {}).get('section_kind') == 'exercises' and re.match('^\\*?\\d+\\.\\d+\\.', block['text']):
            explicit_role = 'exercise'
        if explicit_role:
            if label['role'] != explicit_role:
                label['model_role'] = label['role']
            label['role'] = explicit_role
            label['role_source'] = 'explicit_document_marker'
    anchor_roles = {label['id']: label['role'] for label in labels if label['unit_id'] == label['id']}
    for block_index, (block, label) in enumerate(zip(blocks, labels)):
        reasons = []
        if label['role'] == 'exercise' and label['unit_id'] == block['id'] and re.match('^\\([ivx]+\\)', block['text'], re.I):
            reasons.append('exercise_option_started_independent_unit')
        if label['role'] == 'statement' and label['unit_id'] == block['id'] and (not re.match('^(?:Theorem|Proposition|Lemma|Corollary|Claim)\\b', block['text'], re.I)):
            reasons.append('unmarked_text_started_statement_unit')
        if label['role'] == 'proof' and anchor_roles.get(label['unit_id']) not in ('statement', 'example', 'exercise'):
            reasons.append('proof_without_statement_anchor')
        if block.get('metadata', {}).get('needs_review'):
            reasons.append('parser_flagged_block')
        if label['role'] == 'proof' and (block_index == len(blocks) - 1 or group(block) != group(blocks[block_index + 1])):
            reasons.append('range_ends_inside_possible_proof')
        if reasons:
            label['needs_review'] = True
            label['review_reasons'] = reasons
    annotated = [{**block, 'label': label} for block, label in zip(blocks, labels)]
    (output_dir / 'annotated_blocks.jsonl').write_text(''.join((json.dumps(block, ensure_ascii=False) + '\n' for block in annotated)), encoding='utf-8')
    units = {}
    for block in annotated:
        label = block['label']
        unit = units.setdefault(label['unit_id'], {'unit_id': label['unit_id'], 'blocks': [], 'needs_review': False})
        unit['blocks'].append(block)
        unit['needs_review'] |= label['needs_review']
    contents = []
    for unit in units.values():
        first = unit['blocks'][0]
        metadata = {key: value for key, value in first.get('metadata', {}).items() if key not in ('source_blocks', 'context_group', 'bbox', 'block_label', 'layout_grouping')}
        metadata['pdf_pages'] = sorted({b['metadata']['pdf_page'] for b in unit['blocks'] if b.get('metadata', {}).get('pdf_page') is not None})
        metadata['kind'] = first['label']['role']
        metadata['needs_review'] = unit['needs_review']
        metadata['segments'] = [{'id': b['id'], 'role': b['label']['role'], 'metadata': b.get('metadata', {})} for b in unit['blocks']]
        heading = re.match('^(Theorem|Proposition|Lemma|Corollary|Definition|Example|Remark|Exercise)\\s+(\\d+(?:\\.\\d+)*[A-Z]?)', first['text'], re.I)
        if heading:
            metadata['reference_type'] = heading.group(1)
            metadata['reference_number'] = heading.group(2)
            metadata['reference'] = (str(metadata['chapter']) + ':' if metadata.get('chapter') else '') + heading.group(1) + ' ' + heading.group(2)
        if not heading and metadata['kind'] == 'exercise':
            exercise = re.match('^\\*{0,2}(\\d+(?:\\.\\d+)+[A-Z]?)\\.', first['text'])
            if exercise:
                metadata['reference_type'] = 'Exercise'
                metadata['reference_number'] = exercise.group(1)
                metadata['reference'] = (str(metadata['chapter']) + ':' if metadata.get('chapter') else '') + 'Exercise ' + exercise.group(1)
        contents.append({'id': first['id'], 'text': '\n\n'.join((b['text'] for b in unit['blocks'])), 'metadata': metadata})
    (output_dir / 'content_units.jsonl').write_text(''.join((json.dumps(item, ensure_ascii=False) + '\n' for item in contents)), encoding='utf-8')
    review = ['# 本地模型候选分块', '', '按模型归属整理；保留解析器原始文字和公式，不自动修复识别错误。未替换现有检索索引。', '']
    for number, unit in enumerate(units.values(), start=1):
        pages = sorted({block.get('metadata', {}).get('pdf_page') for block in unit['blocks'] if block.get('metadata', {}).get('pdf_page') is not None})
        review.extend([f"## 单元 {number} · PDF 页 {pages} · 待复核 {unit['needs_review']}", '', f"起点：`{unit['unit_id']}`", ''])
        for block in unit['blocks']:
            review.extend([f"类别：{block['label']['role']}；块：`{block['id']}`", '', '````text', block['text'], '````', ''])
    (output_dir / 'review.md').write_text('\n'.join(review), encoding='utf-8')
    report = {'model': annotator.model, 'signature': signature, 'blocks': len(blocks), 'units': len(units), 'review_blocks': sum((label['needs_review'] for label in labels)), 'coverage_ok': [label['id'] for label in labels] == [block['id'] for block in blocks], 'elapsed_this_run': round(time.monotonic() - started, 2), 'batches': batches, 'quality_note': 'Structural validation is not semantic accuracy. Original parser text is preserved; formulas are not repaired.'}
    (output_dir / 'annotation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report

def main():
    parser = argparse.ArgumentParser(description='本地模型标注文档块，输出候选内容单元，不修改检索索引')
    parser.add_argument('blocks', type=Path, help='JSONL: id, text, optional metadata')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--batch-size', type=int, default=3)
    args = parser.parse_args()
    result = annotate(read_blocks(args.blocks), OllamaAnnotator(args.model, args.base_url), args.output, batch_size=args.batch_size)
    print(json.dumps({key: value for key, value in result.items() if key != 'batches'}, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
