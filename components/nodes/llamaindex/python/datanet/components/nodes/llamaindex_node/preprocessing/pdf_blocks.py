"""Provisional digital-PDF layout blocks for annotation probes, not formula OCR."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

def extract_blocks(pdf_path, first_page, last_page):
    import pymupdf
    from .structure import StructureTracker
    pdf_path = Path(pdf_path).resolve()
    with pdf_path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    blocks = []
    tracker = StructureTracker()
    section_kind = 'body'
    with pymupdf.open(pdf_path) as document:
        if not 1 <= first_page <= last_page <= len(document):
            raise ValueError('Invalid PDF page range')
        for page_number in range(1, last_page + 1):
            page = document[page_number - 1]
            raw_blocks = page.get_text('blocks', sort=True)
            previous_chapter = tracker.chapter
            previous_section = (tracker.section, tracker.section_title)
            structure = tracker.update(page.get_text())
            if tracker.chapter == previous_chapter and previous_section[0] is not None:
                tracker.section, tracker.section_title = previous_section
                structure = {**structure, 'section': tracker.section, 'section_title': tracker.section_title}
            elif tracker.chapter != previous_chapter:
                section_kind = 'body'
            last_text = next((raw[4].strip() for raw in reversed(raw_blocks) if raw[6] == 0), '')
            printed_page = int(last_text) if re.fullmatch('\\d{1,4}', last_text) else None
            for number, raw in enumerate(raw_blocks):
                if raw[6] != 0 or not raw[4].strip():
                    continue
                text = raw[4].strip()
                body_section = re.fullmatch('([1-9]\\d?)\\s+([A-Z][A-Za-z ,?()\\x27/;:\\-]{2,90})', text)
                if body_section and raw[1] >= page.rect.height * 0.09:
                    tracker.section, tracker.section_title = (body_section.group(1), body_section.group(2))
                    structure = {**structure, 'section': tracker.section, 'section_title': tracker.section_title}
                    section_kind = 'body'
                if re.fullmatch('EXERCISES?', text, re.I):
                    section_kind = 'exercises'
                if page_number < first_page:
                    continue
                margin = raw[3] < page.rect.height * 0.09 or raw[1] > page.rect.height * 0.9
                blocks.append({'id': f'pdf:{digest}/page/{page_number}/block/{number}', 'text': text, 'metadata': {'source': str(pdf_path), 'pdf_page': page_number, 'bbox': list(raw[:4]), 'page_height': page.rect.height, 'printed_page': printed_page, **structure, 'section_kind': section_kind, 'extraction': 'pymupdf_text_blocks', 'margin_candidate': margin, 'formula_quality': 'unverified_text_layer'}})
    counts = Counter((block['text'] for block in blocks if block['metadata']['margin_candidate']))
    kept, excluded = ([], [])
    for block in blocks:
        metadata = block['metadata']
        running_title = re.fullmatch('(?:[IVXLCDM]+|\\d{1,2})\\s+[A-Za-z][A-Za-z ,\\-]+', block['text'])
        if metadata['margin_candidate'] and (re.fullmatch('\\d{1,4}', block['text']) or counts[block['text']] >= 2 or running_title):
            excluded.append(block)
        else:
            kept.append(block)
    grouped = []
    opener = re.compile('^(?:Theorem|Proposition|Lemma|Corollary|Definition|Example|Remark|Exercise|PROOF|Proof)\\b')
    for block in kept:
        current = block['metadata']
        if grouped:
            prev = grouped[-1]
            previous = prev['metadata']
            same_page = current['pdf_page'] == previous['pdf_page']
            inset = current['bbox'][0] - previous['bbox'][0]
            title_continuation = re.match('^(?:Theorem|Proposition|Lemma|Corollary)\\b', prev['text']) and inset > 8
            formula_fragment = inset > 60 and len(block['text']) < 250
            if same_page and (not opener.match(block['text'])) and (title_continuation or formula_fragment):
                previous.setdefault('source_blocks', []).append({'id': block['id'], 'text': block['text'], 'bbox': current['bbox']})
                prev['text'] += '\n' + block['text']
                continue
        block['metadata']['source_blocks'] = [{'id': block['id'], 'text': block['text'], 'bbox': current['bbox']}]
        grouped.append(block)
    return (grouped, excluded)

def main():
    parser = argparse.ArgumentParser(description='按版面提取数字 PDF 原始文本块；不执行公式 OCR')
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--first-page', type=int, required=True)
    parser.add_argument('--last-page', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    kept, excluded = extract_blocks(args.pdf, args.first_page, args.last_page)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for path, rows in ((args.output, kept), (args.output.with_suffix('.excluded.jsonl'), excluded)):
        path.write_text(''.join((json.dumps(row, ensure_ascii=False) + '\n' for row in rows)), encoding='utf-8')
    print(json.dumps({'blocks': len(kept), 'excluded_margin_blocks': len(excluded)}, ensure_ascii=False))
if __name__ == '__main__':
    main()
