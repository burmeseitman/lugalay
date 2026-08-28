#!/usr/bin/env python3
"""Lugalay's eye: one webcam frame, on demand.

The camera is opened only for the moment it takes to grab a frame and then
released again, so the light is not on while nobody is looking and other
programs (the hands board, Zoom) can still have the device the rest of the time.

Webcams hand back the first few frames before auto-exposure has settled — they
come out black. `grab` throws those away and keeps the last one.

Three platforms, three capture backends. OpenCV picks one on its own, but its
default on Windows (MSMF) is slow to open and fails on plenty of cheap webcams,
so each platform is asked for its good backend first and only then left to
OpenCV's judgement.
"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    # Packaged, the bundle is read-only, so frames belong in the writable half.
    import bus
    FRAMES = os.path.join(bus.ROOT, "eyes", "frames")
except Exception:
    FRAMES = os.path.join(HERE, "frames")

WARMUP_FRAMES = 8      # discarded; auto-exposure needs about this many


class CameraError(RuntimeError):
    """The camera could not be opened or produced nothing usable."""


def _backends(cv2):
    """Preferred capture backends for this platform, best first.

    The trailing CAP_ANY is the important one: if a machine has some webcam the
    named backend does not drive, OpenCV still gets its turn.
    """
    if sys.platform == "darwin":
        names = ("CAP_AVFOUNDATION",)
    elif sys.platform == "win32":
        # DSHOW opens in well under a second; MSMF regularly takes five and
        # returns nothing at all on some devices.
        names = ("CAP_DSHOW", "CAP_MSMF")
    else:
        names = ("CAP_V4L2",)
    out = [getattr(cv2, n) for n in names if hasattr(cv2, n)]
    out.append(cv2.CAP_ANY)
    return out


def _denied_hint():
    """Where this platform hides the camera permission."""
    if sys.platform == "darwin":
        return ("macOS may not have granted camera access — System Settings > "
                "Privacy & Security > Camera, and switch on whatever is running "
                "Lugalay (the app itself, or your terminal). QUIT AND REOPEN "
                "LUGALAY AFTERWARDS: macOS decides a program's camera access "
                "when it starts, so a permission granted while it is running "
                "does not reach it. Note also that an ad-hoc signed build gets "
                "a new identity every time it is rebuilt, which macOS treats as "
                "a different program — so a fresh build has to be allowed again")
    if sys.platform == "win32":
        return ("Windows may be blocking it — Settings > Privacy & security > "
                "Camera, and turn on both 'Camera access' and 'Let desktop apps "
                "access your camera'")
    return ("on Linux the camera is a device file: check that /dev/video0 exists "
            "and that your user is in the 'video' group "
            "(sudo usermod -aG video $USER, then log out and back in)")


def _import_cv2():
    try:
        import cv2
        return cv2
    except ImportError as e:
        raise CameraError(
            "opencv is not installed in this environment — "
            "pip install opencv-python-headless") from e
    except Exception as e:
        # On Linux the non-headless build dies here for want of libGL.
        raise CameraError(f"opencv failed to load: {e}") from e


def grab(index=0, width=1280, height=720):
    """Return one settled BGR frame. Raises CameraError if the device is unusable."""
    cv2 = _import_cv2()
    tried = []
    for backend in _backends(cv2):
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            tried.append(backend)
            continue
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            frame = None
            for _ in range(WARMUP_FRAMES):
                ok, f = cap.read()
                if ok and f is not None:
                    frame = f
            if frame is not None:
                return frame
            tried.append(backend)
        finally:
            cap.release()

    raise CameraError(
        f"camera {index} gave no picture (tried {len(tried)} backend(s)). "
        f"Another program may be holding it — only one at a time can — or "
        f"{_denied_hint()}")


def snapshot(index=0, path=None, quality=88):
    """Grab a frame and write it to disk. Returns the absolute path."""
    cv2 = _import_cv2()
    frame = grab(index)
    path = path or os.path.join(FRAMES, "latest.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]):
        raise CameraError(f"could not write the frame to {path}")
    return os.path.abspath(path)


def available(index=0):
    """True if a frame can actually be grabbed right now."""
    try:
        grab(index)
        return True
    except Exception:
        return False
