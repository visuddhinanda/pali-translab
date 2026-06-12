"""Write a chunk's translations to per-para jsonl files.

Usage: python scripts/write_chunk.py <translations_json> <book_id> <para_start> <para_end>

translations_json format: {"para_num": ["sent1_zh", "sent2_zh", ...], ...}
Each list entry maps 1:1 to the sentences in that paragraph (sorted by word_start).
"""
import subprocess, json, os, sys
from collections import defaultdict

zh_file = sys.argv[1]
book = int(sys.argv[2])
para_start = int(sys.argv[3])
para_end = int(sys.argv[4])

with open(zh_file, encoding='utf-8') as f:
    translations = {int(k): v for k, v in json.load(f).items()}

result = subprocess.run(
    ['python', '.claude/skills/translate/scripts/fetch_sentence.py',
     '--book', str(book),
     '--para', ','.join(str(i) for i in range(para_start, para_end + 1)),
     '--channel', '00b577c0-13b9-11ee-a05a-b7307efd9ee6'],
    capture_output=True, text=True
)

sentences = [json.loads(line) for line in result.stdout.strip().split('\n') if line.strip()]
by_para = defaultdict(list)
for s in sentences:
    by_para[s['paragraph']].append(s)

base = f'/mnt/visuddhinanda/workspace/pali-translab/workspace/tipitaka/pali-only/jsonl/{book}'

written = 0
for para in sorted(by_para.keys()):
    zh_list = translations.get(para)
    if not zh_list:
        continue

    para_dir = os.path.join(base, str(para))
    os.makedirs(para_dir, exist_ok=True)

    sents = sorted(by_para[para], key=lambda x: x['word_start'])
    outfile = os.path.join(para_dir, f'{para}_v1.jsonl')

    if len(zh_list) != len(sents):
        print(f'WARNING para {para}: {len(zh_list)} translations vs {len(sents)} sentences')

    with open(outfile, 'w', encoding='utf-8') as f:
        for i, s in enumerate(sents):
            zh = zh_list[i] if i < len(zh_list) else ''
            record = {
                'id': s['id'],
                'book': book,
                'paragraph': para,
                'word_start': s['word_start'],
                'word_end': s['word_end'],
                'pali': s['html'],
                'zh': zh,
                'confidence': 75
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    written += 1

print(f'Written {written} para files to {base}/')
