# load.py

import os
import time
import random
import json
import subprocess
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm

# bulk API를 활용해 ai 관련한 논문들을 찾아오는 함수
def get_ai_papers(script_path="script_ai_paper.sh", key_env="S2_API_KEY"):
    if not os.getenv(key_env):
        raise RuntimeError(f"Missing {key_env} (set it in .env or shell).")
    if not Path(script_path).exists():
        raise FileNotFoundError(script_path)
    subprocess.run(["bash", script_path], check=True)


# reference 논문과 그 정보를 추출하는 함수
GRAPH_FIELDS = "contexts,intents,isInfluential,citedPaper.paperId"
BATCH_FIELDS = "paperId,title,year,url,abstract,venue,referenceCount,citationCount,fieldsOfStudy,s2FieldsOfStudy"
COLS = [
    "ref_paper_id","seed_paper_id","title","year","url","abstract","publication",
    "referenceCount","citationCount","fieldsOfStudy","s2FieldsOfStudy",
    "intents","isInfluential","contexts"
]

MIN_INTERVAL = 1.05  # 429 방지용 최소 간격

def _req(method, url, api_key, params=None, payload=None, retries=6, timeout=30, _state={"last": 0.0}):
    headers = {"x-api-key": api_key}

    for i in range(retries):
        # throttle
        wait = MIN_INTERVAL - (time.time() - _state["last"])
        if wait > 0:
            time.sleep(wait)
        _state["last"] = time.time()

        try:
            r = requests.request(method, url, headers=headers, params=params, json=payload, timeout=timeout)
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                time.sleep(float(ra) if ra else 1.5 * (2 ** i) + random.uniform(0, 0.3))
                continue
            r.raise_for_status()
            return r.json(), None
        except Exception as e:
            body = ""
            try:
                body = (r.text or "").strip()[:300]  # noqa: F821 (r exists if request returned)
            except Exception:
                pass
            err = f"{type(e).__name__}: {e}" + (f" | body: {body}" if body else "")
            if i == retries - 1:
                return None, err
            time.sleep(1.5 * (2 ** i) + random.uniform(0, 0.3))
    return None, "Unknown error"


def _chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _batch_papers(ids, api_key, fields=BATCH_FIELDS, chunk_size=50):
    url = "https://api.semanticscholar.org/graph/v1/paper/batch"
    out, errs = [], []
    for c in _chunks(ids, chunk_size):
        j, err = _req("POST", url, api_key, params={"fields": fields}, payload={"ids": c})
        if j:
            out.extend(j)
        else:
            errs.append(f"batch 실패 (ids {len(c)}개): {err}")
    return out, errs


def extract_references_from_papers_json(
    seeds_json_path="papers.json",
    key_env="S2_API_KEY",
    ref_fetch=100,
    top_k=5,
):
    """
    papers.json(seed 목록) -> 각 seed의 reference 조회 -> batch로 상세 조회 -> top_k 선별 -> DataFrame 반환
    """
    api_key = os.getenv(key_env)
    if not api_key:
        raise RuntimeError(f"Missing {key_env} (set it in .env or shell).")

    res = json.load(open(seeds_json_path, encoding="utf-8"))
    seed_ids = [p.get("paperId") for p in (res.get("data") or []) if p.get("paperId")]

    rows, errors = [], []

    for seed_id in tqdm(seed_ids, desc="Fetching references"):
        refs, err = _req(
            "GET",
            f"https://api.semanticscholar.org/graph/v1/paper/{seed_id}/references",
            api_key,
            params={"fields": GRAPH_FIELDS, "limit": ref_fetch})
        if not refs:
            errors.append(f"[references 실패] seed={seed_id} :: {err}")
            continue

        seen, edges = set(), []
        for e in refs.get("data") or []:
            pid = (e.get("citedPaper") or {}).get("paperId")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            edges.append({
                "pid": pid,
                "intents": e.get("intents", []),
                "inf": e.get("isInfluential", False),
                "contexts": e.get("contexts", []),
            })

        details, batch_errs = _batch_papers([e["pid"] for e in edges], api_key)
        errors += [f"[batch 경고] seed={seed_id} :: {be}" for be in batch_errs]

        meta = {d["paperId"]: d for d in details if d and d.get("paperId")}

        # score & pick top-k: influential 우선, 그 다음 citationCount desc
        for e in edges:
            e["cit"] = (meta.get(e["pid"], {}) or {}).get("citationCount") or 0
        top_edges = sorted(edges, key=lambda x: (x["inf"], x["cit"]), reverse=True)[:top_k]

        for e in top_edges:
            d = meta.get(e["pid"]) or {}
            if not d:
                errors.append(f"[상세 누락] seed={seed_id} ref={e['pid']} :: batch 결과에 없음")

            rows.append({
                "seed_paper_id": seed_id,
                "ref_paper_id": e["pid"],
                "title": d.get("title"),
                "year": d.get("year"),
                "url": d.get("url"),
                "abstract": d.get("abstract"),
                "publication": d.get("venue"),
                "referenceCount": d.get("referenceCount"),
                "citationCount": d.get("citationCount"),
                "fieldsOfStudy": d.get("fieldsOfStudy"),
                "s2FieldsOfStudy": d.get("s2FieldsOfStudy"),
                "intents": e["intents"],
                "isInfluential": e["inf"],
                "contexts": e["contexts"],
            })

    return pd.DataFrame(rows, columns=COLS), errors