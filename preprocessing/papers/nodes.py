# nodes.py

import pandas as pd
import numpy as np
from tqdm import tqdm
import ast
from urllib.parse import quote

from generate import build_chat_prompt, extract_json, generate_batch
from prompts import KC_PROMPT, ALIAS_PROMPT 

# paper node 생성
## papers와 ref_papers를 불러와서 노드로 저장
## 이때 ref_papers의 ref_paper_id 중 papers에 없는 게 있을 수 있기 때문에 확인해서 nodes에 추가

## cols: ['paperId', 'url', 'title', 'venue', 'year', 'referenceCount', 'citationCount', 'openAccessPdf', 'fieldsOfStudy', 's2FieldsOfStudy', 'authors', 'abstract']
## alias, proposed_concepts, prerequisite_concepts -> 추가하는데 pd.NA로

BASE_COLS = [
    "paperId", "url", "title", "publication", "year",
    "referenceCount", "citationCount",
    "openAccessPdf", "fieldsOfStudy", "s2FieldsOfStudy",
    "authors", "abstract",
]
EXTRA_COLS = ["alias", "proposed_concepts", "prerequisite_concepts"]

def build_nodes_paper(papers: pd.DataFrame, ref_papers: pd.DataFrame) -> pd.DataFrame:
    # papers: raw_papers_df (venue -> publication)
    paper_nodes = papers.copy()
    if "venue" in paper_nodes.columns and "publication" not in paper_nodes.columns:
        paper_nodes = paper_nodes.rename(columns={"venue": "publication"})

    # ref_papers: ref_df (ref_paper_id -> paperId, seed_paper_id drop)
    ref_nodes = ref_papers.rename(columns={"ref_paper_id": "paperId"}).copy()
    if "seed_paper_id" in ref_nodes.columns:
        ref_nodes = ref_nodes.drop(columns=["seed_paper_id"])

    # 합치기 (papers에 없는 ref도 포함됨)
    nodes_paper = pd.concat([paper_nodes, ref_nodes], ignore_index=True, sort=False)

    # 필요한 컬럼 없으면 채우기
    for c in BASE_COLS + EXTRA_COLS:
        if c not in nodes_paper.columns:
            nodes_paper[c] = pd.NA

    # categories 만들고 fieldsOfStudy/s2FieldsOfStudy 드롭
    def to_list(x):
        # 1) 이미 list/tuple/ndarray면 그대로(또는 list로)
        if isinstance(x, (list, tuple, np.ndarray)):
            return list(x)

        # 2) 결측(스칼라) 처리
        if x is None:
            return []
        try:
            # pd.NA / np.nan 같은 스칼라 결측만 안전하게 처리
            if pd.isna(x):
                return []
        except Exception:
            pass

        # 3) 문자열로 들어온 list 표현 파싱
        s = str(x).strip()
        if not s:
            return []
        try:
            v = ast.literal_eval(s)
            if isinstance(v, (list, tuple)):
                return list(v)
        except Exception:
            pass

        # 4) 그 외 단일 값이면 1개짜리 리스트로
        return [x]

    nodes_paper["categories"] = nodes_paper.apply(
        lambda r: list(dict.fromkeys(
            [v for v in to_list(r["fieldsOfStudy"]) if isinstance(v, str)] +
            [d.get("category") for d in to_list(r["s2FieldsOfStudy"])
             if isinstance(d, dict) and isinstance(d.get("category"), str)]
        )),
        axis=1
    )

    nodes_paper = nodes_paper.drop(columns=["fieldsOfStudy", "s2FieldsOfStudy"])

    # 컬럼 정렬 + paperId 기준 중복 제거
    final_cols = [
        "paperId", "url", "title", "publication", "year",
        "referenceCount", "citationCount",
        "openAccessPdf", "categories",
        "authors", "abstract",
        *EXTRA_COLS
    ]

    nodes_paper = (
        nodes_paper[final_cols]
        .drop_duplicates(subset=["paperId"], keep="first")
        .reset_index(drop=True)
    )
    return nodes_paper

