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
from config import *
from data_processing import *
from html_generator import markdown_filter, generate_static_site
from datetime import datetime

def extract_text_from_all_pdfs(pdf_paths):
    all_text = ""
    for pdf_path in pdf_paths:
        text = extract_text_from_pdf(pdf_path)
        all_text += text + "\n\n"  # Separate texts by double newline
    return all_text.strip()


def generate(force_summaries=False, force_extract=False):
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
            if 'ai_summaries' in cached_req:
                processed_request_data['ai_summaries'] = cached_req['ai_summaries']
        for file_entry in foi_request['files']:
            key = (foi_request['id'], file_entry['server_filename'])
            if download_results.get(key):
                local_path = download_dir / file_entry['server_filename']
                file_metadata = dict(file_entry)
                file_metadata['foi_id'] = foi_request['id']
                processed_file_data = process_file(file_metadata, local_path, config, metadata, force_extract=force_extract)
                processed_file_data.update({
                    'original_url': file_entry['original_url'],
                    'link_text': file_entry['link_text'],
                    'server_filename': file_entry['server_filename']
                })
                # Copy cached per-file ai_summaries if available
                if cached_req and 'files' in cached_req:
                    for cached_file in cached_req['files']:
                        if (cached_file.get('server_filename') == file_entry['server_filename'] and 'ai_summaries' in cached_file):
                            processed_file_data['ai_summaries'] = cached_file['ai_summaries']
                        # For ZIPs, copy ai_summaries for inner files
                        if 'content_files' in processed_file_data and 'content_files' in cached_file:
                            for idx, item in enumerate(processed_file_data['content_files']):
                                for cached_item in cached_file['content_files']:
                                    if (cached_item.get('filename') == item.get('filename') and 'ai_summaries' in cached_item):
                                        processed_file_data['content_files'][idx]['ai_summaries'] = cached_item['ai_summaries']
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
        # Persona loop
        for current_persona_id in LLM_CONFIG['PROMPT_TEMPLATES'].keys():
            if 'ai_summaries' not in foi_request:
                foi_request['ai_summaries'] = {}
            if current_persona_id not in foi_request['ai_summaries']:
                foi_request['ai_summaries'][current_persona_id] = {}
            # --- Overall summary ---
            ai_overall_summary = foi_request['ai_summaries'][current_persona_id].get('overall')
            reason = None
            if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
                reason = 'forced regeneration (--force-summaries)'
            elif not ai_overall_summary:
                reason = 'no previous summary exists'
            elif ai_overall_summary.get('source_hash') != combined_text_hash:
                reason = 'source text changed (hash mismatch)'
            if reason:
                print(f"[LLM][{foi_request['id']}][{current_persona_id}] Regenerating overall summary because: {reason}")
            if reason:
                if combined_text:
                    print(f"[LLM][{foi_request['id']}][{current_persona_id}] Requesting overall summary...", end='', flush=True)
                    summary_text, raw_response = llm_client.generate_summary(
                        combined_text,
                        LLM_CONFIG['PROMPT_TEMPLATES'][current_persona_id]['overall'],
                        LLM_CONFIG['DEFAULT_MODEL'],
                        LLM_CONFIG['MAX_TOKENS'][current_persona_id]['overall'],
                        return_full_response=True
                    )
                    resp_path = save_llm_response(raw_response, foi_request['id'], 'overall', current_persona_id)
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
            foi_request['ai_summaries'][current_persona_id]['overall'] = ai_overall_summary
            # --- Short index summary ---
            ai_short_summary = foi_request['ai_summaries'][current_persona_id].get('short_index')
            short_source_hash = ai_overall_summary['source_hash'] if ai_overall_summary else None
            reason = None
            if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
                reason = 'forced regeneration (--force-summaries)'
            elif not ai_short_summary:
                reason = 'no previous summary exists'
            elif ai_short_summary.get('source_hash') != short_source_hash:
                reason = 'source text changed (hash mismatch)'
            if reason:
                print(f"[LLM][{foi_request['id']}][{current_persona_id}] Regenerating short index summary because: {reason}")
            if reason:
                if ai_overall_summary and ai_overall_summary.get('text'):
                    print(f"[LLM][{foi_request['id']}][{current_persona_id}] Requesting short index summary...", end='', flush=True)
                    short_text, raw_response = llm_client.generate_summary(
                        ai_overall_summary['text'],
                        LLM_CONFIG['PROMPT_TEMPLATES'][current_persona_id]['short_index'],
                        LLM_CONFIG['DEFAULT_MODEL'],
                        LLM_CONFIG['MAX_TOKENS'][current_persona_id]['short_index'],
                        return_full_response=True
                    )
                    resp_path = save_llm_response(raw_response, foi_request['id'], 'short_index', current_persona_id)
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
            foi_request['ai_summaries'][current_persona_id]['short_index'] = ai_short_summary
            # --- Per-file summaries ---
            for file in foi_request['files']:
                if 'ai_summaries' not in file:
                    file['ai_summaries'] = {}
                # Top-level file
                persona_file_summary = file['ai_summaries'].get(current_persona_id)
                file_hash_val = None
                if file.get('extracted_text_path'):
                    output_base_dir = Path(config['output_dir'])
                    text = load_text_content(file.get('extracted_text_path', ''), output_base_dir)
                    file_hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None
                else:
                    text = None
                reason = None
                if file.get('type') == 'pdf':
                    if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
                        reason = 'forced regeneration (--force-summaries)'
                    elif not persona_file_summary:
                        reason = 'no previous summary exists'
                    elif persona_file_summary.get('source_hash') != file_hash_val:
                        reason = 'source text changed (hash mismatch)'
                    if reason:
                        print(f"[LLM][{foi_request['id']}][{current_persona_id}] Regenerating per-file summary for {file.get('server_filename', file.get('link_text', 'file'))} because: {reason}")
                    if text and reason:
                        print(f"[LLM][{foi_request['id']}][{current_persona_id}] Requesting per-file summary for {file.get('server_filename', file.get('link_text', 'file'))}...", end='', flush=True)
                        per_file_prompt = LLM_CONFIG['PROMPT_TEMPLATES'][current_persona_id]['per_file'].format(
                            overall_short_summary=ai_short_summary['text'], text=text)
                        summary_text, raw_response = llm_client.generate_summary(
                            text,
                            per_file_prompt,
                            LLM_CONFIG['DEFAULT_MODEL'],
                            LLM_CONFIG['MAX_TOKENS'][current_persona_id]['per_file'],
                            return_full_response=True
                        )
                        resp_path = save_llm_response(raw_response, foi_request['id'], 'per_file', current_persona_id, file.get('server_filename', file.get('link_text', 'file')))
                        usage = raw_response.get('usage_metadata', {}) if isinstance(raw_response, dict) else {}
                        output_tokens = usage.get('candidates_token_count')
                        prompt_tokens = usage.get('prompt_token_count')
                        total_tokens = usage.get('total_token_count')
                        print(f" done. Saved raw response: {resp_path} | Model: {LLM_CONFIG['DEFAULT_MODEL']} | Output tokens: {output_tokens} | Prompt tokens: {prompt_tokens} | Total tokens: {total_tokens} | Summary length: {len(summary_text)}")
                    else:
                        summary_text = ''
                        resp_path = None
                        output_tokens = prompt_tokens = total_tokens = None
                    file['ai_summaries'][current_persona_id] = {
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
                        if 'ai_summaries' not in item:
                            item['ai_summaries'] = {}
                        persona_item_summary = item['ai_summaries'].get(current_persona_id)
                        file_hash_val = None
                        if item.get('extracted_text_path'):
                            output_base_dir = Path(config['output_dir'])
                            text = load_text_content(item.get('extracted_text_path', ''), output_base_dir)
                            file_hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None
                        else:
                            text = None
                        reason = None
                        if item.get('type') == 'pdf':
                            if LLM_CONFIG['FORCE_SUMMARY_REGENERATION']:
                                reason = 'forced regeneration (--force-summaries)'
                            elif not persona_item_summary:
                                reason = 'no previous summary exists'
                            elif persona_item_summary.get('source_hash') != file_hash_val:
                                reason = 'source text changed (hash mismatch)'
                            if reason:
                                print(f"[LLM][{foi_request['id']}][{current_persona_id}] Regenerating per-file summary for ZIP inner {item.get('filename', 'file')} because: {reason}")
                            if text and reason:
                                print(f"[LLM][{foi_request['id']}][{current_persona_id}] Requesting per-file summary for ZIP inner {item.get('filename', 'file')}...", end='', flush=True)
                                per_file_prompt = LLM_CONFIG['PROMPT_TEMPLATES'][current_persona_id]['per_file'].format(
                                    overall_short_summary=ai_short_summary['text'], text=text)
                                summary_text, raw_response = llm_client.generate_summary(
                                    text,
                                    per_file_prompt,
                                    LLM_CONFIG['DEFAULT_MODEL'],
                                    LLM_CONFIG['MAX_TOKENS'][current_persona_id]['per_file'],
                                    return_full_response=True
                                )
                                resp_path = save_llm_response(raw_response, foi_request['id'], 'per_file', current_persona_id, item.get('filename', 'file'))
                                usage = raw_response.get('usage_metadata', {}) if isinstance(raw_response, dict) else {}
                                output_tokens = usage.get('candidates_token_count')
                                prompt_tokens = usage.get('prompt_token_count')
                                total_tokens = usage.get('total_token_count')
                                print(f" done. Saved raw response: {resp_path} | Model: {LLM_CONFIG['DEFAULT_MODEL']} | Output tokens: {output_tokens} | Prompt tokens: {prompt_tokens} | Total tokens: {total_tokens} | Summary length: {len(summary_text)}")
                            else:
                                summary_text = ''
                                resp_path = None
                                output_tokens = prompt_tokens = total_tokens = None
                            item['ai_summaries'][current_persona_id] = {
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

def save_llm_response(raw_response, foi_id, summary_type, persona_id, file_id=None):
    """Save the raw LLM response to disk and return the path."""
    out_dir = Path(CONFIG['data_dir']) / 'llm_responses'
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{foi_id}__{summary_type}__{persona_id}"
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
    parser.add_argument('--force-extract', action='store_true', help='Force re-extraction of text from PDFs (does not force summary regeneration unless text changes)')
    args = parser.parse_args()
    generate(force_summaries=args.force_summaries, force_extract=args.force_extract)
