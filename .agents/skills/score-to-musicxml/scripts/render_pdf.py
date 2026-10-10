"""Render PDF review pages with an explicitly configured Poppler command."""
import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, fresh_output, load_project, tool_command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--out', required=True, type=Path, help='New page-bundle directory')
    add_config_argument(parser)
    args = parser.parse_args(argv)
    config = load_project(args.config_root)
    source = data_path(config, args.pdf, must_exist=True)
    output = fresh_output(data_path(config, args.out, directory=True), inputs=[source])
    command = tool_command(config, 'pdftoppm')
    output.mkdir(parents=True)
    result = subprocess.run(command + ['-png', '-r', '150', str(source), str(output / 'page')],
                            capture_output=True)
    log = result.stdout + result.stderr
    for path, token in ((source, '{input:pdf}'), (output, '{output}')):
        log = log.replace(str(path).encode(), token.encode())
    (output / 'RENDER.log').write_bytes(log)
    if result.returncode:
        raise ValueError(f'PDF renderer failed with exit status {result.returncode}')
    pages = list(output.glob('page-*.png'))
    if not 1 <= len(pages) <= 256:
        raise ValueError('Renderer must produce 1–256 PNG pages')
    for page in pages:
        if page.is_symlink() or not page.is_file():
            raise ValueError('Renderer produced an unsafe page path')
        with page.open('rb') as stream:
            if stream.read(8) != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Renderer produced an invalid PNG page')


if __name__ == '__main__':
    main()
