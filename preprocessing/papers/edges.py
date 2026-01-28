# edges.py

import json
import pandas as pd
from tqdm import tqdm

from generate import build_chat_prompt, extract_json, generate_batch
from prompts import EDGE_ABOUT_PROMPT, EDGE_IN_PROMPT, EDGE_REF_BY_PROMPT


## proposed_concepts(ABOUT): 논문이 새로 제안/도입/정의/모델링한 핵심 개념들
## prerequisite_concepts (IN): 이해를 위해 미리 알아야 하는 개념들

## (paperId, concept) 엣지 DF 만들어야 함
## edges_about 칼럼: paperId, title, abstract, concept (kc_proposed)
## edges_in 칼럼: paperId, title, abstract, concept (kc_prerequisite)


# 엣지 df 생성
def make_edges_from_nodes(nodes_df_wiki: pd.DataFrame):
    """
    nodes_df_wiki: kc_to_nodes_df 결과에 alias/wiki_map까지 붙은 DF
    required cols: paperId, name, edge_type, paper_title, abstract
    """
    base = nodes_df_wiki.copy()
    base["paperId"] = base["paperId"].astype(str)
    base["concept"] = base["name"].astype(str).str.strip()
    base["title"] = base["paper_title"].fillna("").astype(str)
    base["abstract"] = base["abstract"].fillna("").astype(str)
    base = base[base["concept"] != ""]

    cols = ["paperId", "title", "abstract", "concept"]

    edges_about = (
        base[base["edge_type"] == "ABOUT"][cols]
        .drop_duplicates(subset=["paperId", "concept"])
        .reset_index(drop=True)
    )
    edges_in = (
        base[base["edge_type"] == "IN"][cols]
        .drop_duplicates(subset=["paperId", "concept"])
        .reset_index(drop=True)
    )

    return edges_about, edges_in


# edge에 reason과 strength를 생성하는 함수
def add_edge_reason_strength(edge_df: pd.DataFrame, prompt_template: str) -> pd.DataFrame:
    df = edge_df.copy()

    key_df = df[["paperId", "concept"]].dropna().drop_duplicates().astype(str)
    key_pairs = list(key_df.itertuples(index=False, name=None))

    paper_ctx = (
        df[["paperId", "title", "abstract"]]
        .drop_duplicates(subset=["paperId"])
        .set_index("paperId")[["title", "abstract"]]
        .to_dict(orient="index")
    )

    chat_inputs = []
    for paperId, concept in tqdm(key_pairs, desc="edge: build prompts"):
        ctx = paper_ctx.get(paperId, {"title": "", "abstract": ""})
        system_msg = (
            prompt_template
            .replace("{PAPER_TITLE}", str(ctx.get("title", "")))
            .replace("{PAPER_ABSTRACT}", str(ctx.get("abstract", "")))
            .replace("{CONCEPT}", str(concept))
        )
        chat_inputs.append(build_chat_prompt(system_msg, "Return raw JSON only."))

    generations = generate_batch(chat_inputs)

    score_map = {}
    for (paperId, concept), gen in tqdm(
        list(zip(key_pairs, generations)),
        total=len(key_pairs),
        desc="edge: parse outputs",
    ):
        raw = gen.outputs[0].text.strip()
        parsed = extract_json(raw)

        strength = pd.NA
        reason = pd.NA
        ok = False

        if isinstance(parsed, dict):
            ok = ("strength" in parsed) or ("reason" in parsed)

            s = parsed.get("strength")
            r = parsed.get("reason")

            if isinstance(s, (int, float)):
                strength = float(max(0.0, min(1.0, s)))
            if isinstance(r, str) and r.strip():
                reason = r.strip()

        score_map[(str(paperId), str(concept))] = (strength, reason, raw, ok)

    def _get(row, idx):
        key = (str(row["paperId"]), str(row["concept"]))
        return score_map.get(key, (pd.NA, pd.NA, "", False))[idx]

    df["strength"] = df.apply(lambda r: _get(r, 0), axis=1)
    df["reason"]   = df.apply(lambda r: _get(r, 1), axis=1)
    df["edge_raw"] = df.apply(lambda r: _get(r, 2), axis=1)
    df["edge_ok"]  = df.apply(lambda r: _get(r, 3), axis=1)
    return df


def build_scored_edges(nodes_df_wiki: pd.DataFrame) -> pd.DataFrame:
    """
    nodes_df_wiki -> (ABOUT, IN) edges -> LLM score -> concat
    output cols: paperId, concept, edge_type, strength, reason, edge_raw, edge_ok
    """
    edges_about, edges_in = make_edges_from_nodes(nodes_df_wiki)

    edges_about_scored = add_edge_reason_strength(edges_about, EDGE_ABOUT_PROMPT)
    edges_about_scored["edge_type"] = "ABOUT"

    edges_in_scored = add_edge_reason_strength(edges_in, EDGE_IN_PROMPT)
    edges_in_scored["edge_type"] = "IN"

    edges_all = pd.concat([edges_about_scored, edges_in_scored], ignore_index=True)
    return edges_all


