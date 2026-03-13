# AI Social Video Pipeline

A fully orchestrated AI pipeline that turns a finance or AI topic into a ready-to-publish short-form vertical video. Built with Streamlit, Claude, ElevenLabs, and DALL-E.

---

## What it does

1. **Gathers data** — fetches live finance news (Marketaux + Finnhub) or researches a custom topic via Claude
2. **Fact-checks** — Claude cross-references claims, flags low-confidence items, and produces a cleaned dataset
3. **Writes a script** — conversational, engaging voiceover script targeting under 2 minutes
4. **Generates a background** — DALL-E image with a Ken Burns pan-and-zoom animation at 9:16
5. **Sources images** — Pexels API for overlay candidates, with per-slot DALL-E swap option
6. **Assembles the video** — FFmpeg + MoviePy composites everything with the ElevenLabs voiceover
7. **Exports** — download the finished MP4 directly from the browser

Every step has a human approval checkpoint before the pipeline continues.

---

## Tech stack

| Layer | Technology |
|---|---|
| UI and deployment | Streamlit |
| AI reasoning | Claude API (claude-sonnet-4-5) |
| Voice synthesis | ElevenLabs API |
| Image generation | DALL-E 3 API |
| Finance news | Marketaux API (free) + Finnhub (free fallback) |
| Image search | Pexels API (free) |
| Video assembly | FFmpeg + MoviePy |
| Image processing | Pillow |

---

## Output format

- Resolution: 1080 x 1920 px (9:16 vertical)
- Duration: under 2 minutes
- Format: MP4 (H.264, web-optimised)

---

## Prerequisites

- Python 3.11 or higher
- FFmpeg installed and on your PATH
- API keys for Claude, ElevenLabs, OpenAI (DALL-E), Marketaux, Finnhub, and Pexels

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/ai-video-pipeline.git
cd ai-video-pipeline
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure secrets

Copy the example secrets file and fill in your keys:

```bash
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Then edit `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "your-key-here"
ELEVENLABS_API_KEY = "your-key-here"
ELEVENLABS_VOICE_ID = "your-voice-id-here"
OPENAI_API_KEY = "your-key-here"
MARKETAUX_API_KEY = "your-key-here"
FINNHUB_API_KEY = "your-key-here"
PEXELS_API_KEY = "your-key-here"
```

> **Never commit `.streamlit/secrets.toml` to version control.** It is already listed in `.gitignore`.

### 4. Run the app

```bash
streamlit run app.py
```

---

## Project structure

```
ai-video-pipeline/
├── app.py                        # Main entry point and state router
├── pipeline/
│   ├── gather.py                 # Step 1: data gathering (news + custom topic)
│   ├── factcheck.py              # Step 2: fact-checking via Claude
│   ├── script.py                 # Step 3: script generation
│   ├── background.py             # Step 4: Ken Burns background generation
│   ├── images.py                 # Step 5: image sourcing and management
│   ├── assemble.py               # Step 6: video assembly
│   └── export.py                 # Step 7: download and export
├── skills/
│   ├── script_skill.md           # Claude system prompt for script writing
│   ├── composition_skill.md      # Rules for image composition in video
│   └── factcheck_prompt.md       # Claude system prompt for fact-checking
├── utils/
│   ├── api_clients.py            # Initialised API client instances
│   ├── state.py                  # Session state schema
│   ├── video_utils.py            # Ken Burns renderer and FFmpeg compositor
│   └── image_utils.py            # Pexels image fetching and processing
├── .streamlit/
│   ├── secrets.toml              # Your API keys (gitignored)
│   └── secrets.example.toml     # Template to copy from
├── requirements.txt
├── CLAUDE.md                     # Instructions for Claude Code
└── README.md
```

---

## API keys — where to get them

| API | Free tier | Link |
|---|---|---|
| Anthropic Claude | Pay per token | [console.anthropic.com](https://console.anthropic.com) |
| ElevenLabs | Free tier available | [elevenlabs.io](https://elevenlabs.io) |
| OpenAI (DALL-E) | Pay per image | [platform.openai.com](https://platform.openai.com) |
| Marketaux | Free, no card required | [marketaux.com](https://marketaux.com) |
| Finnhub | Free, no card required | [finnhub.io](https://finnhub.io) |
| Pexels | Free, no card required | [pexels.com/api](https://pexels.com/api) |

---

## Topic modes

| Mode | Description |
|---|---|
| Live finance news | Fetches headlines from the last 24 hours via Marketaux, falls back to Finnhub |
| Custom topic | Enter any finance or AI topic and Claude researches it |
| Mode 3 (TBD) | Reserved — see open items in technical brief |

---

## Pipeline approval flow

Each step requires explicit approval before the next step runs. You can regenerate any step without losing progress on approved steps above it.

```
[Gather data] → approve → [Fact-check] → approve → [Write script] → approve
      → [Generate background] → approve → [Source images] → approve
      → [Assemble video] → approve → [Download]
```

---

## Development

### Build order

Follow the phase order in the implementation plan. Each phase produces a working slice before the next begins.

| Phase | Focus |
|---|---|
| P1 | Scaffold and environment setup |
| P2 | Data gathering |
| P3 | Fact-checking |
| P4 | Script generation |
| P5 | Ken Burns background |
| P6 | Image sourcing |
| P7 | Video assembly |
| P8 | UI development and optimisation |
| P9 | Deployment |

### Running tests

```bash
python -m pytest tests/
```

### Linting

```bash
ruff check .
```

---

## Deployment

### Streamlit Community Cloud

1. Push to GitHub
2. Connect repo at [share.streamlit.io](https://share.streamlit.io)
3. Add all secrets in the Streamlit Cloud secrets panel
4. Check render time — if video assembly exceeds ~45 seconds, move to a private VPS

### Private VPS

See the deployment section of the implementation plan for nginx + systemd setup instructions.

---

## Known limitations

- Video render time scales with script length. Target under 2 minutes of audio.
- Pexels image search works best with specific 3 to 5 word queries. Niche finance terms may return limited results and fall back to DALL-E.
- Marketaux free tier has a daily request cap. Finnhub is used automatically as a fallback.

---

## License

MIT