# paper로부터 KC 생성하는 함수
def add_kc_to_paper_nodes(papers_df: pd.DataFrame) -> pd.DataFrame:
    df = papers_df.copy()
    df["title"] = df["title"].fillna("").astype(str)
    df["abstract"] = df["abstract"].fillna("").astype(str)

    chat_inputs, row_keys = [], []
    for i, row in tqdm(df.iterrows(), total=len(df), desc="kc: build prompts"):
        system_msg = KC_PROMPT.replace("{INPUT_TITLE}", row["title"].strip()).replace("{INPUT_ABSTRACT}", row["abstract"].strip())
        user_msg = 'Return ONLY raw JSON with keys "proposed_concepts" and "prerequisite_concepts".'
        chat_inputs.append(build_chat_prompt(system_msg, user_msg))
        row_keys.append(i)

    generations = generate_batch(chat_inputs)

    def _clean_list(xs):
        out, seen = [], set()
        for item in xs:
            if not isinstance(item, str):
                continue
            s = item.strip()
            if not s or len(s) > 80:
                continue
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    proposed_map, prereq_map, raw_map, ok_map = {}, {}, {}, {}

    for idx, gen in tqdm(list(zip(row_keys, generations)), total=len(row_keys), desc="kc: parse outputs"):
        raw = gen.outputs[0].text.strip()
        parsed = extract_json(raw)

        ok = (
            isinstance(parsed, dict)
            and isinstance(parsed.get("proposed_concepts"), list)
            and isinstance(parsed.get("prerequisite_concepts"), list)
        )

        raw_map[idx] = raw
        ok_map[idx] = ok

        if ok:
            proposed_map[idx] = _clean_list(parsed["proposed_concepts"])
            prereq_map[idx] = _clean_list(parsed["prerequisite_concepts"])
        else:
            proposed_map[idx] = []
            prereq_map[idx] = []

    df["proposed_concepts"] = df.index.map(lambda i: proposed_map.get(i, []))
    df["prerequisite_concepts"] = df.index.map(lambda i: prereq_map.get(i, []))
    df["kc_raw"] = df.index.map(lambda i: raw_map.get(i, ""))
    df["kc_ok"] = df.index.map(lambda i: ok_map.get(i, False))
    return df


# KC를 concept 노드용 테이블로 펼치기
def kc_to_nodes_df(papers_df: pd.DataFrame) -> pd.DataFrame:
    base = papers_df.copy()
    base["paperId"] = base["paperId"].astype(str)

    a = base[["paperId","title","abstract","proposed_concepts"]].explode("proposed_concepts")
    a = a.rename(columns={"proposed_concepts":"name", "title":"paper_title"})
    a["edge_type"] = "ABOUT"

    b = base[["paperId","title","abstract","prerequisite_concepts"]].explode("prerequisite_concepts")
    b = b.rename(columns={"prerequisite_concepts":"name", "title":"paper_title"})
    b["edge_type"] = "IN"

    out = pd.concat([a, b], ignore_index=True)
    out["name"] = out["name"].fillna("").astype(str).str.strip()
    out = out[out["name"] != ""]

    out["category"] = pd.NA
    out["link"] = pd.NA

    return out[["name","link","category","edge_type","paperId","paper_title","abstract"]]


# alias 생성하는 함수
def add_alias_column(node_df: pd.DataFrame) -> pd.DataFrame:
    df = node_df.copy()
    names = df["name"].dropna().astype(str).unique().tolist()

    chat_inputs = []
    for name in tqdm(names, desc="alias: build prompts"):
        system_msg = ALIAS_PROMPT.replace("{INPUT_name}", name)
        user_msg = 'Return ONLY raw JSON in the form {"alias": [...]}'
        chat_inputs.append(build_chat_prompt(system_msg, user_msg))

    generations = generate_batch(chat_inputs)

    alias_map, raw_map, ok_map = {}, {}, {}

    for name, gen in tqdm(list(zip(names, generations)), total=len(names), desc="alias: parse outputs"):
        raw = gen.outputs[0].text.strip()
        raw_map[name] = raw

        parsed = extract_json(raw)
        ok = isinstance(parsed, dict) and isinstance(parsed.get("alias"), list)
        ok_map[name] = ok

        cleaned = []
        if ok:
            seen = set()
            for item in parsed["alias"]:
                if not isinstance(item, str):
                    continue
                s = item.strip()
                if not s or s == name:
                    continue
                if s not in seen:
                    seen.add(s)
                    cleaned.append(s)

        alias_map[name] = cleaned

    df["alias"] = df["name"].astype(str).map(alias_map)
    df["alias_raw"] = df["name"].astype(str).map(raw_map)
    df["alias_ok"] = df["name"].astype(str).map(ok_map)
    return df

def _norm(s: str) -> str:
    return " ".join(str(s).strip().lower().split())

def _u_path(s: str) -> str:
    return quote(str(s).replace(" ", "_"), safe="()_-.,:")

def _u_frag(s: str) -> str:
    return quote(str(s).replace(" ", "_"), safe="()_-.,:")

