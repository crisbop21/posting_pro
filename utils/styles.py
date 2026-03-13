"""Visual style definitions for background generation.

Each style maps to a DALL-E prompt template, color grade parameters,
and available background modes. The {topic} placeholder is replaced
at runtime with the video's topic string.
"""

VISUAL_STYLES = {
    "cinematic": {
        "label": "Cinematic",
        "description": "Dark, dramatic lighting with rich contrast and depth of field",
        "dalle_prompt": (
            "A cinematic wide-angle photograph with dramatic lighting, deep shadows, "
            "and rich warm-cool contrast. Abstract financial theme related to {topic}. "
            "Shallow depth of field, anamorphic lens flare, 9:16 vertical composition. "
            "No text, no people, no logos."
        ),
        "color_grade": {
            "brightness": 0.0,
            "contrast": 1.3,
            "saturation": 0.85,
            "warmth": -0.1,
            "vignette": True,
        },
        "green_screen_colors": ("#0a0a1a", "#1a1a3a"),
    },
    "clean": {
        "label": "Clean",
        "description": "Minimal, bright, modern design with soft gradients",
        "dalle_prompt": (
            "A clean, minimal abstract background with soft pastel gradients and "
            "geometric shapes. Modern corporate feel related to {topic}. Bright, airy "
            "lighting, 9:16 vertical composition. No text, no people, no logos."
        ),
        "color_grade": {
            "brightness": 0.1,
            "contrast": 1.0,
            "saturation": 0.9,
            "warmth": 0.05,
            "vignette": False,
        },
        "green_screen_colors": ("#f0f4f8", "#dce6f0"),
    },
    "vintage": {
        "label": "Vintage",
        "description": "Warm film grain look with muted tones",
        "dalle_prompt": (
            "A vintage-style photograph with warm film grain, muted earthy tones, and "
            "subtle vignette. Abstract financial or technology theme related to {topic}. "
            "Analog film aesthetic, 9:16 vertical composition. No text, no people, "
            "no logos."
        ),
        "color_grade": {
            "brightness": 0.0,
            "contrast": 1.1,
            "saturation": 0.7,
            "warmth": 0.3,
            "vignette": True,
        },
        "green_screen_colors": ("#2a2018", "#3d2e1e"),
    },
    "dynamic": {
        "label": "Dynamic",
        "description": "Bold colours, motion blur, energetic feel",
        "dalle_prompt": (
            "A dynamic abstract background with bold neon colours, motion blur streaks, "
            "and energetic geometric patterns. Futuristic tech and finance theme related "
            "to {topic}. High energy, 9:16 vertical composition. No text, no people, "
            "no logos."
        ),
        "color_grade": {
            "brightness": 0.0,
            "contrast": 1.4,
            "saturation": 1.3,
            "warmth": -0.15,
            "vignette": False,
        },
        "green_screen_colors": ("#0a001a", "#1a0033"),
    },
}

BACKGROUND_MODES = {
    "ai_generated": {
        "label": "AI Generated",
        "description": "DALL-E abstract image with Ken Burns animation",
    },
    "stock_broll": {
        "label": "Stock B-Roll",
        "description": "Real Pexels footage, cropped vertical, color graded",
    },
    "green_screen": {
        "label": "Green Screen",
        "description": "Solid/gradient background for overlay-focused content",
    },
    "hybrid": {
        "label": "Hybrid",
        "description": "Stock footage base with AI-generated accent layer",
    },
}
