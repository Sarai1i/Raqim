import json
from pathlib import Path
path = Path('/tmp/models.json')
if not path.exists():
    print('models_file_missing')
    raise SystemExit(0)
data = json.loads(path.read_text(encoding='utf-8'))
for model in data.get('data', []):
    text = ' '.join(str(model.get(k, '')) for k in ['id', 'display_name', 'description', 'owned_by']).lower()
    if any(term in text for term in ['allam', 'alam', 'ibm', 'watson']):
        print(f"{model.get('id')}\t{model.get('display_name', '')}")
