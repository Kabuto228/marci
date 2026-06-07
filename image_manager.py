"""
Image Manager for Marci Agent
Shows a random small image popup (no frame, no buttons) that fades out after 1 second.
Uses tkinter — runs its own event loop in a dedicated daemon thread to avoid
"Tcl_AsyncDelete: async handler deleted by the wrong thread" errors.

Features:
- Tk() and mainloop run in the SAME background daemon thread (required by Tcl/Tk)
- Thread-safe: show_random_image() can be called from any thread via root.after()
- Only one popup at a time: calling show_random_image() destroys the previous one instantly
"""

import os
import random
import threading
import time

from resource_path import resource_path

try:
    import tkinter as tk
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

IMAGES_DIR = resource_path("images")
IMAGE_SIZE = (200, 200)  # Small popup size
FADE_DELAY = 1         # Show at full opacity for 0.3 sec
FADE_STEPS = 15           # Number of fade steps
FADE_DURATION = 0.5      # Total fade out duration (0.3 sec)

# Single hidden root window — created and mainlooped in a background daemon thread
_root = None
_root_lock = threading.Lock()
_root_ready = threading.Event()

# Currently visible popup (Toplevel) — destroyed on next show
_current_top = None


def _tk_thread_main():
    """Create Tk() and run mainloop in this daemon thread.

    Tcl/Tk requires that Tk() creation and mainloop() happen in the same thread.
    """
    global _root

    try:
        _root = tk.Tk()
        _root.withdraw()  # Hide the main window entirely
        _root.attributes("-topmost", True)

        # Signal that root is ready
        _root_ready.set()

        # Run mainloop forever (daemon thread, will be killed on exit)
        _root.mainloop()

    except Exception:
        _root_ready.set()  # Don't hang forever if init fails
        _root = None


def _ensure_root():
    """Start the background tk thread and wait for root to be ready."""
    global _root

    if _root is None and HAS_PIL:
        # Start the background thread that creates Tk() and runs mainloop
        thread = threading.Thread(target=_tk_thread_main, daemon=True)
        thread.start()

        # Wait for root to be created (with timeout to avoid deadlock)
        _root_ready.wait(timeout=5.0)

    return _root


def show_random_image():
    """Show a random image popup — thread-safe.

    Only one popup at a time. Calling this while another popup is visible
    will instantly destroy the old one before showing the new one.

    Uses root.after(0, callback) which is safe to call from any thread.
    The actual tkinter work runs in the background tk thread via mainloop.
    """
    if not HAS_PIL:
        return

    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        return

    extensions = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
    images = [f for f in os.listdir(IMAGES_DIR)
              if f.lower().endswith(extensions)]

    if not images:
        return

    filename = random.choice(images)
    filepath = os.path.join(IMAGES_DIR, filename)

    try:
        root = _ensure_root()
        if root is not None:
            root.after(0, _show_and_fade, filepath)
    except Exception:
        pass


def _destroy_current():
    """Destroy the currently visible popup window, if any."""
    global _current_top
    if _current_top is not None:
        try:
            _current_top.destroy()
        except Exception:
            pass
        _current_top = None


def _show_and_fade(filepath):
    """Show image in a borderless Toplevel window, then fade out and close.

    Runs in the tkinter thread (called from root.after()).
    Uses root.after() for the fade animation.
    """
    global _current_top

    # Destroy previous popup immediately
    _destroy_current()

    try:
        img = Image.open(filepath)
        img = img.resize(IMAGE_SIZE, Image.LANCZOS)

        root = _ensure_root()
        if root is None:
            return

        top = tk.Toplevel(root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.wm_attributes("-topmost", True)

        try:
            top.attributes("-alpha", 1.0)
        except Exception:
            pass

        # Random position
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        margin = 50
        x = random.randint(margin, max(margin, screen_w - IMAGE_SIZE[0] - margin))
        y = random.randint(margin, max(margin, screen_h - IMAGE_SIZE[1] - margin))
        top.geometry(f"{IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}+{x}+{y}")

        photo = ImageTk.PhotoImage(img)
        top.photo = photo  # Keep reference

        label = tk.Label(top, image=photo, borderwidth=0, highlightthickness=0)
        label.pack()

        root.update_idletasks()

        # Store reference so it can be killed by next call
        _current_top = top

        # Schedule fade after FADE_DELAY
        fade_ms = int(FADE_DELAY * 1000)
        root.after(fade_ms, _fade_step, top, FADE_STEPS)

    except Exception:
        try:
            top.destroy()
        except Exception:
            pass
        if _current_top is top:
            _current_top = None


def _fade_step(top, steps_remaining):
    """Perform one fade step, then schedule the next or close."""
    global _current_top

    try:
        alpha = steps_remaining / FADE_STEPS
        top.attributes("-alpha", alpha)

        if steps_remaining > 1:
            step_ms = int((FADE_DURATION / FADE_STEPS) * 1000)
            root = _ensure_root()
            if root is not None:
                root.after(step_ms, _fade_step, top, steps_remaining - 1)
        else:
            if _current_top is top:
                _current_top = None
            top.destroy()

    except Exception:
        try:
            top.destroy()
        except Exception:
            pass
        if _current_top is top:
            _current_top = None