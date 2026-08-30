# -*- coding: utf-8 -*-
"""Burmese Emotion & Prosody Analysis Pipeline for Edge-TTS.

Provides:
1. EmotionAnalyzer: Segments text into emotional clauses and detects tone (Excited, Serious, Calm, Questioning).
2. ProsodyInjector: Calculates dynamic Pitch, Rate, and Breathing Pauses (break_ms) mapped to persona base settings.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Tuple


class EmotionType:
    EXCITED = "excited"       # Happy, energetic, enthusiastic (+10Hz to +15Hz, +10% to +15%, 200ms)
    SERIOUS = "serious"       # Sad, serious, solemn (-8Hz to -12Hz, -15% to -20%, 800ms-1200ms)
    CALM = "calm"             # Narrative, relaxed, neutral (0Hz, -5%, 500ms)
    QUESTIONING = "questioning" # Inquisitive, clarifying (+8Hz, 0%, 400ms)


@dataclass
class EmotionChunk:
    text: str
    emotion: str
    pitch: str
    rate: str
    volume: str
    break_ms: int


# Emotion mapping deltas specified for Edge-TTS
PROSODY_MAP = {
    EmotionType.EXCITED: {
        "pitch_delta_hz": 12,
        "rate_delta_pct": 12,
        "break_ms": 200,
    },
    EmotionType.SERIOUS: {
        "pitch_delta_hz": -10,
        "rate_delta_pct": -18,
        "break_ms": 900,
    },
    EmotionType.CALM: {
        "pitch_delta_hz": 0,
        "rate_delta_pct": -5,
        "break_ms": 500,
    },
    EmotionType.QUESTIONING: {
        "pitch_delta_hz": 8,
        "rate_delta_pct": 0,
        "break_ms": 400,
    },
}

# Burmese keywords & particles associated with emotions
_SERIOUS_WORDS = {
    "သတိထား", "စိတ်မကောင်း", "ဝမ်းနည်း", "အန္တရာယ်", "ပြဿနာ", "အရေးကြီး",
    "မှား", "ပျက်", "ဆုံးရှုံး", "ခက်ခဲ", "မဖြစ်နိုင်", "ဆိုး", "သတိပြု",
    "အထူးဂရုစိုက်", "ကြေကွဲ", "အမှား", "မကောင်း", "စိတ်ညစ်", "စိတ်ပူ",
    "ဟင့်အင်း", "မရဘူး", "မဖြစ်ပါဘူး"
}

_EXCITED_WORDS = {
    "ဝမ်းသာ", "ပျော်", "သတင်းကောင်း", "ကောင်းလိုက်တာ", "မိုက်တယ်",
    "အောင်မြင်", "ကြိုဆို", "လှလိုက်တာ", "သဘောကျ", "အဆင်ပြေသွားပြီ",
    "အရမ်းကောင်း", "အရမ်းလှ", "အရမ်းပျော်", "ဟေး", "ဝိုး", "အံ့သြ",
    "မင်္ဂလာပါ", "ကြိုးစား", "အားရစရာ", "ကြိုက်တယ်", "ဟုတ်တယ်ဗျာ"
}

_QUESTION_WORDS = {
    "လား", "လဲ", "ပါသလား", "ပါသလဲ", "ပါ့မလား", "ဘာလဲ", "ဘယ်သူ", "ဘယ်လို",
    "ဘယ်အချိန်", "ဘယ်မှာ", "ဘယ်အတွက်", "ဘယ်တော့", "ဟုတ်လား", "အဆင်ပြေရဲ့လား",
    "ဘာဖြစ်လို့", "ဟုတ်ရဲ့လား", "ရမလား"
}


class EmotionAnalyzer:
    """Analyzes text context, clauses, punctuation, and Burmese particles to detect emotion."""

    @staticmethod
    def detect_clause_emotion(clause: str) -> str:
        """Detect the emotion of an individual clause or sentence."""
        c = clause.strip()
        if not c:
            return EmotionType.CALM

        # 1. Questioning check: ends with question mark or typical Burmese question particles
        if c.endswith("?") or any(c.endswith(qw) or (qw + "။" in c) for qw in _QUESTION_WORDS):
            return EmotionType.QUESTIONING

        # 2. Serious / Warning / Sad check (takes precedence over generic excited markers)
        if "…" in c or any(w in c for w in _SERIOUS_WORDS):
            return EmotionType.SERIOUS

        # 3. Excited check: exclamation mark or excited vocabulary
        if "!" in c or any(w in c for w in _EXCITED_WORDS):
            return EmotionType.EXCITED

        # 4. Default: Calm / Narrative
        return EmotionType.CALM

    @classmethod
    def segment_text(cls, text: str) -> List[Tuple[str, str]]:
        """Split text by sentences/clauses into (clause_text, emotion) pairs."""
        if not text or not text.strip():
            return []

        # Split along major sentence / clause boundaries while preserving meaningful chunks
        raw_parts = re.split(r"([။!?\n]+)", text)
        clauses = []
        i = 0
        while i < len(raw_parts):
            chunk = raw_parts[i].strip()
            punct = raw_parts[i + 1].strip() if i + 1 < len(raw_parts) else ""
            i += 2
            if not chunk and not punct:
                continue

            full_clause = (chunk + punct).strip()
            if not full_clause:
                continue

            # Check if clause contains multiple comma-separated thoughts (၊)
            sub_clauses = re.split(r"([၊,]+)", full_clause)
            j = 0
            while j < len(sub_clauses):
                sub = sub_clauses[j].strip()
                sub_punct = sub_clauses[j + 1].strip() if j + 1 < len(sub_clauses) else ""
                j += 2
                if not sub and not sub_punct:
                    continue
                combined = (sub + (" " if sub_punct else "")).strip()
                if combined:
                    emotion = cls.detect_clause_emotion(combined)
                    clauses.append((combined, emotion))

        if not clauses and text.strip():
            clauses.append((text.strip(), cls.detect_clause_emotion(text)))

        return clauses


class ProsodyInjector:
    """Calculates final SSML/Edge-TTS prosody parameters based on persona and emotion."""

    @staticmethod
    def _parse_pitch(pitch_str: str) -> int:
        """Parse pitch string like '+2Hz' or '-7Hz' to integer."""
        if not pitch_str:
            return 0
        m = re.search(r"([+-]?\d+)", str(pitch_str))
        return int(m.group(1)) if m else 0

    @staticmethod
    def _parse_rate(rate_str: str) -> int:
        """Parse rate string like '+2%' or '-6%' to integer."""
        if not rate_str:
            return 0
        m = re.search(r"([+-]?\d+)", str(rate_str))
        return int(m.group(1)) if m else 0

    @classmethod
    def calculate_prosody(cls, emotion: str, base_pitch: str = "+0Hz", base_rate: str = "-2%") -> Tuple[str, str, int]:
        """Combine base persona pitch/rate with emotion deltas.
        Returns: (final_pitch_str, final_rate_str, break_ms)
        """
        p_info = PROSODY_MAP.get(emotion, PROSODY_MAP[EmotionType.CALM])

        base_p_val = cls._parse_pitch(base_pitch)
        base_r_val = cls._parse_rate(base_rate)

        final_p_val = base_p_val + p_info["pitch_delta_hz"]
        final_r_val = base_r_val + p_info["rate_delta_pct"]

        # Clamp within reasonable Azure Edge-TTS limits
        final_p_val = max(-25, min(25, final_p_val))
        final_r_val = max(-30, min(30, final_r_val))

        p_str = f"+{final_p_val}Hz" if final_p_val >= 0 else f"{final_p_val}Hz"
        r_str = f"+{final_r_val}%" if final_r_val >= 0 else f"{final_r_val}%"

        return p_str, r_str, p_info["break_ms"]

    @classmethod
    def inject_prosody_chunks(
        cls,
        text: str,
        base_pitch: str = "+0Hz",
        base_rate: str = "-2%",
        base_volume: str = "+0%"
    ) -> List[EmotionChunk]:
        """Convert input text into structured EmotionChunks with calibrated pitch, rate, and breath pauses."""
        segmented = EmotionAnalyzer.segment_text(text)
        chunks = []
        for clause_text, emotion in segmented:
            pitch, rate, break_ms = cls.calculate_prosody(emotion, base_pitch, base_rate)
            chunks.append(
                EmotionChunk(
                    text=clause_text,
                    emotion=emotion,
                    pitch=pitch,
                    rate=rate,
                    volume=base_volume,
                    break_ms=break_ms
                )
            )
        return chunks
