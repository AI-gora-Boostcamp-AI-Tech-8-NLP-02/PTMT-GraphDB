# PTMT-GraphDB

### 폴더 구조
```
PTMT-GraphDB/
├─ .venv
├─ notebooks/
├─ data/
│  ├─ kc_dataset/       # 전처리 완료된 거 저장해도 됨
│  ├─ wikipedia/
│  └─ papers/
│
├─ preprocessing/
│  ├─ kc_dataset/
│  ├─ wikipedia/
│  └─ papers/  # py로 확정
│
├─ schema.md           # 노드/엣지 정의 (KC, LO 타입, Property 등)
└─ graph_build/         # 실제 노드/엣지 생성 -> neo4j 업로드하는 코드 + 업데이트 코드
```