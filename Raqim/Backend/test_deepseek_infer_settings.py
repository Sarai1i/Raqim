from PIL import Image

import ocr_model


def test_crop_mode_normalizes_unsupported_base_size():
    ocr_model.DEEPSEEK_OCR_BASE_SIZE = 1280
    ocr_model.DEEPSEEK_OCR_IMAGE_SIZE = 768
    ocr_model.DEEPSEEK_OCR_CROP_MODE = True

    settings = ocr_model._resolve_deepseek_infer_settings(Image.new("RGB", (2480, 3508)))

    assert settings["base_size"] == 1024
    assert settings["image_size"] == 768
    assert settings["crop_mode"] is True


def test_format_deepseek_error_param_img():
    message = ocr_model._format_deepseek_error(
        RuntimeError("cannot access local variable 'param_img' where it is not associated with a value")
    )
    assert "param_img" in message
    assert "DeepSeek-OCR-2" in message


def test_html_table_columns_flip_to_rtl():
    html = (
        "<table><tr>"
        "<td>يسار</td><td>وسط</td><td>يمين</td>"
        "</tr></table>"
    )
    cells = ocr_model._parse_html_table_cells(html)
    by_text = {cell["text"]: cell["col"] for cell in cells}
    assert by_text["يمين"] == 0
    assert by_text["وسط"] == 1
    assert by_text["يسار"] == 2


def test_html_table_colspan_rtl_anchor():
    html = (
        "<table><tr>"
        '<td colspan="2">مدموج</td><td>منفرد</td>'
        "</tr></table>"
    )
    cells = ocr_model._parse_html_table_cells(html)
    merged = next(cell for cell in cells if cell["text"] == "مدموج")
    single = next(cell for cell in cells if cell["text"] == "منفرد")
    assert single["col"] == 0
    assert merged["col"] == 1
    assert merged["colspan"] == 2
