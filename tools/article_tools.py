"""
Article Tools for Artribune MCP Server
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi_mcp import MCPTool
from database.connection import db


class ArticleQuery(BaseModel):
    """Query for single article"""
    article_id: int = Field(..., description="ID of the article to retrieve")


class ArticleDetailTool(MCPTool):
    """Tool for getting detailed article information"""
    
    name = "get_article"
    description = "Get detailed information about a specific article by ID, including full content, metadata, and publication details"
    
    async def execute(self, params: ArticleQuery) -> Dict[str, Any]:
        """Get article details"""
        article = await db.get_article(params.article_id)
        
        if not article:
            return {
                "error": "Article not found",
                "article_id": params.article_id
            }
        
        # Extract metadata if available
        metadata = article["extracted_metadata"] or {}
        
        result = {
            "id": article["id"],
            "title": article["title"],
            "url": article["url"],
            "content": article["content_text"],
            "excerpt": article["excerpt"],
            "published_date": str(article["published_date"]) if article["published_date"] else None,
            "created_at": str(article["created_at"]),
        }
        
        # Add metadata fields if present
        if metadata:
            result.update({
                "description": metadata.get("description"),
                "category": metadata.get("category"),
                "entities": metadata.get("entities", {}),
                "images": metadata.get("images", []),
                "internal_links": metadata.get("internal_links", []),
                "external_links": metadata.get("external_links", []),
                "media_files": metadata.get("media_files", []),
                "has_entities": bool(metadata.get("entities")),
                "has_images": bool(metadata.get("images")),
                "extraction_version": metadata.get("extraction_version")
            })
        
        return result


class ArticleContentQuery(BaseModel):
    """Query for article content only"""
    article_id: int = Field(..., description="ID of the article")
    include_metadata: bool = Field(default=False, description="Whether to include extracted metadata")


class ArticleContentTool(MCPTool):
    """Tool for getting article content without full details"""
    
    name = "get_article_content"
    description = "Get the content text of an article, optionally with extracted metadata"
    
    async def execute(self, params: ArticleContentQuery) -> Dict[str, Any]:
        """Get article content"""
        article = await db.get_article(params.article_id)
        
        if not article:
            return {
                "error": "Article not found",
                "article_id": params.article_id
            }
        
        result = {
            "id": article["id"],
            "title": article["title"],
            "content": article["content_text"],
            "word_count": len(article["content_text"].split()) if article["content_text"] else 0
        }
        
        if params.include_metadata and article["extracted_metadata"]:
            result["metadata"] = article["extracted_metadata"]
        
        return result


class ArticleEntitiesQuery(BaseModel):
    """Query for article entities"""
    article_id: int = Field(..., description="ID of the article")


class ArticleEntitiesTool(MCPTool):
    """Tool for getting entities mentioned in an article"""
    
    name = "get_article_entities"
    description = "Get all entities (artists, venues, locations, events) mentioned in an article"
    
    async def execute(self, params: ArticleEntitiesQuery) -> Dict[str, Any]:
        """Get article entities"""
        article = await db.get_article(params.article_id)
        
        if not article:
            return {
                "error": "Article not found",
                "article_id": params.article_id
            }
        
        metadata = article["extracted_metadata"] or {}
        entities = metadata.get("entities", {})
        
        return {
            "article_id": article["id"],
            "title": article["title"],
            "entities": {
                "artists": entities.get("artists", []),
                "venues": entities.get("venues", []),
                "locations": entities.get("locations", []),
                "organizations": entities.get("organizations", []),
                "events": entities.get("events", [])
            },
            "total_entities": sum(len(v) if isinstance(v, list) else 0 for v in entities.values()),
            "verified_entities": metadata.get("verified_entities", [])
        }


# Export tools
article_tools = [
    ArticleDetailTool(),
    ArticleContentTool(),
    ArticleEntitiesTool()
]