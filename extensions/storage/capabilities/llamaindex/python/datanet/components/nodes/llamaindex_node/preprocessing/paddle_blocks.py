"""Adapt saved PaddleOCR page JSON without loading an OCR or embedding model."""
import argparse
import hashlib
import json
import math
from pathlib import Path
MARGIN_LABELS = {'number', 'header', 'footer', 'header_image', 'footer_image', 'aside_text'}

def adapt_pages(page_results, *, source, page_map, order='parser', structure_blocks=()):
    """Preserve raw blocks; optional geometry ordering is only for single-column pages."""
    if order not in ('parser', 'single_column'):
        raise ValueError('order must be parser or single_column')
    source = Path(source).resolve()
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if not page_map or any((type(p) is not int or p < 1 for p in page_map)):
        raise ValueError('page_map requires positive original PDF pages')
    if page_map != sorted(set(page_map)):
        raise ValueError('page_map must be strictly increasing')
    pages = sorted(page_results, key=lambda d: d['page_index'])
    if [d['page_index'] for d in pages] != list(range(len(page_map))):
        raise ValueError('Each sample page requires exactly one JSON result and page mapping')
    structures = {}
    for block in structure_blocks:
        structures.setdefault(block['metadata']['pdf_page'], []).append(block['metadata'])
    kept, excluded, issues = ([], [], [])
    group = 0
    for index, data in enumerate(pages):
        page = page_map[index]
        if index and page != page_map[index - 1] + 1:
            group += 1
        width, height = (data['width'], data['height'])
        if not all((isinstance(v, (int, float)) and math.isfinite(v) and (v > 0) for v in (width, height))):
            raise ValueError('Invalid OCR image dimensions')
        raw = data['parsing_res_list']
        seen = set()
        for b in raw:
            if b['block_id'] in seen:
                raise ValueError('Duplicate OCR block ID')
            seen.add(b['block_id'])
            box = b['block_bbox']
            if len(box) != 4 or not all((isinstance(v, (int, float)) and math.isfinite(v) for v in box)) or box[0] > box[2] or (box[1] > box[3]):
                raise ValueError('Invalid OCR bounding box')
        active = [b for b in raw if b['block_label'] not in MARGIN_LABELS]
        if order == 'single_column':
            texts = [b for b in active if b['block_label'] == 'text' and len(b['block_content']) > 40]
            for n, a in enumerate(texts):
                for b in texts[n + 1:]:
                    x, y = (a['block_bbox'], b['block_bbox'])
                    overlap = min(x[3], y[3]) - max(x[1], y[1])
                    if overlap > 0.5 * min(x[3] - x[1], y[3] - y[1]) and (x[2] + width * 0.02 < y[0] or y[2] + width * 0.02 < x[0]):
                        raise ValueError('Multiple columns detected; use parser order or a layout-specific adapter')
            active.sort(key=lambda b: (b['block_bbox'][1], b['block_bbox'][0]))
        else:
            active.sort(key=lambda b: (b.get('block_order') is None, b.get('block_order') or 0, raw.index(b)))
        original_order = [b['block_id'] for b in raw if b['block_label'] not in MARGIN_LABELS]
        if original_order != [b['block_id'] for b in active]:
            issues.append({'pdf_page': page, 'issue': 'reading_order_changed', 'original': original_order, 'adapted': [b['block_id'] for b in active]})
        numbered = [b for b in raw if b['block_label'] == 'number' and b['block_content'].strip().isdigit() and (b['block_bbox'][1] > height * 0.85)]
        printed_page = int(numbered[-1]['block_content']) if numbered else None
        structural = structures.get(page, [])

        def make(b):
            metadata = {'source': str(source), 'document_id': f'pdf:{digest}', 'pdf_page': page, 'printed_page': printed_page, 'bbox': b['block_bbox'], 'image_width': width, 'image_height': height, 'extraction': 'PaddleOCR-VL', 'block_label': b['block_label'], 'context_group': f'{digest}/{group}', 'reading_order': order, 'formula_quality': 'unverified_ocr', 'source_blocks': [b]}
            if structural:
                nearest = min(structural, key=lambda m: abs(m['bbox'][1] / m['page_height'] - b['block_bbox'][1] / height))
                for key in ('chapter', 'chapter_title', 'section', 'section_title', 'section_kind', 'part', 'part_title'):
                    metadata[key] = nearest.get(key)
                metadata['structure_method'] = 'text_layer_sidecar_heuristic'
            return {'id': f"pdf:{digest}/paddle/page/{page}/block/{b['block_id']}", 'text': b['block_content'].strip(), 'metadata': metadata}
        for b in raw:
            if b['block_label'] in MARGIN_LABELS or not b['block_content'].strip():
                item = make(b)
                item['reason'] = 'margin_label' if b['block_label'] in MARGIN_LABELS else 'empty_ocr_content'
                excluded.append(item)
        formula_numbers = {}
        formulas = [b for b in active if b['block_label'] == 'display_formula']
        for b in active:
            if b['block_label'] == 'formula_number' and formulas:
                center = lambda item: (item['block_bbox'][1] + item['block_bbox'][3]) / 2
                nearest = min(formulas, key=lambda f: abs(center(f) - center(b)))
                if abs(center(nearest) - center(b)) < height * 0.025:
                    formula_numbers.setdefault(nearest['block_id'], []).append(b)
        attached_numbers = {b['block_id'] for ns in formula_numbers.values() for b in ns}
        for b in active:
            if b['block_id'] in attached_numbers:
                continue
            if not b['block_content'].strip():
                issues.append({'pdf_page': page, 'block_id': b['block_id'], 'issue': 'empty_ocr_content'})
                continue
            item = make(b)
            for number in formula_numbers.get(b['block_id'], []):
                item['text'] += '\n' + number['block_content'].strip()
                item['metadata']['source_blocks'].append(number)
            if b['block_label'] == 'display_formula' and kept:
                previous = kept[-1]
                metadata = previous['metadata']
                last_box = metadata['source_blocks'][-1]['block_bbox']
                gap = b['block_bbox'][1] - last_box[3]
                if metadata['pdf_page'] == page and metadata['block_label'] == 'text' and (0 <= gap <= height * 0.035):
                    previous['text'] += '\n\n' + item['text']
                    metadata['source_blocks'].extend(item['metadata']['source_blocks'])
                    metadata['layout_grouping'] = 'adjacent_formula_heuristic'
                    continue
            if b['block_label'] in ('image', 'chart'):
                item['metadata']['needs_review'] = True
            kept.append(item)
    return (kept, excluded, {'source': str(source), 'sha256': digest, 'page_map': page_map, 'blocks': len(kept), 'excluded_blocks': len(excluded), 'context_groups': group + 1, 'order': order, 'issues': issues, 'quality_note': 'Coordinates refer to OCR image pixels. Raw OCR blocks are retained; formulas are not corrected.'})

def main():
    parser = argparse.ArgumentParser(description='转换本地 PaddleOCR JSON；不加载模型')
    parser.add_argument('results', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--page-map', required=True, help='原始 PDF 页码，如 287,288,289')
    parser.add_argument('--order', choices=['parser', 'single_column'], default='parser')
    parser.add_argument('--structure', type=Path, help='可选的带章/节元数据的文本层块 JSONL')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = list(args.results.glob('*_res.json'))
    if not paths:
        raise ValueError('No saved PaddleOCR page JSON found')
    pages = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    structure = [json.loads(l) for l in args.structure.read_text(encoding='utf-8').splitlines() if l.strip()] if args.structure else []
    blocks, excluded, report = adapt_pages(pages, source=args.source, page_map=[int(p) for p in args.page_map.split(',')], order=args.order, structure_blocks=structure)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for path, rows in ((args.output, blocks), (args.output.with_suffix('.excluded.jsonl'), excluded)):
        path.write_text(''.join((json.dumps(b, ensure_ascii=False) + '\n' for b in rows)), encoding='utf-8')
    args.output.with_suffix('.report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'issues'}, ensure_ascii=False))
if __name__ == '__main__':
    main()
