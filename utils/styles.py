"""Visual style definitions for background generation.

Each style maps to a DALL-E prompt template (used as fallback) and a style
brief that the background_skill uses to craft a topic-aware prompt via Claude.
"""

VISUAL_STYLES = {
    "cinematic": {
        "label": "Cinematic",
        "description": "Dark, dramatic lighting with extreme contrast — Roger Deakins mood",
        "accent_color": "#FF6B35",  # warm orange — pops against dark cinematic tones
        "style_brief": (
            "Anamorphic lens bokeh, film-grade colour grading, extreme shallow depth "
            "of field, true-black shadows with a single intense light source. "
            "Roger Deakins inspired. Push luminance contrast to the maximum."
        ),
        "dalle_prompt": (
            "A cinematic wide-angle scene with deep true-black shadows and a single "
            "intense warm light source cutting through dark atmosphere. Abstract financial "
            "theme related to {topic}. Volumetric light rays, floating dust particles, "
            "anamorphic lens flare, extreme shallow depth of field. Wet reflective surface "
            "in foreground. 9:16 vertical composition. No text, no words, no letters, "
            "no numbers, no watermarks. No people, no faces, no hands. No logos, "
            "no brand names. Photorealistic, ultra high detail, 8K quality."
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
        "description": "Ultra-minimal dark space with one vivid accent — Apple aesthetic",
        "accent_color": "#00D4FF",  # electric cyan — matches minimal-dark aesthetic
        "style_brief": (
            "Ultra-minimal, geometric precision, dark negative space with a single "
            "intensely vivid accent colour element. Apple product photography aesthetic "
            "in a dark room. Dopamine from precision and colour isolation."
        ),
        "dalle_prompt": (
            "An ultra-minimal dark background with a single vivid geometric accent "
            "element glowing against deep black negative space. Modern and precise, "
            "related to {topic}. One saturated colour pop against monochrome. Glass "
            "or metallic surface texture. 9:16 vertical composition. No text, no words, "
            "no letters, no numbers, no watermarks. No people, no faces, no hands. "
            "No logos, no brand names. Photorealistic, ultra high detail, 8K quality."
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
        "description": "Warm film grain with one Kodachrome colour anomaly — dark academia",
        "accent_color": "#E8C547",  # warm gold — Kodachrome highlight
        "style_brief": (
            "Warm analogue film grain adding tactile texture. Muted earth tones with "
            "one vivid Kodachrome-anomaly accent colour. Slight vignette, nostalgic "
            "warmth. Wes Anderson meets dark academia. Rich material textures."
        ),
        "dalle_prompt": (
            "A vintage-style photograph with rich warm film grain, muted earthy tones, "
            "and a single vivid warm accent light source. Dark wood and leather textures, "
            "soft vignette. Abstract financial theme related to {topic}. Rain on a window "
            "creating bokeh. 9:16 vertical composition. No text, no words, no letters, "
            "no numbers, no watermarks. No people, no faces, no hands. No logos, "
            "no brand names. Photorealistic, ultra high detail, 8K quality."
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
        "description": "Neon energy, impossible geometry — Blade Runner meets data viz",
        "accent_color": "#FF2D78",  # hot magenta — neon energy
        "style_brief": (
            "Maximum energy. Neon light trails, motion blur on particles, electric "
            "colour palette. Impossible geometry, surreal scale distortion. "
            "Blade Runner 2049 meets financial data visualization."
        ),
        "dalle_prompt": (
            "A dynamic futuristic scene with bold neon light trails streaking through "
            "dark geometric architecture. Electric cyan and hot magenta against deep "
            "black. Motion blur energy, floating light particles, surreal scale. "
            "Related to {topic}. Converging lines toward a glowing vanishing point. "
            "9:16 vertical composition. No text, no words, no letters, no numbers, "
            "no watermarks. No people, no faces, no hands. No logos, no brand names. "
            "Photorealistic, ultra high detail, 8K quality."
        ),
    },
    "hypnotic": {
        "label": "Hypnotic",
        "description": "Dreamlike iridescence, infinite depth — deep ocean meets luxury",
        "accent_color": "#A855F7",  # vivid purple — bioluminescent glow
        "style_brief": (
            "Slow, mesmerizing, dreamlike. Iridescent surfaces, oil-on-water colour "
            "shifts, glass refractions, bioluminescent glow. Infinite depth tunnel. "
            "Deep ocean meets luxury brand commercial."
        ),
        "dalle_prompt": (
            "A hypnotic dreamlike scene with iridescent surfaces shifting between "
            "purple, teal, and gold. Oil-on-water colour refraction, bioluminescent "
            "glow emanating from within a deep tunnel-like composition receding to "
            "infinity. Glass and liquid textures, floating luminous particles. "
            "Related to {topic}. 9:16 vertical composition. No text, no words, "
            "no letters, no numbers, no watermarks. No people, no faces, no hands. "
            "No logos, no brand names. Photorealistic, ultra high detail, 8K quality."
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
