# category_extractor.py

import pandas as pd
import requests
import time
import logging
import json
import os
from typing import List, Dict
from collections import defaultdict
from urllib.parse import quote
from tqdm import tqdm

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('papers_processing.log'),
        logging.StreamHandler()
    ]
)


class PapersCategoryExtractor:
    def __init__(self, language='en'):
        """
        Args:
            language: 위키피디아 언어 코드 (en, ko 등)
        """
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Papers Category Extractor/1.0 (Educational Purpose)',
            'Accept-Encoding': 'gzip'
        })

        self.current_delay = 0.5  # 초기 delay를 더 길게
        self.min_delay = 0.5
        self.max_delay = 10.0  # 최대 delay도 증가

    def api_request(self, params: Dict, max_retries: int = 5) -> Dict:
        """API 요청 with exponential backoff"""
        params['format'] = 'json'
        retry_count = 0

        while retry_count < max_retries:
            time.sleep(self.current_delay)

            try:
                response = self.session.get(self.base_url, params=params, timeout=30)

                # HTTP 429 에러 특별 처리
                if response.status_code == 429:
                    retry_count += 1
                    wait_time = min(10 * (2 ** retry_count), 60)  # 최대 60초
                    logging.warning(f"HTTP 429 Too Many Requests. {wait_time}초 대기 후 재시도 ({retry_count}/{max_retries})")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                data = response.json()

                # Rate limit 체크
                if 'error' in data:
                    error_code = data['error'].get('code', '')
                    if error_code == 'ratelimited':
                        retry_count += 1
                        wait_time = min(5 * (2 ** retry_count), 30)
                        logging.warning(f"API Rate limit. {wait_time}초 대기 후 재시도 ({retry_count}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error(f"API 에러: {data['error']}")
                        return {}

                # 성공 시 딜레이 감소
                if self.current_delay > self.min_delay:
                    self.current_delay = max(self.current_delay * 0.9, self.min_delay)

                return data

            except requests.exceptions.HTTPError as e:
                if '429' in str(e):
                    retry_count += 1
                    wait_time = min(10 * (2 ** retry_count), 60)
                    logging.warning(f"HTTP 429 에러. {wait_time}초 대기 후 재시도 ({retry_count}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    retry_count += 1
                    logging.warning(f"HTTP 에러: {e}. 재시도 중... ({retry_count}/{max_retries})")
                    self.current_delay = min(self.current_delay * 1.5, self.max_delay)

            except Exception as e:
                retry_count += 1
                logging.warning(f"에러: {e}. 재시도 중... ({retry_count}/{max_retries})")
                self.current_delay = min(self.current_delay * 1.5, self.max_delay)

        logging.error(f"최대 재시도 횟수 초과")
        return {}

    def create_wikipedia_link(self, page_name: str) -> str:
        """
        페이지 이름으로부터 Wikipedia URL 생성

        Args:
            page_name: Wikipedia 페이지 이름

        Returns:
            Wikipedia URL
        """
        # 공백을 언더스코어로 변경하고 URL 인코딩
        formatted_name = page_name.replace(' ', '_')
        encoded_name = quote(formatted_name, safe='')
        return f"https://en.wikipedia.org/wiki/{encoded_name}"


    def check_pages_exist_and_get_categories(
        self,
        page_names: List[str],
        batch_size: int = 20,
        checkpoint_file: str = "papers_checkpoint.json",
        save_every_batches: int = 5,
    ) -> Dict[str, Dict]:
        """
        input: page_names (concept name들)
        output: {input_name: {'exists': bool, 'link': str, 'categories': [str...]}}
        """
        results = defaultdict(lambda: {"exists": False, "link": "", "categories": []})

        # 체크포인트 로드
        start_index = 0
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    checkpoint = json.load(f)
                    # checkpoint["results"]는 일반 dict여야 함
                    results.update(checkpoint.get("results", {}))
                    start_index = int(checkpoint.get("last_index", 0))
                    logging.info(f"체크포인트 로드: {start_index}번째 항목부터 재개")
            except Exception as e:
                logging.warning(f"체크포인트 로드 실패: {e}. 처음부터 시작합니다.")
                start_index = 0

        page_names = [str(x).strip() for x in page_names if x is not None and str(x).strip()]
        if not page_names:
            return {}

        logging.info(f"{len(page_names)}개 페이지 처리 중... (시작: {start_index})")
        for i in tqdm(range(start_index, len(page_names), batch_size), desc="wiki: fetch categories"):
            batch = page_names[i:i + batch_size]
            titles_str = "|".join(batch)

            clcontinue = None
            while True:
                params = {
                    "action": "query",
                    "titles": titles_str,
                    "prop": "categories",
                    "cllimit": "max",
                    "clshow": "!hidden",
                    "redirects": 1,
                }
                if clcontinue:
                    params["clcontinue"] = clcontinue

                data = self.api_request(params)
                if "query" not in data:
                    break

                redirect_map = {}
                for r in (data.get("query", {}).get("redirects") or []):
                    redirect_map[r.get("from")] = r.get("to")

                normalized_map = {}
                for n in (data.get("query", {}).get("normalized") or []):
                    normalized_map[n.get("from")] = n.get("to")

                pages = data.get("query", {}).get("pages", {}) or {}

                for page_id, page_data in pages.items():
                    if page_id == "-1" or "missing" in page_data:
                        continue

                    page_title = page_data.get("title", "")
                    if not page_title:
                        continue

                    # 원본 입력 name 추적(정규화/리다이렉트 역추적)
                    original_title = page_title
                    for orig, norm in normalized_map.items():
                        if norm == page_title:
                            original_title = orig
                    for orig, redir in redirect_map.items():
                        if redir == page_title or redir == original_title:
                            original_title = orig

                    # batch 내에서 매칭되는 입력 name 찾기
                    matched_name = None
                    for name in batch:
                        if (
                            name.replace("_", " ").lower() == original_title.replace("_", " ").lower()
                            or name.replace("_", " ").lower() == page_title.replace("_", " ").lower()
                        ):
                            matched_name = name
                            break
                    if not matched_name:
                        matched_name = original_title

                    link = self.create_wikipedia_link(page_title)

                    categories = []
                    for c in (page_data.get("categories") or []):
                        cat_name = (c.get("title") or "").replace("Category:", "")
                        if cat_name:
                            categories.append(cat_name)

                    # merge
                    cur = results[matched_name]
                    cur["exists"] = True
                    # link: 저장은 하되, 나중에 "link 없을 때만 채우기" 규칙 적용
                    cur["link"] = link or cur.get("link", "")

                    if categories:
                        cur_set = set(cur.get("categories") or [])
                        cur_set.update(categories)
                        cur["categories"] = list(cur_set)

                cont = data.get("continue", {}) or {}
                if "clcontinue" in cont:
                    clcontinue = cont["clcontinue"]
                else:
                    break
            
            # 체크포인트 저장
            batch_no = (i // batch_size)
            if save_every_batches and (batch_no % save_every_batches == 0):
                try:
                    with open(checkpoint_file, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "last_index": min(i + batch_size, len(page_names)),
                                "results": dict(results),
                            },
                            f,
                            ensure_ascii=False,
                        )
                    logging.info(f"진행 상황 저장: {i + batch_size}/{len(page_names)}")
                except Exception as e:
                    logging.warning(f"체크포인트 저장 실패: {e}")

        # 완료 후 체크포인트 파일 삭제
        if os.path.exists(checkpoint_file):
            try:
                os.remove(checkpoint_file)
                logging.info("체크포인트 파일 삭제")
            except Exception:
                pass
        return dict(results)

    # DataFrame을 받아서 categories/link를 채워서 반환
    def fill_categories_in_df(
        self,
        df: pd.DataFrame,
        name_col: str = "name",
        link_col: str = "link",
        categories_col: str = "categories",
        batch_size: int = 20,
        only_when_missing: bool = True,
    ) -> pd.DataFrame:
        """
        - df[name_col] 기준으로 위키 조회
        - df[link_col]이 비어있으면: 위키에서 찾은 link로 채움 (덮어쓰기 X)
        - df[categories_col]은:
            - only_when_missing=True면 비어있는 row만 채움
            - False면 기존 categories와 union
        """
        out = df.copy()

        # 컬럼 없으면 생성 (너 요구대로 컬럼명은 categories 유지)
        if link_col not in out.columns:
            out[link_col] = pd.NA
        if categories_col not in out.columns:
            out[categories_col] = pd.NA

        # 비어있음 판단
        def _is_empty(v) -> bool:
            # pd.NA / np.nan 포함해서 전부 빈 값 처리
            try:
                if pd.isna(v):
                    return True
            except Exception:
                pass

            if isinstance(v, str) and not v.strip():
                return True
            if isinstance(v, list) and len(v) == 0:
                return True
            return False

        # 조회 대상: (categories가 비었거나 / link가 비었거나)
        need_mask = out[name_col].notna()
        if only_when_missing:
            need_mask = need_mask & (out[categories_col].apply(_is_empty) | out[link_col].apply(_is_empty))
        # else: 어차피 union 할 거지만, 없는 것들만 조회해도 충분 -> link/categories 비어있는 것만 조회
        else:
            need_mask = need_mask & (out[categories_col].apply(_is_empty) | out[link_col].apply(_is_empty))

        targets = out.loc[need_mask, name_col].astype(str).tolist()
        targets = list(dict.fromkeys([t.strip() for t in targets if t.strip()]))

        if not targets:
            logging.info("No targets to fetch categories.")
            return out

        wiki_data = self.check_pages_exist_and_get_categories(targets, batch_size=batch_size)

        # apply
        def _merge_categories(existing, new_list):
            # 기존이 list면 union, 문자열이면 split하기 애매해서 그냥 기존 우선(안전)
            if isinstance(existing, list):
                s = set(existing)
                s.update(new_list or [])
                return list(s)
            if _is_empty(existing):
                return list(dict.fromkeys(new_list or []))
            if isinstance(existing, str):
                # 혹시 기존이 "a,b,c" 형태면 보수적으로 union 시도
                parts = [p.strip() for p in existing.split(",") if p.strip()]
                s = set(parts)
                s.update(new_list or [])
                return list(s)
            return existing

        for idx, row in out.loc[need_mask].iterrows():
            name = str(row.get(name_col) or "").strip()
            if not name:
                continue

            hit = wiki_data.get(name) or {}
            new_link = hit.get("link", "")
            new_cats = hit.get("categories", []) or []

            # link는 "기존이 비어있을 때만" 채움
            if _is_empty(row.get(link_col)) and new_link:
                out.at[idx, link_col] = new_link

            # categories 채움/병합
            if only_when_missing:
                if _is_empty(row.get(categories_col)) and new_cats:
                    out.at[idx, categories_col] = list(dict.fromkeys(new_cats))
            else:
                out.at[idx, categories_col] = _merge_categories(row.get(categories_col), new_cats)

        return out