"""
Search Tools for Artribune MCP Server
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi_mcp import MCPTool
from database.connection import db
from services.vertex_ai import vertex_search


class SearchQuery(BaseModel):
    """Search query parameters"""
    query: str = Field(..., description="Search query for articles")
    limit: int = Field(default=10, description="Maximum number of results to return")
    search_type: str = Field(default="database", description="Type of search: 'database', 'semantic', or 'hybrid'")


class SearchResult(BaseModel):
    """Search result structure"""
    id: int
    title: str
    url: str
    content_preview: str
    published_date: Optional[str]
    score: Optional[float] = None
    source: str


class ArticleSearchTool(MCPTool):
    """Tool for searching articles about contemporary art"""
    
    name = "search_articles"
    description = "Search for articles in the Artribune database about contemporary art, artists, exhibitions, and art events"
    
    async def execute(self, params: SearchQuery) -> Dict[str, Any]:
        """Execute article search"""
        
        if params.search_type == "semantic":
            # Use Vertex AI semantic search
            results = await vertex_search.semantic_search(params.query, params.limit)
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.get("id", ""),
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content_preview": result.get("snippet", "")[:300],
                    "published_date": result.get("published_date"),
                    "score": result.get("score"),
                    "source": "vertex_ai"
                })
            
            return {
                "query": params.query,
                "search_type": "semantic",
                "total_results": len(formatted_results),
                "results": formatted_results
            }
            
        elif params.search_type == "hybrid":
            # Combine database and semantic search
            db_results = await db.search_articles(params.query, params.limit // 2)
            vertex_results = await vertex_search.semantic_search(params.query, params.limit // 2)
            
            # Format database results
            db_formatted = []
            for article in db_results:
                db_formatted.append({
                    "id": article["id"],
                    "title": article["title"],
                    "url": article["url"],
                    "content_preview": article["content_text"][:300] if article["content_text"] else "",
                    "published_date": str(article["published_date"]) if article["published_date"] else None,
                    "score": 1.0,
                    "source": "database"
                })
            
            # Format vertex results
            vertex_formatted = []
            for result in vertex_results:
                vertex_formatted.append({
                    "id": result.get("id", ""),
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content_preview": result.get("snippet", "")[:300],
                    "published_date": result.get("published_date"),
                    "score": result.get("score", 0),
                    "source": "vertex_ai"
                })
            
            all_results = db_formatted + vertex_formatted
            
            return {
                "query": params.query,
                "search_type": "hybrid",
                "total_results": len(all_results),
                "results": all_results,
                "sources": ["database", "vertex_ai"]
            }
        
        else:
            # Default database search
            articles = await db.search_articles(params.query, params.limit)
            
            results = []
            for article in articles:
                results.append({
                    "id": article["id"],
                    "title": article["title"],
                    "url": article["url"],
                    "content_preview": article["content_text"][:300] if article["content_text"] else "",
                    "published_date": str(article["published_date"]) if article["published_date"] else None,
                    "score": 1.0,
                    "source": "database"
                })
            
            return {
                "query": params.query,
                "search_type": "database",
                "total_results": len(results),
                "results": results
            }


class RecentArticlesQuery(BaseModel):
    """Query for recent articles"""
    limit: int = Field(default=20, description="Number of recent articles to retrieve")


class RecentArticlesTool(MCPTool):
    """Tool for getting recent articles"""
    
    name = "get_recent_articles"
    description = "Get the most recently published articles from Artribune"
    
    async def execute(self, params: RecentArticlesQuery) -> Dict[str, Any]:
        """Get recent articles"""
        articles = await db.get_recent_articles(params.limit)
        
        results = []
        for article in articles:
            results.append({
                "id": article["id"],
                "title": article["title"],
                "url": article["url"],
                "content_preview": article["content_text"][:200] if article["content_text"] else "",
                "published_date": str(article["published_date"]) if article["published_date"] else None,
                "created_at": str(article["created_at"])
            })
        
        return {
            "total_results": len(results),
            "results": results
        }


# Export tools
search_tools = [
    ArticleSearchTool(),
    RecentArticlesTool()
]