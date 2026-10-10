"""Nishiren boundary fixtures; fake decoder/backend are not a singing-quality test."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tempfile

SKILLS = Path(__file__).resolve().parents[2]

SCRIPT = SKILLS / 'synthesize_vocal_with_diffsinger/scripts/synthesize_vocal_with_diffsinger.py'


def load_stage():
    spec = importlib.util.spec_from_file_location('managed_synthesis_fixture', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def message(name='onnx.ModelProto', children=(), external=()):
    return SimpleNamespace(DESCRIPTOR=SimpleNamespace(full_name=name),
                           external_data=[SimpleNamespace(key=k, value=v) for k, v in external],
                           ListFields=lambda: [(SimpleNamespace(message_type=True), list(children))] if children else [])


class SynthesisBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="synthesis å ")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.data = self.directory / "data"
        self.data.mkdir()
        self.stage = load_stage()
        self.bank = self.directory / 'bank'
        names = ['dsdur/linguistic.onnx', 'dsdur/dur.onnx', 'dsdur/phonemes.json', 'dsdur/languages.json',
                 'dsmain/acoustic.onnx', 'dsmain/phonemes.json', 'dsmain/languages.json',
                 'dsmain/Standard.emb', 'dsvocoder/vocoder.onnx']
        for name in names:
            path = self.bank / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic-model-fixture')
        self.model_names = names
        self.decoder = SimpleNamespace(load=lambda path, load_external_data: message())

    def test_ordinary_synthesis_receives_explicit_paths_and_rejects_clobber(self):
        source = self.data / 'events.json'
        source.write_text(json.dumps({'global': {'tempo_bpm': 120, 'meter': '4/4'},
            'vocal_events': [{'measure': 1, 'start_beat': 1, 'duration_beats': 1,
                              'pitch': 'C4', 'lyric': 'la', 'phonemes': ['l','aa']}]}))
        args = SimpleNamespace(vocal_events_json=source, out=self.data/'voice.wav',
            debug_out=self.data/'debug.json', log=self.data/'log.json',
            nishiren_root=self.bank, pronunciation_lexicon=None, nishiren_style='Standard',
            nishiren_lang='en', nishiren_vel=1.25, nishiren_gender=0.0,
            nishiren_steps=30, sample_rate=44100)
        def fake_backend(**values):
            for key in ('out_wav','debug_out','log_path'):
                values[key].write_bytes(b'fixture output, not real synthesis')
        with patch.dict(sys.modules, {'onnx': self.decoder}), patch.object(self.stage, '_run_nishiren_onnx', side_effect=fake_backend) as backend:
            self.stage.produce(args)
            backend.assert_called_once()
            with self.assertRaisesRegex(ValueError, 'exist|overwrite'):
                self.stage.produce(args)
            self.assertEqual(args.out.read_bytes(), b'fixture output, not real synthesis')

    def test_escaping_external_tensor_data_rejected_before_backend(self):
        tensor = message('onnx.TensorProto', external=[('location', '../../outside.bin')])
        decoder = SimpleNamespace(load=lambda path, load_external_data: message(children=[tensor]))
        with patch.dict(sys.modules, {'onnx': decoder}), self.assertRaisesRegex(ValueError, 'Unsafe|unsafe|Traversal|traversal'):
            self.stage.model_files(self.bank, 'Standard')
        self.assertFalse((self.directory / 'cache').exists())

    def test_external_tensor_files_are_in_exact_model_set(self):
        (self.bank / 'dsdur/weights.bin').write_bytes(b'weights')
        tensor = message('onnx.TensorProto', external=[('location', 'weights.bin')])
        def decode(path, load_external_data):
            self.assertFalse(load_external_data)
            return message(children=[tensor]) if Path(path).name == 'dur.onnx' else message()
        with patch.dict(sys.modules, {'onnx': SimpleNamespace(load=decode)}):
            files = self.stage.model_files(self.bank, 'Standard')
        self.assertEqual(set(files), {*self.model_names, 'dsdur/weights.bin'})

    def test_missing_decoder_and_models_fail_without_publication(self):
        before = list(self.data.iterdir())
        with patch.dict(sys.modules, {'onnx': None}), self.assertRaisesRegex(ValueError, 'requirements-vocals'):
            self.stage.model_files(self.bank, 'Standard')
        (self.bank / 'dsdur/dur.onnx').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing Nishiren resources'):
            self.stage.model_files(self.bank, 'Standard')
        self.assertEqual(list(self.data.iterdir()), before)
        self.assertFalse((self.directory / 'cache').exists())


if __name__ == '__main__':
    unittest.main()
