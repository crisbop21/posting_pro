# Video Composition Skill

Rules for compositing overlay images onto the Ken Burns background video. These constraints must be followed exactly by the assembly pipeline.

## Canvas

- Resolution: **1080 x 1920 px** (9:16 vertical)
- Frame rate: 30 fps
- Colour space: yuv420p

## Background

- The Ken Burns loop (slow pan-and-zoom on a DALL-E generated image) must match or exceed the total audio duration.
- If the background is shorter than the audio, loop it seamlessly.

## Overlay images

- **Maximum width**: 85% of canvas width = **918 px**. Scale down proportionally if wider.
- **Rounded corners**: 24 px radius on all four corners.
- **Drop shadow**: 8 px offset, black at 30% opacity, Gaussian blur radius 8 px.
- **Horizontal position**: Always centred (`x = (1080 - image_width) / 2`).
- **Vertical position**: Centre the overlay in the safe zone (top of canvas to 200 px above the bottom). The vertical centre of the safe zone is `(1920 - 200) / 2 = 860 px`.
- **Bottom 200 px**: Reserved for captions/subtitles. No overlay may extend into this zone.

## Overlay timing

- **Fade in**: 0.4 seconds (linear alpha ramp from 0 to 1).
- **Fade out**: 0.3 seconds (linear alpha ramp from 1 to 0).
- **Minimum on-screen duration**: 4 seconds (including fades).
- **Maximum on-screen duration**: 18 seconds.
- **Gap between overlays**: At least 0.5 seconds of background-only between consecutive overlays.

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
