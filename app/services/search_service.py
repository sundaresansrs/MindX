"""
MindX AI - Enhanced Search Service
Stack: SearXNG (primary) + Jina AI Reader (full content) + DuckDuckGo (fallback) + Wikipedia
"""

import asyncio
import httpx  # type: ignore
import re
import logging
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field

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
                with DDGS() as ddgs:  # type: ignore
                    return list(ddgs.text(  # type: ignore
                        query,
                        region='us-en',      # Force US English results
                        safesearch='off',
                        max_results=max_results,
                    ))

            fn: Callable[[], List[Dict]] = sync_search
            raw: List[Dict] = await asyncio.wait_for(asyncio.to_thread(fn), timeout=15.0)  # type: ignore
            results = []
            for item in raw:
                score, label = get_credibility_score(item.get("href", ""))
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
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
        try:
            response = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
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
        seen_urls = set()
        deduplicated: List[Dict] = []
        for result in results:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(result)
        return deduplicated  # type: ignore

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

    async def search_web(self, query: str, max_results: int = MAX_RESULTS, deep_fetch: bool = True) -> List[Dict]:
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

            # Deduplicate and sort by credibility
            all_results = self.filter_chinese_results(all_results)
            unique = self.deduplicate_sources(all_results)
            unique.sort(key=lambda x: x.get("credibility_score", 0.5), reverse=True)

            # Deep fetch full content for top results via Jina
            if deep_fetch and unique:
                fetch_tasks = [
                    self._fetch_full_content(r["url"], client)
                    for r in unique[:MAX_FULL_PAGES]  # type: ignore
                ]
                full_contents = await asyncio.gather(*fetch_tasks)
                for i, content in enumerate(full_contents):
                    if content:
                        unique[i]["full_content"] = content
                        logger.info(f"Jina fetched full content for: {unique[i]['title'][:50]}")

            return unique[:max_results]  # type: ignore

    async def search_multiple_queries(self, queries: List[str], max_results_per_query: int = 10) -> List[Dict]:
        """
        Search multiple queries in parallel and aggregate results.
        Used by the quality pipeline for expanded query search.
        """
        tasks = [self.search_web(q, max_results=max_results_per_query, deep_fetch=False) for q in queries]
        results_nested = await asyncio.gather(*tasks)

        all_results: List[Dict] = []
        for results in results_nested:
            all_results.extend(results)  # type: ignore

        return self.deduplicate_sources(all_results)  # type: ignore
