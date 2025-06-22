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
from data_processing import *
import llm_client
from config import *
from datetime import datetime

def markdown_filter(text):
    # Enable 'extra' for lists, tables, etc. and 'nl2br' for newlines
    return md.markdown(text or "", extensions=["extra", "nl2br"])

def ensure_default_persona_ai_summaries(data, default_persona):
    # For each FOI request
    for req in data:
        if 'ai_summaries' not in req or not isinstance(req['ai_summaries'], dict):
            req['ai_summaries'] = {}
        if default_persona not in req['ai_summaries']:
            req['ai_summaries'][default_persona] = {'overall': {'text': ''}, 'short_index': {'text': ''}}
        else:
            if 'overall' not in req['ai_summaries'][default_persona]:
                req['ai_summaries'][default_persona]['overall'] = {'text': ''}
            if 'short_index' not in req['ai_summaries'][default_persona]:
                req['ai_summaries'][default_persona]['short_index'] = {'text': ''}
        for file in req.get('files', []):
            if 'ai_summaries' not in file or not isinstance(file['ai_summaries'], dict):
                file['ai_summaries'] = {}
            if default_persona not in file['ai_summaries']:
                file['ai_summaries'][default_persona] = {'text': ''}
            if file.get('content_files'):
                for item in file['content_files']:
                    if 'ai_summaries' not in item or not isinstance(item['ai_summaries'], dict):
                        item['ai_summaries'] = {}
                    if default_persona not in item['ai_summaries']:
                        item['ai_summaries'][default_persona] = {'text': ''}

def generate_static_site(all_foi_data, output_base_dir):
    output_base_dir = Path(output_base_dir)
    (output_base_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_base_dir / "static").mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(CONFIG['template_dir']))
    env.filters['markdown'] = markdown_filter
    env.globals['PERSONAS'] = list(LLM_CONFIG['PROMPT_TEMPLATES'].keys())
    env.globals['DEFAULT_PERSONA'] = LLM_CONFIG['DEFAULT_PERSONA']
    index_template = env.get_template("index.html")
    detail_template = env.get_template("document_detail.html")
    # --- PATCH: Ensure every FOI request, file, and inner file has ai_summaries[DEFAULT_PERSONA] ---
    ensure_default_persona_ai_summaries(all_foi_data, LLM_CONFIG['DEFAULT_PERSONA'])
    # --- Sort by date (newest first), then by ID (larger number first) ---
    def sort_key(req):
        # Date as int (fallback 0), ID as int if possible (fallback 0)
        try:
            date_val = int(req.get('date', 0))
        except Exception:
            date_val = 0
        id_val = 0
        id_str = str(req.get('id', ''))
        match = re.search(r'(\d+)$', id_str)
        if match:
            try:
                id_val = int(match.group(1))
            except Exception:
                id_val = 0
        return (date_val, id_val)
    sorted_foi_data = sorted(all_foi_data, key=sort_key, reverse=True)
    renderable_foi_data = []
    generated_files = []
    for req_data in sorted_foi_data:
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
            f.write(detail_template.render(request=req_data, request_data_json=json.dumps(req_data)))
        generated_files.append(str(output_html_path))
    index_path = output_base_dir / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_template.render(
            documents=index_page_documents,
            documents_data_json=json.dumps(index_page_documents, ensure_ascii=False)
        ))
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