# paper-paper 엣지 만드는 함수
def add_ref_by_strength(ref_df: pd.DataFrame, seeds_json_path: str = "papers.json") -> pd.DataFrame:
    """
    (seed_paper_id -> ref_paper_id) 엣지에 대해 LLM으로 strength 생성.
    - target(=seed)는 papers.json에서 title/abstract 가져옴
    - ref paper는 ref_df의 title/abstract 사용
    """
    df = ref_df.copy()

    # 1) seed 컨텍스트 (papers.json)
    with open(seeds_json_path, "r", encoding="utf-8") as f:
        seeds = json.load(f).get("data", [])

    seed_ctx = {
        str(s["paperId"]): {"title": (s.get("title") or ""), "abstract": (s.get("abstract") or "")}
        for s in seeds if s.get("paperId")
    }

    # 2) ref 컨텍스트 (ref_df 내부)
    df["seed_paper_id"] = df["seed_paper_id"].astype(str)
    df["ref_paper_id"] = df["ref_paper_id"].astype(str)

    ref_ctx = (
        df[["ref_paper_id", "title", "abstract"]]
        .drop_duplicates(subset=["ref_paper_id"])
        .set_index("ref_paper_id")[["title", "abstract"]]
        .to_dict(orient="index")
    )

    # 3) unique (seed, ref)
    key_df = df[["seed_paper_id", "ref_paper_id"]].dropna().drop_duplicates()
    key_pairs = list(key_df.itertuples(index=False, name=None))

    # 4) 프롬프트 생성
    chat_inputs = []
    meta_rows = []
    for seed_id, ref_id in tqdm(key_pairs, desc="ref_by: build prompts"):
        t = seed_ctx.get(seed_id, {"title": "", "abstract": ""})
        r = ref_ctx.get(ref_id, {"title": "", "abstract": ""})

        row0 = df[(df["seed_paper_id"] == seed_id) & (df["ref_paper_id"] == ref_id)].iloc[0]

        system_msg = (
            EDGE_REF_BY_PROMPT
            .replace("{TARGET_TITLE}", str(t.get("title", "")))
            .replace("{TARGET_ABSTRACT}", str(t.get("abstract", "")))
            .replace("{REF_TITLE}", str(r.get("title", "")))
            .replace("{REF_ABSTRACT}", str(r.get("abstract", "")))
            .replace("{INTENTS}", str(row0.get("intents", [])))
            .replace("{IS_INF}", str(bool(row0.get("isInfluential", False))))
            .replace("{CONTEXTS}", str((row0.get("contexts", []) or [])[:3]))
        )
        chat_inputs.append(build_chat_prompt(system_msg, "Return raw JSON only."))
        meta_rows.append((seed_id, ref_id))

    generations = generate_batch(chat_inputs)

    # 5) 파싱
    score_map = {}
    raw_map = {}
    ok_map = {}

    for (seed_id, ref_id), gen in tqdm(
        list(zip(meta_rows, generations)),
        total=len(meta_rows),
        desc="ref_by: parse",
    ):
        raw = gen.outputs[0].text.strip()
        raw_map[(seed_id, ref_id)] = raw

        parsed = extract_json(raw)
        ok = isinstance(parsed, dict) and isinstance(parsed.get("strength"), (int, float))
        ok_map[(seed_id, ref_id)] = ok

        strength = pd.NA
        if ok:
            strength = float(max(0.0, min(1.0, float(parsed["strength"]))))

        score_map[(seed_id, ref_id)] = strength

    df["strength"] = df.apply(
        lambda r: score_map.get((str(r["seed_paper_id"]), str(r["ref_paper_id"])), pd.NA),
        axis=1
    )
    df["edge_raw"] = df.apply(
        lambda r: raw_map.get((str(r["seed_paper_id"]), str(r["ref_paper_id"])), ""),
        axis=1
    )
    df["edge_ok"] = df.apply(
        lambda r: ok_map.get((str(r["seed_paper_id"]), str(r["ref_paper_id"])), False),
        axis=1
    )

    return df


def finalize_ref_by_edges(scored_ref_df: pd.DataFrame) -> pd.DataFrame:
    """
    저장 포맷으로 정리
    cols: name, ref_paper_id, seed_paper_id, intents, isInfluential, contexts, strength, edge_raw, edge_ok
    """
    out = scored_ref_df.copy()
    out["name"] = "REF_BY"
    cols = ["name","ref_paper_id","seed_paper_id","intents","isInfluential","contexts","strength","edge_raw","edge_ok"]
    return out[cols].drop_duplicates(subset=["seed_paper_id","ref_paper_id"]).reset_index(drop=True)