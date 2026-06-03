import time
from pathlib import Path
import requests

BASE = 'http://127.0.0.1:5000'
image_path = Path('/home/ubuntu/Raqim/ocr_test_upload.png')

with image_path.open('rb') as f:
    upload_response = requests.post(f'{BASE}/upload', files={'file': (image_path.name, f, 'image/png')}, timeout=30)
print('upload_status', upload_response.status_code, upload_response.text)
upload_response.raise_for_status()

for attempt in range(30):
    status_response = requests.get(f'{BASE}/processing_status', timeout=10)
    print('processing_status', attempt + 1, status_response.status_code, status_response.text)
    if status_response.ok and status_response.json().get('status') == 'done':
        break
    time.sleep(1)
else:
    raise RuntimeError('OCR processing did not finish')

review_response = requests.get(f'{BASE}/review', timeout=10)
print('review_status', review_response.status_code)
review_response.raise_for_status()
review_data = review_response.json()
filename = review_data['original_file']
first_word = review_data['pages'][0]['text'][0]
print('first_word_before', first_word)

corrected = 'RAQIM_FIXED'
save_payload = {
    'filename': filename,
    'original_word': first_word.get('original_word') or first_word.get('word'),
    'corrected_word': corrected,
    'page_number': 1,
    'word_index': first_word.get('index', 0),
}
save_response = requests.post(f'{BASE}/save_correction', json=save_payload, timeout=10)
print('save_status', save_response.status_code, save_response.text)
save_response.raise_for_status()

submit_payload = {
    'filename': filename,
    'corrections': [
        {
            'page_number': 1,
            'text': [
                {
                    'index': first_word.get('index', 0),
                    'word': first_word.get('original_word') or first_word.get('word'),
                    'corrected_word': corrected,
                }
            ],
        }
    ],
}
submit_response = requests.post(f'{BASE}/submit_corrections', json=submit_payload, timeout=10)
print('submit_status', submit_response.status_code, submit_response.text)
submit_response.raise_for_status()

download_response = requests.get(f'{BASE}/download_corrected', timeout=10)
print('download_status', download_response.status_code)
download_response.raise_for_status()
text = download_response.text
out_path = Path('/home/ubuntu/Raqim/manual_corrected_download_test.txt')
out_path.write_text(text, encoding='utf-8')
print('download_text', text)
if corrected not in text:
    raise AssertionError('Corrected word was not found in downloaded file')
print('PASS manual correction reflected in downloaded file:', out_path)
