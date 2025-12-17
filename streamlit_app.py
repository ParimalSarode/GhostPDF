import streamlit as st
import io
import zipfile
import fitz  # PyMuPDF
from pypdf import PdfWriter, PdfReader
from pdf2image import convert_from_bytes
from PIL import Image
import img2pdf
import shutil

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="OpenPDF Master", page_icon="📄", layout="centered")

st.title("📄 OpenPDF Master")

# --- SIDEBAR ---
option = st.sidebar.selectbox(
    "Choose Action",
    ("Merge PDFs", "Compress PDF", "Convert PDF to Images", "Convert Images to PDF")
)

# --- ENGINE FUNCTIONS ---

def get_first_page(input_bytes):
    """Extracts just the first page for fast estimation"""
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    # Make a new empty PDF
    single_page_doc = fitz.open()
    # Copy page 0 (first page) to new doc
    single_page_doc.insert_pdf(doc, from_page=0, to_page=0)
    
    out_buffer = io.BytesIO()
    single_page_doc.save(out_buffer)
    single_page_doc.close()
    doc.close()
    return out_buffer.getvalue()

def compress_standard(input_bytes):
    """Refined standard compression using PyMuPDF"""
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    output_buffer = io.BytesIO()
    doc.save(output_buffer, garbage=4, deflate=True, clean=True)
    doc.close()
    return output_buffer.getvalue()

def compress_strong(input_bytes, strength_level):
    """
    Strong compression using Image Conversion.
    """
    # Map slider (41-100) to DPI (140 -> 50) and Quality (80 -> 20)
    factor = (strength_level - 40) / 60.0
    target_dpi = int(140 - (90 * factor))
    target_quality = int(80 - (60 * factor))
    
    if not shutil.which("pdftoppm"):
        st.error("❌ Poppler not found.")
        return input_bytes

    images = convert_from_bytes(input_bytes, dpi=target_dpi, fmt='jpeg')
    
    img_bytes_list = []
    for img in images:
        img_buf = io.BytesIO()
        img.save(img_buf, format='JPEG', quality=target_quality, optimize=True)
        img_bytes_list.append(img_buf.getvalue())
    
    return img2pdf.convert(img_bytes_list)

# --- MAIN LOGIC ---

# 1. COMPRESS PDF (WITH INSTANT ESTIMATION)
if option == "Compress PDF":
    st.header("Compress PDF")
    uploaded_file = st.file_uploader("Upload PDF", type="pdf")

    if uploaded_file:
        # Load file once into memory
        file_bytes = uploaded_file.read()
        orig_size = len(file_bytes)
        
        st.write("---")
        st.write("#### Compression Strength")
        
        # SLIDER (Triggers re-run on release)
        strength = st.slider(
            "Select Level", 
            min_value=0, 
            max_value=100, 
            value=30
        )
        
        # --- INSTANT ESTIMATION LOGIC ---
        # We calculate this IMMEDIATELY as the slider moves (on release)
        try:
            # 1. Get just the first page to test compression speed
            first_page_bytes = get_first_page(file_bytes)
            first_page_orig_size = len(first_page_bytes)

            # 2. Compress the sample page based on current slider
            if strength <= 40:
                compressed_sample = compress_standard(first_page_bytes)
                mode_text = "Standard (Lossless)"
            else:
                compressed_sample = compress_strong(first_page_bytes, strength)
                mode_text = "Strong (Lossy)"

            # 3. Calculate Ratio
            sample_new_size = len(compressed_sample)
            ratio = sample_new_size / first_page_orig_size
            
            # 4. Estimate Total Size (Original Total * Ratio)
            estimated_total_size = orig_size * ratio
            savings = (1 - ratio) * 100

            # Display the Estimate nicely
            col1, col2, col3 = st.columns(3)
            col1.metric("Original Size", f"{orig_size / 1024:.2f} KB")
            col2.metric("Estimated New Size", f"~{estimated_total_size / 1024:.2f} KB")
            col3.metric("Est. Reduction", f"{savings:.1f}%", delta_color="normal")
            
            st.caption(f"ℹ️ Prediction based on Page 1 analysis. Mode: **{mode_text}**")

        except Exception as e:
            st.warning("Could not estimate size (file might be encrypted or empty).")

        st.write("---")

        # FINAL BUTTON
        if st.button("Compress"):
            with st.spinner("Processing full document..."):
                if strength <= 40:
                    out_bytes = compress_standard(file_bytes)
                else:
                    out_bytes = compress_strong(file_bytes, strength)
                
                final_size = len(out_bytes)
                st.success(f"Done! Final Size: {final_size/1024:.2f} KB")
                
                st.download_button(
                    label="Download Compressed PDF",
                    data=out_bytes,
                    file_name="compressed_doc.pdf",
                    mime="application/pdf"
                )

# 2. MERGE PDFS
elif option == "Merge PDFs":
    st.header("Merge Multiple PDFs")
    uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)
    if uploaded_files and st.button("Merge Files"):
        merger = PdfWriter()
        for pdf in uploaded_files:
            merger.append(pdf)
        output_buffer = io.BytesIO()
        merger.write(output_buffer)
        st.success("Merged!")
        st.download_button("Download Merged PDF", output_buffer.getvalue(), "merged.pdf", "application/pdf")

# 3. CONVERT PDF TO IMAGES
elif option == "Convert PDF to Images":
    st.header("PDF to Images")
    uploaded_file = st.file_uploader("Upload PDF", type="pdf")
    if uploaded_file and st.button("Convert"):
        if not shutil.which("pdftoppm"):
            st.error("❌ Poppler is missing.")
        else:
            with st.spinner("Converting..."):
                images = convert_from_bytes(uploaded_file.read())
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, img in enumerate(images):
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='JPEG')
                        zf.writestr(f"page_{i+1}.jpg", img_byte_arr.getvalue())
                st.success(f"Extracted {len(images)} pages.")
                st.download_button("Download ZIP", zip_buffer.getvalue(), "images.zip", "application/zip")

# 4. IMAGES TO PDF
elif option == "Convert Images to PDF":
    st.header("Images to PDF")
    uploaded_images = st.file_uploader("Upload Images", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    if uploaded_images and st.button("Create PDF"):
        image_list = [Image.open(f).convert('RGB') for f in uploaded_images]
        if image_list:
            output_buffer = io.BytesIO()
            image_list[0].save(output_buffer, save_all=True, append_images=image_list[1:], format="PDF")
            st.success("Created!")
            st.download_button("Download PDF", output_buffer.getvalue(), "images.pdf", "application/pdf")