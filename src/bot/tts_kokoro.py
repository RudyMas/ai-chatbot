# NEW: Kokoro helper (new layout only)
# One voice per .bin in a directory (e.g., models/kokoro_voices/af_sarah.bin)

import os
from functools import lru_cache
import io, soundfile as sf
from kokoro_onnx import Kokoro
from typing import List
import os, re, zipfile
from functools import lru_cache
from typing import List
import numpy as np

def _voice_bin_path(voices_dir: str, voice: str) -> str:
    """
    voices_dir: directory containing per-voice .bin files.
    voice: name like 'af_sarah' or 'am_adam'.
    """
    if not os.path.isdir(voices_dir):
        raise FileNotFoundError(f"Kokoro voices directory not found: {voices_dir}")
    path = os.path.join(voices_dir, f"{voice}.pt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Voice file not found: {path}")
    return path

@lru_cache(maxsize=1)
def _kokoro(model_path: str, voices_file: str) -> Kokoro:
    # voices_file should be the single multi-voice pack: voices-v1.0.bin
    return Kokoro(model_path, voices_file)

def kokoro_tts_to_wav_bytes(text, voice, model_path, voices_file, speed=1.0, lang="en-us"):
    tts = _kokoro(model_path, voices_file)

    # Newer kokoro-onnx exposes .create(); keep a tiny fallback just in case.
    if hasattr(tts, "create"):
        samples, sr = tts.create(text, voice=voice, speed=float(speed), lang=lang)
    elif hasattr(tts, "generate"):
        samples, sr = tts.generate(text, voice=voice)  # older versions
    else:
        raise RuntimeError("Unsupported kokoro-onnx version: no create()/generate() method found.")

    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV")
    return buf.getvalue()

@lru_cache(maxsize=1)
def _parse_voices_from_bin(voices_file: str) -> List[str]:
    """
    Best-effort extractor for voice names inside voices-v1.0.bin.
    Tries NumPy NPZ first (no pickle), then NPZ with pickle, then raw zip members.
    """
    names: set[str] = set()

    # Strategy A: np.load without pickle (safest)
    try:
        with np.load(voices_file, allow_pickle=False) as npz:
            keys = list(npz.keys())
            # Common containers
            for k in ("voices", "speakers", "names"):
                if k in keys:
                    arr = npz[k]
                    try:
                        names.update(str(x) for x in np.atleast_1d(arr).tolist())
                    except Exception:
                        pass
            # If entries look like voice names themselves
            probable = [k for k in keys if "_" in k or re.match(r"^[abc][mf]_", k)]
            names.update(probable)
            if names:
                return sorted(names)
    except Exception:
        pass

    # Strategy B: np.load with pickle (less safe but file is local)
    try:
        with np.load(voices_file, allow_pickle=True) as npz:
            # Try common dict-in-array pattern
            for k in ("voices", "speakers"):
                if k in npz.files:
                    arr = npz[k]
                    try:
                        obj = arr.item()  # often a dict {name: embedding}
                        if isinstance(obj, dict):
                            names.update(str(n) for n in obj.keys())
                    except Exception:
                        # maybe list/array of names
                        try:
                            names.update(str(x) for x in np.atleast_1d(arr).tolist())
                        except Exception:
                            pass
            if names:
                return sorted(names)
    except Exception:
        pass

    # Strategy C: treat as a zip and derive names from .npy entries
    try:
        with zipfile.ZipFile(voices_file) as zf:
            members = [m for m in zf.namelist() if m.endswith(".npy")]
            stems = [os.path.splitext(os.path.basename(m))[0] for m in members]
            probable = [s for s in stems if "_" in s or re.match(r"^[abc][mf]_", s)]
            if probable:
                return sorted(set(probable))
    except Exception:
        pass

    return []

def list_kokoro_voices(model_path: str, voices_file: str) -> List[str]:
    """
    First try the runtime (if it exposes voices), else parse the .bin file.
    """
    tts = _kokoro(model_path, voices_file)

    # Try runtime APIs
    if hasattr(tts, "voices"):
        v = getattr(tts, "voices")
        if isinstance(v, dict):
            return sorted(v.keys())
        if isinstance(v, (list, tuple, set)):
            return sorted(v)

    if hasattr(tts, "list_voices"):
        try:
            return sorted(tts.list_voices())
        except Exception:
            pass

    # Fallback: read from the .bin
    names = _parse_voices_from_bin(voices_file)
    return names if names else []