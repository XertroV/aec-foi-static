from env_utils import load_env_var_from_dotenv
load_env_var_from_dotenv('GEMINI_API_KEY')
from config import *
from data_processing import *
from html_generator import markdown_filter, generate_static_site
from llm_summarizer import deep_merge_foi_request, generate_all_summaries
from pathlib import Path
import concurrent.futures
import json

def main():
    import argparse
    import datetime
    parser = argparse.ArgumentParser(description="Build AEC FOI static archive.")
    parser.add_argument('--force-summaries', action='store_true', help='Force regeneration of all AI summaries')
    parser.add_argument('--force-extract', action='store_true', help='Force re-extraction of text from PDFs (does not force summary regeneration unless text changes)')
    parser.add_argument('--year', type=int, help='Process only a specific year (e.g., 2023)')
    parser.add_argument('--personas', type=str, help='Comma-separated list of persona IDs to generate summaries for (others will be skipped, existing summaries for other personas will be untouched)')
    parser.add_argument('--foi-id', type=str, help='Process only a specific FOI request ID (e.g., LEX1234 or LS5678)')
    parser.add_argument('--list-xlsx', action='store_true', help='List all FOI requests that have an xlsx file (from foi_data.json) and exit')
    args = parser.parse_args()
    config = CONFIG


    if args.list_xlsx:
        foi_data_path = Path(config['data_dir']) / "foi_data.json"
        if not foi_data_path.exists():
            print("No foi_data.json found.")
            return
        with open(foi_data_path, "r", encoding="utf-8") as f:
            foi_data = json.load(f)
        found = False
        for req in foi_data:
            # Top-level xlsx files
            xlsx_files = [f for f in req.get('files', []) if f.get('type') == 'xlsx']
            # Inner xlsx files in zips
            for file in req.get('files', []):
                if file.get('type') == 'zip' and file.get('content_files'):
                    for inner in file['content_files']:
                        if inner.get('type') == 'xlsx':
                            xlsx_files.append(inner)
            if xlsx_files:
                found = True
                print(f"FOI {req['id']} ({req.get('title', '')}):")
                for f in xlsx_files:
                    print(f"  - {f.get('server_filename', f.get('filename', ''))}")
        if not found:
            print("No FOI requests with xlsx files found.")
        return


    LLM_CONFIG['FORCE_SUMMARY_REGENERATION'] = args.force_summaries
    config['FORCE_EXTRACT'] = args.force_extract  # <--- propagate to config
    # Parse personas flag
    selected_personas = None
    if args.personas:
        selected_personas = set([p.strip() for p in args.personas.split(',') if p.strip()])
    metadata_path = Path(config['data_dir']) / "file_metadata.json"
    metadata = load_metadata(metadata_path)
    # Determine years to process
    if args.year:
        years = [args.year]
    else:
        current_year = datetime.datetime.now().year
        years = list(range(2012, current_year + 1))
    all_foi_requests = []
    for year in years:
        print(f"Fetching FOI requests for year {year}...")
        config['year'] = year
        foi_requests = get_foi_documents_metadata(year=year)
        for req in foi_requests:
            req['year'] = year
        all_foi_requests.extend(foi_requests)
    # --- Filter by FOI ID if requested ---
    if args.foi_id:
        all_foi_requests = [req for req in all_foi_requests if req['id'].lower() == args.foi_id.lower()]
        print(f"Filtered to FOI ID {args.foi_id}: {len(all_foi_requests)} requests remain.")
    print(f"Found {len(all_foi_requests)} FOI requests across years {years}.")
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
            "year": foi_request.get('year', config['year']),
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
                processed_file_data = process_file(file_metadata, local_path, config, metadata, force_extract=args.force_extract)
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

    # temp disable per-file summaries
    no_generate_per_file = True
    generate_all_summaries(final_processed_foi_data, config, metadata, selected_personas=selected_personas, no_generate_per_file=no_generate_per_file)

    # --- Merge with cache: always update/add processed requests, keep others ---
    for req in final_processed_foi_data:
        cached_foi_data[req['id']] = deep_merge_foi_request(req, cached_foi_data.get(req['id']))
    merged_foi_data = list(cached_foi_data.values())

    # Save after all summaries
    Path(config['data_dir']).mkdir(exist_ok=True)
    with open(Path(config['data_dir']) / "foi_data.json", "w", encoding="utf-8") as f:
        json.dump(merged_foi_data, f, ensure_ascii=False, indent=2)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    with open(Path(config['data_dir']) / "foi_data.json", "r", encoding="utf-8") as f:
        all_foi_data = json.load(f)
    generate_static_site(all_foi_data, output_base_dir)


if __name__ == "__main__":
    main()
