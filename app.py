"""Flask web interface for CIFAKE prediction, Grad-CAM, and reports."""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from PIL import Image
from werkzeug.utils import secure_filename

from database.db import (
    create_prediction,
    get_prediction,
    init_db,
    list_predictions,
)
from src import config


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
GRADCAM_DIR = os.path.join(BASE_DIR, "static", "gradcam")
ALLOWED_EXTENSIONS = {"bmp", "gif", "jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SKIP_RENDER_GRADCAM = (
    os.environ.get("RENDER") == "true"
    and os.environ.get("CIFAKE_ENABLE_RENDER_GRADCAM") != "1"
)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GRADCAM_DIR, exist_ok=True)
init_db()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
logger = logging.getLogger(__name__)
_model = None


def _get_model():
    global _model
    if _model is None:
        from src.model import load_trained_model

        logger.info("Loading CIFAKE model from %s", config.FINAL_MODEL_PATH)
        _model = load_trained_model(config.FINAL_MODEL_PATH)
    return _model


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.errorhandler(400)
def bad_request(error):
    return render_template("404.html", message=str(error)), 400


@app.errorhandler(413)
def request_too_large(error):
    return render_template("404.html", message="Image must be 10 MB or smaller."), 413


def _row_view(row):
    if row is None:
        return None
    view = dict(row)
    view["confidence_percent"] = f"{view['confidence'] * 100:.2f}%"
    view["real_percent"] = f"{view['real_probability'] * 100:.2f}"
    view["fake_percent"] = f"{view['fake_probability'] * 100:.2f}"
    view["thumbnail_url"] = url_for("static", filename=f"uploads/{view['stored_filename']}")
    view["uploaded_image_url"] = view["thumbnail_url"]
    if view.get("gradcam_filename"):
        view["gradcam_image_url"] = url_for(
            "static", filename=f"gradcam/{view['gradcam_filename']}"
        )
    else:
        view["gradcam_image_url"] = None
    return view


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/upload")
def upload():
    return render_template("upload.html", model_ready=os.path.isfile(config.FINAL_MODEL_PATH))


@app.post("/predict")
def predict():
    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename or not _allowed_file(uploaded.filename):
        abort(400, "Upload a BMP, GIF, JPG, JPEG, PNG, or WEBP image.")

    original_filename = secure_filename(uploaded.filename)
    stored_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename}"
    image_path = os.path.join(UPLOAD_DIR, stored_filename)
    uploaded.save(image_path)

    try:
        with Image.open(image_path) as image:
            image.verify()

        model = _get_model()

        from src.gradcam import explain_image
        from src.predict import predict_single_image

        prediction = predict_single_image(model, image_path)
        generated_gradcam = None
        if SKIP_RENDER_GRADCAM:
            logger.warning(
                "Skipping Grad-CAM on Render to avoid worker memory exhaustion. "
                "Set CIFAKE_ENABLE_RENDER_GRADCAM=1 to force it."
            )
        else:
            _, gradcam_path, _ = explain_image(
                model=model,
                image_path=image_path,
                output_dir=GRADCAM_DIR,
            )
            generated_gradcam = os.path.basename(gradcam_path)

    except Exception:
        logger.exception("Prediction failed for uploaded file %s", original_filename)

        if os.path.exists(image_path):
            os.remove(image_path)

        abort(500)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record_id = create_prediction(
        {
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "predicted_label": prediction["predicted_label"],
            "real_probability": prediction["real_probability"],
            "fake_probability": prediction["fake_probability"],
            "confidence": prediction["predicted_confidence"],
            "gradcam_filename": generated_gradcam,
            "created_at": now,
        }
    )

    return redirect(url_for("result", record_id=record_id))


@app.get("/result/<int:record_id>")
def result(record_id: int):
    view = _row_view(get_prediction(record_id))
    if view is None:
        abort(404)
    view["id"] = record_id
    return render_template("result.html", **view)


@app.get("/history")
def history():
    return render_template("history.html", rows=[_row_view(row) for row in list_predictions()])


@app.get("/report/<int:record_id>")
def download_report(record_id: int):
    row = get_prediction(record_id)
    if row is None:
        abort(404)

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as ReportImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    view = _row_view(row)
    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=0.65 * inch,
                                 leftMargin=0.65 * inch, topMargin=0.6 * inch,
                                 bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("CIFAKE Image Analysis Report", styles["Title"]),
        Spacer(1, 0.15 * inch),
        Paragraph(f"File: {view['original_filename']}", styles["BodyText"]),
        Paragraph(f"Created: {view['created_at']}", styles["BodyText"]),
        Spacer(1, 0.18 * inch),
        Paragraph(f"Verdict: <b>{view['predicted_label']}</b>", styles["Heading2"]),
        Paragraph(f"Confidence: {view['confidence_percent']}", styles["BodyText"]),
        Paragraph(f"REAL probability: {view['real_percent']}%", styles["BodyText"]),
        Paragraph(f"FAKE probability: {view['fake_percent']}%", styles["BodyText"]),
        Spacer(1, 0.2 * inch),
    ]
    original_path = os.path.join(UPLOAD_DIR, view["stored_filename"])
    gradcam_path = (
        os.path.join(GRADCAM_DIR, view["gradcam_filename"])
        if view.get("gradcam_filename")
        else None
    )
    for label, path in (("Original image", original_path), ("Grad-CAM overlay", gradcam_path)):
        if path and os.path.isfile(path):
            story.append(Paragraph(label, styles["Heading3"]))
            story.append(ReportImage(path, width=3.2 * inch, height=2.4 * inch, kind="proportional"))
            story.append(Spacer(1, 0.15 * inch))
    document.build(story)
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True,
                     download_name=f"cifake_report_{record_id}.pdf")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
