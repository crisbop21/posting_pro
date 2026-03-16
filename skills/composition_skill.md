# Video Composition Skill

Rules for compositing overlay images onto the Ken Burns background video. These constraints must be followed exactly by the assembly pipeline.

## Canvas

- Resolution: **1080 x 1920 px** (9:16 vertical)
- Frame rate: 30 fps
- Colour space: yuv420p

## Background

- The Ken Burns loop (slow pan-and-zoom on a DALL-E generated image) must match or exceed the total audio duration.
- If the background is shorter than the audio, loop it seamlessly.

## Background treatment

- The background video is **darkened** before any overlays are composited on top.
- Brightness is reduced by 15% (`eq=brightness=-0.15`) and saturation by 15% (`saturation=0.85`).
- This creates clear depth separation between the background layer and foreground overlays.
- Darkening is applied even when there are no image overlays, to maintain consistent visual tone.

## Overlay images

- **Maximum width**: 85% of canvas width = **918 px**. Scale down proportionally if wider.
- **Rounded corners**: 24 px radius on all four corners.
- **Drop shadow**: 8 px offset, black at 30% opacity, Gaussian blur radius 8 px.
- **Horizontal position**: Always centred (`x = (1080 - image_width) / 2`).
- **Vertical position**: Centre the overlay in the safe zone (top of canvas to 300 px above the bottom). The vertical centre of the safe zone is `(1920 - 300) / 2 = 810 px`.
- **Bottom 300 px**: Reserved for captions/subtitles and TikTok UI elements (username, description, music bar). No overlay may extend into this zone.

## Overlay timing

- **Beat map**: When available, overlay timing is driven by a beat map generated alongside the script. The beat map uses percentage-based positions (0.0–1.0 of total duration) that are converted to absolute seconds at assembly time using the actual audio duration.
- **Fallback**: When no beat map is available, overlays are distributed evenly across the video duration.
- **First overlay (hook frame)**: Appears at t=0 with a **hard cut** (no fade-in). This ensures the viewer sees visual content immediately — no empty background frames on scroll.
- **Fade in** (subsequent overlays): 0.4 seconds (linear alpha ramp from 0 to 1).
- **Fade out**: 0.3 seconds (linear alpha ramp from 1 to 0).
- **Minimum on-screen duration**: 4 seconds (including fades).
- **Maximum on-screen duration**: 18 seconds.
- **Gap between overlays**: At least 0.5 seconds of background-only between consecutive overlays.

## Accent text overlays

- Key phrases marked with `**double asterisks**` in the script are rendered as accent text overlays.
- Each accent phrase is drawn in the style's **accent colour** on a semi-transparent dark pill background (rounded rectangle, ~70% opacity black).
- Font: bold sans-serif, 64–68 px. Text wraps at 920 px max width.
- **Position**: Centred horizontally in the caption zone (bottom 300 px). Vertically placed 30 px below the top of the caption zone.
- **Timing**: Accent overlays are spaced evenly across the video duration. Each displays for ~3 seconds.
- **Fade in**: 0.3 seconds. **Fade out**: 0.25 seconds.
- **Z-order**: Accent text is composited on top of all other layers (background, image overlays).
- **Gap-filling**: When an accent text clip falls during a gap between image overlays (no image on screen), it is promoted from the caption zone to the **centre of the safe zone** (where images normally appear). This ensures there is always visual activity on screen. When an image overlay is showing, accent text stays in the caption zone.
- Accent overlays are stripped from the voiceover text before TTS generation — they are visual-only.

## Title text overlay

- An optional **title card** is rendered as the topmost text layer during the video intro.
- The title is drawn in white (default) on a semi-transparent dark pill background (rounded rectangle, ~63% opacity).
- Font: bold sans-serif, 80 px. Text wraps at 900 px max width.
- **Position**: Centred horizontally, placed at ~18% from the top of the safe zone (above the caption area).
- **Timing**: Appears at 0.0 seconds (instant hook — no delay), displays for ~4 seconds by default.
- **Fade in**: None (hard cut for immediate visual impact). **Fade out**: 0.4 seconds.
- **Z-order**: Above image overlays, below accent text overlays.
- The title text is user-editable and auto-populated from the topic. It can be disabled entirely.

## Audio

- Voiceover audio track from ElevenLabs is the master clock.
- The video duration equals the audio duration.
- Audio codec: AAC at 192 kbps.

## Encoding

- Video codec: `libx264`
- CRF: `23`
- Output must include `-movflags faststart` for web streaming.
- Container: MP4

## Output naming

```
outputs/{topic-slug}-{YYYYMMDD}.mp4
```

Slug rules: lowercase, spaces to hyphens, max 40 characters, strip all special characters.
