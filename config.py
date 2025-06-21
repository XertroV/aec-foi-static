
# --- CONFIGURATION ---
CONFIG = {
    "year": 2025,
    "base_url": "https://www.aec.gov.au/information-access/foi/{year}/",
    "data_dir": "data",
    "output_dir": "docs",
    "download_dir": "downloads",
    "template_dir": "templates",
    "USE_OCR_FOR_PDFS": True,
}

# --- LLM CONFIGURATION ---
LLM_CONFIG = {
    'GEMINI_API_KEY_ENV_VAR': 'GEMINI_API_KEY',
    'DEFAULT_MODEL': 'gemini-2.5-flash',
    'DEFAULT_PERSONA': 'balanced',
    'PROMPT_TEMPLATES': {
        'balanced': {
            'overall': (
                "Summarize the following documents in markdown format. These documents are the released documents associated with an FOI request. "
                "The summary should focus on: the main purpose of the FOI request, the documents from the FOI request, and the main content from the FOI request documents that relates to the FOI request.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'short_index': (
                "Create a concise, single-paragraph summary in markdown format of the following FOI request summary:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'per_file': (
                "Considering this document as part of an FOI request, summarize the document and its relevance to the FOI request in markdown format. "
                "FYI the overview of the FOI request is: {overall_short_summary}\n\n"
                "Document Text:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
        },
        'left_leaning': {
            'overall': (
                "As a politically left-leaning analyst, summarize the following FOI documents. Focus on issues related to social justice, environmental impact, wealth distribution, corporate influence, and civil liberties. Highlight how government actions or policies revealed in these documents align with or deviate from progressive values.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'short_index': (
                "From a left-leaning perspective, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'per_file': (
                "From a left-leaning perspective, summarize this specific document within the context of the FOI request. Emphasize its implications for social equity, environmental concerns, or democratic accountability. "
                "The overall FOI overview is: {overall_short_summary}\n\n"
                "Document Text:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
        },
        'right_leaning': {
            'overall': (
                "As a politically right-leaning analyst, summarize the following FOI documents. Focus on issues related to economic efficiency, individual liberty, national security, fiscal responsibility, and limited government. Highlight how government actions or policies revealed in these documents align with or deviate from conservative principles.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'short_index': (
                "From a right-leaning perspective, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'per_file': (
                "From a right-leaning perspective, summarize this specific document within the context of the FOI request. Emphasize its implications for market freedom, government overreach, or national interest. "
                "The overall FOI overview is: {overall_short_summary}\n\n"
                "Document Text:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
        },
        'government_skeptic': {
            'overall': (
                "As a government skeptic, summarize the following FOI documents. Assume a critical stance, scrutinizing government claims, highlighting potential inefficiencies, overreach, or lack of transparency. Focus on findings that suggest waste, power abuse, or questionable decision-making.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'short_index': (
                "From a government skeptic's viewpoint, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'per_file': (
                "From a government skeptic's viewpoint, summarize this specific document within the context of the FOI request. Look for evidence of bureaucracy, lack of accountability, or any hidden agendas. "
                "The overall FOI overview is: {overall_short_summary}\n\n"
                "Document Text:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
        },
        'government_apologist': {
            'overall': (
                "As a government apologist, summarize the following FOI documents. Assume a supportive stance, emphasizing effective governance, necessary regulations, and positive outcomes. Frame any controversies as challenges effectively managed or essential actions for public good. Highlight the government's efforts to serve the public.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'short_index': (
                "From a government apologist's viewpoint, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'per_file': (
                "From a government apologist's viewpoint, summarize this specific document within the context of the FOI request. Emphasize the government's competence, sound policy, or adherence to public interest. "
                "The overall FOI overview is: {overall_short_summary}\n\n"
                "Document Text:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
        },
        'highly_critical': {
            'overall': (
                "Adopt a highly critical stance to summarize the following FOI documents. Ruthlessly analyze every detail for signs of failure, corruption, incompetence, or malice. Highlight every negative implication and present the most damning possible interpretation of the government's actions or inactions.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'short_index': (
                "With a highly critical view, provide a scathing, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
            'per_file': (
                "Critically summarize this specific document within the FOI request context. Point out every flaw, missed opportunity, or potential harm. Frame the content in the most negative light possible, questioning motives and outcomes. "
                "The overall FOI overview is: {overall_short_summary}\n\n"
                "Document Text:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble."
            ),
        },
    },
    'MAX_TOKENS': {
        'balanced': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
        'left_leaning': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
        'right_leaning': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
        'government_skeptic': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
        'government_apologist': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
        'highly_critical': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
    },
    'FORCE_SUMMARY_REGENERATION': False,
}
