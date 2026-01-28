#!/usr/bin/env bash
set -euo pipefail

curl -G "https://api.semanticscholar.org/graph/v1/paper/search/bulk" \
  --data-urlencode 'query=AI | "machine learning" | "deep learning" | "large language model" | NLP | "natural language processing" | CV | "computer vision" | "multi-modal"' \
  --data-urlencode 'limit=1' \
  --data-urlencode 'sort=citationCount:desc' \
  --data-urlencode 'fields=paperId,title,year,url,abstract,venue,referenceCount,citationCount,fieldsOfStudy,s2FieldsOfStudy' \
  -H "x-api-key: ${S2_API_KEY}" \
  -o papers.json
