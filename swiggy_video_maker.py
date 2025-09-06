#!/usr/bin/env python3
"""
Swiggy Instamart – Automated 2:1 Product Video Builder
- Reads an Excel sheet for slide copy + associated image filenames
- Renders up to N slides, 5s each, image enters from right, text enters from left
- Adds brand logo (top-right by default)
- Optional background removal (uses `rembg` if installed)
- Optional blur screening (requires OpenCV)
- Exports H.264 MP4 via ffmpeg through MoviePy
"""

import os, sys, math, io, json, textwrap
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import pandas as pd

# MoviePy
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, VideoFileClip
from moviepy.video.fx.all import resize as mp_resize

# Optional deps
try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None

try:
    import cv2
except Exception:
    cv2 = None

import yaml

def load_cfg(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0,2,4))

def ensure_font(path, fallback_bold=False):
    # Attempt to load font at path; fallback to DejaVuSans
    try:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=10)  # size overridden later
    except Exception:
        pass
    # Fallback – PIL bundled font (DejaVu)
    try:
        fallback = "DejaVuSans-Bold.ttf" if fallback_bold else "DejaVuSans.ttf"
        return ImageFont.truetype(fallback, size=10)
    except Exception:
        # Last resort
        return ImageFont.load_default()

def apply_title_case(s, style="standard"):
    s = (s or "").strip()
    if style == "upper":
        return s.upper()
    if style == "sentence":
        return s[:1].upper() + s[1:]
    return s  # standard – no forced transform

def clamp_words(s, max_words):
    toks = (s or "").split()
    return " ".join(toks[:max_words])

def detect_blur_variance(im: Image.Image) -> float:
    if cv2 is None:
        return 1e9  # if no cv2, pretend it's sharp
    arr = np.array(im.convert("L"))
    return cv2.Laplacian(arr, cv2.CV_64F).var()

def remove_bg_if_possible(im: Image.Image) -> Image.Image:
    if rembg_remove is None:
        return im
    try:
        out = rembg_remove(im)
        if isinstance(out, (bytes, bytearray)):
            return Image.open(io.BytesIO(out)).convert("RGBA")
        return out.convert("RGBA")
    except Exception:
        return im

def upscale_min_side(im: Image.Image, min_side: int) -> Image.Image:
    w, h = im.size
    if min(w, h) >= min_side:
        return im
    scale = min_side / min(w, h)
    new = (int(w*scale), int(h*scale))
    return im.resize(new, Image.LANCZOS)

def render_text_panel(text_title, bullets, cfg, fonts):
    W, H = cfg["frame_width"], cfg["frame_height"]
    left_ratio = cfg["left_panel_ratio"]
    panel_w = int(W * left_ratio)
    panel_h = H
    pad = cfg["edge_padding_px"]
    title_fs = cfg["title_font_size_px"]
    body_fs  = cfg["body_font_size_px"]
    line_gap = cfg["text_line_spacing_px"]
    bullet_color = hex_to_rgb(cfg["bullet_color_hex"])

    # Create transparent RGBA
    canvas = Image.new("RGBA", (panel_w, panel_h), (255,255,255,0))
    draw = ImageDraw.Draw(canvas)

    # Title
    title_font = ImageFont.truetype(fonts["title"].path, title_fs) if hasattr(fonts["title"], "path") else ImageFont.truetype("DejaVuSans-Bold.ttf", title_fs) if fonts["title"].__class__.__name__ != "ImageFont" else fonts["title"]
    body_font  = ImageFont.truetype(fonts["body"].path, body_fs) if hasattr(fonts["body"], "path") else ImageFont.truetype("DejaVuSans.ttf", body_fs) if fonts["body"].__class__.__name__ != "ImageFont" else fonts["body"]

    y = pad
    # Wrap title if needed
    title = apply_title_case(text_title, cfg.get("title_case_style","standard"))
    # simple wrap based on width
    def wrap_text(txt, font, max_w):
        words = txt.split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            bw, _ = draw.textsize(test, font=font)
            if bw <= max_w - pad*2:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    title_lines = wrap_text(title, title_font, panel_w - 2*pad)
    for line in title_lines:
        draw.text((pad, y), line, fill=(0,0,0,255), font=title_font)
        tw, th = draw.textsize(line, font=title_font)
        y += th + line_gap

    y += line_gap

    # Bullets
    for b in bullets:
        if not b: 
            continue
        b = clamp_words(b, cfg["text_max_words_per_bullet"])
        arrow = "➤"
        # draw arrow
        draw.text((pad, y), arrow, fill=bullet_color + (255,), font=body_font)
        aw, ah = draw.textsize(arrow, font=body_font)
        # bullet text
        draw.text((pad + aw + 18, y), b, fill=(0,0,0,255), font=body_font)
        _, th = draw.textsize(b, font=body_font)
        y += max(ah, th) + line_gap

    return canvas

