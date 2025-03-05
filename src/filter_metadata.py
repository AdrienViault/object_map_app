#!/usr/bin/env python3
"""
This script filters JSON metadata files from the source directory and builds a new
tree of filtered metadata and associated images.

Source metadata directory:
  METADATA_DIR = "/media/adrien/Space/Datasets/Overhead/processed/"

Output directory:
  KEEP_METADATA_DIR = "/media/adrien/Space/Datasets/Overhead/filtered/"

Only objects with labels:
  - "overhead utility power distribution line"
  - "utility pole"
  - "electricity management box"
are kept.

For each file with at least one kept object:
  - A new JSON is written containing:
       - The original "source" info, with the source image path rewritten as a relative path (starting with "Grenoble/...")
       - The filtered objects.
  - The projection images and cropped depth images referenced by each kept object are copied.
  - The source image is resized to 1000px wide and copied.
"""

import os
import json
import glob
import shutil
from tqdm import tqdm
from PIL import Image

# Set source and destination directories.
METADATA_DIR = "/media/adrien/Space/Datasets/Overhead/processed/"
KEEP_METADATA_DIR = "/media/adrien/Space/Datasets/Overhead/filtered/"

# List of labels to keep (case-insensitive)
LABELS_OF_INTEREST = {
    "overhead utility power distribution line",
    "utility pole",
    "electricity management box"
}

# For source images, they are originally in:
RAW_DIR = "/media/adrien/Space/Datasets/Overhead/raw/"

def ensure_dir(path):
    """Ensure directory exists."""
    if not os.path.exists(path):
        os.makedirs(path)

def make_relative_path(full_path, base_dir):
    """
    Given a full path and a base directory, returns the relative path starting with the base directory's basename.
    For example, if full_path="/media/adrien/Space/Datasets/Overhead/raw/Grenoble/barnes38/..."
    and base_dir="/media/adrien/Space/Datasets/Overhead/raw/", then returns "Grenoble/barnes38/..."
    """
    # Normalize paths.
    full_path = os.path.normpath(full_path)
    base_dir = os.path.normpath(base_dir)
    if full_path.startswith(base_dir):
        rel = os.path.relpath(full_path, base_dir)
        # Optionally, ensure it starts with the base directory's name.
        return rel
    return full_path

def resize_image(src_path, dst_path, width=1000):
    """Resize image from src_path to a width of 1000 pixels (maintaining aspect ratio) and save to dst_path."""
    try:
        img = Image.open(src_path)
        w_percent = (width / float(img.size[0]))
        height = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((width, height), Image.ANTIALIAS)
        ensure_dir(os.path.dirname(dst_path))
        img.save(dst_path)
        print(f"[INFO] Resized and saved source image to {dst_path}")
    except Exception as e:
        print(f"[ERROR] Resizing image {src_path} to {dst_path}: {e}")

def process_metadata_file(filepath):
    """Process a single metadata JSON file; return True if a filtered file is written."""
    try:
        with open(filepath, "r") as f:
            meta = json.load(f)
    except Exception as e:
        print(f"[ERROR] Reading {filepath}: {e}")
        return False

    # Filter objects based on label.
    objects = meta.get("objects", [])
    filtered_objects = []
    for obj in objects:
        label = obj.get("label", "").strip().lower()
        if label in LABELS_OF_INTEREST:
            filtered_objects.append(obj)
    
    if not filtered_objects:
        return False

    # Prepare new metadata dictionary.
    new_meta = {}
    # For "source": rewrite its "path" to be relative starting with "Grenoble"
    source = meta.get("source", {})
    if "path" in source:
        # Assume the original source path is absolute and under RAW_DIR.
        rel_source = make_relative_path(source["path"], RAW_DIR)
        source["path"] = rel_source  # update the path to be relative
    new_meta["source"] = source
    new_meta["objects"] = filtered_objects

    # Determine relative path for JSON file.
    rel_path = os.path.relpath(filepath, METADATA_DIR)
    new_filepath = os.path.join(KEEP_METADATA_DIR, rel_path)
    ensure_dir(os.path.dirname(new_filepath))
    try:
        with open(new_filepath, "w") as f:
            json.dump(new_meta, f, indent=4)
        print(f"[INFO] Wrote filtered metadata to {new_filepath}")
    except Exception as e:
        print(f"[ERROR] Writing {new_filepath}: {e}")
        return False

    # Copy associated files:
    # 1. For each object, copy its projection image and depth image.
    for i, obj in enumerate(filtered_objects):
        # Projection image: path is under obj["projection_path"], which is relative (e.g., "Grenoble/...")
        proj_path = obj.get("projection_path")
        if proj_path:
            # Ensure the proj_path does not repeat "Grenoble" if already present.
            # Since proj_path should start with "Grenoble", we directly copy:
            src_proj = os.path.join(METADATA_DIR, proj_path)
            dst_proj = os.path.join(KEEP_METADATA_DIR, proj_path)
            ensure_dir(os.path.dirname(dst_proj))
            try:
                shutil.copy2(src_proj, dst_proj)
                print(f"[INFO] Copied projection image to {dst_proj}")
            except Exception as e:
                print(f"[ERROR] Copying projection image from {src_proj} to {dst_proj}: {e}")
        # Depth image: similarly, from obj["depth_path"]
        depth_path = obj.get("depth_path")
        if depth_path:
            src_depth = os.path.join(METADATA_DIR, depth_path)
            dst_depth = os.path.join(KEEP_METADATA_DIR, depth_path)
            ensure_dir(os.path.dirname(dst_depth))
            try:
                shutil.copy2(src_depth, dst_depth)
                print(f"[INFO] Copied depth image for object {i} to {dst_depth}")
            except Exception as e:
                print(f"[ERROR] Copying depth image from {src_depth} to {dst_depth}: {e}")

    # 2. For the source image, resize and copy.
    if "path" in source:
        src_source_img = source["path"]
        # Since source["path"] is now relative (e.g., "Grenoble/...")
        # But the original file is in RAW_DIR.
        full_src_source = os.path.join(RAW_DIR, src_source_img.lstrip("/"))
        dst_source_img = os.path.join(KEEP_METADATA_DIR, src_source_img.lstrip("/"))
        ensure_dir(os.path.dirname(dst_source_img))
        resize_image(full_src_source, dst_source_img, width=2000)

    return True

def main():
    metadata_files = glob.glob(os.path.join(METADATA_DIR, "**", "*_metadata.json"), recursive=True)
    total_files = len(metadata_files)
    print(f"[INFO] Found {total_files} metadata files in {METADATA_DIR}")
    
    processed_count = 0
    kept_count = 0
    for filepath in tqdm(metadata_files, desc="Processing files"):
        processed_count += 1
        if process_metadata_file(filepath):
            kept_count += 1
    
    print(f"[INFO] Processed {processed_count} files. Filtered metadata written for {kept_count} files.")

if __name__ == '__main__':
    main()
