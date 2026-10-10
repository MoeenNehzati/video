"""Managed browser orchestration stand-in; does not qualify a real browser."""
from pathlib import Path
import sys

folder=Path(__file__).resolve().parents[1]/'.agents/skills/song-arrangement-research/scripts/jjazzlab_experiments'
sys.path.insert(0,str(folder))
import check_delivery


def check_page(directory, config, browser_command, environment, *, out):
    assert (directory/'index.html').is_file()
    assert (directory/'catalogue.json').is_file()
    assert Path(browser_command[-1]).is_file()
    assert Path(environment['HOME']).is_dir()
    assert not Path(out).exists()
    return {'fixture_browser':True,'scope':'Browser not launched; orchestration fixture only','media_loads':[]}


if __name__=='__main__':
    check_delivery.check_page=check_page
    check_delivery.main()
