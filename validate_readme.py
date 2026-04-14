from huggingface_hub.utils import validate_yaml
from pathlib import Path

# Use absolute path for README
content = Path(r'd:\Meta Hackathon\invoice-env\README.md').read_text(encoding='utf-8')
try:
    validate_yaml(content, 'README.md')
    print("Valid")
except Exception as e:
    print(e)
