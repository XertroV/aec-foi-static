import requests
from bs4 import BeautifulSoup
import os
import time
import re
import io
from pdfminer.high_level import extract_text
from pdfminer.pdfparser import PDFSyntaxError
import zipfile
from pathlib import Path
import json
import shutil
import tempfile
from jinja2 import Environment, FileSystemLoader

# Note: AEC server can easily handle 100 MB/s of requests.
# We won't sleep between requests since it's already single threaded.

def get_foi_documents_metadata(year=2025):
    aec_foi_url = f"https://www.aec.gov.au/information-access/foi/{year}/".format(year=year)
    try:
        response = requests.get(aec_foi_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching FOI Disclosure Log: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    # Find all FOI request sections by h2 with id starting with 'lex'
    for h2 in soup.find_all("h2"):  # h2s for each FOI request
        if h2.has_attr("id") and h2["id"].startswith("lex"):
            title = h2.get_text(strip=True)
            # title format "FOI Request LEX7512"
            lex_match = re.search(r"LEX(\d+)", title)
            lex = lex_match.group(1) if lex_match else ""

            # The next sibling ul with class 'linkList' contains the document links
            ul = h2.find_next_sibling("ul", class_="linkList")
            if not ul:
                continue
            for a in ul.find_all("a", href=True):
                href = a["href"]
                if any(href.lower().endswith(ext) for ext in [".pdf", ".zip", ".docx"]):
                    doc_url = href if href.startswith("http") else f"https://www.aec.gov.au{href}"
                    link_text = a.get_text(strip=True)
                    server_filename = Path(href).name
                    results.append({
                        "title": title,
                        "lex": lex,
                        "date": f"{year}",  # Date extraction can be improved if date is present
                        "url": doc_url,
                        "link_text": link_text,
                        "server_filename": server_filename,
                    })
                else:
                    print(f"⚠️⚠️⚠️   Skipping unsupported file type: {href}")
    return results

def download_document(url, filename, download_dir):
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    file_path = download_dir / filename
    try:
        # Check if file exists and compare size with HEAD request
        if file_path.exists():
            try:
                head = requests.head(url, allow_redirects=True, timeout=10)
                head.raise_for_status()
                remote_size = int(head.headers.get('Content-Length', 0))
                local_size = file_path.stat().st_size
                if remote_size > 0 and local_size == remote_size:
                    print(f"Skipping {filename}: already exists and size matches ({local_size} bytes)")
                    return True
                print(f"File {filename} exists but size differs: local {local_size} bytes, remote {remote_size} bytes; abs diff = {abs(remote_size - local_size)} bytes")
            except Exception as e:
                print(f"Warning: Could not verify remote file size for {filename}: {e}")
                # Proceed to download if HEAD fails
        size = 0
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
        print(f"Downloaded: {filename} ({size} bytes)")
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

def extract_text_from_pdf(pdf_path):
    """
    Extracts all readable text from a PDF file using pdfminer.six.
    Returns the extracted text as a string, or an empty string on failure.
    """
    try:
        text = extract_text(pdf_path)
        return text if text else ""
    except (PDFSyntaxError, Exception) as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""

def extract_zip_file(zip_path, extract_to_dir=None):
    """
    Extracts a zip file to a subfolder (named after the zip file, minus extension) in extract_to_dir.
    Returns a list of Paths to the extracted files (files only, not directories).
    """
    zip_path = Path(zip_path)
    if extract_to_dir is None:
        extract_to_dir = zip_path.parent
    extract_folder = Path(extract_to_dir) / zip_path.stem
    extracted_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_folder)
            for name in zip_ref.namelist():
                file_path = extract_folder / name
                if file_path.is_file():
                    extracted_files.append(file_path)
        print(f"Extracted {zip_path} to {extract_folder}")
    except Exception as e:
        print(f"Error extracting {zip_path}: {e}")
    return extracted_files

def save_text_to_file(text, foi_id, filename_suffix, output_base_dir):
    if not text:
        return ""
    text_output_dir = output_base_dir / "extracted_texts"
    text_output_dir.mkdir(parents=True, exist_ok=True)
    generated_filename = f"{foi_id}{filename_suffix}.txt"
    output_path = text_output_dir / generated_filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    return str(Path('/extracted_texts') / generated_filename)

