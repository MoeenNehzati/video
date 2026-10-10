"""Synthetic instrument fixture for managed renderer checks, never musical acceptance."""
from pathlib import Path
import runpy
import sys

import numpy as np

folder=Path(__file__).resolve().parents[1]/'.agents/skills/song-arrangement-research/scripts/jjazzlab_experiments'
sys.path.insert(0,str(folder))
import sample_renderer


class SyntheticRenderer:
    def __init__(self, fonts, library):
        pass

    def render(self, path, room):
        amplitude=.06 if '_backing' in path.name else .1
        wave=amplitude*np.sin(2*np.pi*440*np.arange(96000)/48000)
        return np.column_stack((wave,wave)),{'routes':{'1':{'library':'generaluser'}},'fixture_synthesis':True}

    def close(self):
        pass


if __name__=='__main__':
    sample_renderer.CounterRenderer=SyntheticRenderer
    sys.argv[0]=str(folder/'render_child_versions.py')
    runpy.run_path(sys.argv[0],run_name='__main__')
