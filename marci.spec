# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Marci Voice Agent.
Builds a single-file, windowed (no console) executable bundling:
- vosk model (vosk-model-small-ru-0.22)
- sounds/  (mp3 voice lines)
- images/  (popup images)
Build with:  pyinstaller marci.spec --noconfirm --clean
Result:      dist/Marci.exe
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

datas = [
    ("vosk-model-small-ru-0.22", "vosk-model-small-ru-0.22"),
    ("sounds", "sounds"),
    ("images", "images"),
]
datas += collect_data_files("vosk")
binaries = collect_dynamic_libs("vosk")

hiddenimports = [
    "vosk", "cffi", "numpy", "pygame", "pyaudio",
    "speech_recognition", "PIL", "PIL.Image", "PIL.ImageTk",
    "requests", "urllib3", "certifi",
]

EXCLUDES = [
    "transformers", "tokenizers", "sentencepiece", "huggingface_hub",
    "datasets", "accelerate", "safetensors",
    "torch", "torchvision", "torchaudio", "torchmetrics",
    "pytorch_lightning", "lightning",
    "tensorflow", "keras",
    "scipy", "sympy", "pandas", "matplotlib", "seaborn", "plotly",
    "statsmodels", "scikit_learn", "sklearn", "numba", "llvmlite",
    "cv2", "opencv", "onnxruntime", "tflite_runtime", "ml_dtypes",
    "xarray", "bottleneck", "numexpr", "tables",
    "wandb", "mlflow", "tensorboard",
    "boto3", "botocore", "s3transfer", "awscli",
    "av", "pyarrow",
    "hydra", "omegaconf", "antlr4", "gevent", "zope", "zope.interface",
    "sentry_sdk", "rich", "fsspec", "s3fs", "gcsfs", "adlfs",
    "yt_dlp", "mutagen", "brotli", "secretstorage", "curl_cffi",
    "lxml", "pygments", "psutil", "pytz", "tzdata",
    "setuptools", "pkg_resources", "pip",
    "sounddevice", "soundfile", "audioread", "pydub",
    "imageio", "imageio_ffmpeg", "moviepy", "ffmpy",
    "spacy", "nltk", "gensim", "textblob", "pattern",
    "thinc", "blis", "wasabi", "srsly", "langcodes",
    "preshed", "catalogue", "typer", "shellingham", "smart_open",
    "Cython", "IPython", "jupyter", "jedi", "parso", "debugpy",
    "cryptography", "pyopenssl", "OpenSSL", "nacl", "bcrypt",
    "paramiko",
    "win32com", "pythoncom", "pywintypes",
    "win32api", "win32con", "win32file", "win32gui",
    "win32process", "win32security",
    "pydantic", "pydantic_core",
    "test", "distutils", "ensurepip", "venv", "idlelib",
    "lib2to3", "turtledemo",
]

a = Analysis(
    ["marci_agent.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Marci",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="marci.ico",
)