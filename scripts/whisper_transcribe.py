#!/usr/bin/env python3
"""
Transcribe audio with faster-whisper + QLU spiritual glossary priming.

CLI:
  python scripts/whisper_transcribe.py path/to/audio.webm --lang te
  python scripts/whisper_transcribe.py path/to/audio.mp3 --lang en --model small

Requires: pip install faster-whisper  (and ffmpeg via imageio-ffmpeg / system)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from qlu_spiritual_glossary import build_initial_prompt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


def ensure_ffmpeg_on_path() -> str | None:
  """Prefer the imageio-ffmpeg bundle so Whisper can decode webm/mp3."""
  try:
    from imageio_ffmpeg import get_ffmpeg_exe

    exe = get_ffmpeg_exe()
    if exe and Path(exe).is_file():
      parent = str(Path(exe).resolve().parent)
      path = os.environ.get("PATH", "")
      if parent not in path.split(os.pathsep):
        os.environ["PATH"] = parent + os.pathsep + path
      return exe
  except Exception:
    pass
  return None


def convert_to_wav(src: Path, dest: Path) -> Path:
  """
  Convert browser WebM/Opus (and other formats) to 16 kHz mono WAV.

  faster-whisper's PyAV decoder often fails on MediaRecorder WebM; ffmpeg is reliable.
  """
  ffmpeg = ensure_ffmpeg_on_path()
  if not ffmpeg:
    raise RuntimeError(
      "ffmpeg not found. Run: python -m pip install -r requirements.txt"
    )
  dest.parent.mkdir(parents=True, exist_ok=True)
  cmd = [
    ffmpeg,
    "-y",
    "-hide_banner",
    "-loglevel",
    "error",
    "-i",
    str(src),
    "-vn",
    "-ac",
    "1",
    "-ar",
    "16000",
    "-c:a",
    "pcm_s16le",
    str(dest),
  ]
  try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
  except subprocess.CalledProcessError as e:
    err = (e.stderr or e.stdout or "").strip() or str(e)
    raise RuntimeError(
      "Could not decode audio with ffmpeg. "
      "Try uploading .wav/.mp3, or record a longer clip. "
      f"Details: {err[:400]}"
    ) from e
  if not dest.is_file() or dest.stat().st_size < 64:
    raise RuntimeError(
      "Audio conversion produced an empty file — recording may be too short or silent."
    )
  return dest


def prepare_audio_for_whisper(audio_path: Path) -> tuple[Path, Path]:
  """
  Return (wav_path, temp_dir_to_cleanup).

  Always convert via ffmpeg CLI to 16 kHz mono WAV (avoids PyAV WebM failures).
  """
  path = Path(audio_path)
  tmp_dir = Path(tempfile.mkdtemp(prefix="qlu-whisper-wav-"))
  wav = tmp_dir / "audio.wav"
  try:
    convert_to_wav(path, wav)
  except Exception:
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)
    raise
  return wav, tmp_dir


def load_wav_mono_float32(path: Path) -> np.ndarray:
  """Load PCM WAV as float32 mono — bypasses PyAV entirely."""
  with wave.open(str(path), "rb") as wf:
    channels = wf.getnchannels()
    width = wf.getsampwidth()
    rate = wf.getframerate()
    nframes = wf.getnframes()
    raw = wf.readframes(nframes)
  if width != 2:
    raise RuntimeError(f"Expected 16-bit PCM WAV, got sample width {width}")
  audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
  if channels > 1:
    audio = audio.reshape(-1, channels).mean(axis=1)
  if rate != 16000:
    # Should already be 16 kHz from ffmpeg; resample crudely if not.
    duration = audio.shape[0] / float(rate)
    target = max(1, int(duration * 16000))
    audio = np.interp(
      np.linspace(0, audio.shape[0] - 1, target),
      np.arange(audio.shape[0]),
      audio,
    ).astype(np.float32)
  return audio


def normalize_lang(lang: str) -> str:
  code = (lang or "te").lower().replace("_", "-")
  if code.startswith("te"):
    return "te"
  if code.startswith("hi"):
    return "hi"
  if code.startswith("en"):
    return "en"
  return code.split("-")[0] or "te"


def load_model(model_size: str = "small", device: str = "auto"):
  try:
    from faster_whisper import WhisperModel
  except ImportError as e:
    raise RuntimeError(
      "faster-whisper is not installed. Run:\n"
      "  python -m pip install faster-whisper\n"
      "Then retry."
    ) from e

  ensure_ffmpeg_on_path()
  # CPU int8 is the practical default on most Windows laptops.
  compute = "int8"
  dev = device
  if device == "auto":
    dev = "cpu"
  return WhisperModel(model_size, device=dev, compute_type=compute)


_MODEL_CACHE: dict[tuple[str, str], object] = {}


def get_cached_model(model_size: str = "small", device: str = "auto"):
  key = (model_size, device)
  if key not in _MODEL_CACHE:
    _MODEL_CACHE[key] = load_model(model_size, device)
  return _MODEL_CACHE[key]


def transcribe_audio(
  audio_path: Path,
  lang: str = "te",
  model_size: str = "small",
  device: str = "auto",
  extra_prompt: str | None = None,
  *,
  use_cache: bool = True,
) -> dict:
  """Return {text, language, segments, model}."""
  path = Path(audio_path)
  if not path.is_file():
    raise FileNotFoundError(f"Audio not found: {path}")
  if path.stat().st_size < 256:
    raise RuntimeError("Audio file is empty or too short — record a few seconds and try again.")

  whisper_lang = normalize_lang(lang)
  initial = build_initial_prompt(whisper_lang, extra_prompt)
  model = get_cached_model(model_size, device) if use_cache else load_model(model_size, device)

  wav_path, tmp_dir = prepare_audio_for_whisper(path)
  try:
    # Pass numpy audio so faster-whisper never calls PyAV (broken on many WebM/WAV paths).
    audio = load_wav_mono_float32(wav_path)
    if audio.size < 1600:  # < ~0.1s
      raise RuntimeError("Recording too short — speak for a couple of seconds, then stop.")
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    if rms < 0.003:
      raise RuntimeError(
        "Audio is nearly silent (mic level too low). "
        "Raise Windows mic volume, speak closer, watch the level bar, then retry."
      )

    # VAD off by default — short mic clips were often wiped as "silence".
    segments_iter, info = model.transcribe(
      audio,
      language=whisper_lang,
      task="transcribe",
      vad_filter=False,
      beam_size=5,
      best_of=5,
      patience=1.0,
      condition_on_previous_text=False,
      initial_prompt=initial,
      word_timestamps=False,
      no_speech_threshold=0.4,
      compression_ratio_threshold=2.8,
    )

    segments = []
    parts: list[str] = []
    for seg in segments_iter:
      text = (seg.text or "").strip()
      if not text:
        continue
      segments.append(
        {
          "start": round(float(seg.start), 2),
          "end": round(float(seg.end), 2),
          "text": text,
        }
      )
      parts.append(text)

    full = "\n".join(parts).strip()
    # Light cleanup: collapse runaway spaces, keep Telugu punctuation intact.
    full = re.sub(r"[ \t]{2,}", " ", full)
    full = re.sub(r"\n{3,}", "\n\n", full)

    return {
      "text": full,
      "language": getattr(info, "language", whisper_lang) or whisper_lang,
      "duration": round(float(getattr(info, "duration", 0) or 0), 2),
      "segments": segments,
      "model": model_size,
      "initialPrompt": initial,
    }
  finally:
    try:
      import shutil

      shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
      pass


def safe_out_name(stem: str, lang: str) -> str:
  clean = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_") or "transcript"
  return f"whisper-{clean}-{normalize_lang(lang)}.txt"


def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(description="Whisper transcription with QLU glossary")
  ap.add_argument("audio", type=Path, help="Audio/video file path")
  ap.add_argument("--lang", default="te", help="te | en | hi (default te)")
  ap.add_argument("--model", default="small", help="tiny|base|small|medium|large-v3")
  ap.add_argument("--device", default="auto", help="cpu|cuda|auto")
  ap.add_argument("--extra-prompt", default="", help="Optional extra priming words")
  ap.add_argument("-o", "--output", type=Path, help="Output .txt path")
  args = ap.parse_args(argv)

  ensure_ffmpeg_on_path()
  print(f"Transcribing {args.audio} ({args.lang}, model={args.model})…", flush=True)
  result = transcribe_audio(
    args.audio,
    lang=args.lang,
    model_size=args.model,
    device=args.device,
    extra_prompt=args.extra_prompt or None,
    use_cache=False,
  )
  OUT.mkdir(parents=True, exist_ok=True)
  out = args.output or (OUT / safe_out_name(args.audio.stem, args.lang))
  out.write_text(result["text"] + "\n", encoding="utf-8", newline="\n")
  print(f"Language: {result['language']} · duration ~{result['duration']}s")
  print(f"Wrote {out} ({len(result['text'])} chars, {len(result['segments'])} segments)")
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    raise SystemExit(1)