def _parse_listlike(x):
    if isinstance(x, (list, tuple)):
        return [str(v) for v in x]

    if x is None:
        return []

    try:
        if pd.isna(x):
            return []
    except Exception:
        pass

    s = str(x).strip()
    if not s:
        return []
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
        try:
            v = ast.literal_eval(s)
            if isinstance(v, (list, tuple)):
                return [str(i) for i in v]
        except Exception:
            pass
    return [s]

def wiki_map(node_df: pd.DataFrame, wiki_df: pd.DataFrame) -> pd.DataFrame:
    df = node_df.copy()

    w = wiki_df.copy().dropna(subset=["title"])
    w["title_raw"] = w["title"].astype(str)
    w["title_n"] = w["title_raw"].map(_norm)

    # subtitles 파싱 + explode
    if "subtitles" in w.columns:
        w["subtitle_list"] = w["subtitles"].apply(_parse_listlike)
        w_sub = w.explode("subtitle_list")
        w_sub["subtitle_raw"] = w_sub["subtitle_list"].fillna("").astype(str).str.strip()
        w_sub["subtitle_n"] = w_sub["subtitle_raw"].map(_norm)
        w_sub = w_sub[w_sub["subtitle_n"] != ""]
    else:
        w_sub = w.iloc[0:0].copy()
        w_sub["subtitle_raw"] = ""
        w_sub["subtitle_n"] = ""

    # subtitle -> (title, subtitle) 매핑(중복 subtitle은 최초 1개)
    sub_map = {}
    for _, r in w_sub.iterrows():
        sub_map.setdefault(r["subtitle_n"], (r["title_raw"], r["subtitle_raw"]))

    # title -> title 매핑(중복 title은 최초 1개)
    title_map = {}
    for _, r in w.iterrows():
        title_map.setdefault(r["title_n"], r["title_raw"])

    def dedup(xs):
        out, seen = [], set()
        for x in xs:
            x = "" if x is None else str(x).strip()
            if not x or x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    def _as_list_alias(alias):
        if isinstance(alias, list):
            return alias
        if pd.isna(alias):
            return []
        return _parse_listlike(alias)

    def map_one(name, alias):
        alias = _as_list_alias(alias)
        cand = dedup([name] + alias)

        # 1) subtitle 매칭: name/alias 중 하나가 subtitle이면 링크를 section으로
        for x in cand:
            xn = _norm(x)
            if xn in sub_map:
                wiki_title, wiki_sub = sub_map[xn]
                new_name = wiki_sub
                new_alias = dedup([a for a in cand if _norm(a) != xn] + [name])
                link = f"https://en.wikipedia.org/wiki/{_u_path(wiki_title)}#{_u_frag(wiki_sub)}"
                return new_name, new_alias, link, "subtitle"

        # 2) title 매칭
        for x in cand:
            xn = _norm(x)
            if xn in title_map:
                wiki_title = title_map[xn]
                new_name = wiki_title
                new_alias = dedup([a for a in cand if _norm(a) != xn] + [name])
                link = f"https://en.wikipedia.org/wiki/{_u_path(wiki_title)}"
                return new_name, new_alias, link, "title"

        # 3) 미매칭
        return name, dedup(alias), None, None

    mapped = df.apply(lambda r: map_one(r.get("name"), r.get("alias", [])),
                      axis=1, result_type="expand")
    mapped.columns = ["name", "alias", "link", "wiki_match_type"]
    df[["name", "alias", "link", "wiki_match_type"]] = mapped
    return df


# kc node 저장 전 로직
def _merge_alias(series):
    out, seen = [], set()
    for xs in series:
        if not isinstance(xs, list):
            continue
        for x in xs:
            if isinstance(x, str):
                s = x.strip()
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)
    return out

def _pick_link(links):
    links = [x for x in links if isinstance(x, str) and x.strip()]
    if not links:
        return None
    # 섹션(#) 있는 링크를 우선, 그다음 길이
    links.sort(key=lambda u: ("#" in u, len(u)), reverse=True)
    return links[0]

def finalize_kc_nodes(nodes_df_wiki: pd.DataFrame) -> pd.DataFrame:
    """
    KC 노드만 name 기준 unique하게 합치고,
    최종 저장 포맷(name, link, category, alias)로 정리
    """
    df = nodes_df_wiki.copy()

    kc = (
        df.groupby("name", as_index=False)
          .agg(
              link=("link", _pick_link),
              category=("category", "first"),
              alias=("alias", _merge_alias),
          )
    )

    # alias에서 name 제거(있다면)
    kc["alias"] = kc.apply(lambda r: [a for a in r["alias"] if a != r["name"]], axis=1)

    kc["categories"] = pd.NA

    # 최종은 KC만 저장하므로 alias drop
    return kc[["name", "link", "categories", "alias"]]
