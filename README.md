# Swiggy Instamart Video Automation (Python)

This package builds up to 4–5 slides (5s each) from an **images folder** and an **Excel sheet**,
with the Swiggy Instamart logo in the top-right, 50:50 layout (content:left, image:right),
and simple entrance animations (text from left, product from right).

> ⚠️ *Conflicts noted in your brief:*  
> - Aspect ratio says **2:1**, but frame size is **1920×1080 (16:9)**. Default here is **2:1 = 1920×960** (configurable).  
> - **120 FPS Ultra 4K** vs **9–10 MB** target: extremely high fps/resolution will inflate size. Default is **30 fps** at a tuned bitrate.

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Place your Proxima Nova fonts if you have them, and your logo PNG at assets/swiggy_instamart_logo.png
# Put your images in inputs/images and edit inputs/slides_template.xlsx
python swiggy_video_maker.py --config config.yaml
```

The output video will be written to `outputs/final_video.mp4`.

## Inputs

- **Images**: put product images in `inputs/images/`. The Excel sheet should reference filenames (e.g., `product1.jpg`).  
  - The script will **optionally remove backgrounds** (if `rembg` is installed and `remove_bg: true`).  
  - It will **upscale** smaller images to avoid pixelation.  
  - Filenames containing `barcode`, `qr`, or `code128` are skipped automatically (configurable).

- **Excel**: edit `inputs/slides_template.xlsx`. Columns:
  - `image_filename` (required)
  - `title`
  - `bullet1`, `bullet2`, `bullet3` (short, 3–4 words each)
  - `dimensions_text` (optional ribbon, e.g., sizes)
  - `capacity_text` (optional ribbon, e.g., 1L, 500g)
  - `skip` (set to `yes` to skip a row)

## Branding

- **Logo**: put a **PNG** logo at `assets/swiggy_instamart_logo.png`. It's placed **top-right** with a safe margin.  
- **Fonts**: supply Proxima Nova font files via `config.yaml` (`font_title_path`, `font_body_path`). Fallback fonts are used if not present.
- **Bullets**: magenta-ish `#78185A` arrow. Title 55px, body 50px by default.

## Tuning File Size / FPS

- Use `fps` and `target_bitrate` in `config.yaml` to meet the **9–10MB** constraint.  
- For 20–30s videos, a bitrate in the range of **3–6 Mbps** is often appropriate, depending on motion.

## Notes

- **Dimension Marking**: If `capacity_text` and/or `dimensions_text` are provided, a semi-transparent ribbon appears near the bottom-left.  
- **Music**: set `music_path` to a local audio file; it will loop or trim to match video duration.  
- **Repetition**: If you have fewer images than slides, duplicate rows in the Excel or lower `max_slides` in the config.

## Reference Video
Place any reference video (like your upload) anywhere you like; the script doesn't need it to run.

---

**Folder structure**

```
swiggy_video_automation/
├── assets/
│   └── swiggy_instamart_logo.png   # (place your downloaded PNG here)
├── config.yaml
├── inputs/
│   ├── images/                     # (put your product images here)
│   └── slides_template.xlsx
├── outputs/
│   └── final_video.mp4             # (rendered output)
├── requirements.txt
└── swiggy_video_maker.py
```
