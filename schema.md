# Graph DB Schema

**본 문서는 Knowledge Concept(KC) 와 Paper를 노드로 가지는 그래프 DB 스키마를 정의한다.**

## Overview
- Graph Model
    - Node: KC, Paper
    - Edge: PREREQ, ABOUT, IN, REF_BY
- ID
    - 모든 Node / Edge는 내부적으로 id: int 를 가지며, 시스템에서 자동 생성됨
- Strength: 관계의 중요도 / 필수성을 0 ~ 1 범위의 float 값으로 표현

### Nodes
#### 1. KC (Knowledge Concept): 지식 단위(개념, 이론, 방법론 등)를 표현하는 노드
```
{
  "id": int,
  "name": "string",
  "categories": ["string"],
  "link": "string", 
  "alias": [List]
}
```
| Field    | Type         | Description             |
| -------- | ------------ | ----------------------- |
| id       | int          | 내부 식별자 (auto-generated) |
| name     | string       | 지식 개념 이름                |
| categories | list[string] | 개념 분류 (도메인, 레벨 등)       |
| link     | string (optional)       | wiki 링크 |
| alias    | list[string] | 동의어 |

#### 2. Paper: 논문
```
{
  "id": int,
  "paperId": str,  // semantic scholar에서 제공해줌
  "name": "string",
  "categories": "string",
  "year": "string",
  "url": "string",
  "authors": [List], 
  "abstract": "string",
  "publication": "string",
  "referenceCount": int,
  "citationCount": int
}
```
| Field          | Type              | Description     |
| -------------- | ----------------- | --------------- |
| id             | int               | 내부 식별자          |
| paperId | string | semantic scholar에서 제공해줌 |
| title          | string            | 논문 제목           |
| categories       | string            | 논문 주제/분야        |
| year           | string            | 출판 연도           |
| url            | string (optional)   | Open-access URL |
| authors | list[json] (optional) | 저자와 저자 id |
| abstract       | string (optional) | 초록              |
| publication    | string (optional) | 학회/저널           |
| referenceCount | int (optional)    | 참고문헌 수          |
| citationCount  | int (optional)    | 피인용 수           |


### Edges
#### 1. KC → KC : `PREREQ`
```
A -{PREREQ}→ B
```
- A는 B의 선수 지식이다.
- B를 이해하기 위해 A가 필요하다.
```
{
  "id": int,
  "strength": float,
  "reason": "string"
}
```
| Field    | Type              | Description |
| -------- | ----------------- | ----------- |
| id       | int               | 관계 ID       |
| strength | float (0~1)       | 선수 지식 강도    |
| reason   | string (optional) | 선수 관계의 근거   |

#### 2. Paper ↔ KC
#### 2.1 Paper → KC : `ABOUT`
```
Paper -{ABOUT}→ KC
```
- 해당 Paper에서 KC를 제안/소개하였다.
- KC의 기원(origin)을 나타냄
#### 2.2 KC → Paper : `IN`
```
KC -{IN}→ Paper
```
- 해당 KC가 Paper에서 주요하게 언급된다.
- Paper를 이해하기 위한 선수 지식으로 KC가 필요함
```
{
  "id": int,
  "reason": "string",
  "strength": float
}
```
| Field    | Type        | Description      |
| -------- | ----------- | ---------------- |
| id       | int         | 관계 ID            |
| reason   | string      | 관계 설명            |
| strength | float (0~1) | 핵심적으로 다루는 정도     |

#### 3. Paper → Paper : `REF_BY`
```
A -{REF_BY}→ B
```
- Paper B가 Paper A를 참고하였다.
- B의 참고문헌에 A가 포함됨
- A는 B의 선수 지식이다.
```
{
  "id": int,
  "intents": ["string"],
  "isInfluential": boolean,
  "contexts": ["string"]
}
```
| Field         | Type         | Description                                 |
| ------------- | ------------ | ------------------------------------------- |
| id            | int          | 관계 ID                                       |
| intents       | list[string] | 인용 목적 (Background / Methodology / Result 등) |
| isInfluential | boolean      | 핵심적 영향 여부                                   |
| contexts      | list[string] | 인용 문맥                                       |