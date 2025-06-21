from env_utils import load_env_var_from_dotenv
load_env_var_from_dotenv('GEMINI_API_KEY')

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
import markdown as md
import concurrent.futures
import hashlib
import llm_client
from datetime import datetime

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
            "Summarize the following documents in markdown format. These documents are the released documents associated with an FOI request. "
            "The summary should focus on: the main purpose of the FOI request, the documents from the FOI request, and the main content from the FOI request documents that relates to the FOI request.\n\nDocuments:\n\n{text}"
        ),
        'short_index': (
            "Create a single paragraph summary in markdown format of the following FOI request summary:\n\nSummary:\n\n{text}"
        ),
        'per_file': (
            "Considering this document as part of an FOI request, summarize the document and its relevance to the FOI request in markdown format. "
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
    # --- AI summary placeholder logic ---
    ai_summary = None
    extracted_text_path = artifact_info.get('extracted_text_path')
    if file_type == 'pdf' and extracted_text_path:
        output_base_dir = Path(config['output_dir'])
        extracted_text = load_text_content(extracted_text_path, output_base_dir)
        current_text_hash = hashlib.sha256(extracted_text.encode('utf-8')).hexdigest() if extracted_text else None
        meta_ai_summary = None
        if meta and 'artifact_info' in meta and 'ai_summary' in meta['artifact_info']:
            meta_ai_summary = meta['artifact_info']['ai_summary']
        if not extracted_text:
            ai_summary = None
        elif (LLM_CONFIG['FORCE_SUMMARY_REGENERATION'] or not meta_ai_summary or meta_ai_summary.get('source_hash') != current_text_hash):
            ai_summary = {'needs_summary': True, 'source_hash': current_text_hash}
        else:
            ai_summary = meta_ai_summary
    artifact_info['ai_summary'] = ai_summary
    # For ZIPs, propagate ai_summary logic to content_files
    if file_type == 'zip' and artifact_info.get('content_files'):
        for idx, item in enumerate(artifact_info['content_files']):
            # Only update if not already present
            if 'ai_summary' not in item:
                artifact_info['content_files'][idx]['ai_summary'] = None
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

def markdown_filter(text):
    return md.markdown(text or "")

def generate_static_site(all_foi_data, output_base_dir):
    output_base_dir = Path(output_base_dir)
    (output_base_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "static").mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(CONFIG['template_dir']))
    env.filters['markdown'] = markdown_filter
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

