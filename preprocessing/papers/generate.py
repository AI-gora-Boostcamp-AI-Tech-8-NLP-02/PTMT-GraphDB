# generate.py

import json
import re
from functools import lru_cache

from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

MODEL = "JunHowie/Qwen3-30B-A3B-Instruct-2507-GPTQ-Int4"

@lru_cache(maxsize=1)
def get_tokenizer():
    return AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)

@lru_cache(maxsize=1)
def get_llm():
    return LLM(
        model=MODEL,
        trust_remote_code=True,
        max_model_len=3200,
        gpu_memory_utilization=0.9,
        tensor_parallel_size=1,
        enable_prefix_caching=True,
        enforce_eager=True,
    )

@lru_cache(maxsize=1)
def get_sampling():
    return SamplingParams(temperature=0.2, top_p=0.9, max_tokens=512)

def build_chat_prompt(system: str, user: str) -> str:
    tok = get_tokenizer()
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

def extract_json(text: str):
    if not text:
        return None
    t = re.sub(r"<think>[\s\S]*?</think>", "", text.strip()).strip()
    if not t:
        return None

    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, flags=re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        for trial in (cand, cand + "}" if cand.startswith("{") and not cand.endswith("}") else None):
            if not trial: 
                continue
            try:
                return json.loads(trial)
            except Exception:
                pass

    s = t.find("{")
    if s == -1:
        return None
    e = t.rfind("}")
    cand = t[s:e+1].strip() if e != -1 and e > s else t[s:].strip()

    for trial in (
        cand,
        cand + "}" if cand.startswith("{") and not cand.endswith("}") else None,
        cand.rstrip() + "}" if cand.startswith("{") and cand.rstrip().endswith("]") and not cand.endswith("}") else None,
    ):
        if not trial:
            continue
        try:
            return json.loads(trial)
        except Exception:
            pass
    return None

def generate_batch(prompts: list[str]):
    llm = get_llm()
    return llm.generate(prompts, get_sampling())
