"""Prevent orphan implementation code and stale imported-source provenance."""
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_all_implementation_has_skill_ownership_and_import_hashes_match(self):
        manifest = json.loads((REPO / 'docs/skill-imports.json').read_text())
        found = set()
        for directory, folders, names in os.walk(REPO):
            folders[:] = [name for name in folders if name not in
                          {'.git', 'env', '__pycache__', 'tests'} and
                          not (Path(directory) / name).is_symlink()]
            for name in names:
                path = Path(directory) / name
                if path.suffix in {'.py', '.java', '.html'}:
                    found.add(path.relative_to(REPO).as_posix())
        records = manifest['code_ownership']
        self.assertEqual(found, {record['path'] for record in records})
        self.assertEqual(len(records), len(found), 'Duplicate ownership entries')
        skills = {path.parent.name for path in (REPO / '.agents/skills').glob('*/SKILL.md')}
        for record in records:
            self.assertTrue(record['usage'])
            if record['path'].startswith('.agents/'):
                self.assertIn(record['owner'], skills)
        for record in manifest['source_files']:
            self.assertFalse(Path(record['source']).is_absolute())
            retained = ([record] if 'destination' in record else []) + record.get('extractions', [])
            for current in retained:
                with self.subTest(path=current['destination']):
                    content = (REPO / current['destination']).read_bytes()
                    self.assertEqual(hashlib.sha256(content).hexdigest(), current['current_sha256'])

    def test_local_markdown_links_and_toml_example(self):
        files = [REPO / 'AGENTS.md', REPO / 'README.md', REPO / '.claude/README.md']
        for folder in ('docs', 'requirements', 'tools', '.agents/skills'):
            files.extend((REPO / folder).rglob('*.md'))
        for path in files:
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
                target = target.split('#')[0]
                if target and '://' not in target and not target.startswith('mailto:'):
                    with self.subTest(document=str(path), target=target):
                        self.assertTrue((path.parent / target).exists())
        example = tomllib.loads((REPO / 'config.local.example.toml').read_text())
        self.assertTrue(example['paths']['data_root'])
        self.assertEqual({p.name for p in (REPO / 'bin').iterdir() if p.is_file()},
                         {'__init__.py', 'read_config.py', 'project_runtime.py'})


if __name__ == '__main__':
    unittest.main()