def generate(force_summaries=False):
    config = CONFIG
    LLM_CONFIG['FORCE_SUMMARY_REGENERATION'] = force_summaries
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
    # --- Load cached summaries from foi_data.json if available ---
    cached_foi_data = {}
    foi_data_path = Path(config['data_dir']) / "foi_data.json"
    if foi_data_path.exists():
        with open(foi_data_path, "r", encoding="utf-8") as f:
            try:
                for req in json.load(f):
                    cached_foi_data[req['id']] = req
            except Exception as e:
                print(f"Warning: Could not load cached FOI data: {e}")
    final_processed_foi_data = []
    for foi_request in all_foi_requests:
        processed_request_data = {
            "id": foi_request['id'],
            "title": foi_request['title'],
            "date": foi_request['date'],
            "files": []
        }
        # Copy cached summaries if available
        cached_req = cached_foi_data.get(foi_request['id'])
        if cached_req:
            if 'ai_overall_summary' in cached_req:
                processed_request_data['ai_overall_summary'] = cached_req['ai_overall_summary']
            if 'ai_short_summary' in cached_req:
                processed_request_data['ai_short_summary'] = cached_req['ai_short_summary']
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
                # Copy cached per-file ai_summary if available
                if cached_req and 'files' in cached_req:
                    for cached_file in cached_req['files']:
                        if (cached_file.get('server_filename') == file_entry['server_filename'] and 'ai_summary' in cached_file):
                            processed_file_data['ai_summary'] = cached_file['ai_summary']
                        # For ZIPs, copy ai_summary for inner files
                        if 'content_files' in processed_file_data and 'content_files' in cached_file:
                            for idx, item in enumerate(processed_file_data['content_files']):
                                for cached_item in cached_file['content_files']:
                                    if (cached_item.get('filename') == item.get('filename') and 'ai_summary' in cached_item):
                                        processed_file_data['content_files'][idx]['ai_summary'] = cached_item['ai_summary']
                processed_request_data['files'].append(processed_file_data)
            else:
                print(f"Download failed for {file_entry['server_filename']} in {foi_request['id']}")
        final_processed_foi_data.append(processed_request_data)

    # --- AI SUMMARY GENERATION ---
    for foi_request in final_processed_foi_data:
        # Aggregate all extracted text for overall summary
        all_texts = []
        for file in foi_request['files']:
            if file.get('extracted_text_path'):
                output_base_dir = Path(config['output_dir'])
                text = load_text_content(file['extracted_text_path'], output_base_dir)
                if text:
                    all_texts.append(text)
            if file.get('content_files'):
                for item in file['content_files']:
                    if item.get('extracted_text_path'):
                        output_base_dir = Path(config['output_dir'])
                        text = load_text_content(item['extracted_text_path'], output_base_dir)
                        if text:
                            all_texts.append(text)
        combined_text = '\n\n'.join(all_texts)
        combined_text_hash = hashlib.sha256(combined_text.encode('utf-8')).hexdigest() if combined_text else None
        # --- Overall summary ---
        ai_overall_summary = foi_request.get('ai_overall_summary')
        reason = None
        if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
            reason = 'forced regeneration (--force-summaries)'
        elif not ai_overall_summary:
            reason = 'no previous summary exists'
        elif ai_overall_summary.get('source_hash') != combined_text_hash:
            reason = 'source text changed (hash mismatch)'
        if reason:
            print(f"[LLM][{foi_request['id']}] Regenerating overall summary because: {reason}")
        if reason:
            if combined_text:
                print(f"[LLM][{foi_request['id']}] Requesting overall summary...", end='', flush=True)
                summary_text, raw_response = llm_client.generate_summary(
                    combined_text,
                    LLM_CONFIG['PROMPT_TEMPLATES']['overall'],
                    LLM_CONFIG['DEFAULT_MODEL'],
                    LLM_CONFIG['MAX_TOKENS']['overall'],
                    return_full_response=True
                )
                resp_path = save_llm_response(raw_response, foi_request['id'], 'overall')
                usage = raw_response.get('usage_metadata', {}) if isinstance(raw_response, dict) else {}
                output_tokens = usage.get('candidates_token_count')
                prompt_tokens = usage.get('prompt_token_count')
                total_tokens = usage.get('total_token_count')
                print(f" done. Saved raw response: {resp_path} | Model: {LLM_CONFIG['DEFAULT_MODEL']} | Output tokens: {output_tokens} | Prompt tokens: {prompt_tokens} | Total tokens: {total_tokens} | Summary length: {len(summary_text)}")
            else:
                summary_text = ''
                resp_path = None
                output_tokens = prompt_tokens = total_tokens = None
            ai_overall_summary = {
                'text': summary_text,
                'model': LLM_CONFIG['DEFAULT_MODEL'],
                'generated_at': datetime.now().isoformat(),
                'source_hash': combined_text_hash,
                'raw_response_path': resp_path,
                'output_tokens': output_tokens,
                'prompt_tokens': prompt_tokens,
                'total_tokens': total_tokens,
                'summary_length': len(summary_text) if summary_text else 0
            }
        foi_request['ai_overall_summary'] = ai_overall_summary
        # --- Short index summary ---
        ai_short_summary = foi_request.get('ai_short_summary')
        short_source_hash = ai_overall_summary['source_hash'] if ai_overall_summary else None
        reason = None
        if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
            reason = 'forced regeneration (--force-summaries)'
        elif not ai_short_summary:
            reason = 'no previous summary exists'
        elif ai_short_summary.get('source_hash') != short_source_hash:
            reason = 'source text changed (hash mismatch)'
        if reason:
            print(f"[LLM][{foi_request['id']}] Regenerating short index summary because: {reason}")
        if reason:
            if ai_overall_summary and ai_overall_summary.get('text'):
                print(f"[LLM][{foi_request['id']}] Requesting short index summary...", end='', flush=True)
                short_text, raw_response = llm_client.generate_summary(
                    ai_overall_summary['text'],
                    LLM_CONFIG['PROMPT_TEMPLATES']['short_index'],
                    LLM_CONFIG['DEFAULT_MODEL'],
                    LLM_CONFIG['MAX_TOKENS']['short_index'],
                    return_full_response=True
                )
                resp_path = save_llm_response(raw_response, foi_request['id'], 'short_index')
                usage = raw_response.get('usage_metadata', {}) if isinstance(raw_response, dict) else {}
                output_tokens = usage.get('candidates_token_count')
                prompt_tokens = usage.get('prompt_token_count')
                total_tokens = usage.get('total_token_count')
                print(f" done. Saved raw response: {resp_path} | Model: {LLM_CONFIG['DEFAULT_MODEL']} | Output tokens: {output_tokens} | Prompt tokens: {prompt_tokens} | Total tokens: {total_tokens} | Summary length: {len(short_text)}")
            else:
                short_text = ''
                resp_path = None
                output_tokens = prompt_tokens = total_tokens = None
            ai_short_summary = {
                'text': short_text,
                'model': LLM_CONFIG['DEFAULT_MODEL'],
                'generated_at': datetime.now().isoformat(),
                'source_hash': short_source_hash,
                'raw_response_path': resp_path,
                'output_tokens': output_tokens,
                'prompt_tokens': prompt_tokens,
                'total_tokens': total_tokens,
                'summary_length': len(short_text) if short_text else 0
            }
        foi_request['ai_short_summary'] = ai_short_summary
        # --- Per-file summaries ---
        for file in foi_request['files']:
            # Top-level file
            if file.get('ai_summary', {}).get('needs_summary'):
                output_base_dir = Path(config['output_dir'])
                text = load_text_content(file.get('extracted_text_path', ''), output_base_dir)
                file_hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None
                reason = None
                if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
                    reason = 'forced regeneration (--force-summaries)'
                elif not file.get('ai_summary'):
                    reason = 'no previous summary exists'
                elif file.get('ai_summary', {}).get('source_hash') != file_hash_val:
                    reason = 'source text changed (hash mismatch)'
                if reason:
                    print(f"[LLM][{foi_request['id']}] Regenerating per-file summary for {file.get('server_filename', file.get('link_text', 'file'))} because: {reason}")
                if text and reason:
                    print(f"[LLM][{foi_request['id']}] Requesting per-file summary for {file.get('server_filename', file.get('link_text', 'file'))}...", end='', flush=True)
                    per_file_prompt = LLM_CONFIG['PROMPT_TEMPLATES']['per_file'].format(
                        overall_short_summary=ai_short_summary['text'], text=text)
                    summary_text, raw_response = llm_client.generate_summary(
                        text,
                        per_file_prompt,
                        LLM_CONFIG['DEFAULT_MODEL'],
                        LLM_CONFIG['MAX_TOKENS']['per_file'],
                        return_full_response=True
                    )
                    resp_path = save_llm_response(raw_response, foi_request['id'], 'per_file', file.get('server_filename', file.get('link_text', 'file')))
                    usage = raw_response.get('usage_metadata', {}) if isinstance(raw_response, dict) else {}
                    output_tokens = usage.get('candidates_token_count')
                    prompt_tokens = usage.get('prompt_token_count')
                    total_tokens = usage.get('total_token_count')
                    print(f" done. Saved raw response: {resp_path} | Model: {LLM_CONFIG['DEFAULT_MODEL']} | Output tokens: {output_tokens} | Prompt tokens: {prompt_tokens} | Total tokens: {total_tokens} | Summary length: {len(summary_text)}")
                else:
                    summary_text = ''
                    resp_path = None
                    output_tokens = prompt_tokens = total_tokens = None
                file['ai_summary'] = {
                    'text': summary_text,
                    'model': LLM_CONFIG['DEFAULT_MODEL'],
                    'generated_at': datetime.now().isoformat(),
                    'source_hash': file_hash_val,
                    'raw_response_path': resp_path,
                    'output_tokens': output_tokens,
                    'prompt_tokens': prompt_tokens,
                    'total_tokens': total_tokens,
                    'summary_length': len(summary_text) if summary_text else 0
                }
            # ZIP inner files
            if file.get('content_files'):
                for item in file['content_files']:
                    if item.get('ai_summary', {}).get('needs_summary'):
                        output_base_dir = Path(config['output_dir'])
                        text = load_text_content(item.get('extracted_text_path', ''), output_base_dir)
                        file_hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None
                        reason = None
                        if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
                            reason = 'forced regeneration (--force-summaries)'
                        elif not item.get('ai_summary'):
                            reason = 'no previous summary exists'
                        elif item.get('ai_summary', {}).get('source_hash') != file_hash_val:
                            reason = 'source text changed (hash mismatch)'
                        if reason:
                            print(f"[LLM][{foi_request['id']}] Regenerating per-file summary for ZIP inner {item.get('filename', 'file')} because: {reason}")
                        if text and reason:
                            print(f"[LLM][{foi_request['id']}] Requesting per-file summary for ZIP inner {item.get('filename', 'file')}...", end='', flush=True)
                            per_file_prompt = LLM_CONFIG['PROMPT_TEMPLATES']['per_file'].format(
                                overall_short_summary=ai_short_summary['text'], text=text)
                            summary_text, raw_response = llm_client.generate_summary(
                                text,
                                per_file_prompt,
                                LLM_CONFIG['DEFAULT_MODEL'],
                                LLM_CONFIG['MAX_TOKENS']['per_file'],
                                return_full_response=True
                            )
                            resp_path = save_llm_response(raw_response, foi_request['id'], 'per_file', item.get('filename', 'file'))
                            usage = raw_response.get('usage_metadata', {}) if isinstance(raw_response, dict) else {}
                            output_tokens = usage.get('candidates_token_count')
                            prompt_tokens = usage.get('prompt_token_count')
                            total_tokens = usage.get('total_token_count')
                            print(f" done. Saved raw response: {resp_path} | Model: {LLM_CONFIG['DEFAULT_MODEL']} | Output tokens: {output_tokens} | Prompt tokens: {prompt_tokens} | Total tokens: {total_tokens} | Summary length: {len(summary_text)}")
                        else:
                            summary_text = ''
                            resp_path = None
                            output_tokens = prompt_tokens = total_tokens = None
                        item['ai_summary'] = {
                            'text': summary_text,
                            'model': LLM_CONFIG['DEFAULT_MODEL'],
                            'generated_at': datetime.now().isoformat(),
                            'source_hash': file_hash_val,
                            'raw_response_path': resp_path,
                            'output_tokens': output_tokens,
                            'prompt_tokens': prompt_tokens,
                            'total_tokens': total_tokens,
                            'summary_length': len(summary_text) if summary_text else 0
                        }
    # Save after all summaries
    Path(config['data_dir']).mkdir(exist_ok=True)
    with open(Path(config['data_dir']) / "foi_data.json", "w", encoding="utf-8") as f:
        json.dump(final_processed_foi_data, f, ensure_ascii=False, indent=2)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    with open(Path(config['data_dir']) / "foi_data.json", "r", encoding="utf-8") as f:
        all_foi_data = json.load(f)
    generate_static_site(all_foi_data, output_base_dir)

def save_llm_response(raw_response, foi_id, summary_type, file_id=None):
    """Save the raw LLM response to disk and return the path."""
    out_dir = Path(CONFIG['data_dir']) / 'llm_responses'
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{foi_id}__{summary_type}"
    if file_id:
        fname += f"__{file_id}"
    fname += f"__{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out_path = out_dir / fname
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(raw_response, f, ensure_ascii=False, indent=2)
    return str(out_path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build AEC FOI static archive.")
    parser.add_argument('--force-summaries', action='store_true', help='Force regeneration of all AI summaries')
    args = parser.parse_args()
    generate(force_summaries=args.force_summaries)
