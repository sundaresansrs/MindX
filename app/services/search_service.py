"""
MindX AI - Enhanced Search Service
Stack: SearXNG (primary) + Jina AI Reader (full content) + DuckDuckGo (fallback) + Wikipedia
"""

import asyncio
import httpx  # type: ignore
import re
import logging
import re
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from langdetect import detect, LangDetectException # type: ignore

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

SEARXNG_BASE_URL = "http://localhost:8080"   # Self-hosted SearXNG (optional)
JINA_BASE_URL    = "https://r.jina.ai"       # Free, no key needed
MAX_RESULTS      = 10
MAX_FULL_PAGES   = 3                          # How many URLs to deep-fetch via Jina
REQUEST_TIMEOUT  = 15


# ============================================================
# CREDIBILITY SCORER
# ============================================================

CREDIBILITY_TIERS = {
    "high": [
        "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "scholar.google.com",
        "nature.com", "science.org", "ieee.org", "acm.org",
        "researchgate.net", "semanticscholar.org"
    ],
    "medium_high": [
        "bbc.com", "reuters.com", "apnews.com", "theguardian.com",
        "nytimes.com", "techcrunch.com", "wired.com", "arstechnica.com",
        "github.com", "stackoverflow.com", "wikipedia.org", ".gov"
    ],
    "medium": [
        "medium.com", "dev.to", "hashnode.com", "towardsdatascience.com"
    ],
    "low_medium": [
        "reddit.com", "quora.com", "twitter.com", "x.com"
    ]
}


def get_credibility_score(url: str) -> tuple:
    """Returns (score 0-1, label)"""
    domain = url.lower()
    for site in CREDIBILITY_TIERS["high"]:
        if site in domain:
            return 0.95, "Academic/Research"
    for site in CREDIBILITY_TIERS["medium_high"]:
        if site in domain:
            return 0.80, "News/Official"
    for site in CREDIBILITY_TIERS["medium"]:
        if site in domain:
            return 0.65, "Tech Blog"
    for site in CREDIBILITY_TIERS["low_medium"]:
        if site in domain:
            return 0.50, "Community"
    return 0.55, "General Web"


def is_english_content(text: str) -> bool:
    """Strictly filter non-English content."""
    if not text or len(text.strip()) < 20:
        return False
    try:
        lang = detect(text)
        return lang == 'en'
    except LangDetectException:
        return True  # keep if detection fails


def filter_results(results: List[Dict]) -> List[Dict]:
    """
    Remove non-English results, low quality domains,
    and results with no snippet.
    """
    BLOCKED_DOMAINS = [
        # Chinese Portals & Search
        'zhihu.com', 'baidu.com', 'weibo.com', 'qq.com',
        'taobao.com', 'bilibili.com', 'sina.com.cn',
        'tieba.baidu.com', '163.com', 'sohu.com',
        'toutiao.com', 'pan.baidu.com', 'zhuanlan.zhihu.com',
        
        # Chinese Tech Spam / Aggregators
        'csdn.net', 'jianshu.com', 'douban.com',
        'xiaohongshu.com', 'gitee.com', 'iteye.com',
        'oschina.net', 'cnblogs.com', '51cto.com',
        'aliyun.com', 'tencent.com', 'juejin.cn',
        
        # Generic Spam / Low Quality
        'pinterest.com', 'softonic.com', 'cnet.com' 
    ]

    from langdetect import detect # type: ignore

    filtered = []
    seen_domains = set()
    
    for r in results:
        url = r.get('url', '').lower()
        snippet = r.get('snippet', '')
        title = r.get('title', '')
        
        if not url: continue

        # 1. Block known spam/non-English domains
        if any(domain in url for domain in BLOCKED_DOMAINS):
            logger.info(f"🚫 Blocked domain: {url}")
            continue
        
        # Extra check for .cn domains
        if ".cn/" in url or url.endswith(".cn"):
            logger.info(f"🚫 Blocked .cn domain: {url}")
            continue

        # 2. Block non-English content (Chinese/Hindi/etc tokens)
        if re.search(r'[\u4e00-\u9fff]', title + snippet): # Chinese
            logger.info(f"🚫 Blocked Chinese characters in: {title[:30]}")
            continue
            
        try:
            # Combine title and snippet for better detection
            combined = (title + " " + snippet).strip()
            if len(combined) > 60: # Only filter longer text to avoid false positives on short titles
                if detect(combined) != 'en':
                    logger.info(f"🚫 Detected non-English content ({detect(combined)}): {title[:40]}")
                    continue
        except:
            pass

        # 3. Block results with tiny snippets
        if len(snippet.strip()) < 20: 
            continue
            
        # 4. Domain-based Deduplication (keep first found)
        try:
            match = re.search(r'https?://([^/]+)', url)
            domain = match.group(1).lower() if match else url
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
        except:
            pass

        filtered.append(r)

    logger.info(f"✅ {len(filtered)}/{len(results)} results passed filters")
    return filtered


