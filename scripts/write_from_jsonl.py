# -*- coding: utf-8 -*-
"""Parse translation JSONL and write per-para output files.

Input JSONL format (one line per sentence):
{"book":209,"paragraph":3,"word_start":2,"word_end":2,"zh":"金刚慧复注","confidence":75}

The script fetches pali text from wikipali API and merges with translations.

Usage: python scripts/write_from_jsonl.py <input.jsonl> [--method pali-only]
"""
import json
import os
import subprocess
import sys
from collections import defaultdict

def main():
    infile = sys.argv[1]
    method = 'pali-only'
    if '--method' in sys.argv:
        method = sys.argv[sys.argv.index('--method') + 1]

    # Parse input translations
    trans = []
    with open(infile, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                trans.append(json.loads(line))

    # Group by paragraph
    by_para = defaultdict(list)
    for t in trans:
        by_para[t['paragraph']].append(t)

    book = trans[0]['book']
    paras = sorted(by_para.keys())

    # Fetch pali sentences for all paragraphs
    result = subprocess.run(
        ['python', '.claude/skills/translate/scripts/fetch_sentence.py',
         '--book', str(book),
         '--para', ','.join(str(p) for p in paras),
         '--channel', '00b577c0-13b9-11ee-a05a-b7307efd9ee6'],
        capture_output=True, text=True
    )

    pali_sents = [json.loads(l) for l in result.stdout.strip().split('\n') if l.strip()]
    pali_by_para = defaultdict(list)
    for s in pali_sents:
        pali_by_para[s['paragraph']].append(s)

    base = f'workspace/tipitaka/{method}/jsonl/{book}'
    written = 0

    for para in paras:
        para_dir = os.path.join(base, str(para))
        os.makedirs(para_dir, exist_ok=True)

        pali_list = sorted(pali_by_para[para], key=lambda x: x['word_start'])
        trans_list = sorted(by_para[para], key=lambda x: x['word_start'])

        outfile = os.path.join(para_dir, f'{para}_v1.jsonl')

        with open(outfile, 'w', encoding='utf-8') as f:
            for ps in pali_list:
                # Find matching translation by word_start
                zh = ''
                conf = 75
                for t in trans_list:
                    if t['word_start'] == ps['word_start']:
                        zh = t['zh']
                        conf = t.get('confidence', 75)
                        break
                record = {
                    'id': ps['id'],
                    'book': book,
                    'paragraph': para,
                    'word_start': ps['word_start'],
                    'word_end': ps['word_end'],
                    'pali': ps['html'],
                    'zh': zh,
                    'confidence': conf
                }
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        written += 1

    print(f'Written {written} para files to {base}/')


if __name__ == '__main__':
    main()
