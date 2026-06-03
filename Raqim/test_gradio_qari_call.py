from gradio_client import Client, handle_file

client = Client('oddadmix/Arabic-OCR-Models-Demos')
for endpoint in ['/perform_ocr', '/perform_ocr_1']:
    for model in ['Qari OCR 0.2.2.1', 'KATIB OCR 0.8B 0.1']:
        print('CALL', endpoint, model)
        try:
            result = client.predict(handle_file('qari_arabic_sample.png'), model, api_name=endpoint)
            print('OK', repr(result[:300] if isinstance(result, str) else result))
        except Exception as exc:
            print('ERR', type(exc).__name__, exc)