def process_foi_entry(entry_metadata, downloaded_file_path, output_base_dir):
    # Determine unique foi_id
    if entry_metadata.get('lex'):
        foi_id = f"foi-{entry_metadata['lex']}"
    else:
        # Slug from server_filename or title
        base = entry_metadata.get('server_filename') or entry_metadata.get('title', 'foi')
        foi_id = re.sub(r'[^a-zA-Z0-9_-]+', '-', base).strip('-').lower()
    main_file_type = downloaded_file_path.suffix.lower()
    extracted_text = ""
    content_files = []
    output_file_path = output_base_dir / 'downloaded_originals' / downloaded_file_path.name
    (output_base_dir / 'downloaded_originals').mkdir(parents=True, exist_ok=True)
    extracted_text_path = ""
    if main_file_type == '.pdf':
        extracted_text = extract_text_from_pdf(downloaded_file_path)
        extracted_text_path = save_text_to_file(extracted_text, foi_id, '', output_base_dir)
        shutil.copy2(downloaded_file_path, output_file_path)
    elif main_file_type == '.zip':
        # Use a persistent extraction directory under downloads
        extract_dir = downloaded_file_path.parent / f"_extracted_{downloaded_file_path.stem}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        extracted_paths = extract_zip_file(downloaded_file_path, extract_to_dir=extract_dir)
        assets_output_subdir = output_base_dir / 'foi_assets' / foi_id
        assets_output_subdir.mkdir(parents=True, exist_ok=True)
        for extracted_file_path in extracted_paths:
            if not extracted_file_path.is_file():
                continue
            inner_file_type = extracted_file_path.suffix.lower()
            inner_extracted_text = ""
            inner_extracted_text_path = ""
            if inner_file_type == '.pdf':
                inner_extracted_text = extract_text_from_pdf(extracted_file_path)
                inner_extracted_text_path = save_text_to_file(inner_extracted_text, foi_id, f"_{Path(extracted_file_path.name).stem}", output_base_dir)
            inner_download_path = str(Path('/foi_assets') / foi_id / extracted_file_path.name)
            shutil.copy2(extracted_file_path, assets_output_subdir / extracted_file_path.name)
            content_files.append({
                'filename': extracted_file_path.name,
                'type': inner_file_type.lstrip('.'),
                'extracted_text_path': inner_extracted_text_path,
                'download_path': inner_download_path
            })
        shutil.copy2(downloaded_file_path, output_file_path)
    else:
        shutil.copy2(downloaded_file_path, output_file_path)
    return {
        "id": foi_id,
        "title": entry_metadata['title'],
        "date": entry_metadata['date'],
        "original_url": entry_metadata['url'],
        "main_file_type": main_file_type.lstrip('.'),
        "extracted_text_path": extracted_text_path,
        "output_file_path": str(Path('/downloaded_originals') / downloaded_file_path.name),
        "content_files": content_files
    }

def load_text_content(text_file_path, output_base_dir):
    try:
        abs_path = output_base_dir / text_file_path.lstrip('/')
        if abs_path.exists():
            with open(abs_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"Error loading text from {text_file_path}: {e}")
    return ""

def generate_static_site(all_foi_data, output_base_dir):
    output_base_dir = Path(output_base_dir)
    (output_base_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "static").mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader('templates'))
    index_template = env.get_template("index.html")
    detail_template = env.get_template("document_detail.html")
    renderable_foi_data = []
    for doc_data in all_foi_data:
        render_data = doc_data.copy()
        # Load main document text
        if render_data.get('extracted_text_path'):
            render_data['extracted_text'] = load_text_content(render_data['extracted_text_path'], output_base_dir)
        # Load inner file text for ZIPs
        if render_data.get('content_files'):
            for item in render_data['content_files']:
                if item.get('extracted_text_path'):
                    item['extracted_text'] = load_text_content(item['extracted_text_path'], output_base_dir)
        renderable_foi_data.append(render_data)
    index_page_documents = []
    for doc_data in renderable_foi_data:
        html_filename = f"{doc_data['id']}.html"
        output_html_path = output_base_dir / "documents" / html_filename
        doc_data['output_html_path'] = f"/documents/{html_filename}"
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(detail_template.render(document=doc_data))
        index_page_documents.append({
            'id': doc_data['id'],
            'title': doc_data['title'],
            'date': doc_data['date'],
            'output_html_path': f"/documents/{html_filename}",
            'main_file_type': doc_data['main_file_type'],
            'original_url': doc_data.get('original_url', '')
        })
    with open(output_base_dir / "index.html", 'w', encoding='utf-8') as f:
        f.write(index_template.render(documents=index_page_documents))
    # Copy static assets
    if Path('static').exists():
        shutil.copytree('static', output_base_dir / 'static', dirs_exist_ok=True)

if __name__ == "__main__":
    metadata = get_foi_documents_metadata()
    print(f"Found {len(metadata)} FOI document entries.")
    download_dir = Path("downloads")
    download_dir.mkdir(exist_ok=True)
    output_base_dir = Path("docs")
    (output_base_dir / "downloaded_originals").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "foi_assets").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "extracted_texts").mkdir(parents=True, exist_ok=True)
    all_foi_data = []
    for entry in metadata:
        filename = entry["server_filename"]
        success = download_document(entry["url"], filename, download_dir)
        if not success:
            continue
        local_path = download_dir / filename
        processed_data = process_foi_entry(entry, local_path, output_base_dir)
        all_foi_data.append(processed_data)
    Path("data").mkdir(exist_ok=True)
    with open(Path("data") / "foi_data.json", "w", encoding="utf-8") as f:
        json.dump(all_foi_data, f, ensure_ascii=False, indent=2)
    # Generate static site
    with open(Path("data") / "foi_data.json", "r", encoding="utf-8") as f:
        all_foi_data = json.load(f)
    generate_static_site(all_foi_data, output_base_dir)
