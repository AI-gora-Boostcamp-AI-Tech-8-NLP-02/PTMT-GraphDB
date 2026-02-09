# PTMT-GraphDB

페튜와 매튜(Paper Tutor & Map Tutor) Graph Database 구축 레포지토리입니다.
데이터셋 수집과 전처리 및 논문과 선수 개념 간의 그래프 구축을 위한 코드들이 있습니다.

## 주요 기능
- 활용한 데이터: 선수 관계 데이터셋 (Metacademy, TutorialBank), Wikipedia dump, 논문 데이터셋 (Semantic Scholar API)
- Graph Database 구축 전 전처리 및 구축 코드

## 실행 방법
### 의존성 설치
`uv` 기준: 
```bash
uv sync
```
`pip` 기준:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 환경 변수 설정
`.env_example`을 복사해 `.env`를 만듭니다.
API 키 값을 설정합니다.

### 실행
```bash
## 전처리
Wiki & KC 데이터셋: preprocessing 내 ipynb 활용
Paper: preprocessing 내 ipynb 활용 OR uv run preprocessing/papers/main.py

## 그래프 빌드
graph_build 내 ipynb 활용
```

## 프로젝트 구조
```bash
PTMT-GraphDB/
├─ .venv
├─ notebooks/
├─ data/
│  ├─ kc_dataset/       
│  ├─ wikipedia/
│  └─ papers/
│
├─ preprocessing/
│  ├─ kc_dataset/
│  ├─ wikipedia/
│  └─ papers/  
│
├─ schema.md           # 노드/엣지 정의 (KC, LO 타입, Property 등)
└─ graph_build/         # 실제 노드/엣지 생성 -> neo4j 업로드하는 코드 + 업데이트 코드
```
