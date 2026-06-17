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


def test_html_table_columns_keep_ltr_physical_order():
    html = (
        "<table><tr>"
        "<td>يسار</td><td>وسط</td><td>يمين</td>"
        "</tr></table>"
    )
    cells = ocr_model._parse_html_table_cells(html)
    by_text = {cell["text"]: cell["col"] for cell in cells}
    assert by_text["يسار"] == 0
    assert by_text["وسط"] == 1
    assert by_text["يمين"] == 2


def test_html_table_colspan_ltr_anchor():
    html = (
        "<table><tr>"
        '<td colspan="2">مدموج</td><td>منفرد</td>'
        "</tr></table>"
    )
    cells = ocr_model._parse_html_table_cells(html)
    merged = next(cell for cell in cells if cell["text"] == "مدموج")
    single = next(cell for cell in cells if cell["text"] == "منفرد")
    assert merged["col"] == 0
    assert single["col"] == 2
    assert merged["colspan"] == 2


def test_table_cells_to_words_places_left_column_on_left():
    cells = [
        {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "يسار"},
        {"row": 0, "col": 2, "rowspan": 1, "colspan": 1, "text": "يمين"},
    ]
    words = ocr_model._table_cells_to_words(cells, table_id=1, width=1000, height=1400)
    left = next(w for w in words if w["word"] == "يسار")
    right = next(w for w in words if w["word"] == "يمين")
    assert left["bounding_box"]["x"] < right["bounding_box"]["x"]
