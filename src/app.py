import os
import json  # <-- Add this line
from flask import Flask, jsonify, send_from_directory, render_template

# Compute the absolute path to the templates folder (which is one level up from src)
template_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'templates')
app = Flask(__name__, template_folder=template_dir)

# Path to your metadata file (adjust if needed)
METADATA_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'metadata_dummy.json')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/markers')
def markers():
    with open(METADATA_PATH, 'r') as f:
        metadata = json.load(f)
    return jsonify(metadata)

@app.route('/image/<path:filename>')
def serve_image(filename):
    # Serve images from the 'images' folder in the project root
    images_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'images')
    return send_from_directory(images_dir, filename)

if __name__ == '__main__':
    app.run(debug=True)
