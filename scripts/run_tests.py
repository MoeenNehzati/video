"""Run repository integration tests and each skill's own tests."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    skills = ROOT / '.agents/skills'
    test_directories = [ROOT / 'tests', *sorted(skills.glob('*/tests'))]
    script_directories = sorted({path.parent for path in skills.rglob('*.py')
                                 if 'tests' not in path.relative_to(skills).parts})
    sys.path[:0] = list(map(str, [ROOT, *test_directories, *script_directories]))
    suite = unittest.TestSuite()
    for directory in test_directories:
        suite.addTests(unittest.TestLoader().discover(str(directory), top_level_dir=str(directory)))
    return not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
