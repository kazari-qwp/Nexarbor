"""Run optional local PaddleOCR in a separate process, saving page results."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='本地 OCR 单独阶段；完成后进程退出并释放模型')
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--first-page', type=int, required=True)
    parser.add_argument('--last-page', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--device', default='gpu:0')
    parser.add_argument('--reuse', type=Path, action='append', default=[], help='复用同一 PDF 已识别的页目录')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.cache = args.cache.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    for key, subdir in {'PADDLE_PDX_CACHE_HOME': 'paddle-cache', 'HF_HOME': 'hf-cache', 'MODELSCOPE_CACHE': 'modelscope-cache', 'MPLCONFIGDIR': 'mpl-cache', 'TEMP': 'tmp', 'TMP': 'tmp'}.items():
        path = args.cache / subdir
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    import pymupdf
    import torch
    from paddleocr import PaddleOCRVL
    with args.pdf.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    page_map = list(range(args.first_page, args.last_page + 1))
    with pymupdf.open(args.pdf) as source:
        if not 1 <= args.first_page <= args.last_page <= len(source):
            raise ValueError('Invalid page range')
        with pymupdf.open() as sample:
            sample.insert_pdf(source, from_page=args.first_page - 1, to_page=args.last_page - 1)
            sample.save(args.output / 'sample.pdf')
    manifest_path = args.output / 'source.json'
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding='utf-8'))
        if old['sha256'] != digest or old['page_map'] != page_map:
            raise ValueError('Output directory belongs to another PDF/range')
    pages_dir = args.output / 'pages'
    pages_dir.mkdir(exist_ok=True)
    for reused in args.reuse:
        manifest = json.loads((reused / 'source.json').read_text(encoding='utf-8'))
        if manifest['sha256'] != digest or manifest.get('parser') != 'PaddleOCR-VL-1.6':
            raise ValueError('Reuse requires the identical PDF and parser')
        for saved in (reused / 'pages').glob('*_res.json'):
            result = json.loads(saved.read_text(encoding='utf-8'))
            source_page = manifest['page_map'][result['page_index']]
            if source_page in page_map:
                result['reused_from'] = str(saved.resolve())
                result['parser_page_index'] = result['page_index']
                result['page_index'] = source_page - args.first_page
                (pages_dir / f'page_{source_page:04d}_res.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    (args.output / 'source.json').write_text(json.dumps({'source': str(args.pdf.resolve()), 'sha256': digest, 'page_map': page_map, 'parser': 'PaddleOCR-VL-1.6'}, ensure_ascii=False, indent=2), encoding='utf-8')
    started = time.monotonic()
    pipeline = PaddleOCRVL(pipeline_version='v1.6', engine='transformers', device=args.device, use_doc_orientation_classify=False, use_doc_unwarping=False, use_queues=False)
    ready = time.monotonic()
    cached = {}
    for path in pages_dir.glob('*_res.json'):
        result = json.loads(path.read_text(encoding='utf-8'))
        if result['page_index'] in cached:
            raise ValueError('Duplicate saved page results')
        cached[result['page_index']] = path
    count = len(cached)
    with pymupdf.open(args.pdf) as source:
        for index, page_number in enumerate(page_map):
            if index in cached:
                print(f'OCR cached {page_number}', flush=True)
                continue
            single_path = args.output / 'current_page.pdf'
            with pymupdf.open() as single:
                single.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
                single.save(single_path)
            results = list(pipeline.predict(str(single_path)))
            if len(results) != 1:
                raise ValueError('OCR requires exactly one page result')
            result = results[0]
            result.save_to_json(str(pages_dir / f'page_{page_number:04d}_res.json'))
            result.save_to_markdown(str(pages_dir / f'page_{page_number:04d}.md'))
            saved = pages_dir / f'page_{page_number:04d}_res.json'
            content = json.loads(saved.read_text(encoding='utf-8'))
            content['parser_page_index'] = content['page_index']
            content['page_index'] = index
            content['page_count'] = len(page_map)
            temporary = saved.with_suffix('.tmp')
            temporary.write_text(json.dumps(content, ensure_ascii=False), encoding='utf-8')
            temporary.replace(saved)
            count += 1
            print(f'OCR {count}/{len(page_map)} pages; PDF page {page_number}; {time.monotonic() - ready:.1f}s', flush=True)
    if count != len(page_map):
        raise ValueError('OCR returned incomplete page coverage')
    report = {'pages': count, 'initialization_seconds': ready - started, 'parse_seconds': time.monotonic() - ready}
    if args.device.startswith('gpu'):
        report.update(torch_peak_allocated_mib=torch.cuda.max_memory_allocated() / 2 ** 20, torch_peak_reserved_mib=torch.cuda.max_memory_reserved() / 2 ** 20)
    (args.output / 'runtime.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
if __name__ == '__main__':
    main()
