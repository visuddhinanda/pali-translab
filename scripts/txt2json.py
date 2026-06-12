# -*- coding: utf-8 -*-
"""Convert plain-text translation file to JSON for write_chunk.py.

Input format (one block per paragraph):
    === 38
    sent1 translation
    sent2 translation
    === 39
    single sentence translation

Output: JSON file {para_str: [sent1, sent2, ...], ...}
"""
import json
import sys

def parse(path):
    result = {}
    current_para = None
    current_sents = []

    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('=== '):
                if current_para is not None:
                    result[current_para] = current_sents
                current_para = line[4:].strip()
                current_sents = []
            elif current_para is not None:
                current_sents.append(line)

    if current_para is not None:
        result[current_para] = current_sents

    # Remove trailing empty strings from each list
    for k in result:
        while result[k] and result[k][-1] == '':
            result[k].pop()

    return result

if __name__ == '__main__':
    infile = sys.argv[1]
    outfile = sys.argv[2]
    data = parse(infile)
    with open(outfile, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    total_sents = sum(len(v) for v in data.values())
    print(f'Converted {len(data)} paras ({total_sents} sentences) -> {outfile}')
