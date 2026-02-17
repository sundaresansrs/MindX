"""
Search Service - Web search integration using DuckDuckGo
Provides web search capabilities for retrieving real-time information
"""
from typing import List, Dict, Optional
from duckduckgo_search import DDGS
import logging

logger = logging.getLogger(__name__)


class SearchService:
    """
    Service for performing web searches using DuckDuckGo
    """
    
    def __init__(self):
        self.ddgs = DDGS()
    
    def search_web(self, query: str, max_results: int = 50) -> List[Dict[str, str]]:
        """
        Perform web search and return structured results
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return (default: 50)
        
        Returns:
            List of dictionaries containing title, url, snippet, and source
        """
        try:
            logger.info(f"Searching web for: {query}")
            
            # Perform search
            raw_results = self.ddgs.text(query, max_results=max_results)
            
            # Parse and structure results
            structured_results = self.parse_results(raw_results)
            
            # Deduplicate by URL
            deduplicated = self.deduplicate_sources(structured_results)
            
            logger.info(f"Found {len(deduplicated)} unique results")
            return deduplicated
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return []
    
    def parse_results(self, raw_results: List) -> List[Dict[str, str]]:
        """
        Parse raw search results into structured format
        
        Args:
            raw_results: Raw results from DuckDuckGo
        
        Returns:
            List of structured result dictionaries
        """
        structured = []
        
        for result in raw_results:
            try:
                structured.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                    "source": self.extract_domain(result.get("href", ""))
                })
            except Exception as e:
                logger.warning(f"Failed to parse result: {e}")
                continue
        
        return structured
    
    def extract_domain(self, url: str) -> str:
        """
        Extract domain name from URL
        
        Args:
            url: Full URL string
        
        Returns:
            Domain name (e.g., "wikipedia.org")
        """
        try:
            # Extract domain from URL
            parts = url.split("/")
            if len(parts) >= 3:
                domain = parts[2]
                # Remove www. prefix if present
                domain_str = str(domain)
                if domain_str.startswith("www."):
                    domain_str = domain_str[4:]
                return domain_str

            return url
        except:
            return url
    
    def deduplicate_sources(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Remove duplicate URLs from search results
        
        Args:
            results: List of search results
        
        Returns:
            Deduplicated list of results
        """
        seen_urls = set()
        deduplicated = []
        
        for result in results:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(result)
        
        return deduplicated
    
    def search_multiple_queries(self, queries: List[str], max_results_per_query: int = 20) -> List[Dict[str, str]]:
        """
        Search multiple queries and aggregate results
        
        Args:
            queries: List of search query strings
            max_results_per_query: Max results per individual query
        
        Returns:
            Aggregated and deduplicated results from all queries
        """
        all_results = []
        
        for query in queries:
            results = self.search_web(query, max_results=max_results_per_query)
            all_results.extend(results)
        
        # Deduplicate across all queries
        return self.deduplicate_sources(all_results)
