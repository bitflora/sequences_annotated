#!/usr/bin/env python3
"""
Extract skeptic's annotations from HTML files into per-article JSON files.
Removes the bottom annotation block from each HTML file and adds the annotations.js
script tag. Annotation content goes into annotations/<ArticleName>.json.

Usage: python3 scripts/extract_annotations.py [file1.html file2.html ...]
If no files given, reads annotated files from git diff.
"""

import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser


SEQUENCES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANNOTATIONS_DIR = os.path.join(SEQUENCES_DIR, 'annotations')
SCRIPT_TAG = '<script src="wiki/pub/skins/readthesequences/annotations.js" defer></script>'


class AnnotationBlockParser(HTMLParser):
    """Extracts annotation entries from a skeptic-annotations block."""

    def __init__(self):
        super().__init__()
        self.annotations = []
        self._in_entry = False
        self._in_number_span = False
        self._depth = 0
        self._entry_id = None
        self._content_parts = []
        self._skip_span = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get('class', '').split()
        id_val = attrs_dict.get('id', '')

        if 'annotation-entry' in classes:
            self._in_entry = True
            self._depth = 0
            m = re.search(r'annotation-(\d+)', id_val)
            self._entry_id = int(m.group(1)) if m else None
            self._content_parts = []
            return

        if self._in_entry:
            self._depth += 1
            if 'annotation-number' in classes:
                self._skip_span = True
                return

            # Reconstruct the opening tag for content
            attr_str = ''
            for k, v in attrs:
                if v is not None:
                    attr_str += f' {k}="{v}"'
                else:
                    attr_str += f' {k}'
            self._content_parts.append(f'<{tag}{attr_str}>')

    def handle_endtag(self, tag):
        if self._in_entry and self._skip_span and tag == 'span':
            self._skip_span = False
            self._depth -= 1
            return

        if self._in_entry:
            if tag == 'div' and self._depth == 0:
                # End of annotation-entry div
                content = ''.join(self._content_parts).strip()
                if self._entry_id is not None:
                    side = 'left' if self._entry_id % 2 == 1 else 'right'
                    self.annotations.append({
                        'id': self._entry_id,
                        'side': side,
                        'content': content,
                    })
                self._in_entry = False
                self._entry_id = None
                self._content_parts = []
            else:
                self._depth -= 1
                if not self._skip_span:
                    self._content_parts.append(f'</{tag}>')

    def handle_data(self, data):
        if self._in_entry and not self._skip_span:
            self._content_parts.append(data)

    def handle_entityref(self, name):
        if self._in_entry and not self._skip_span:
            self._content_parts.append(f'&{name};')

    def handle_charref(self, name):
        if self._in_entry and not self._skip_span:
            self._content_parts.append(f'&#{name};')


def extract_annotations_block(html):
    """Return (block_text, start_idx, end_idx) of the skeptic-annotations div, or None."""
    # Match from <div class="skeptic-annotations"> to its closing </div>
    start = html.find('<div class="skeptic-annotations">')
    if start == -1:
        return None
    # Walk forward counting div depth to find the matching close
    depth = 0
    i = start
    while i < len(html):
        open_m = re.search(r'<div', html[i:])
        close_m = re.search(r'</div>', html[i:])
        if open_m and (not close_m or open_m.start() < close_m.start()):
            depth += 1
            i += open_m.start() + 4
        elif close_m:
            depth -= 1
            end = i + close_m.start() + len('</div>')
            if depth == 0:
                return html[start:end], start, end
            i += close_m.start() + len('</div>')
        else:
            break
    return None


def process_file(html_path):
    name = os.path.basename(html_path).replace('.html', '')
    json_path = os.path.join(ANNOTATIONS_DIR, name + '.json')

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    result = extract_annotations_block(html)
    if result is None:
        print(f'  SKIP {name} — no skeptic-annotations block found')
        return False

    block_text, start, end = result

    # Parse annotations out of the block
    parser = AnnotationBlockParser()
    parser.feed(block_text)
    annotations = sorted(parser.annotations, key=lambda a: a['id'])

    if not annotations:
        print(f'  SKIP {name} — block found but no annotation entries parsed')
        return False

    # Write JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(annotations, f, indent=2, ensure_ascii=False)
    print(f'  JSON {name}.json ({len(annotations)} annotations)')

    # Remove the block from HTML (also eat any preceding whitespace/newline)
    before = html[:start].rstrip('\n')
    after = html[end:]
    html = before + '\n' + after

    # Add script tag before </head> if not already present
    if 'annotations.js' not in html:
        html = html.replace('</head>', f'  {SCRIPT_TAG}\n</head>', 1)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  HTML {name}.html cleaned')
    return True


def get_annotated_files():
    result = subprocess.run(
        ['git', 'diff', '--name-only'],
        cwd=SEQUENCES_DIR,
        capture_output=True, text=True
    )
    files = [
        os.path.join(SEQUENCES_DIR, line.strip())
        for line in result.stdout.splitlines()
        if line.strip().endswith('.html')
    ]
    return files


def main():
    os.makedirs(ANNOTATIONS_DIR, exist_ok=True)

    if len(sys.argv) > 1:
        files = [os.path.abspath(f) for f in sys.argv[1:]]
    else:
        files = get_annotated_files()

    if not files:
        print('No annotated HTML files found.')
        return

    print(f'Processing {len(files)} file(s)...')
    ok = 0
    for f in sorted(files):
        ok += process_file(f)
    print(f'\nDone. {ok}/{len(files)} files processed.')


if __name__ == '__main__':
    main()
