#!/usr/bin/env python3
"""Standalone proof-of-concept for dots.mocr OCR.

This script is intentionally *self-contained* and independent from Raqim's
production OCR pipeline:

  * It does NOT import or touch ``ocr_model.py`` / ``app.py``.
  * It does NOT replace or interact with the DeepSeek-OCR-2 engine.
  * It only demonstrates running rednote-hilab's ``dots.mocr`` model on a single
    image and emitting Markdown.

Usage
-----
    python test_dots_ocr.py path/to/image.png
    python test_dots_ocr.py page.jpg --prompt-mode ocr
    python test_dots_ocr.py page.jpg --output-dir dots_outputs --max-new-tokens 16000

What it does
------------
1. Accepts an image path on the command line.
2. Runs the ``dots.mocr`` vision-language model (via Hugging Face Transformers
   + ``trust_remote_code``).
3. Prints the extracted Markdown to stdout.
4. Saves the Markdown (and the raw model output / parsed JSON when available)
   into ``dots_outputs/``.

Notes
-----
* A CUDA GPU is strongly recommended. CPU inference works but is extremely slow
  and downloads several GB of weights on first run.
* See ``requirements-dots.txt`` for the (branch-scoped) dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Default Hugging Face model id. Override with --model or the
# DOTS_MOCR_MODEL_NAME environment variable / --model flag.
DEFAULT_MODEL_NAME = "rednote-hilab/dots.mocr"

# The full layout-parsing prompt recommended by the dots.mocr model card. It
# asks the model to return a single JSON object describing every layout element
# (bbox + category + text), which we then flatten into Markdown.
PROMPT_LAYOUT_ALL = """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
"""

# A lighter prompt that asks only for the page text (no layout JSON), excluding
# page headers/footers. Useful when you just want raw Markdown text.
PROMPT_OCR_ONLY = (
    "Extract the text content from this image, preserving the original reading "
    "order, and format the result as Markdown. Do not translate. Exclude page "
    "headers and page footers."
)

PROMPT_MODES = {
    "layout": PROMPT_LAYOUT_ALL,
    "ocr": PROMPT_OCR_ONLY,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run dots.mocr OCR on a single image (proof-of-concept).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("image_path", help="Path to the input image (png/jpg/...).")
    parser.add_argument(
        "--model",
        default=None,
        help="Hugging Face model id or local path (defaults to "
        f"DOTS_MOCR_MODEL_NAME env var or '{DEFAULT_MODEL_NAME}').",
    )
    parser.add_argument(
        "--output-dir",
        default="dots_outputs",
        help="Directory to save the extracted output.",
    )
    parser.add_argument(
        "--prompt-mode",
        choices=sorted(PROMPT_MODES),
        default="layout",
        help="'layout' returns structured JSON (flattened to Markdown); "
        "'ocr' asks directly for Markdown text.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=24000,
        help="Maximum number of tokens to generate.",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Force a device, e.g. 'cuda', 'cpu'. Auto-detected when omitted.",
    )
    return parser.parse_args(argv)


def _select_dtype_and_device(requested_device: str | None):
    """Pick a sensible (device, dtype) pair based on hardware availability."""
    import torch

    if requested_device:
        device = requested_device
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # dots.mocr's vision tower hardcodes a ``hidden_states.bfloat16()`` cast, so
    # the weights must also be bfloat16 to avoid dtype mismatches. Modern CPUs
    # support bf16 (it is slow, but correct), so we use it on every device.
    dtype = torch.bfloat16
    return device, dtype


def _flash_attn_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("flash_attn") is not None


def _install_flash_attn_stub() -> None:
    """Register a pure-torch ``flash_attn`` stub so dots.mocr imports on CPU.

    The upstream dots.mocr vision code does an unconditional
    ``from flash_attn import flash_attn_varlen_func`` at import time, even though
    it also ships ``sdpa``/``eager`` attention classes. On machines without the
    (CUDA-only) ``flash-attn`` package, that import aborts model loading. We
    insert a lightweight stand-in module that satisfies the import (and, if ever
    called, falls back to standard scaled-dot-product attention). The real
    attention path is forced to ``sdpa`` separately, so this stub is normally
    only needed to make the import succeed.
    """
    import sys
    import types

    if "flash_attn" in sys.modules or _flash_attn_available():
        return

    import torch
    import torch.nn.functional as F

    def flash_attn_varlen_func(
        q, k, v, cu_seqlens_q, cu_seqlens_k, max_seqlen_q=None, max_seqlen_k=None,
        dropout_p=0.0, softmax_scale=None, causal=False, **kwargs,
    ):
        # q/k/v: (total_tokens, num_heads, head_dim). Run attention per sequence
        # segment delimited by the cumulative sequence lengths.
        outputs = []
        cu = cu_seqlens_q.tolist()
        for start, end in zip(cu[:-1], cu[1:]):
            qs = q[start:end].transpose(0, 1)  # (heads, seq, dim)
            ks = k[start:end].transpose(0, 1)
            vs = v[start:end].transpose(0, 1)
            out = F.scaled_dot_product_attention(
                qs, ks, vs, dropout_p=dropout_p, is_causal=causal, scale=softmax_scale
            )
            outputs.append(out.transpose(0, 1))  # back to (seq, heads, dim)
        return torch.cat(outputs, dim=0)

    stub = types.ModuleType("flash_attn")
    stub.flash_attn_varlen_func = flash_attn_varlen_func
    stub.__version__ = "0.0.0-cpu-stub"
    sys.modules["flash_attn"] = stub
    print(
        "flash-attn not installed; registered a pure-torch CPU stub so dots.mocr "
        "can load (attention forced to 'sdpa').",
        flush=True,
    )


def load_model_and_processor(model_name: str, device: str | None):
    """Load dots.mocr, transparently supporting CPU (no flash-attn) setups."""
    import torch  # noqa: F401  (imported for availability check)
    from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor

    device, dtype = _select_dtype_and_device(device)

    use_flash = device.startswith("cuda") and _flash_attn_available()
    if use_flash:
        attn_impl = "flash_attention_2"
    else:
        attn_impl = "sdpa"
        _install_flash_attn_stub()

    print(
        f"Loading dots.mocr model '{model_name}' on {device} ({dtype}) "
        f"with attn_implementation='{attn_impl}'...",
        flush=True,
    )

    # Force the attention implementation on BOTH the language and vision configs;
    # the vision tower defaults to flash_attention_2 in the checkpoint config.
    config = AutoConfig.from_pretrained(model_name, trust_remote_code=True)
    config.attn_implementation = attn_impl
    if hasattr(config, "vision_config") and config.vision_config is not None:
        try:
            config.vision_config.attn_implementation = attn_impl
        except AttributeError:
            pass

    common_kwargs: dict[str, Any] = {
        "config": config,
        "dtype": dtype,
        "trust_remote_code": True,
        "attn_implementation": attn_impl,
    }
    if device.startswith("cuda"):
        common_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(model_name, **common_kwargs)

    if not device.startswith("cuda"):
        model = model.to(device)
    model = model.eval()

    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    return model, processor, device


def run_inference(model, processor, device: str, image_path: str, prompt: str, max_new_tokens: int) -> str:
    """Run a single forward pass and return the raw decoded model output."""
    from qwen_vl_utils import process_vision_info

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image_path},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(device)

    print("Running inference (this can take a while on CPU)...", flush=True)
    generated_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    return output_text[0] if output_text else ""


def _cell_to_markdown(cell: dict) -> str:
    """Convert a single dots.mocr layout cell into a Markdown fragment."""
    category = (cell.get("category") or "").strip()
    text = cell.get("text")

    if category == "Picture" or text is None:
        return ""

    text = str(text).strip()
    if not text:
        return ""

    if category in {"Title"}:
        return f"# {text}"
    if category in {"Section-header"}:
        return f"## {text}"
    if category in {"Page-header", "Page-footer", "Footnote", "Caption"}:
        # Keep them but de-emphasize; they are still part of the page content.
        return text
    # Text, List-item, Formula, Table, etc. are already Markdown/HTML/LaTeX.
    return text


def layout_json_to_markdown(parsed: Any) -> str:
    """Flatten a dots.mocr layout JSON payload into Markdown.

    The model returns a JSON array (or an object containing one) of layout
    cells already sorted in reading order. We concatenate each cell's text.
    """
    cells: list[dict] = []
    if isinstance(parsed, list):
        cells = [c for c in parsed if isinstance(c, dict)]
    elif isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                cells = [c for c in value if isinstance(c, dict)]
                break

    fragments = [frag for cell in cells if (frag := _cell_to_markdown(cell))]
    return "\n\n".join(fragments).strip()


def extract_markdown(raw_output: str, prompt_mode: str) -> tuple[str, Any | None]:
    """Return (markdown, parsed_json_or_None) from the raw model output."""
    if prompt_mode == "ocr":
        return raw_output.strip(), None

    # layout mode: try to parse JSON, then flatten to Markdown.
    candidate = raw_output.strip()
    # Strip a ```json ... ``` fence if the model wrapped its answer.
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # Not valid JSON; treat the raw output as Markdown directly.
        return raw_output.strip(), None

    markdown = layout_json_to_markdown(parsed)
    if not markdown:
        # JSON parsed but produced no text; fall back to the raw payload.
        markdown = raw_output.strip()
    return markdown, parsed


def save_outputs(output_dir: Path, stem: str, markdown: str, raw_output: str, parsed: Any | None) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{stem}_{timestamp}"

    saved: dict[str, Path] = {}

    md_path = output_dir / f"{base}.md"
    md_path.write_text(markdown, encoding="utf-8")
    saved["markdown"] = md_path

    raw_path = output_dir / f"{base}.raw.txt"
    raw_path.write_text(raw_output, encoding="utf-8")
    saved["raw"] = raw_path

    if parsed is not None:
        json_path = output_dir / f"{base}.json"
        json_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        saved["json"] = json_path

    return saved


def main(argv: list[str] | None = None) -> int:
    import os

    args = parse_args(argv)

    image_path = Path(args.image_path)
    if not image_path.is_file():
        print(f"Error: image not found: {image_path}", file=sys.stderr)
        return 2

    model_name = args.model or os.getenv("DOTS_MOCR_MODEL_NAME", DEFAULT_MODEL_NAME)
    prompt = PROMPT_MODES[args.prompt_mode]

    try:
        model, processor, device = load_model_and_processor(model_name, args.device)
    except ImportError as exc:
        print(
            "Missing dependencies. Install them with:\n"
            "    pip install -r requirements-dots.txt\n"
            f"Underlying import error: {exc}",
            file=sys.stderr,
        )
        return 3

    raw_output = run_inference(
        model,
        processor,
        device,
        str(image_path),
        prompt,
        args.max_new_tokens,
    )

    markdown, parsed = extract_markdown(raw_output, args.prompt_mode)

    print("\n" + "=" * 70)
    print("EXTRACTED MARKDOWN")
    print("=" * 70)
    print(markdown if markdown else "(model returned empty output)")
    print("=" * 70 + "\n")

    saved = save_outputs(
        Path(args.output_dir), image_path.stem, markdown, raw_output, parsed
    )
    print("Saved output files:")
    for kind, path in saved.items():
        print(f"  {kind:>8}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
