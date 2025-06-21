import requests
from bs4 import BeautifulSoup
import re
from pdfminer.high_level import extract_text
from pdfminer.pdfparser import PDFSyntaxError
import zipfile
from pathlib import Path
import json
import markdown as md
import hashlib
from config import *

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

def process_file(file_metadata, local_path, config, metadata_cache, force_extract=False):
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
    if not force_extract and meta and meta.get('hash') == file_hash_val and meta.get('extracted') and meta.get('artifact_info'):
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
            inner_info = process_file(inner_file_metadata, extracted_file_path, config, metadata_cache, force_extract=force_extract)
            inner_info['filename'] = extracted_file_path.name
            inner_info['download_path'] = str(Path('/foi_assets') / foi_id / extracted_file_path.name)
            shutil.copy2(extracted_file_path, assets_output_subdir / extracted_file_path.name)
            artifact_info['content_files'].append(inner_info)
        shutil.copy2(file_path, output_base_dir / 'downloaded_originals' / file_path.name)
    else:
        shutil.copy2(file_path, output_base_dir / 'downloaded_originals' / file_path.name)
    # Update metadata with full artifact_info
    # --- AI summary placeholder logic ---
    ai_summaries = {}
    extracted_text_path = artifact_info.get('extracted_text_path')
    if file_type == 'pdf' and extracted_text_path:
        output_base_dir = Path(config['output_dir'])
        extracted_text = load_text_content(extracted_text_path, output_base_dir)
        current_text_hash = hashlib.sha256(extracted_text.encode('utf-8')).hexdigest() if extracted_text else None
        meta_ai_summaries = None
        if meta and 'artifact_info' in meta and 'ai_summaries' in meta['artifact_info']:
            meta_ai_summaries = meta['artifact_info']['ai_summaries']
        for persona_id in LLM_CONFIG['PROMPT_TEMPLATES'].keys():
            prev = meta_ai_summaries.get(persona_id) if meta_ai_summaries else None
            if not extracted_text:
                ai_summaries[persona_id] = None
            elif (LLM_CONFIG['FORCE_SUMMARY_REGENERATION'] or not prev or prev.get('source_hash') != current_text_hash):
                ai_summaries[persona_id] = {'needs_summary': True, 'source_hash': current_text_hash}
            else:
                ai_summaries[persona_id] = prev
    else:
        # For non-PDFs or if extracted_text_path was not set (e.g., DOCX, image, video)
        for persona_id in LLM_CONFIG['PROMPT_TEMPLATES'].keys():
            ai_summaries[persona_id] = None
    artifact_info['ai_summaries'] = ai_summaries
    # For ZIPs, propagate ai_summaries logic to content_files - make sure it defaults to None as well
    if file_type == 'zip' and artifact_info.get('content_files'):
        for idx, item in enumerate(artifact_info['content_files']):
            if 'ai_summaries' not in item or not item['ai_summaries']:
                item['ai_summaries'] = {p: None for p in LLM_CONFIG['PROMPT_TEMPLATES'].keys()}
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

def load_text_content(text_file_path, output_base_dir):
    try:
        abs_path = output_base_dir / text_file_path.lstrip('/')
        if abs_path.exists():
            with open(abs_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"Error loading text from {text_file_path}: {e}")
    return ""