# ============================================================
# SEARCH SERVICE CLASS
# ============================================================

class SearchService:
    """
    Enhanced search service with:
    - SearXNG (self-hosted, unlimited) as primary
    - DuckDuckGo as automatic fallback
    - Jina AI for full page content (no snippets problem)
    - Wikipedia for factual grounding
    - Credibility scoring per source
    """

    def __init__(self):
        self.searxng_available = False  # Will be checked on first use

    # ─── SearXNG (Primary) ───────────────────────────────────────────────────

    async def _search_searxng(self, query: str, client: httpx.AsyncClient, max_results: int = MAX_RESULTS) -> List[Dict]:
        params = {
            "q": query,
            "format": "json",
            "engines": "google,bing,duckduckgo",
            "language": "en-US",
            "safesearch": "0",
            "pageno": 1
        }
        try:
            response = await client.get(
                f"{SEARXNG_BASE_URL}/search",
                params=params,
                timeout=5.0  # Short timeout - fall back quickly if not running
            )
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("results", [])[:max_results]:
                score, label = get_credibility_score(item.get("url", ""))
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                    "source": label,
                    "credibility_score": score,
                })
            self.searxng_available = True
            logger.info(f"SearXNG returned {len(results)} results for: {query}")
            return results
        except Exception as e:
            logger.info(f"SearXNG unavailable ({e}), will use DuckDuckGo")
            self.searxng_available = False
            return []

    # ─── DuckDuckGo (Fallback) ───────────────────────────────────────────────

    async def _search_duckduckgo(self, query: str, max_results: int = MAX_RESULTS) -> List[Dict]:
        try:
            from duckduckgo_search import DDGS  # type: ignore

            def sync_search() -> List[Dict]:
                with DDGS() as ddgs:
                    # Simplify arguments for better compatibility
                    results = ddgs.text(
                        query,
                        max_results=max_results
                    )
                    return list(results)

            fn: Callable[[], List[Dict]] = sync_search
            raw: List[Dict] = await asyncio.wait_for(asyncio.to_thread(fn), timeout=15.0)  # type: ignore
            
            results = []
            for item in raw:
                url = item.get("href") or item.get("link", "")
                title = item.get("title", "")
                snippet = item.get("body") or item.get("snippet", "")
                
                if not url or not title: continue
                
                score, label = get_credibility_score(url)
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": label,
                    "credibility_score": score,
                })
            
            logger.info(f"DuckDuckGo returned {len(results)} results for: {query}")
            return results
        except asyncio.TimeoutError:
            logger.warning(f"DuckDuckGo timed out for: {query}")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo error: {e}")
            return []

    # ─── Jina AI Full Page Content ───────────────────────────────────────────

    async def _fetch_full_content(self, url: str, client: httpx.AsyncClient) -> Optional[str]:
        """Fetch clean markdown content from any URL via Jina AI Reader (free, no key)."""
        jina_url = f"{JINA_BASE_URL}/{url}"
        headers = {
            "Accept": "text/plain",
            "X-Return-Format": "markdown",
            "X-Remove-Selector": "nav,footer,header,aside,script,style"
        }
        try:
            response = await client.get(jina_url, headers=headers, timeout=20.0)
            response.raise_for_status()
            content = response.text
            content = re.sub(r'\n{3,}', '\n\n', content)
            content = str(content)[:6000]  # type: ignore  # ~1500 tokens
            return content if len(content) > 200 else None
        except Exception as e:
            logger.warning(f"Jina fetch failed for {url}: {e}")
            return None

    # ─── Wikipedia ───────────────────────────────────────────────────────────

    async def _search_wikipedia(self, query: str, client: httpx.AsyncClient) -> List[Dict]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
            "srprop": "snippet"
        }
        # Wikipedia requires a proper User-Agent
        headers = {
            "User-Agent": "MindX-AI/1.0 (Research Assistant; contact@example.com)"
        }
        try:
            response = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            data = response.json()
            results = []
            for item in data.get("query", {}).get("search", []):
                snippet = re.sub(r'<[^>]+>', '', item.get("snippet", ""))
                title = item.get("title", "")
                results.append({
                    "title": title,
                    "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "snippet": snippet,
                    "source": "Wikipedia",
                    "credibility_score": 0.85,
                })
            logger.info(f"Wikipedia returned {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"Wikipedia error: {e}")
            return []

    # ─── Deduplication ───────────────────────────────────────────────────────

    def deduplicate_sources(self, results: List[Dict]) -> List[Dict]:
        seen_domains = set()
        deduplicated: List[Dict] = []
        for result in results:
            url = result.get("url", "")
            if not url: continue
            
            try:
                # Extract domain
                match = re.search(r'https?://([^/]+)', url)
                domain = match.group(1).lower() if match else url
                
                if domain not in seen_domains:
                    seen_domains.add(domain)
                    deduplicated.append(result)
            except:
                deduplicated.append(result)
                
        return deduplicated

    def filter_chinese_results(self, results: List[Dict]) -> List[Dict]:
        """Strictly remove results with Chinese characters or .cn domains."""
        filtered = []
        for r in results:
            url = r.get("url", "").lower()
            if ".cn/" in url or url.endswith(".cn"):
                continue
            
            # Check for Chinese characters in title/snippet
            text = (r.get("title", "") + " " + r.get("snippet", ""))
            if re.search(r'[\u4e00-\u9fff]', text):
                continue
                
            filtered.append(r)
        return filtered

    # ─── Main Search Entry Point ─────────────────────────────────────────────

    async def search_web(self, query: str, max_results: int = MAX_RESULTS, deep_fetch: bool = True, max_full_pages: Optional[int] = None) -> List[Dict]:
        """
        Main search: SearXNG → DuckDuckGo fallback → Wikipedia → Jina deep fetch.
        Returns list of source dicts sorted by credibility.
        """
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": "MindX-AI/1.0 (Research Assistant)"}
        ) as client:
            all_results: List[Dict] = []

            # Try SearXNG first
            searxng_results = await self._search_searxng(query, client, max_results)
            if searxng_results:
                all_results.extend(searxng_results)
            else:
                # Fallback to DuckDuckGo
                ddg_results = await self._search_duckduckgo(query, max_results)
                all_results.extend(ddg_results)

            # Always add Wikipedia for factual grounding
            wiki_results = await self._search_wikipedia(query, client)
            all_results.extend(wiki_results)

            # Deduplicate and filter results
            all_results = self.filter_chinese_results(all_results)
            all_results = filter_results(all_results)
            unique = self.deduplicate_sources(all_results)
            unique.sort(key=lambda x: x.get("credibility_score", 0.5), reverse=True)

            # Deep fetch full content for top results via Jina
            if deep_fetch and unique:
                fetch_limit = max_full_pages if max_full_pages is not None else MAX_FULL_PAGES
                fetch_tasks = [
                    self._fetch_full_content(r["url"], client)
                    for r in unique[:fetch_limit]  # type: ignore
                ]
                full_contents = await asyncio.gather(*fetch_tasks)
                for i, content in enumerate(full_contents):
                    if content:
                        unique[i]["full_content"] = content
                        logger.info(f"Jina fetched full content for: {unique[i]['title'][:50]}")

            return unique[:max_results]  # type: ignore
        
        return [] # Fallback

    async def search_multiple_queries(self, queries: List[str], max_results_per_query: int = 10, max_full_pages: Optional[int] = None) -> List[Dict]:
        """
        Search multiple queries in parallel and aggregate results.
        Used by the quality pipeline for expanded query search.
        """
        tasks = [self.search_web(q, max_results=max_results_per_query, deep_fetch=True, max_full_pages=max_full_pages) for q in queries]
        results_nested = await asyncio.gather(*tasks)

        all_results: List[Dict] = []
        for results in results_nested:
            all_results.extend(results)  # type: ignore

        all_results = self.filter_chinese_results(all_results)
        all_results = filter_results(all_results)
        return self.deduplicate_sources(all_results)  # type: ignore

    # ============================================================
    # LAYER 3: SPECIALIZED SEARCH SOURCES
    # ============================================================

    def detect_search_intent(self, query: str) -> List[str]:
        """
        Heuristic intent classifier — determines which specialized
        sources to query based on keyword signals.
        Returns a list of intents: 'news', 'academic', 'code', 'forum'.
        """
        q = query.lower()
        intents = []

        news_signals = [
            "latest", "news", "today", "breaking", "update",
            "announced", "released", "launched", "report",
        ]
        if any(w in q for w in news_signals):
            intents.append("news")

        academic_signals = [
            "paper", "research", "study", "journal", "arxiv",
            "scholar", "peer-reviewed", "thesis", "citation",
            "academic", "doi", "pubmed",
        ]
        if any(w in q for w in academic_signals):
            intents.append("academic")

        code_signals = [
            "github", "repo", "repository", "open source",
            "library", "package", "npm", "pip install", "crate",
            "framework", "sdk", "api docs",
        ]
        if any(w in q for w in code_signals):
            intents.append("code")

        forum_signals = [
            "reddit", "discussion", "forum", "opinion",
            "hacker news", "hn", "community", "thread",
            "experience", "best practices",
        ]
        if any(w in q for w in forum_signals):
            intents.append("forum")

        return intents

    async def search_specialized(
        self, query: str, intents: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Dispatch to specialized sources based on detected intents.
        Should be called in parallel with the primary search.
        """
        if intents is None:
            intents = self.detect_search_intent(query)

        if not intents:
            return []

        tasks = []
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            for intent in intents:
                if intent == "news":
                    tasks.append(self._search_hackernews(query, client))
                elif intent == "academic":
                    tasks.append(self._search_semantic_scholar(query, client))
                elif intent == "code":
                    tasks.append(self._search_github(query, client))
                elif intent == "forum":
                    tasks.append(self._search_reddit(query, client))
                    tasks.append(self._search_hackernews(query, client))

            if not tasks:
                return []

            try:
                results_nested = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Specialized search timed out")
                return []

        all_results: List[Dict] = []
        for result in results_nested:
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Specialized source error: {result}")

        return all_results

    # ── Semantic Scholar (free, no key) ──

    async def _search_semantic_scholar(
        self, query: str, client: httpx.AsyncClient, limit: int = 5
    ) -> List[Dict]:
        """Search Semantic Scholar for academic papers."""
        try:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": query,
                    "limit": limit,
                    "fields": "title,url,abstract,year,citationCount,authors",
                },
                timeout=8.0,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []
            for paper in data.get("data", []):
                authors = ", ".join(
                    a.get("name", "") for a in list(paper.get("authors") or [])[:3]  # type: ignore
                )
                snippet = paper.get("abstract") or ""
                if len(snippet) > 500:
                    snippet = snippet[:500] + "..."

                results.append({
                    "title": paper.get("title", ""),
                    "url": paper.get("url") or f"https://api.semanticscholar.org/CorpusID:{paper.get('paperId','')}",
                    "snippet": snippet,
                    "source": "Semantic Scholar",
                    "credibility_score": 0.92,
                    "metadata": {
                        "year": paper.get("year"),
                        "citations": paper.get("citationCount", 0),
                        "authors": authors,
                    },
                })
            logger.info(f"Semantic Scholar: {len(results)} papers found")
            return results

        except Exception as e:
            logger.warning(f"Semantic Scholar search failed: {e}")
            return []

    # ── GitHub (public search, no key) ──

    async def _search_github(
        self, query: str, client: httpx.AsyncClient, limit: int = 5
    ) -> List[Dict]:
        """Search GitHub repositories."""
        try:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": limit,
                },
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []
            for repo in data.get("items", []):
                results.append({
                    "title": repo.get("full_name", ""),
                    "url": repo.get("html_url", ""),
                    "snippet": repo.get("description") or "No description",
                    "source": "GitHub",
                    "credibility_score": 0.80,
                    "metadata": {
                        "stars": repo.get("stargazers_count", 0),
                        "language": repo.get("language"),
                        "updated": repo.get("updated_at"),
                    },
                })
            logger.info(f"GitHub: {len(results)} repos found")
            return results

        except Exception as e:
            logger.warning(f"GitHub search failed: {e}")
            return []

    # ── Hacker News (Algolia, free) ──

    async def _search_hackernews(
        self, query: str, client: httpx.AsyncClient, limit: int = 5
    ) -> List[Dict]:
        """Search Hacker News via the Algolia API."""
        try:
            resp = await client.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": query, "hitsPerPage": limit, "tags": "story"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []
            for hit in data.get("hits", []):
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
                results.append({
                    "title": hit.get("title", ""),
                    "url": url,
                    "snippet": f"{hit.get('title','')} — {hit.get('num_comments', 0)} comments, {hit.get('points', 0)} points",
                    "source": "Hacker News",
                    "credibility_score": 0.70,
                })
            logger.info(f"HN: {len(results)} stories found")
            return results

        except Exception as e:
            logger.warning(f"HN search failed: {e}")
            return []

    # ── Reddit (public JSON, no key) ──

    async def _search_reddit(
        self, query: str, client: httpx.AsyncClient, limit: int = 5
    ) -> List[Dict]:
        """Search Reddit via the public JSON API."""
        try:
            resp = await client.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "sort": "relevance", "limit": limit, "t": "year"},
                headers={"User-Agent": "MindX/1.0"},
                timeout=8.0,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                results.append({
                    "title": post.get("title", ""),
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "snippet": (post.get("selftext") or post.get("title", ""))[:300],
                    "source": "Reddit",
                    "credibility_score": 0.55,
                    "metadata": {
                        "subreddit": post.get("subreddit"),
                        "score": post.get("score", 0),
                        "num_comments": post.get("num_comments", 0),
                    },
                })
            logger.info(f"Reddit: {len(results)} posts found")
            return results

        except Exception as e:
            logger.warning(f"Reddit search failed: {e}")
            return []
