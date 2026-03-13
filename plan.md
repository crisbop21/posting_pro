# Background Optimization Pipeline — Implementation Plan

## Overview

Enhance Step 4 (Background Generation) to support 4 background modes with Claude-powered auto-recommendation, per-style color grading, and improved Ken Burns variety.

---

## Files to Create

### 1. `skills/background_skill.md`
New skill file injected into Claude API calls for background optimization.

**Contents:**
- System prompt that receives the script text and visual style
- Instructions to analyze the script and recommend the best background mode:
  - `ai_generated` — for abstract, futuristic, or highly stylized topics
  - `stock_broll` — for real-world finance news, market updates, concrete events
  - `green_screen` — for educational explainers, tutorials, step-by-step content
  - `hybrid` — for premium content mixing real footage with AI accents
- Instructions to generate 2-3 Pexels search queries (short, specific, vertical-friendly) for stock_broll and hybrid modes
- Instructions to suggest a Ken Burns direction pattern (e.g., "zoom-in, pan-left, zoom-out")
- Output format: JSON with `recommended_mode`, `pexels_queries`, `ken_burns_pattern`, `reasoning`

---

## Files to Modify

### 2. `utils/state.py`
Add new state keys:
```python
# Step 4 additions
"background_mode": None,          # "ai_generated" | "stock_broll" | "green_screen" | "hybrid"
"background_recommendation": None, # dict from Claude: {recommended_mode, pexels_queries, ken_burns_pattern, reasoning}
"background_color_grade": None,    # auto-set from visual_style
```

### 3. `utils/styles.py`
Expand each style in `VISUAL_STYLES` with:
```python
"color_grade": {
    "brightness": 0.0,     # -1.0 to 1.0
    "contrast": 1.0,       # 0.5 to 2.0
    "saturation": 1.0,     # 0.0 to 3.0
    "warmth": 0.0,         # -1.0 (cool) to 1.0 (warm)
    "vignette": False,     # boolean
}
```

Style-specific presets:
- **Cinematic**: contrast 1.3, saturation 0.85, warmth -0.1 (cool tones), vignette true
- **Clean**: brightness 0.1, contrast 1.0, saturation 0.9, warmth 0.05
- **Vintage**: saturation 0.7, warmth 0.3, contrast 1.1, vignette true
- **Dynamic**: contrast 1.4, saturation 1.3, warmth -0.15

Add `available_modes` list to each style (all 4 modes available for all styles).

### 4. `utils/video_utils.py`
Add new functions:

#### `apply_color_grade(input_path, output_path, grade_params) -> str`
- Build FFmpeg `eq` filter chain from grade params (brightness, contrast, saturation)
- Apply `colortemperature` filter for warmth
- Apply `vignette` filter if enabled
- Return output path

#### `crop_to_vertical(input_path, output_path, target_w=1080, target_h=1920) -> str`
- Detect source dimensions with ffprobe
- Calculate center crop for 9:16 from landscape footage
- Apply FFmpeg crop + scale filter
- Return output path

#### Enhanced `render_ken_burns()`
- Add `direction` parameter: "zoom_in" (default/current), "zoom_out", "pan_left", "pan_right"
- Implement each variant using FFmpeg zoompan filter with different x/y/zoom expressions
- Support a `directions` list to cycle through for multi-segment backgrounds

### 5. `pipeline/background.py`
Refactor `run()` into a dispatcher with 4 mode handlers:

#### `_recommend_mode(state) -> dict`
- Call Claude API with background_skill.md as system prompt
- Pass script text and visual style
- Parse JSON response: {recommended_mode, pexels_queries, ken_burns_pattern, reasoning}
- Store in `state["background_recommendation"]`

#### `_generate_ai_background(state) -> str` (existing logic, extracted)
- Current DALL-E generation path
- Apply color grade after Ken Burns render
- Return video path

#### `_fetch_stock_broll(state) -> str`
- Use pexels_queries from recommendation to search Pexels Videos API
- Download best match (highest resolution, orientation=portrait preferred)
- Crop to 9:16 if needed
- Apply color grade
- Apply Ken Burns with direction variety
- Return video path

#### `_render_green_screen(state) -> str`
- Generate a solid or gradient background using FFmpeg (color based on visual style)
- Optionally add subtle animated particles/grain using FFmpeg filters
- Apply color grade
- Return video path

#### `_build_hybrid(state) -> str`
- Fetch stock B-roll base (reuse _fetch_stock_broll logic)
- Generate AI accent layer via DALL-E (smaller, overlay-style)
- Composite accent over stock base with transparency
- Apply color grade
- Return video path

#### Updated `run(state) -> dict`
1. Get recommendation from Claude (if not already cached)
2. Use `state["background_mode"]` if user overrode, else use recommendation
3. Dispatch to the appropriate handler
4. Set `state["background_video_path"]`
5. Return state

### 6. `app.py` — Step 4 UI Updates
After the visual style radio, add:

1. **"Analyze Script" button** — calls `_recommend_mode()` and shows Claude's recommendation with reasoning
2. **Background mode selector** — `st.radio` with 4 options, pre-selected to Claude's recommendation
3. **Override info** — if user picks a different mode, show a subtle note
4. Keep existing "Generate Background" button that now dispatches to the selected mode
5. Show Pexels query preview for stock_broll/hybrid modes so user can tweak

### 7. `utils/api_clients.py`
No changes needed — Pexels client already exists for image search. We'll use it for video search too (same API, different endpoint).

---

## Implementation Order

1. `skills/background_skill.md` — write the skill prompt
2. `utils/state.py` — add new state keys
3. `utils/styles.py` — add color grade presets and mode lists
4. `utils/video_utils.py` — add `apply_color_grade`, `crop_to_vertical`, enhance `render_ken_burns`
5. `pipeline/background.py` — refactor with all 4 mode handlers
6. `app.py` — update Step 4 UI
7. Test each mode end-to-end

---

## Risk Notes

- Pexels Video API may return landscape footage — `crop_to_vertical` handles this
- Green screen mode is simplest (no external API calls) — good fallback
- Hybrid mode is most complex — stock fetch + DALL-E + composite — may be slow
- All modes respect the existing error handling pattern (MAX_RETRIES + exponential backoff)
- Color grading adds ~2-3 seconds of FFmpeg processing — acceptable
