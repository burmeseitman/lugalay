# -*- coding: utf-8 -*-
"""Unit and Integration tests for the Burmese Emotion & Prosody TTS pipeline."""

import os
import sys
import unittest
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, AGENT)

import bus
from emotion import EmotionAnalyzer, ProsodyInjector, EmotionType, PROSODY_MAP
from voice import Mouth


class TestEmotionPipeline(unittest.TestCase):

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
        self.assertEqual(p, "+12Hz")
        self.assertEqual(r, "+10%")
        self.assertEqual(b, 200)

        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.SERIOUS, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "-10Hz")
        self.assertEqual(r, "-20%")
        self.assertEqual(b, 900)

        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.CALM, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "+0Hz")
        self.assertEqual(r, "-7%")
        self.assertEqual(b, 500)

        p, r, b = ProsodyInjector.calculate_prosody(EmotionType.QUESTIONING, base_pitch="+0Hz", base_rate="-2%")
        self.assertEqual(p, "+8Hz")
        self.assertEqual(r, "-2%")
        self.assertEqual(b, 400)

    def test_text_segmentation_and_chunking(self):
        text = "မင်္ဂလာပါဗျာ! အခုပဲ သတင်းကောင်း ရလာတယ်။ ဒါပေမယ့် သတိထားရမယ့် အချက်လည်း ရှိတယ်နော်။ ဒီအကြောင်း နားလည်ရဲ့လား?"
        chunks = ProsodyInjector.inject_prosody_chunks(text, base_pitch="+2Hz", base_rate="+0%")
        self.assertGreaterEqual(len(chunks), 3)

        emotions = [c.emotion for c in chunks]
        self.assertIn(EmotionType.EXCITED, emotions)
        self.assertIn(EmotionType.SERIOUS, emotions)
        self.assertIn(EmotionType.QUESTIONING, emotions)

    def test_end_to_end_emotional_synthesis(self):
        cfg = bus.config()
        mouth = Mouth(cfg)
        text = "မင်္ဂလာပါဗျာ! အခုပဲ သတင်းကောင်းတစ်ခု ရလာတယ်။ ဒီအကြောင်း နားလည်ရဲ့လား?"
        got = mouth._synth_burmese(text)
        self.assertIsNotNone(got)
        audio, sr = got
        self.assertGreater(len(audio), 0)
        self.assertEqual(sr, 24000)
        # Verify non-silent audio
        self.assertGreater(float(np.max(np.abs(audio))), 0.1)


if __name__ == "__main__":
    unittest.main()
