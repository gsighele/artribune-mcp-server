"""
PostgreSQL Database Connection for Artribune
"""

import os
import asyncpg
from typing import Optional

class ArtribuneDB:
    """PostgreSQL connection manager for Artribune database"""
    
    def __init__(self):
        self.connection: Optional[asyncpg.Connection] = None
        
    async def connect(self) -> asyncpg.Connection:
        """Create database connection"""
        if self.connection is None or self.connection.is_closed():
            self.connection = await asyncpg.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 5432)),
                user=os.getenv('POSTGRES_USER'),
                password=os.getenv('POSTGRES_PASSWORD'),
                database=os.getenv('POSTGRES_DB')
            )
        return self.connection
    
    async def disconnect(self):
        """Close database connection"""
        if self.connection and not self.connection.is_closed():
            await self.connection.close()
            
    async def get_article(self, article_id: int):
        """Get single article by ID"""
        conn = await self.connect()
        query = """
            SELECT id, title, url, content_text, extracted_metadata, 
                   published_date, created_at, excerpt
            FROM articles 
            WHERE id = $1
        """
        return await conn.fetchrow(query, article_id)
    
    async def search_articles(self, query: str, limit: int = 10):
        """Search articles by text"""
        conn = await self.connect()
        search_query = """
            SELECT id, title, url, content_text, extracted_metadata, 
                   published_date, created_at, excerpt
            FROM articles 
            WHERE content_text ILIKE $1 
               OR title ILIKE $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        search_term = f"%{query}%"
        return await conn.fetch(search_query, search_term, limit)
    
    async def get_recent_articles(self, limit: int = 20):
        """Get most recent articles"""
        conn = await self.connect()
        query = """
            SELECT id, title, url, content_text, extracted_metadata, 
                   published_date, created_at, excerpt
            FROM articles 
            WHERE content_text IS NOT NULL
            ORDER BY created_at DESC
            LIMIT $1
        """
        return await conn.fetch(query, limit)

# Global database instance
db = ArtribuneDB()