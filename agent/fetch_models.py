#!/usr/bin/env python3
"""Fetch the speech models. They are far too large to ship in a release.

    python3 agent/fetch_models.py             Kokoro (the English voice)
    python3 agent/fetch_models.py --burmese   also build the Burmese recogniser
    python3 agent/fetch_models.py --check     report what is present

Whisper's own models (small.en, base) are downloaded by faster-whisper the
first time they are used, so they are not handled here.

The Burmese recogniser is a community fine-tune that has to be converted to
CTranslate2 before faster-whisper can load it. That needs PyTorch — about
2.5GB — but only while converting; nothing of it is needed to run.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "voice", "models")
VENV_PY = os.path.join(HERE, "voice", ".venv", "bin", "python")
if sys.platform == "win32":
    VENV_PY = os.path.join(HERE, "voice", ".venv", "Scripts", "python.exe")

KOKORO = [
    ("kokoro-v1.0.onnx",
     "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
     300_000_000),
    ("voices-v1.0.bin",
     "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
     20_000_000),
]

# the fine-tune, and the tokenizer of the base model it was trained from
BURMESE_REPO = "ToeLay/whisper_large_v3_turbo_mm"
BURMESE_DIR = "whisper-my-turbo"
BASE_TOKENIZER = ("https://huggingface.co/openai/whisper-large-v3-turbo/"
                  "resolve/main/tokenizer.json")


def human(n):
    return f"{n / 1_000_000:.0f} MB"


def download(url, dest):
    tmp = dest + ".part"
    seen = [0]

    def hook(blocks, size, total):
        seen[0] = blocks * size
        if total > 0:
            pct = min(100, seen[0] * 100 // total)
            print(f"\r    {pct:3d}%  {human(seen[0])} / {human(total)}",
                  end="", flush=True)

    urllib.request.urlretrieve(url, tmp, hook)
    print()
    os.replace(tmp, dest)


def fetch_kokoro():
    os.makedirs(MODELS, exist_ok=True)
    for name, url, min_size in KOKORO:
        dest = os.path.join(MODELS, name)
        if os.path.exists(dest) and os.path.getsize(dest) > min_size:
            print(f"  ok    {name} ({human(os.path.getsize(dest))})")
            continue
        print(f"  fetch {name}")
        download(url, dest)
    return True


def fetch_burmese():
    """Convert the fine-tune to CTranslate2, then repair its tokenizer.

    The upstream repo has no tokenizer.json, and generating one from its
    vocab/merges produces an empty vocabulary — which in turn writes a
    vocabulary.json in the wrong order, so faster-whisper cannot find
    <|startoftranscript|>. Both files are rebuilt from the base model instead.
    """
    out = os.path.join(MODELS, BURMESE_DIR)
    if os.path.isfile(os.path.join(out, "model.bin")):
        print(f"  ok    {BURMESE_DIR} already built")
        return True

    work = os.path.join(HERE, ".convert-venv")
    py = os.path.join(work, "bin", "python")
    conv = os.path.join(work, "bin", "ct2-transformers-converter")
    if sys.platform == "win32":
        py = os.path.join(work, "Scripts", "python.exe")
        conv = os.path.join(work, "Scripts", "ct2-transformers-converter.exe")

    if not os.path.exists(conv):
        print("  building a throwaway environment for the conversion "
              "(PyTorch, ~2.5GB, not needed afterwards)")
        uv = shutil.which("uv")
        if uv:
            subprocess.run([uv, "venv", "--python", "3.12", work], check=True)
            subprocess.run([uv, "pip", "install", "--python", py, "-q",
                            "torch", "transformers", "ctranslate2"], check=True)
        else:
            subprocess.run([sys.executable, "-m", "venv", work], check=True)
            subprocess.run([py, "-m", "pip", "install", "-q",
                            "torch", "transformers", "ctranslate2"], check=True)

    print(f"  convert {BURMESE_REPO}")
    subprocess.run([conv, "--model", BURMESE_REPO, "--output_dir", out,
                    "--copy_files", "preprocessor_config.json",
                    "--quantization", "int8", "--force"], check=True)

    print("  repair tokenizer and vocabulary from the base model")
    download(BASE_TOKENIZER, os.path.join(out, "tokenizer.json"))
    import json
    with open(os.path.join(out, "tokenizer.json"), encoding="utf-8") as f:
        tok = json.load(f)
    by_id = {i: t for t, i in tok["model"]["vocab"].items()}
    for a in tok.get("added_tokens", []):
        by_id[a["id"]] = a["content"]
    vocab = [by_id.get(i, f"<|unused_{i}|>") for i in range(max(by_id) + 1)]
    with open(os.path.join(out, "vocabulary.json"), "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False)
    if vocab[50258] != "<|startoftranscript|>":
        print("  WARNING: vocabulary looks wrong; the model may not load")
        return False
    print(f"  ok    {BURMESE_DIR} built")
    shutil.rmtree(work, ignore_errors=True)
    return True


def check():
    print("\n  models\n  " + "-" * 44)
    ok = True
    for name, _url, min_size in KOKORO:
        p = os.path.join(MODELS, name)
        good = os.path.exists(p) and os.path.getsize(p) > min_size
        ok &= good
        print(f"  {'ok  ' if good else 'MISSING'}  {name}"
              + (f"  ({human(os.path.getsize(p))})" if os.path.exists(p) else ""))
    my = os.path.join(MODELS, BURMESE_DIR, "model.bin")
    print(f"  {'ok  ' if os.path.exists(my) else '----'}  {BURMESE_DIR}"
          f"{'' if os.path.exists(my) else '  (optional; English still works)'}")
    wh = os.path.join(MODELS, "whisper")
    print(f"  {'ok  ' if os.path.isdir(wh) else '----'}  whisper cache"
          f"{'' if os.path.isdir(wh) else '  (downloads itself on first use)'}")
    print()
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--burmese", action="store_true",
                    help="also build the Burmese recogniser (slow, needs PyTorch)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    print("\n  Fetching models into agent/voice/models\n")
    ok = fetch_kokoro()
    if a.burmese:
        ok = fetch_burmese() and ok
    print("\n  done\n" if ok else "\n  finished with problems\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
