import os

def load_env_var_from_dotenv(var_name, dotenv_path='.env'):
    """Load a variable from .env file if not present in os.environ."""
    if var_name in os.environ:
        return os.environ[var_name]
    try:
        with open(dotenv_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    if k.strip() == var_name:
                        os.environ[var_name] = v.strip()
                        return v.strip()
    except FileNotFoundError:
        pass
    return None
