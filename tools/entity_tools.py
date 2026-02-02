"""
Entity Tools for Artribune MCP Server
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi_mcp import MCPTool
from database.connection import db


class EntitySearchQuery(BaseModel):
    """Query for entity search"""
    entity_name: str = Field(..., description="Name of the entity to search for")
    entity_type: Optional[str] = Field(default=None, description="Type of entity: artist, venue, location, organization, event")
    limit: int = Field(default=10, description="Maximum number of articles to return")


class EntitySearchTool(MCPTool):
    """Tool for finding articles that mention specific entities"""
    
    name = "search_by_entity"
    description = "Find articles that mention a specific artist, venue, location, organization, or event"
    
    async def execute(self, params: EntitySearchQuery) -> Dict[str, Any]:
        """Search articles by entity"""
        # Build search query based on entity type
        if params.entity_type:
            search_query = f'"{params.entity_name}" {params.entity_type}'
        else:
            search_query = f'"{params.entity_name}"'
        
        # Search in database
        articles = await db.search_articles(search_query, params.limit)
        
        # Filter articles that actually contain the entity in metadata
        filtered_articles = []
        for article in articles:
            metadata = article["extracted_metadata"] or {}
            entities = metadata.get("entities", {})
            
            # Check if entity exists in any category
            entity_found = False
            entity_categories = []
            
            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if params.entity_name.lower() in entity.lower():
                            entity_found = True
                            entity_categories.append(category)
                            break
            
            if entity_found or params.entity_name.lower() in article["title"].lower():
                filtered_articles.append({
                    "id": article["id"],
                    "title": article["title"],
                    "url": article["url"],
                    "content_preview": article["content_text"][:300] if article["content_text"] else "",
                    "published_date": str(article["published_date"]) if article["published_date"] else None,
                    "entity_categories": entity_categories,
                    "has_metadata": bool(metadata)
                })
        
        return {
            "entity_name": params.entity_name,
            "entity_type": params.entity_type,
            "total_results": len(filtered_articles),
            "results": filtered_articles
        }


class ArtistQuery(BaseModel):
    """Query for artist information"""
    artist_name: str = Field(..., description="Name of the artist")
    limit: int = Field(default=15, description="Maximum number of articles to return")


class ArtistProfileTool(MCPTool):
    """Tool for getting comprehensive information about an artist"""
    
    name = "get_artist_profile"
    description = "Get comprehensive information about an artist including exhibitions, mentions, and related articles"
    
    async def execute(self, params: ArtistQuery) -> Dict[str, Any]:
        """Get artist profile"""
        # Search for articles mentioning the artist
        articles = await db.search_articles(params.artist_name, params.limit)
        
        artist_articles = []
        exhibitions = []
        venues = set()
        collaborators = set()
        events = set()
        
        for article in articles:
            # Check if artist is mentioned in title or content
            if (params.artist_name.lower() in article["title"].lower() or 
                (article["content_text"] and params.artist_name.lower() in article["content_text"].lower())):
                
                metadata = article["extracted_metadata"] or {}
                entities = metadata.get("entities", {})
                
                artist_articles.append({
                    "id": article["id"],
                    "title": article["title"],
                    "url": article["url"],
                    "published_date": str(article["published_date"]) if article["published_date"] else None,
                    "content_preview": article["content_text"][:200] if article["content_text"] else ""
                })
                
                # Extract exhibition and venue information
                if "events" in entities:
                    events.update(entities["events"])
                if "venues" in entities:
                    venues.update(entities["venues"])
                if "artists" in entities:
                    # Find other artists mentioned (potential collaborators)
                    for artist in entities["artists"]:
                        if artist.lower() != params.artist_name.lower():
                            collaborators.add(artist)
        
        return {
            "artist_name": params.artist_name,
            "total_articles": len(artist_articles),
            "articles": artist_articles[:10],  # Limit to first 10 for response size
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


class VenueQuery(BaseModel):
    """Query for venue information"""
    venue_name: str = Field(..., description="Name of the venue (museum, gallery, etc.)")
    limit: int = Field(default=15, description="Maximum number of articles to return")


class VenueProfileTool(MCPTool):
    """Tool for getting information about venues, museums, and galleries"""
    
    name = "get_venue_profile"
    description = "Get information about a venue, museum, or gallery including exhibitions and events"
    
    async def execute(self, params: VenueQuery) -> Dict[str, Any]:
        """Get venue profile"""
        # Search for articles mentioning the venue
        articles = await db.search_articles(params.venue_name, params.limit)
        
        venue_articles = []
        artists = set()
        events = set()
        
        for article in articles:
            if (params.venue_name.lower() in article["title"].lower() or 
                (article["content_text"] and params.venue_name.lower() in article["content_text"].lower())):
                
                metadata = article["extracted_metadata"] or {}
                entities = metadata.get("entities", {})
                
                venue_articles.append({
                    "id": article["id"],
                    "title": article["title"],
                    "url": article["url"],
                    "published_date": str(article["published_date"]) if article["published_date"] else None,
                    "content_preview": article["content_text"][:200] if article["content_text"] else ""
                })
                
                # Extract related artists and events
                if "artists" in entities:
                    artists.update(entities["artists"])
                if "events" in entities:
                    events.update(entities["events"])
        
        return {
            "venue_name": params.venue_name,
            "total_articles": len(venue_articles),
            "articles": venue_articles[:10],
            "featured_artists": list(artists)[:15],
            "events_exhibitions": list(events)[:10],
            "summary": {
                "total_articles_found": len(venue_articles),
                "unique_artists": len(artists),
                "unique_events": len(events)
            }
        }


# Export tools
entity_tools = [
    EntitySearchTool(),
    ArtistProfileTool(),
    VenueProfileTool()
]