def paste_logo(frame_im: Image.Image, logo_im: Image.Image, cfg):
    margin = cfg["logo_margin_px"]
    W, H = frame_im.size
    lw, lh = logo_im.size
    scale = min(1.0, (W*0.18)/lw)  # cap logo to ~18% width
    if scale != 1.0:
        logo_im = logo_im.resize((int(lw*scale), int(lh*scale)), Image.LANCZOS)
        lw, lh = logo_im.size

    pos = cfg["logo_position"]
    x = W - lw - margin if pos == "top_right" else margin
    y = margin
    frame_im.alpha_composite(logo_im, (int(x), int(y)))

def ribbon_text(frame_im: Image.Image, txt: str, cfg):
    if not txt: return
    draw = ImageDraw.Draw(frame_im)
    W, H = frame_im.size
    pad = 12
    # simple top-left ribbon
    box_w = int(W*0.28)
    box_h = 64
    box = Image.new("RGBA", (box_w, box_h), (0,0,0,122))
    frame_im.alpha_composite(box, (cfg["safe_area_inset_px"], H - box_h - cfg["safe_area_inset_px"]))
    # text over it
    font = ensure_font(cfg.get("font_body_path") or "", fallback_bold=False)
    font = ImageFont.truetype(getattr(font,"path","DejaVuSans.ttf"), 36)
    draw = ImageDraw.Draw(frame_im)
    draw.text((cfg["safe_area_inset_px"] + pad, H - box_h - cfg["safe_area_inset_px"] + pad),
              txt, fill=(255,255,255,255), font=font)

