"""
Artribune MCP Server
FastAPI + MCP integration for arte contemporanea queries
"""

import os
import json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our modules
from auth.api_key import verify_api_key
from database.connection import db
from services.vertex_ai import vertex_search
from tools.tri_query_tools import ArtribuneTriQueryTool, TriQueryParams

# Helper function for metadata parsing
def parse_metadata(metadata: Any) -> Dict[str, Any]:
    """Parse metadata that could be dict or JSON string"""
    if not metadata:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}

# Create FastAPI app
app = FastAPI(
    title="Artribune MCP Server",
    description="Model Context Protocol server for Artribune arte contemporanea database",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create MCP server 
mcp = FastApiMCP(app)

# Health check endpoint (no auth required)
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "artribune-mcp",
        "version": "1.0.0"
    }

# MCP Tools for Artribune

@app.get("/article/{article_id}")
async def get_article(
    article_id: int,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Get single article by ID"""
    article = await db.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return {
        "id": article["id"],
        "title": article["title"],
        "url": article["url"],
        "content_preview": article["content_text"][:500] if article["content_text"] else "",
        "published_date": str(article["published_date"]) if article["published_date"] else None,
        "metadata": parse_metadata(article["extracted_metadata"])
    }

@app.get("/search/database")
async def search_database(
    query: str,
    limit: int = 10,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Search articles in PostgreSQL database"""
    articles = await db.search_articles(query, limit)
    
    results = []
    for article in articles:
        results.append({
            "id": article["id"],
            "title": article["title"],
            "url": article["url"],
            "content_preview": article["content_text"][:300] if article["content_text"] else "",
            "published_date": str(article["published_date"]) if article["published_date"] else None
        })
    
    return {
        "query": query,
        "total_results": len(results),
        "results": results,
        "source": "postgresql"
    }

@app.get("/search/semantic")
async def search_semantic(
    query: str,
    limit: int = 10,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Semantic search using Vertex AI Discovery Engine"""
    results = await vertex_search.semantic_search(query, limit)
    
    return {
        "query": query,
        "total_results": len(results),
        "results": results,
        "source": "vertex_ai"
    }

@app.get("/search/hybrid")
async def search_hybrid(
    query: str,
    limit: int = 10,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Hybrid search: combine PostgreSQL + Vertex AI results"""
    
    # Get results from both sources
    db_results = await db.search_articles(query, limit // 2)
    vertex_results = await vertex_search.semantic_search(query, limit // 2)
    
    # Format database results
    db_formatted = []
    for article in db_results:
        db_formatted.append({
            "id": article["id"],
            "title": article["title"],
            "url": article["url"],
            "content_preview": article["content_text"][:300] if article["content_text"] else "",
            "published_date": str(article["published_date"]) if article["published_date"] else None,
            "source": "database",
            "score": 1.0  # Default score for DB results
        })
    
    # Combine and sort by relevance
    all_results = db_formatted + vertex_results
    
    return {
        "query": query,
        "total_results": len(all_results),
        "results": all_results,
        "sources": ["postgresql", "vertex_ai"]
    }

@app.get("/recent")
async def get_recent_articles(
    limit: int = 20,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Get most recent articles"""
    articles = await db.get_recent_articles(limit)
    
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

# MCP-specific endpoints with tags for organization
@app.post("/mcp/search_articles", tags=["search"])
async def mcp_search_articles(
    query: str,
    limit: int = 10,
    search_type: str = "database",
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Search for articles in the Artribune database"""
    if search_type == "semantic":
        results = await vertex_search.semantic_search(query, limit)
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
            "query": query,
            "search_type": "semantic",
            "total_results": len(formatted_results),
            "results": formatted_results
        }
    else:
        articles = await db.search_articles(query, limit)
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
            "query": query,
            "search_type": "database",
            "total_results": len(results),
            "results": results
        }

@app.post("/mcp/get_artist_profile", tags=["entities"])
async def mcp_get_artist_profile(
    artist_name: str,
    limit: int = 15,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Get comprehensive information about an artist"""
    articles = await db.search_articles(artist_name, limit)
    
    artist_articles = []
    exhibitions = []
    venues = set()
    collaborators = set()
    events = set()
    
    for article in articles:
        if (artist_name.lower() in article["title"].lower() or 
            (article["content_text"] and artist_name.lower() in article["content_text"].lower())):
            
            metadata = parse_metadata(article["extracted_metadata"])
            entities = metadata.get("entities", {})
            
            artist_articles.append({
                "id": article["id"],
                "title": article["title"],
                "url": article["url"],
                "published_date": str(article["published_date"]) if article["published_date"] else None,
                "content_preview": article["content_text"][:200] if article["content_text"] else ""
            })
            
            if "events" in entities:
                events.update(entities["events"])
            if "venues" in entities:
                venues.update(entities["venues"])
            if "artists" in entities:
                for artist in entities["artists"]:
                    if artist.lower() != artist_name.lower():
                        collaborators.add(artist)
    
    return {
        "artist_name": artist_name,
        "total_articles": len(artist_articles),
        "articles": artist_articles[:10],
        "exhibitions_events": list(events)[:10],
        "venues": list(venues)[:10],
        "collaborators": list(collaborators)[:10],
        "summary": {
            "total_articles_found": len(artist_articles),
            "unique_venues": len(venues),
            "unique_events": len(events),
            "potential_collaborators": len(collaborators)
        }
    }

@app.post("/mcp/tri_query", tags=["tri-query"])
async def mcp_tri_query(
    params: TriQueryParams,
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Tri-Query: Combina Semantic + Graph + Temporal con chunking intelligente da 2000 caratteri"""
    
    # Inizializza tool tri-query
    tri_tool = ArtribuneTriQueryTool()
    
    try:
        # Esegui tri-query
        result = await tri_tool.execute(params)
        
        return {
            "tri_query_result": result,
            "mcp_version": "1.0.0",
            "chunking_enabled": True,
            "default_chunk_size": 2000,
            "smart_chunking": params.smart_chunking,
            "systems_available": ["semantic", "graph", "temporal"],
            "systems_used": result.get("systems_used", [])
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tri-query failed: {str(e)}")

# Mount MCP with HTTP transport
mcp.mount_http()

# Startup event
@app.on_event("startup")
async def startup():
    """Initialize database connection"""
    try:
        await db.connect()
        print("✅ Database connected successfully")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

# Shutdown event  
@app.on_event("shutdown")
async def shutdown():
    """Close database connection"""
    await db.disconnect()
    print("🔌 Database disconnected")

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", 1789))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )