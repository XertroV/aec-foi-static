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
import concurrent.futures
import hashlib

# --- CONFIGURATION ---
CONFIG = {
    "year": 2025,
    "base_url": "https://www.aec.gov.au/information-access/foi/{year}/",
    "data_dir": "data",
    "output_dir": "docs",
    "download_dir": "downloads",
    "template_dir": "templates"
}

# --- LLM CONFIGURATION ---
LLM_CONFIG = {
    'GEMINI_API_KEY_ENV_VAR': 'GEMINI_API_KEY',
    'DEFAULT_MODEL': 'gemini-2.5-flash',
    'PROMPT_TEMPLATES': {
        'overall': (
            "Summarize the following documents. These documents are the released documents associated with an FOI request. "
            "The summary should focus on: the main purpose of the FOI request, the documents from the FOI request, and the main content from the FOI request documents that relates to the FOI request.\n\nDocuments:\n\n{text}"
        ),
        'short_index': (
            "Create a single paragraph summary of the following FOI request summary:\n\nSummary:\n\n{text}"
        ),
        'per_file': (
            "Considering this document as part of an FOI request, summarize the document and its relevance to the FOI request. "
            "FYI the overview of the FOI request is: {overall_short_summary}\n\nDocument Text:\n\n{text}"
        ),
    },
    'MAX_TOKENS': {
        'overall': None,
        'short_index': None,
        'per_file': None,
    },
    'FORCE_SUMMARY_REGENERATION': False,
}

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
    grouped_requests = {}
    for h2 in soup.find_all("h2"):
        if h2.has_attr("id") and h2["id"].startswith("lex"):
            title = h2.get_text(strip=True)
            lex_match = re.search(r"LEX(\d+)", title)
            lex = lex_match.group(1) if lex_match else ""
            if not lex:
                continue
            if lex not in grouped_requests:
                grouped_requests[lex] = {
                    "id": f"LEX{lex}",
                    "title": title,
                    "date": str(year),
                    "files": []
                }
            ul = h2.find_next_sibling("ul", class_="linkList")
            if not ul:
                continue
            for a in ul.find_all("a", href=True):
                href = a["href"]
                if any(href.lower().endswith(ext) for ext in [".pdf", ".zip", ".docx"]):
                    doc_url = href if href.startswith("http") else f"https://www.aec.gov.au{href}"
                    link_text = a.get_text(strip=True)
                    server_filename = Path(href).name
                    doc_type = Path(href).suffix.lstrip('.')
                    grouped_requests[lex]["files"].append({
                        "original_url": doc_url,
                        "link_text": link_text,
                        "server_filename": server_filename,
                        "type": doc_type
                    })
                else:
                    print(f"⚠️⚠️⚠️   Skipping unsupported file type: {href}")
    return list(grouped_requests.values())

def file_hash(path, block_size=65536):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block_size), b''):
            h.update(chunk)
    return h.hexdigest()

def download_document(url, filename, download_dir, metadata, metadata_path):
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    file_path = download_dir / filename
    # Check metadata for this file
    meta = metadata.get(str(file_path))
    try:
        # Check if file exists and compare size/hash with metadata
        if file_path.exists():
            stat = file_path.stat()
            file_info = {
                'size': stat.st_size,
                'mtime': int(stat.st_mtime),
                'hash': file_hash(file_path)
            }
            if meta and meta.get('size') == file_info['size'] and meta.get('hash') == file_info['hash']:
                print(f"Skipping {filename}: already exists and matches metadata")
                return True
        # Check remote file size with HEAD request
        try:
            head = requests.head(url, allow_redirects=True, timeout=10)
            head.raise_for_status()
            remote_size = int(head.headers.get('Content-Length', 0))
            local_size = file_path.stat().st_size if file_path.exists() else 0
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
        # Update metadata after download
        stat = file_path.stat()
        metadata[str(file_path)] = {
            'url': url,
            'size': stat.st_size,
            'mtime': int(stat.st_mtime),
            'hash': file_hash(file_path),
            'extracted': False,
            'resources': []
        }
        save_metadata(metadata, metadata_path)
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

def process_file(file_metadata, local_path, config, metadata_cache):
    """
    Process a file (PDF, ZIP, etc.), extract text or unpack as needed, and return artifact info.
    Idempotent: checks metadata_cache to avoid redundant work.
    Handles both top-level and ZIP-contained files.
    """
    from pathlib import Path
    import shutil
    file_path = Path(local_path)
    file_type = file_path.suffix.lower().lstrip('.')
    output_base_dir = Path(config['output_dir'])
    foi_id = file_metadata.get('foi_id', file_metadata.get('id', 'foi'))
    meta = metadata_cache.get(str(file_path))
    stat = file_path.stat()
    file_hash_val = file_hash(file_path)
    # Check if already processed and return full artifact info if so
    if meta and meta.get('hash') == file_hash_val and meta.get('extracted') and meta.get('artifact_info'):
        return meta['artifact_info']
    artifact_info = {
        'type': file_type,
        'output_file_path': str(Path('/downloaded_originals') / file_path.name),
        'content_files': [],
        'extracted_text_path': ''
    }
    if file_type == 'pdf':
        extracted_text = extract_text_from_pdf(file_path)
        extracted_text_path = save_text_to_file(extracted_text, foi_id, f"_{file_path.stem}", output_base_dir)
        shutil.copy2(file_path, output_base_dir / 'downloaded_originals' / file_path.name)
        artifact_info['extracted_text_path'] = extracted_text_path
    elif file_type == 'zip':
        extract_dir = file_path.parent / f"_extracted_{file_path.stem}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        extracted_paths = extract_zip_file(file_path, extract_to_dir=extract_dir)
        assets_output_subdir = output_base_dir / 'foi_assets' / foi_id
        assets_output_subdir.mkdir(parents=True, exist_ok=True)
        for extracted_file_path in extracted_paths:
            if not extracted_file_path.is_file():
                continue
            inner_file_metadata = {
                'foi_id': foi_id,
                'filename': extracted_file_path.name
            }
            inner_info = process_file(inner_file_metadata, extracted_file_path, config, metadata_cache)
            inner_info['filename'] = extracted_file_path.name
            inner_info['download_path'] = str(Path('/foi_assets') / foi_id / extracted_file_path.name)
            shutil.copy2(extracted_file_path, assets_output_subdir / extracted_file_path.name)
            artifact_info['content_files'].append(inner_info)
        shutil.copy2(file_path, output_base_dir / 'downloaded_originals' / file_path.name)
    else:
        shutil.copy2(file_path, output_base_dir / 'downloaded_originals' / file_path.name)
    # Update metadata with full artifact_info
    metadata_cache[str(file_path)] = {
        'size': stat.st_size,
        'mtime': int(stat.st_mtime),
        'hash': file_hash_val,
        'extracted': True,
        'artifact_info': artifact_info
    }
    return artifact_info

def load_metadata(metadata_path):
    if Path(metadata_path).exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_metadata(metadata, metadata_path):
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def extract_text_from_all_pdfs(pdf_paths):
    all_text = ""
    for pdf_path in pdf_paths:
        text = extract_text_from_pdf(pdf_path)
        all_text += text + "\n\n"  # Separate texts by double newline
    return all_text.strip()

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
    env = Environment(loader=FileSystemLoader(CONFIG['template_dir']))
    index_template = env.get_template("index.html")
    detail_template = env.get_template("document_detail.html")
    renderable_foi_data = []
    generated_files = []
    for req_data in all_foi_data:
        render_data = req_data.copy()
        # For each file in the FOI request, load extracted text if present
        for file in render_data.get('files', []):
            if file.get('extracted_text_path'):
                file['extracted_text'] = load_text_content(file['extracted_text_path'], output_base_dir)
            # For ZIPs, load inner file text
            if file.get('content_files'):
                for item in file['content_files']:
                    if item.get('extracted_text_path'):
                        item['extracted_text'] = load_text_content(item['extracted_text_path'], output_base_dir)
        # Pre-calculate type_counts
        type_counts = {}
        for file in render_data.get('files', []):
            t = file.get('type')
            if t:
                type_counts[t] = type_counts.get(t, 0) + 1
        render_data['type_counts'] = type_counts
        renderable_foi_data.append(render_data)
    index_page_documents = []
    for req_data in renderable_foi_data:
        html_filename = f"{req_data['id']}.html"
        output_html_path = output_base_dir / "documents" / html_filename
        req_data['output_html_path'] = f"/documents/{html_filename}"
        index_page_documents.append(req_data)
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(detail_template.render(request=req_data))
        generated_files.append(str(output_html_path))
    index_path = output_base_dir / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_template.render(documents=index_page_documents))
    generated_files.append(str(index_path))
    # Copy static assets
    if Path('static').exists():
        shutil.copytree('static', output_base_dir / 'static', dirs_exist_ok=True)
        # List all files copied from static
        static_files = []
        for root, dirs, files in os.walk('static'):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), 'static')
                out_path = output_base_dir / 'static' / rel_path
                static_files.append(str(out_path))
                print(f"Copied static asset: {out_path}")
        generated_files.extend(static_files)
    # --- Lunr.js search index generation ---
    search_index_data = []
    for req_data in renderable_foi_data:
        searchable_text = req_data['title'] + " "
        for file in req_data.get('files', []):
            if file.get('extracted_text'):
                searchable_text += file['extracted_text'] + " "
            if file.get('content_files'):
                for item in file['content_files']:
                    if item.get('type') == 'pdf' and item.get('extracted_text'):
                        searchable_text += item['extracted_text'] + " "
        search_entry = {
            'id': req_data['id'],
            'title': req_data['title'],
            'body': searchable_text.strip(),
            'url': req_data['output_html_path']
        }
        search_index_data.append(search_entry)
    search_index_path = output_base_dir / "search_index.json"
    with open(search_index_path, "w", encoding="utf-8") as f:
        json.dump(search_index_data, f, ensure_ascii=False, indent=4)
    generated_files.append(str(search_index_path))
    # Print summary of generated files
    print("\nGenerated output files:")
    for path in generated_files:
        print(f" - {path}")

def generate():
    config = CONFIG
    metadata_path = Path(config['data_dir']) / "file_metadata.json"
    metadata = load_metadata(metadata_path)
    all_foi_requests = get_foi_documents_metadata(year=config['year'])
    print(f"Found {len(all_foi_requests)} FOI requests.")
    download_dir = Path(config['download_dir'])
    download_dir.mkdir(exist_ok=True)
    output_base_dir = Path(config['output_dir'])
    (output_base_dir / "downloaded_originals").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "foi_assets").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "extracted_texts").mkdir(parents=True, exist_ok=True)
    MAX_WORKERS = 8
    download_tasks = []
    for foi_request in all_foi_requests:
        for file_entry in foi_request['files']:
            download_tasks.append((foi_request['id'], file_entry))
    download_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_task = {executor.submit(download_document, file_entry['original_url'], file_entry['server_filename'], download_dir, metadata, metadata_path): (foi_request_id, file_entry) for foi_request_id, file_entry in download_tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            foi_request_id, file_entry = future_to_task[future]
            try:
                result = future.result()
                download_results[(foi_request_id, file_entry['server_filename'])] = result
            except Exception as exc:
                print(f"Exception during download for {file_entry['server_filename']}: {exc}")
                download_results[(foi_request_id, file_entry['server_filename'])] = False
    final_processed_foi_data = []
    for foi_request in all_foi_requests:
        processed_request_data = {
            "id": foi_request['id'],
            "title": foi_request['title'],
            "date": foi_request['date'],
            "files": []
        }
        for file_entry in foi_request['files']:
            key = (foi_request['id'], file_entry['server_filename'])
            if download_results.get(key):
                local_path = download_dir / file_entry['server_filename']
                file_metadata = dict(file_entry)
                file_metadata['foi_id'] = foi_request['id']
                processed_file_data = process_file(file_metadata, local_path, config, metadata)
                processed_file_data.update({
                    'original_url': file_entry['original_url'],
                    'link_text': file_entry['link_text'],
                    'server_filename': file_entry['server_filename']
                })
                processed_request_data['files'].append(processed_file_data)
            else:
                print(f"Download failed for {file_entry['server_filename']} in {foi_request['id']}")
        final_processed_foi_data.append(processed_request_data)
    Path(config['data_dir']).mkdir(exist_ok=True)
    with open(Path(config['data_dir']) / "foi_data.json", "w", encoding="utf-8") as f:
        json.dump(final_processed_foi_data, f, ensure_ascii=False, indent=2)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    with open(Path(config['data_dir']) / "foi_data.json", "r", encoding="utf-8") as f:
        all_foi_data = json.load(f)
    generate_static_site(all_foi_data, output_base_dir)

if __name__ == "__main__":
    generate()
