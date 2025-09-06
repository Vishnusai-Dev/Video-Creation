
import streamlit as st
import tempfile, os, io, yaml
from pathlib import Path
from PIL import Image
import base64

st.set_page_config(page_title="Swiggy Instamart Video Builder", layout="wide")

st.title("Swiggy Instamart Video Builder (2:1)")

st.markdown("""
This app turns an Excel file (titles + bullet points) and product images into a short video
(4-5 slides x 5 seconds each). Text enters from the left; product enters from the right; logo at top-right.
""")

# Sidebar config
st.sidebar.header("Settings")
frame_ratio = st.sidebar.selectbox("Frame Ratio", ["2:1 (1920x960)", "16:9 (1920x1080)"], index=0)
fps = st.sidebar.slider("FPS", 10, 60, 30, step=5)
duration = st.sidebar.slider("Seconds per slide", 3, 8, 5, step=1)
max_slides = st.sidebar.slider("Max slides", 1, 5, 5, step=1)
bitrate = st.sidebar.selectbox("Target bitrate", ["3M", "4M", "5M", "6M", "8M"], index=1)
remove_bg = st.sidebar.checkbox("Remove Background (requires rembg)", value=True)
skip_blurry = st.sidebar.checkbox("Skip blurry images (needs OpenCV)", value=True)

st.sidebar.header("Audio")
music = st.sidebar.file_uploader("Background music (mp3/wav, optional)", type=["mp3", "wav"], accept_multiple_files=False)

st.sidebar.header("Brand Logo")
logo = st.sidebar.file_uploader("Swiggy Instamart Logo (PNG preferred)", type=["png","jpg","jpeg"], accept_multiple_files=False)

st.header("1) Upload Excel")
excel = st.file_uploader("Excel with columns: image_filename, title, bullet1, bullet2, bullet3, dimensions_text, capacity_text, skip", type=["xlsx", "xlsm", "xls"])

st.header("2) Upload Images")
images = st.file_uploader("Product images", type=["jpg","jpeg","png","webp"], accept_multiple_files=True)

run = st.button("Build Video")

if run:
    if not excel or not images:
        st.error("Please upload the Excel and at least one image.")
        st.stop()

    # Prepare temp working directory
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="swiggy_video_"))
    (work/"assets").mkdir(exist_ok=True, parents=True)
    (work/"inputs"/"images").mkdir(exist_ok=True, parents=True)
    (work/"outputs").mkdir(exist_ok=True, parents=True)

    # Save uploads
    excel_path = work/"inputs"/"slides.xlsx"
    with open(excel_path, "wb") as f:
        f.write(excel.read())

    img_root = work/"inputs"/"images"
    for f in images:
        with open(img_root/f.name, "wb") as out:
            out.write(f.read())

    logo_path = None
    if logo:
        logo_path = work/"assets"/"swiggy_instamart_logo.png"
        with open(logo_path, "wb") as f:
            f.write(logo.read())

    music_path = None
    if music:
        music_path = work/"assets"/music.name
        with open(music_path, "wb") as f:
            f.write(music.read())

    # Build config
    frame_width = 1920
    frame_height = 960 if frame_ratio.startswith("2:1") else 1080

    cfg = {
        "frame_width": frame_width,
        "frame_height": frame_height,
        "fps": int(fps),
        "duration_per_slide": int(duration),
        "max_slides": int(max_slides),
        "target_bitrate": bitrate,
        "background_color": "#FFFFFF",
        "left_panel_ratio": 0.5,
        "font_title_path": "",
        "font_body_path": "",
        "title_font_size_px": 55,
        "body_font_size_px": 50,
        "bullet_color_hex": "#78185A",
        "bullet_icon": "arrow",
        "title_case_style": "standard",
        "text_max_words_per_bullet": 4,
        "logo_path": str(logo_path) if logo_path else "",
        "logo_position": "top_right",
        "logo_margin_px": 28,
        "images_folder": str(img_root),
        "remove_bg": bool(remove_bg),
        "upscale_to_min_side_px": 1000,
        "skip_if_blurry": bool(skip_blurry),
        "barcode_filename_keywords": ["barcode", "qr", "code128"],
        "excel_path": str(excel_path),
        "title_col": "title",
        "bullets_cols": ["bullet1", "bullet2", "bullet3"],
        "dimensions_col": "dimensions_text",
        "capacity_col": "capacity_text",
        "image_col": "image_filename",
        "skip_col": "skip",
        "music_path": str(music_path) if music_path else "",
        "output_path": str(work/"outputs"/"final_video.mp4"),
        "edge_padding_px": 48,
        "text_line_spacing_px": 10,
        "safe_area_inset_px": 48,
        "animate_from_sides": True,
        "dimension_marking": True,
    }

    cfg_path = work/"config.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True)

    # Call the core script
    import subprocess, sys
    cmd = [sys.executable, "-u", "swiggy_video_maker.py", "--config", str(cfg_path)]
    st.info("Rendering...")
    proc = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent), capture_output=True, text=True)
    if proc.returncode != 0:
        st.error("Video render failed.")
        st.code(proc.stdout + "\n\n" + proc.stderr)
        st.stop()

    out_path = cfg["output_path"]
    st.success("Done! Preview below and download the MP4.")

    # Preview / download
    with open(out_path, "rb") as f:
        data = f.read()
    st.download_button("Download Video", data=data, file_name="final_video.mp4", mime="video/mp4")

    st.video(data)
