# 🎤 Marci Voice Agent — Talking Ben Style

Like "My Talking Ben" but with Marci from Dota 2!

## How it works

1. Marci sits idle, listening
2. Say **"Марси"** (wake word)
3. Marci perks up (wake sound)
4. Say anything — Marci reacts with a random voice line
5. Back to idle

Simple. Lightweight. No heavy models.

## Install

```bash
pip install SpeechRecognition pyaudio pygame
```

## Run

```bash
python marci_agent.py
```

## Sounds

Put MP3 files in `sounds/` folder. Current sounds:

| Intent | Files |
|--------|-------|
| wake | Vo_marci_marci_move.mp3, _2.mp3, _3.mp3 |
| deny | Vo_marci_marci_deny.mp3 |
| immortality | Vo_marci_marci_immortality.mp3 |
| laugh | Vo_marci_marci_laugh.mp3 |
| move | Vo_marci_marci_move.mp3, _2.mp3, _3.mp3 |
| damage | Vo_marci_marci_taking_damage.mp3 |
| thanks | Vo_marci_marci_thanks.mp3 |

## Reactions

**Pure random!** Just like Talking Ben — Marci reacts with a random voice line every time, no matter what you say.
