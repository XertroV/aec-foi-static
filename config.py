# --- CONFIGURATION ---
CONFIG = {
    "year": 2025,
    "base_url": "https://www.aec.gov.au/information-access/foi/{year}/",
    "data_dir": "data",
    "output_dir": "docs",
    "download_dir": "downloads",
    "template_dir": "templates",
    "USE_OCR_FOR_PDFS": False,
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
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "Create a concise, single-paragraph summary in markdown format of the following FOI request summary:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'per_file': (
                "Considering this document as part of an FOI request, summarize the document and its relevance to the FOI request in markdown format. "
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
            ),
        },
        'left_leaning': {
            'overall': (
                "As a politically left-leaning analyst, summarize the following FOI documents. Focus on issues related to social justice, environmental impact, wealth distribution, corporate influence, and civil liberties. Highlight how government actions or policies revealed in these documents align with or deviate from progressive values.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "From a left-leaning perspective, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'per_file': (
                "From a left-leaning perspective, summarize this specific document within the context of the FOI request. Emphasize its implications for social equity, environmental concerns, or democratic accountability. "
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
            ),
        },
        'right_leaning': {
            'overall': (
                "As a politically right-leaning analyst, summarize the following FOI documents. Focus on issues related to economic efficiency, individual liberty, national security, fiscal responsibility, and limited government. Highlight how government actions or policies revealed in these documents align with or deviate from conservative principles.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "From a right-leaning perspective, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'per_file': (
                "From a right-leaning perspective, summarize this specific document within the context of the FOI request. Emphasize its implications for market freedom, government overreach, or national interest. "
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
            ),
        },
        'government_skeptic': {
            'overall': (
                "As a government skeptic, summarize the following FOI documents. Assume a critical stance, scrutinizing government claims, highlighting potential inefficiencies, overreach, or lack of transparency. Focus on findings that suggest waste, power abuse, or questionable decision-making.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "From a government skeptic's viewpoint, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'per_file': (
                "From a government skeptic's viewpoint, summarize this specific document within the context of the FOI request. Look for evidence of bureaucracy, lack of accountability, or any hidden agendas. "
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
            ),
        },
        'government_apologist': {
            'overall': (
                "As a government apologist, summarize the following FOI documents. Assume a supportive stance, emphasizing effective governance, necessary regulations, and positive outcomes. Frame any controversies as challenges effectively managed or essential actions for public good. Highlight the government's efforts to serve the public.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "From a government apologist's viewpoint, provide a concise, single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'per_file': (
                "From a government apologist's viewpoint, summarize this specific document within the context of the FOI request. Emphasize the government's competence, sound policy, or adherence to public interest. "
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
            ),
        },
        'highly_critical': {
            'overall': (
                "Adopt a highly critical stance to summarize the following FOI documents. Ruthlessly analyze every detail for signs of failure, corruption, incompetence, or malice. Highlight every negative implication and present the most damning possible interpretation of the government's actions or inactions.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "With a highly critical view, provide a concise single-paragraph summary in markdown format of the following FOI request overview:\n\n"
                "Summary:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'per_file': (
                "Critically summarize this specific document within the FOI request context. Point out every flaw, missed opportunity, or potential harm. Frame the content in the most negative light possible, questioning motives and outcomes. "
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
            ),
        },
        'objectivist': {
            'overall': (
                "As an Objectivist inspired by Ayn Rand, summarize the following FOI documents. Focus on the content first, and secondarily issues around: primacy of individual rights, rational self-interest, the virtue of productive achievement, and the dangers of collectivism and government overreach. Highlight how the content aligns with or violates the principles of reason, individual liberty, and laissez-faire capitalism. Critique any evidence of forced altruism, bureaucratic interference, or suppression of personal initiative.\n\n"
                "Documents:\n\n{text}\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
            ),
            'short_index': (
                "From an Objectivist perspective, provide a concise, single-paragraph summary in markdown format of the following FOI request overview. Focus on the content of the FOI request particularly.\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "Summary:\n\n{text}\n\n"
            ),
            'per_file': (
                "From an Objectivist perspective, summarize this specific document within the context of the FOI request. Secondarily, analyze how the document reflects or contradicts the values of reason, individualism, and free enterprise. Note any evidence of bureaucratic obstacles, forced altruism, or suppression of productive achievement.\n\n"
                "Provide only the markdown formatted summary text. Do not include any conversational filler or preamble.\n"
                "To aid you, the overview of the FOI request is: [REQUEST OVERVIEW START] {overall_short_summary}\n [REQUEST OVERVIEW END] \n\n"
                "--- MAIN DOCUMENT TEXT START ---\n\n{text}\n\n"
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
        'objectivist': {
            'overall': None,
            'short_index': None,
            'per_file': None,
        },
    },
    'FORCE_SUMMARY_REGENERATION': False,
}
