from gradio_client import Client

client = Client('oddadmix/Arabic-OCR-Models-Demos')
print(client.view_api())
