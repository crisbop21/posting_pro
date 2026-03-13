"""Visual style definitions for Ken Burns background generation.

Each style maps to a DALL-E prompt template (used as fallback) and a style
brief that the background_skill uses to craft a topic-aware prompt via Claude.
"""

VISUAL_STYLES = {
    "cinematic": {
        "label": "Cinematic",
        "description": "Dark, dramatic lighting with rich contrast and depth of field",
        "style_brief": (
            "Dramatic lighting, anamorphic lens character, film-grade colour grading, "
            "shallow depth of field, high contrast."
        ),
        "dalle_prompt": (
            "A cinematic wide-angle photograph with dramatic lighting, deep shadows, "
            "and rich warm-cool contrast. Abstract financial theme related to {topic}. "
            "Shallow depth of field, anamorphic lens flare, 9:16 vertical composition. "
            "No text, no people, no logos."
        ),
    },
    "clean": {
        "label": "Clean",
        "description": "Minimal, bright, modern design with soft gradients",
        "style_brief": (
            "Minimal, modern, soft gradients, geometric precision, airy and bright, "
            "editorial quality."
        ),
        "dalle_prompt": (
            "A clean, minimal abstract background with soft pastel gradients and "
            "geometric shapes. Modern corporate feel related to {topic}. Bright, airy "
            "lighting, 9:16 vertical composition. No text, no people, no logos."
        ),
    },
    "vintage": {
        "label": "Vintage",
        "description": "Warm film grain look with muted tones",
        "style_brief": (
            "Warm analogue film tones, subtle grain, muted palette, slight vignette, "
            "nostalgic warmth."
        ),
        "dalle_prompt": (
            "A vintage-style photograph with warm film grain, muted earthy tones, and "
            "subtle vignette. Abstract financial or technology theme related to {topic}. "
            "Analog film aesthetic, 9:16 vertical composition. No text, no people, "
            "no logos."
        ),
    },
    "dynamic": {
        "label": "Dynamic",
        "description": "Bold colours, motion blur, energetic feel",
        "style_brief": (
            "Bold neon accents, motion-blur energy, futuristic geometry, high saturation, "
            "electric atmosphere."
        ),
        "dalle_prompt": (
            "A dynamic abstract background with bold neon colours, motion blur streaks, "
            "and energetic geometric patterns. Futuristic tech and finance theme related "
            "to {topic}. High energy, 9:16 vertical composition. No text, no people, "
            "no logos."
        ),
    },
}
