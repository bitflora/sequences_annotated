#!/usr/bin/env python3
"""
Migrate inline annotation markers to quote-based anchoring.

For each HTML file that has <span class="annotation-target"> markers:
  1. Extract the text content of each span → add "quote" field to the JSON.
  2. Strip the span and sup markers from the HTML, leaving bare text.

The JS will re-inject markers at runtime using the quote field.

Usage:
  python3 scripts/migrate_to_quote_anchors.py            # all annotated HTML files
  python3 scripts/migrate_to_quote_anchors.py Foo.html   # specific file(s)
"""

import glob
import html as html_module
import json
import os
import re
import sys

SEQUENCES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANNOTATIONS_DIR = os.path.join(SEQUENCES_DIR, 'annotations')

# Matches: <span class="annotation-target">CONTENT</span>
#          <sup class="annotation-ref"><a ...>[AN]</a></sup>
# Captures: group 1 = span inner HTML, group 2 = annotation id (integer)
MARKER_RE = re.compile(
    r'<span class=["\']annotation-target["\']>(.*?)</span>'
    r'<sup class=["\']annotation-ref["\']><a [^>]*>\[A(\d+)\]</a></sup>',
    re.DOTALL,
)


def text_content(inner_html):
    """Strip HTML tags and decode entities to get plain text."""
    stripped = re.sub(r'<[^>]+>', '', inner_html)
    return html_module.unescape(stripped)


def process_file(html_path):
    name = os.path.basename(html_path).replace('.html', '')
    json_path = os.path.join(ANNOTATIONS_DIR, name + '.json')

    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    matches = list(MARKER_RE.finditer(html))
    if not matches:
        print(f'  SKIP {name} — no annotation-target spans found')
        return False

    if not os.path.exists(json_path):
        print(f'  SKIP {name} — JSON not found at {json_path}')
        return False

    with open(json_path, encoding='utf-8') as f:
        annotations = json.load(f)

    ann_map = {a['id']: a for a in annotations}

    for m in matches:
        inner_html = m.group(1)
        ann_id = int(m.group(2))
        quote = text_content(inner_html)
        if ann_id in ann_map:
            ann_map[ann_id]['quote'] = quote
        else:
            print(f'  WARN {name} — annotation id {ann_id} not in JSON')

    # Reorder keys: id, side, quote, content
    updated = []
    for a in sorted(ann_map.values(), key=lambda x: x['id']):
        entry = {'id': a['id'], 'side': a.get('side', 'right')}
        if 'quote' in a:
            entry['quote'] = a['quote']
        entry['content'] = a.get('content', '')
        updated.append(entry)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
    print(f'  JSON {name}.json — {len(matches)} quote(s) added')

    # Strip markers: replace each match with the span's inner HTML only
    def replacer(m):
        return m.group(1)

    new_html = MARKER_RE.sub(replacer, html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f'  HTML {name}.html — markers removed')
    return True


def main():
    if len(sys.argv) > 1:
        files = [
            os.path.join(SEQUENCES_DIR, f) if not os.path.isabs(f) else f
            for f in sys.argv[1:]
        ]
    else:
        files = sorted(glob.glob(os.path.join(SEQUENCES_DIR, '*.html')))
        files = [f for f in files if '<span class=' in open(f).read()
                 and 'annotation-target' in open(f).read()]

    if not files:
        print('No files to process.')
        return

    print(f'Processing {len(files)} file(s)...')
    ok = 0
    for f in files:
        ok += process_file(f)
    print(f'\nDone. {ok}/{len(files)} files migrated.')


if __name__ == '__main__':
    main()
