import hashlib
from datetime import datetime
import llm_client
from config import LLM_CONFIG, CONFIG
from data_processing import load_text_content
from pathlib import Path
import json


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


def generate_all_summaries(final_processed_foi_data, config, metadata):
    """
    For each FOI request, generate all required summaries for all personas.
    Modifies final_processed_foi_data in place.
    """
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
                reason = f'source text changed (hash mismatch) (old: {ai_overall_summary.get("source_hash")}, new: {combined_text_hash})'
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
