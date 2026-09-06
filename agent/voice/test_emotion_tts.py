# -*- coding: utf-8 -*-
"""Unit and Integration tests for the Burmese Emotion & Prosody TTS pipeline."""

import os
import sys
import unittest
from unittest.mock import patch
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, AGENT)

import bus
from emotion import EmotionAnalyzer, ProsodyInjector, EmotionType, PROSODY_MAP
from voice import Brain, Mouth, OpenMic, expression_for_text


class TestEmotionPipeline(unittest.TestCase):

    def test_avatar_expression_tracks_spoken_performance(self):
        self.assertEqual(expression_for_text("ဟုတ်ကဲ့ [laugh]"), "amused")
        self.assertEqual(expression_for_text("အို [gasp]"), "surprised")
        self.assertEqual(expression_for_text("ကောင်းပါတယ် [sigh]"), "tired")
        self.assertEqual(expression_for_text("အဆင်ပြေရဲ့လား။"), "curious")
        self.assertEqual(expression_for_text("ပြီးပါပြီ။"), "neutral")

    def test_audio_classifier_produces_multiple_mouth_shapes(self):
        quiet = np.zeros(1024, dtype=np.float32)
        noisy = np.tile(np.array([-0.5, 0.5], dtype=np.float32), 512)
        low_tone = np.sin(np.linspace(0, 4 * np.pi, 1024)).astype(np.float32)

        self.assertEqual(Mouth._mouth_shape(quiet, 0.0), "closed")
        self.assertEqual(Mouth._mouth_shape(noisy, 0.8), "consonant")
        self.assertEqual(Mouth._mouth_shape(low_tone, 0.8), "oh")

    def test_playback_reuses_output_stream_between_sentences(self):
        class FakeStream:
            def start(self): pass
            def stop(self): pass
            def close(self): pass
            def write(self, block): pass

        mouth = Mouth.__new__(Mouth)
        mouth.stop_flag = __import__("threading").Event()
        mouth._output_stream = None
        mouth._output_rate = None
        audio = np.ones(256, dtype=np.float32) * 0.1
        with patch("sounddevice.OutputStream", return_value=FakeStream()) as output:
            mouth._play(audio, 24000)
            mouth._play(audio, 24000)
        self.assertEqual(output.call_count, 1)

    def test_emotion_detection(self):
        # 1. Questioning
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("မင်း နေကောင်းလား?"),
            EmotionType.QUESTIONING
        )
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("ဒါ ဘယ်လို လုပ်ရမှာလဲ"),
            EmotionType.QUESTIONING
        )
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("အဆင်ပြေရဲ့လား"),
            EmotionType.QUESTIONING
        )

        # 2. Excited / Happy
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("မင်္ဂလာပါဗျာ! အရမ်းပျော်ပါတယ်!"),
            EmotionType.EXCITED
        )
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("ဒီနေ့ သတင်းကောင်းတစ်ခု ရှိတယ်"),
            EmotionType.EXCITED
        )

        # 3. Serious / Sad / Warning
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("သတိထားပါ… ဒါ အရမ်းအရေးကြီးတယ်"),
            EmotionType.SERIOUS
        )
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("စိတ်မကောင်းစရာ တစ်ခု ဖြစ်သွားတယ်"),
            EmotionType.SERIOUS
        )

        # 4. Calm / Narrative
        self.assertEqual(
            EmotionAnalyzer.detect_clause_emotion("ဒီနေ့ စာရင်းဇယားတွေကို ကြည့်နေပါတယ်။"),
            EmotionType.CALM
        )

    def test_prosody_calculation(self):
        # Base pitch +0Hz, base rate -2%
        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.EXCITED, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "+2Hz")
        self.assertEqual(r, "+2%")
        self.assertEqual(b, 250)

        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.SERIOUS, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "-2Hz")
        self.assertEqual(r, "-6%")
        self.assertEqual(b, 650)

        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.CALM, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "+0Hz")
        self.assertEqual(r, "-2%")
        self.assertEqual(b, 400)

        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.QUESTIONING, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "+2Hz")
        self.assertEqual(r, "-2%")
        self.assertEqual(b, 350)

    def test_text_segmentation_and_chunking(self):
        text = "မင်္ဂလာပါဗျာ! အခုပဲ သတင်းကောင်း ရလာတယ်။ ဒါပေမယ့် သတိထားရမယ့် အချက်လည်း ရှိတယ်နော်။ ဒီအကြောင်း နားလည်ရဲ့လား?"
        chunks = ProsodyInjector.inject_prosody_chunks(text, base_pitch="+2Hz", base_rate="+0%")
        self.assertGreaterEqual(len(chunks), 3)

        emotions = [c.emotion for c in chunks]
        self.assertIn(EmotionType.EXCITED, emotions)
        self.assertIn(EmotionType.SERIOUS, emotions)
        self.assertIn(EmotionType.QUESTIONING, emotions)

    def test_plain_burmese_is_synthesized_as_one_continuous_utterance(self):
        """Punctuation should shape cadence without resetting the voice."""
        mouth = Mouth.__new__(Mouth)
        mouth.stop_flag = __import__("threading").Event()
        calls = []

        def fake_synth(text, pitch=None, rate=None):
            calls.append((text, pitch, rate))
            return np.ones(240, dtype=np.float32), 24000

        mouth._synth_burmese_edge_bytes = fake_synth
        got = mouth._synth_burmese_emotional(
            "မင်္ဂလာပါ၊ နေကောင်းလား။ ဒီနေ့ အဆင်ပြေပါတယ်။")

        self.assertIsNotNone(got)
        self.assertEqual(len(calls), 1)
        self.assertIn("၊", calls[0][0])
        self.assertIn("။", calls[0][0])

    def test_stream_units_do_not_split_at_burmese_commas(self):
        units = Mouth._stream_units("မင်္ဂလာပါ၊ နေကောင်းလား။ အဆင်ပြေပါတယ်။")
        self.assertEqual(units, ["မင်္ဂလာပါ၊ နေကောင်းလား။ အဆင်ပြေပါတယ်။"])

    def test_stream_batches_starts_first_sentence_immediately(self):
        batches = list(Mouth._stream_batches([
            "မင်္ဂလာပါ၊ နေကောင်းလား။",
            "ဒီနေ့ အဆင်ပြေပါတယ်။",
            "ဘာကူညီပေးရမလဲ။",
        ]))
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0], "မင်္ဂလာပါ၊ နေကောင်းလား။")
        self.assertIn("ဒီနေ့ အဆင်ပြေပါတယ်။ ဘာ", batches[1])

    def test_existing_mic_config_gets_fast_silence_cap(self):
        cfg = {"mic": {"open_silence_seconds": 1.0, "fast_response": True}}
        with patch("sounddevice.InputStream"):
            mic = OpenMic(cfg, __import__("queue").Queue())
        self.assertEqual(mic.hang_s, 0.6)

    def test_gemini_brain_streams_sentences_and_hides_key(self):
        events = [
            {"candidates": [{"content": {"parts": [{"text": "ဟုတ်ကဲ့ခင်ဗျာ။"}]}}]},
            {"candidates": [{"content": {"parts": [{"text": " အခုပဲလုပ်ပေးမယ်။"}]}}]},
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                return iter([
                    ("data: " + __import__("json").dumps(e, ensure_ascii=False) + "\n").encode()
                    for e in events
                ])

        brain = Brain({"engine": "gemini", "gemini": {
            "model": "gemini-3.1-flash-lite", "max_tokens": 80,
        }})
        live = {"tts": {"gemini_api_key": "secret-key"}, "language": {}, "faces": []}
        with patch.object(bus, "config", return_value=live), \
                patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            pieces = list(brain.stream("မြန်မြန်ဖြေပေးပါ", lang="my"))

        self.assertEqual([first for _, first in pieces], [True, False])
        request = urlopen.call_args.args[0]
        self.assertNotIn("secret-key", request.full_url)
        self.assertEqual(request.headers["X-goog-api-key"], "secret-key")
        payload = __import__("json").loads(request.data)
        self.assertEqual(
            payload["generationConfig"]["thinkingConfig"]["thinkingLevel"],
            "minimal",
        )

    def test_end_to_end_emotional_synthesis(self):
        cfg = bus.config()
        mouth = Mouth(cfg)
        text = "မင်္ဂလာပါဗျာ! အခုပဲ သတင်းကောင်းတစ်ခု ရလာတယ်။ ဒီအကြောင်း နားလည်ရဲ့လား?"
        try:
            got = mouth._synth_burmese(text)
        except Exception as e:
            self.skipTest(f"Edge-TTS network service unavailable: {e}")
        if got is None:
            self.skipTest("Edge-TTS network service unreachable in this environment")
        audio, sr = got
        self.assertGreater(len(audio), 0)
        self.assertEqual(sr, 24000)
        # Verify non-silent audio
        self.assertGreater(float(np.max(np.abs(audio))), 0.1)


if __name__ == "__main__":
    unittest.main()
