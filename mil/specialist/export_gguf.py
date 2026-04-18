"""
export_gguf.py — Export qwen3-mil-v1 LoRA adapter to GGUF for Ollama inference testing.

Merges LoRA weights with base model, saves GGUF quantised at q4_k_m.
Output: mil/specialist/qwen3-mil-v1-gguf/

Usage:
  py mil/specialist/export_gguf.py

Then load into Ollama:
  ollama create qwen3-mil-ft -f mil/specialist/qwen3-mil-v1-gguf/Modelfile

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["XFORMERS_DISABLED"] = "1"
os.environ["XFORMERS_MORE_DETAILS"] = "0"

SPECIALIST = Path(__file__).parent
ADAPTER_DIR = SPECIALIST / "qwen3-mil-v1"
OUTPUT_DIR  = SPECIALIST / "qwen3-mil-v1-gguf"

MODEL_ID = "unsloth/Qwen3-8B-unsloth-bnb-4bit"

# Local cache populated by:
#   py -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-8B', local_dir='C:/Users/hussa/.cache/hf-qwen3-8b', resume_download=True)"
LOCAL_BASE = Path("C:/Users/hussa/.cache/hf-qwen3-8b")


def main():
    print(f"\n[export_gguf] Loading fine-tuned adapter from: {ADAPTER_DIR}")

    try:
        from unsloth import FastLanguageModel
    except ImportError:
        print("ERROR: unsloth not installed — run: pip install unsloth")
        sys.exit(1)

    # Use local cache if available, fall back to HuggingFace hub
    base = str(LOCAL_BASE) if LOCAL_BASE.exists() else MODEL_ID
    print(f"[export_gguf] Base model: {base}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(ADAPTER_DIR),
        max_seq_length=1024,
        load_in_4bit=True,
        dtype=None,
    )

    print(f"\n[export_gguf] Exporting GGUF (q4_k_m) to: {OUTPUT_DIR}")
    model.save_pretrained_gguf(
        str(OUTPUT_DIR),
        tokenizer,
        quantization_method="q4_k_m",
    )

    # Write Ollama Modelfile
    modelfile = OUTPUT_DIR / "Modelfile"
    gguf_files = list(OUTPUT_DIR.glob("*.gguf"))
    if gguf_files:
        gguf_name = gguf_files[0].name
        modelfile.write_text(
            f'FROM ./{gguf_name}\n'
            f'PARAMETER temperature 0.1\n'
            f'PARAMETER top_p 0.9\n',
            encoding="utf-8",
        )
        print(f"[export_gguf] Modelfile written: {modelfile}")
        print(f"\n[export_gguf] Done. Load into Ollama:")
        print(f'  ollama create qwen3-mil-ft -f "{OUTPUT_DIR / "Modelfile"}"')
        print(f"\n[export_gguf] Then evaluate:")
        print(f'  py mil/tests/evaluate_enrichment.py --file mil/tests/spot_check_2026-04-18.json --model qwen3-mil-ft --label fine_tuned_v1')
    else:
        print("[export_gguf] WARNING: No .gguf file found in output dir — check export.")


if __name__ == "__main__":
    main()
