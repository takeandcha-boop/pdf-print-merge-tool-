from flask import Flask, render_template, request, send_file
import os
from io import BytesIO
from PyPDF2 import PdfReader, PdfWriter

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_pdf_pages(filepath):
    reader = PdfReader(filepath)
    return len(reader.pages)


def make_unique_filename(filename):
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 2

    while os.path.exists(os.path.join(UPLOAD_FOLDER, candidate)):
        candidate = f"{base}_{counter}{ext}"
        counter += 1

    return candidate


def sanitize_output_filename(filename):
    filename = (filename or "").strip()

    if not filename:
        return "merged_output.pdf"

    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


def build_selected_pdf_list(selected_values):
    selected_pdf_list = []
    total_pages = 0
    odd_pdfs = []
    blank_page_suggestions = []

    for i, value in enumerate(selected_values):
        if "|" not in value:
            continue

        filename, pages = value.split("|", 1)
        pages = int(pages)

        pdf = {
            "order": i + 1,
            "filename": filename,
            "pages": pages,
            "is_odd": (pages % 2 == 1)
        }

        selected_pdf_list.append(pdf)
        total_pages += pages

        if pdf["is_odd"]:
            odd_pdfs.append(pdf)

        if i < len(selected_pdf_list) - 1 or i < len(selected_values) - 1:
            blank_page_suggestions.append({
                "after_order": i + 1,
                "after_filename": filename
            })

    if len(selected_pdf_list) > 0:
        blank_page_suggestions = blank_page_suggestions[:len(selected_pdf_list) - 1]
    else:
        blank_page_suggestions = []

    return selected_pdf_list, total_pages, odd_pdfs, blank_page_suggestions


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    uploaded_files = request.files.getlist("pdf_files")
    pdf_list = []

    for file in uploaded_files:
        if not file or not file.filename:
            continue

        if not file.filename.lower().endswith(".pdf"):
            continue

        safe_filename = make_unique_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
        file.save(filepath)

        try:
            pages = get_pdf_pages(filepath)
            pdf_list.append({
                "filename": safe_filename,
                "pages": pages
            })
        except Exception:
            if os.path.exists(filepath):
                os.remove(filepath)

    return render_template(
        "result.html",
        pdf_list=pdf_list,
        insert_blank_pages=True
    )


@app.route("/delete_pdf", methods=["POST"])
def delete_pdf():
    filename_to_delete = request.form.get("filename_to_delete", "")
    current_values = request.form.getlist("current_pdf")
    insert_blank_pages = request.form.get("insert_blank_pages") == "on"

    filepath = os.path.join(UPLOAD_FOLDER, filename_to_delete)
    if filename_to_delete and os.path.exists(filepath):
        os.remove(filepath)

    pdf_list = []

    for value in current_values:
        if "|" not in value:
            continue

        filename, pages = value.split("|", 1)

        if filename == filename_to_delete:
            continue

        remaining_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(remaining_path):
            continue

        pdf_list.append({
            "filename": filename,
            "pages": int(pages)
        })

    return render_template(
        "result.html",
        pdf_list=pdf_list,
        insert_blank_pages=insert_blank_pages
    )


@app.route("/delete_all_pdfs", methods=["POST"])
def delete_all_pdfs():
    current_values = request.form.getlist("current_pdf")

    for value in current_values:
        if "|" not in value:
            continue

        filename, _pages = value.split("|", 1)
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        if os.path.exists(filepath):
            os.remove(filepath)

    return render_template(
        "result.html",
        pdf_list=[],
        insert_blank_pages=True
    )


@app.route("/select", methods=["POST"])
def select():
    selected_values = request.form.getlist("selected_pdf")
    insert_blank_pages = request.form.get("insert_blank_pages") == "on"
    output_filename = sanitize_output_filename(request.form.get("output_filename", ""))

    selected_pdf_list, total_pages, odd_pdfs, blank_page_suggestions = build_selected_pdf_list(selected_values)
    suggested_blank_pages_count = len(blank_page_suggestions)
    blank_pages_count = suggested_blank_pages_count if insert_blank_pages else 0
    estimated_total_pages = total_pages + blank_pages_count

    return render_template(
        "selected.html",
        selected_pdf_list=selected_pdf_list,
        total_pages=total_pages,
        odd_pdfs=odd_pdfs,
        blank_page_suggestions=blank_page_suggestions,
        blank_pages_count=blank_pages_count,
        estimated_total_pages=estimated_total_pages,
        insert_blank_pages=insert_blank_pages,
        suggested_blank_pages_count=suggested_blank_pages_count,
        output_filename=output_filename
    )


@app.route("/download_merged", methods=["POST"])
def download_merged():
    selected_values = request.form.getlist("selected_pdf")
    insert_blank_pages = request.form.get("insert_blank_pages") == "on"
    output_filename = sanitize_output_filename(request.form.get("output_filename", ""))

    writer = PdfWriter()
    valid_files = []

    for value in selected_values:
        if "|" not in value:
            continue

        filename, _pages = value.split("|", 1)
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        if os.path.exists(filepath):
            valid_files.append(filepath)

    for i, filepath in enumerate(valid_files):
        reader = PdfReader(filepath)

        for page in reader.pages:
            writer.add_page(page)

        is_last = i == len(valid_files) - 1
        is_odd = len(reader.pages) % 2 == 1

        if insert_blank_pages and is_odd and not is_last:
            last_page = reader.pages[-1]
            blank_width = float(last_page.mediabox.width)
            blank_height = float(last_page.mediabox.height)
            writer.add_blank_page(width=blank_width, height=blank_height)

    pdf_buffer = BytesIO()
    writer.write(pdf_buffer)
    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=output_filename,
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)
