# main.py

import json
import pandas as pd
from dotenv import load_dotenv
import os

from load import get_ai_papers, extract_references_from_papers_json
from nodes import (
    build_nodes_paper,
    add_description_to_nodes, 
    add_kc_to_paper_nodes,
    kc_to_nodes_df,
    add_alias_column,
    wiki_map,
    finalize_kc_nodes
)
from edges import build_scored_edges, add_ref_by_strength, finalize_ref_by_edges
from category_extractor import PapersCategoryExtractor


REF_FETCH = 100          # references에서 먼저 가져올 후보 수
TOP_K = 5                # 최종 저장할 참고문헌 개수(논문당)


def main():
    load_dotenv()
    wiki = pd.read_csv("../../data/wikipedia/wiki_subtitle.csv")
    os.makedirs("../../data/test", exist_ok=True)

    # bulk API를 활용해 ai 관련한 논문들을 찾아옴
    print("[step 1] 논문 불러오기")
    get_ai_papers()

    res = json.load(open("papers.json", encoding="utf-8"))
    print("total:", res.get("total"), "data_len:", len(res.get("data", [])), "token:", res.get("token"))

    # DataFrame 변환
    papers = res.get("data", [])
    raw_papers_df = pd.DataFrame(papers)

    # reference 논문과 그 정보를 추출
    print("[step 2] 논문이 참고한 논문 불러오기")
    ref_df, errors = extract_references_from_papers_json(
        seeds_json_path="papers.json",
        ref_fetch=REF_FETCH,
        top_k=TOP_K)

    # nodes

    # paper node 생성
    print("[step 3] 불러온 논문을 합쳐서 paper 노드.csv 만들기")
    nodes_paper = build_nodes_paper(raw_papers_df, ref_df)
    ## paper node 저장
    nodes_paper = add_description_to_nodes(nodes_paper)
    nodes_paper.to_csv("../../data/test/papers_nodes_paper.csv", index=False)

    # 해당 paper node에서의 핵심 KC를 뽑고 alias 까지 생성
    print("[step 4] 논문에서 핵심 키워드를 뽑고 키워드의 동의어를 뽑기")
    nodes_paper_kc = add_kc_to_paper_nodes(nodes_paper)
    # KC를 concept 노드용 테이블로 펼치기
    nodes_kc_all = kc_to_nodes_df(nodes_paper_kc)
    # alias 컬럼 추가
    nodes_kc_alias = add_alias_column(nodes_kc_all)

    # 위키의 subtitle, title과 비교해서 link 매칭
    nodes_kc_wiki = wiki_map(nodes_kc_alias, wiki)
    nodes_kc = finalize_kc_nodes(nodes_kc_wiki)
    # 위키 API를 활용한 카테고리 매칭
    print("[step 5] wikipedia 상 어떤 카테고리에 속하는지 카테고리 매칭")
    extractor = PapersCategoryExtractor(language="en")
    nodes_kc = extractor.fill_categories_in_df(nodes_kc, only_when_missing=True)
    # kc node 저장
    nodes_kc.to_csv("../../data/test/papers_node_kc.csv", index=False)
    print("-- 논문, 논문에서 추출된 키워드 노드들 저장 완료")

    # edges
    print("[step 6] 논문에서 뽑은 논문과 키워드 간 엣지의 strength 생성")
    # paper에서 뽑은 kc 엣지
    edges_paper_kc = build_scored_edges(nodes_kc_wiki)
    papers_edge_paper_kc = (
        edges_paper_kc
        .rename(columns={'edge_type': 'name'})
        [['paperId', 'concept', 'name', 'strength', 'reason']]
    )
    papers_edge_paper_kc.to_csv("../../data/test/papers_edge_paper_kc.csv", index=False)

    # paper간의 엣지
    print("[step 7] 논문 간 엣지의 strength 생성")
    ref_scored = add_ref_by_strength(ref_df, seeds_json_path="papers.json")
    edge_paper_paper = finalize_ref_by_edges(ref_scored)
    edge_paper_paper.to_csv("../../data/test/papers_edge_paper_paper.csv", index=False)
    print("-- 논문과 관련된 엣지들 저장 완료")


if __name__ == "__main__":
    main()