def build_slide_clip(img_path, title, bullets, cfg, fonts, logo_rgba):
    W, H = cfg["frame_width"], cfg["frame_height"]
    left_ratio = cfg["left_panel_ratio"]
    panel_w = int(W * left_ratio)
    panel_h = H

    # Base frame (white)
    bg = Image.new("RGBA", (W, H), hex_to_rgb(cfg["background_color"]) + (255,))

    # Text panel (left), animated from left
    panel_im = render_text_panel(title, bullets, cfg, fonts)
    panel_clip = ImageClip(np.array(panel_im)).set_duration(cfg["duration_per_slide"])

    # Product image (right), animated from right
    try:
        im = Image.open(img_path).convert("RGBA")
    except Exception as e:
        # placeholder block if image missing
        im = Image.new("RGBA", (800, 800), (230,230,230,255))
        d = ImageDraw.Draw(im)
        d.text((40,40), f"Missing image:\n{Path(img_path).name}", fill=(80,80,80,255))

    # optional blur check
    if cfg.get("skip_if_blurry", False):
        try:
            variance = detect_blur_variance(im)
            if variance < 30:  # heuristic
                print(f"[warn] {img_path} looks blurry (var={variance:.1f}). Keeping, but you may want to replace.")
        except Exception:
            pass

    # bg removal if possible
    if cfg.get("remove_bg", True):
        im = remove_bg_if_possible(im)

    # upscale if too small
    im = upscale_min_side(im, cfg.get("upscale_to_min_side_px", 1000))

    # Fit into right pane (half width, maintain aspect, add padding)
    avail_w = W - panel_w - cfg["safe_area_inset_px"]*2
    avail_h = H - cfg["safe_area_inset_px"]*2
    iw, ih = im.size
    scale = min(avail_w/iw, avail_h/ih)
    new_size = (int(iw*scale), int(ih*scale))
    im_resized = im.resize(new_size, Image.LANCZOS)

    # Compose static base image for the slide mid-state (used for logo + ribbons snapshot)
    composed = bg.copy()
    # paste panel at x=0
    composed.alpha_composite(panel_im, (0,0))

    # compute right area position
    rx = panel_w + (avail_w - new_size[0])//2 + cfg["safe_area_inset_px"]
    ry = (H - new_size[1])//2
    composed.alpha_composite(im_resized, (rx, ry))

    # optional dimension/capacity ribbon
    # (We pass bullets[0] as placeholder for overlay; but use dedicated fields when provided by caller)
    # Ribbons are added later by caller via post_fn when needed.

    # add logo
    if logo_rgba is not None:
        paste_logo(composed, logo_rgba.copy(), cfg)

    # Turn composed RGBA into clip with animations:
    base_clip = ImageClip(np.array(composed)).set_duration(cfg["duration_per_slide"])

    # For entrance animations, we'll animate position of panel and product separately on top of a white canvas
    # Panel from left
    panel_anim = ImageClip(np.array(panel_im)).set_duration(cfg["duration_per_slide"])
    # Product anim
    prod_anim  = ImageClip(np.array(im_resized)).set_duration(cfg["duration_per_slide"])

    # motion functions (first 0.6s easing)
    def ease_out_cubic(t, d=0.6):
        if t >= d: return 1.0
        p = (t/d) - 1.0
        return p*p*p + 1

    def panel_pos(t):
        x = int(-panel_w + ease_out_cubic(t)*panel_w)
        y = 0
        return (x, y)

    def prod_pos(t):
        x0 = W  # offscreen right
        x1 = rx
        x = int(x0 + (x1 - x0)*ease_out_cubic(t))
        y = ry
        return (x, y)

    canvas = ImageClip(np.array(bg)).set_duration(cfg["duration_per_slide"])
    comp = CompositeVideoClip([
        canvas,
        panel_anim.set_position(panel_pos),
        prod_anim.set_position(prod_pos),
        # Logo as static overlay (no animation)
        ImageClip(np.array(logo_rgba)).set_position(
            (lambda t: (W - logo_rgba.size[0] - cfg["logo_margin_px"], cfg["logo_margin_px"]))
        ).set_duration(cfg["duration_per_slide"]) if logo_rgba is not None else None,
    ].__iter__())

    return comp

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()

    cfg = load_cfg(args.config)

    W, H = int(cfg["frame_width"]), int(cfg["frame_height"])
    fps = int(cfg["fps"])
    per = float(cfg["duration_per_slide"])
    max_slides = int(cfg["max_slides"])
    left_ratio = float(cfg["left_panel_ratio"])

    # Fonts
    title_font = ensure_font(cfg.get("font_title_path") or "", fallback_bold=True)
    body_font  = ensure_font(cfg.get("font_body_path") or "", fallback_bold=False)
    fonts = {"title": title_font, "body": body_font}

    # Logo
    logo_rgba = None
    if cfg.get("logo_path") and Path(cfg["logo_path"]).exists():
        logo_rgba = Image.open(cfg["logo_path"]).convert("RGBA")
    else:
        print("[info] No logo found at", cfg.get("logo_path"))

    # Data
    df = pd.read_excel(cfg["excel_path"])
    img_root = Path(cfg["images_folder"])

    slides = []
    for i, row in df.iterrows():
        if len(slides) >= max_slides:
            break
        if str(row.get(cfg.get("skip_col","skip"), "")).strip().lower() in {"1","true","yes","y"}:
            continue
        image_file = str(row.get(cfg["image_col"], "")).strip()
        if not image_file:
            continue
        # skip barcode-ish filenames
        lowered = image_file.lower()
        if any(k in lowered for k in cfg.get("barcode_filename_keywords", [])):
            print(f"[skip] looks like barcode image: {image_file}")
            continue
        img_path = img_root / image_file

        title = str(row.get(cfg["title_col"], "")).strip()
        bullets = []
        for col in cfg["bullets_cols"]:
            val = str(row.get(col, "")).strip()
            if val:
                bullets.append(val)

        clip = build_slide_clip(
            img_path, title, bullets, cfg, fonts, logo_rgba
        )

        # add dimension/capacity ribbons if provided
        dim_txt = str(row.get(cfg.get("dimensions_col",""), "")).strip()
        cap_txt = str(row.get(cfg.get("capacity_col",""), "")).strip()
        overlay_txt = " • ".join([t for t in [cap_txt, dim_txt] if t])
        if overlay_txt and cfg.get("dimension_marking", True):
            # Render a quick overlay by compositing a semi-transparent ribbon on each frame.
            # We'll do this by creating a small clip of the ribbon area and placing it.
            W, H = int(cfg["frame_width"]), int(cfg["frame_height"])
            base = Image.new("RGBA", (W, H), (0,0,0,0))
            # draw ribbon on base
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(base)
            box_w = int(W*0.28); box_h = 64
            x = cfg["safe_area_inset_px"]; y = H - box_h - cfg["safe_area_inset_px"]
            draw.rectangle([x, y, x+box_w, y+box_h], fill=(0,0,0,122))
            font = ensure_font(cfg.get("font_body_path") or "", fallback_bold=False)
            try:
                font = ImageFont.truetype(getattr(font,"path","DejaVuSans.ttf"), 36)
            except Exception:
                pass
            draw.text((x+12, y+12), overlay_txt, fill=(255,255,255,255), font=font)
            ribbon_clip = ImageClip(np.array(base)).set_duration(cfg["duration_per_slide"])
            clip = CompositeVideoClip([clip, ribbon_clip])

        slides.append(clip)

    if not slides:
        print("No slides to render. Check your Excel and image paths.")
        sys.exit(1)

    video = CompositeVideoClip(slides).set_duration(per*len(slides))

    # Audio
    if cfg.get("music_path") and Path(cfg["music_path"]).exists():
        audio = AudioFileClip(cfg["music_path"])
        # loop/trim to match video
        if audio.duration < video.duration:
            loops = math.ceil(video.duration / audio.duration)
            from moviepy.editor import concatenate_audioclips
            audio = concatenate_audioclips([audio] * loops)
        audio = audio.subclip(0, video.duration).volumex(0.9)
        video = video.set_audio(audio)

    # Export
    out = cfg.get("output_path", "outputs/final_video.mp4")
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # sensible bitrate for size ~9–10MB for short videos; adjust target_bitrate in config if needed
    bitrate = cfg.get("target_bitrate", "4M")
    print(f"[export] Writing {out} at {bitrate} bitrate, fps={fps} ({video.duration:.1f}s)")
    video.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        bitrate=bitrate,
        threads=4,
        preset="medium",
        temp_audiofile=str(out_path.with_suffix(".temp-audio.m4a")),
        remove_temp=True,
    )

if __name__ == "__main__":
    main()
