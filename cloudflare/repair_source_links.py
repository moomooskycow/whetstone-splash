"""Repair only owner-dispositioned links in immutable Jekyll Markdown SOURCE.

Kaylee, t_c60b5646: resolve the 71 unambiguous filenames to rendered HTML;
unlink the eight absent pages, retaining their text. Never edit generated HTML.
"""
import json
from pathlib import Path
import re
import urllib.parse

ROOT = Path.cwd()
CONFIG = json.loads(Path('cloudflare/site.json').read_text())
PREFIX = '/' + CONFIG['project_prefix'] + '/'
MISSING = {
    'secure-by-design-principles', 'input-validation-standards',
    'authentication-authorization-patterns', 'secrets-management-practices',
    'single-responsibility', 'dependency-injection',
    'architecture-decision-records', 'meaningful-naming',
}
# Only Markdown corresponding to the public emitted allowlist is in scope.
markdown = []
for line in Path('cloudflare/files.sha256').read_text().splitlines():
    _, asset = line.split('  ', 1)
    local = Path(asset).relative_to('_site').relative_to(CONFIG['project_prefix'])
    source = local.with_suffix('.md')
    if local.suffix == '.html' and source.is_file():
        markdown.append(source)
by_name = {}
for source in markdown:
    by_name.setdefault(source.name, []).append(source)
pattern = re.compile(r'(?<!!)\[([^\]\n]+)\]\(([^\s)]+)\)')
changes = []
planned = {}
for source in markdown:
    original = source.read_text()
    page = 'https://whetstone-splash-site.mistystep.io' + PREFIX + source.with_suffix('.html').as_posix()

    def repair(match):
        text, target = match.groups()
        url = urllib.parse.urlsplit(urllib.parse.urljoin(page, target))
        if url.netloc != 'whetstone-splash-site.mistystep.io' or not url.path.endswith('.md'):
            return match[0]
        if not url.path.startswith(PREFIX):
            raise RuntimeError('out-of-scope Markdown target: ' + target)
        local = Path(urllib.parse.unquote(url.path.removeprefix(PREFIX)))
        if local in markdown:
            return match[0]  # Jekyll's existing relative-links plugin handles it.
        candidates = by_name.get(local.name, [])
        if len(candidates) == 1:
            destination = PREFIX + candidates[0].with_suffix('.html').as_posix()
            destination = urllib.parse.urlunsplit(('', '', destination, url.query, url.fragment))
            replacement = '[' + text + '](' + destination + ')'
            action = 'rendered_html'
        elif not candidates and local.stem in MISSING:
            destination = None
            replacement = text
            action = 'unlink_keep_text'
        else:
            raise RuntimeError('unapproved absent/ambiguous target: ' + target)
        changes.append({'source': source.as_posix(), 'old_path': url.path,
                        'before': match[0], 'after': replacement,
                        'destination': destination, 'action': action})
        return replacement

    updated = pattern.sub(repair, original)
    if updated != original:
        planned[source] = updated
# Refuse source drift before writing anything; never silently expand the ruling.
rewrites = {c['old_path'] for c in changes if c['action'] == 'rendered_html'}
unlinks = {c['old_path'] for c in changes if c['action'] == 'unlink_keep_text'}
if len(rewrites) != 71 or len(unlinks) != 8:
    raise RuntimeError(f'source-link inventory drift: {len(rewrites)} rewrites, {len(unlinks)} unlinks')
for source, content in planned.items():
    source.write_text(content)
report = {'rewritten_unique_targets': len(rewrites), 'unlinked_unique_targets': len(unlinks),
          'changed_source_files': len(planned), 'occurrences': len(changes), 'changes': changes,
          'generated_bytes_edited': False}
Path('cloudflare-source-link-proof.json').write_text(json.dumps(report, indent=2) + '\n')
print('Source link repair:', len(rewrites), 'rendered targets;', len(unlinks),
      'absent targets unlinked;', len(changes), 'occurrences in', len(planned), 'Markdown files')
