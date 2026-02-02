#!/usr/bin/env python3
"""
MCP Vertex AI Search Server for Artribune
Uses mcp-vertexai-search package with custom configuration
"""

import os
import sys
import yaml
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

# Add package path
sys.path.insert(0, str(Path(__file__).parent))

# Import MCP Vertex AI Search components
from mcp.server import Server
from mcp import Resource, Tool
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import StreamingResponse
import uvicorn

# Import Google Cloud components
from google.cloud import discoveryengine_v1beta
from google.oauth2 import service_account
from google.api_core.client_options import ClientOptions
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

# Load configuration
config_path = Path(__file__).parent / "mcp_vertex_config.yaml"
with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Setup logging
logging.basicConfig(
    level=getattr(logging, config['logging']['level']),
    format=config['logging']['format'],
    handlers=[
        logging.FileHandler(config['logging']['file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ArtribuneMCPServer:
    """MCP Server for Artribune Vertex AI Search"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.server = Server(config['server']['name'])
        self.client = None
        self.model = None
        self._setup_clients()
        self._register_tools()
        
    def _setup_clients(self):
        """Setup Google Cloud clients"""
        try:
            # Load credentials
            creds_path = self.config['vertexai']['service_account_path']
            if os.path.exists(creds_path):
                credentials = service_account.Credentials.from_service_account_file(creds_path)
                logger.info(f"✅ Credentials loaded from {creds_path}")
            else:
                logger.error(f"❌ Credentials file not found: {creds_path}")
                return
            
            # Initialize Vertex AI
            vertexai.init(
                project=self.config['vertexai']['project'],
                location=self.config['vertexai']['location'],
                credentials=credentials
            )
            
            # Setup Discovery Engine client
            client_options = ClientOptions(
                api_endpoint=f"{self.config['vertexai']['location']}-discoveryengine.googleapis.com"
            )
            
            self.client = discoveryengine_v1beta.SearchServiceClient(
                credentials=credentials,
                client_options=client_options
            )
            
            # Setup Gemini model for grounding
            self.model = GenerativeModel(
                self.config['model']['name'],
                generation_config=GenerationConfig(
                    temperature=self.config['model']['temperature'],
                    max_output_tokens=self.config['model']['max_output_tokens'],
                    top_p=self.config['model']['top_p'],
                    top_k=self.config['model']['top_k']
                )
            )
            
            logger.info("✅ Google Cloud clients initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup clients: {e}")
            
    def _register_tools(self):
        """Register MCP tools"""
        
        @self.server.tool()
        async def search_artribune(query: str, limit: int = 10) -> Dict[str, Any]:
            """
            Search Artribune articles using Vertex AI Discovery Engine
            
            Args:
                query: Search query
                limit: Maximum number of results
                
            Returns:
                Search results with articles and metadata
            """
            try:
                datastore = self.config['data_stores'][0]  # Use default datastore
                serving_config = f"projects/{datastore['project']}/locations/{datastore['location']}/collections/default_collection/dataStores/{datastore['id']}/servingConfigs/default_search"
                
                request = discoveryengine_v1beta.SearchRequest(
                    serving_config=serving_config,
                    query=query,
                    page_size=limit,
                    query_expansion_spec=discoveryengine_v1beta.SearchRequest.QueryExpansionSpec(
                        condition=discoveryengine_v1beta.SearchRequest.QueryExpansionSpec.Condition.AUTO
                    ),
                    spell_correction_spec=discoveryengine_v1beta.SearchRequest.SpellCorrectionSpec(
                        mode=discoveryengine_v1beta.SearchRequest.SpellCorrectionSpec.Mode.AUTO
                    )
                )
                
                response = self.client.search(request=request)
                
                results = []
                for result in response.results:
                    if hasattr(result, 'document') and result.document:
                        doc = result.document
                        doc_data = {
                            "id": doc.id if hasattr(doc, 'id') else None,
                            "score": result.relevance_score if hasattr(result, 'relevance_score') else None
                        }
                        
                        if hasattr(doc, 'struct_data') and doc.struct_data:
                            data = dict(doc.struct_data)
                            doc_data.update({
                                "title": data.get("title", ""),
                                "url": data.get("url", ""),
                                "published_date": data.get("published_date", ""),
                                "content": data.get("content", "")[:500],
                                "ner_entities": data.get("ner_entities", {})
                            })
                        
                        results.append(doc_data)
                
                return {
                    "query": query,
                    "total_results": len(results),
                    "total_documents": response.total_size if hasattr(response, 'total_size') else None,
                    "results": results
                }
                
            except Exception as e:
                logger.error(f"Search error: {e}")
                return {"error": str(e)}
        
        @self.server.tool()
        async def search_with_grounding(query: str, context: str = None) -> Dict[str, Any]:
            """
            Search and generate grounded response using Gemini
            
            Args:
                query: User question
                context: Additional context for grounding
                
            Returns:
                Grounded response with citations
            """
            try:
                # First search for relevant documents
                search_results = await search_artribune(query, limit=5)
                
                if not search_results.get('results'):
                    return {"error": "No results found"}
                
                # Build context from search results
                grounding_context = "\n\n".join([
                    f"Article: {r.get('title', '')}\nURL: {r.get('url', '')}\nContent: {r.get('content', '')}"
                    for r in search_results['results']
                ])
                
                # Generate grounded response
                prompt = f"""Based on the following articles from Artribune, answer this question: {query}

Context from Artribune articles:
{grounding_context}

{f'Additional context: {context}' if context else ''}

Please provide a comprehensive answer with citations to the relevant articles."""
                
                response = self.model.generate_content(prompt)
                
                return {
                    "query": query,
                    "response": response.text,
                    "sources": [
                        {"title": r.get('title'), "url": r.get('url')}
                        for r in search_results['results']
                    ],
                    "total_sources": search_results.get('total_results', 0)
                }
                
            except Exception as e:
                logger.error(f"Grounding error: {e}")
                return {"error": str(e)}
        
        @self.server.tool()
        async def get_article_details(article_id: str) -> Dict[str, Any]:
            """
            Get detailed information about a specific article
            
            Args:
                article_id: Article ID from search results
                
            Returns:
                Detailed article information
            """
            try:
                # For now, search by ID (could be optimized with direct lookup)
                query = f"id:{article_id}"
                results = await search_artribune(query, limit=1)
                
                if results.get('results'):
                    return results['results'][0]
                else:
                    return {"error": "Article not found"}
                    
            except Exception as e:
                logger.error(f"Article lookup error: {e}")
                return {"error": str(e)}
        
        logger.info(f"✅ Registered {len(self.server._tools)} tools")
    
    async def handle_sse(self, request):
        """Handle SSE requests"""
        async def generate():
            transport = SseServerTransport()
            async for message in transport.handle(request):
                yield message
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    def run(self):
        """Run the MCP server"""
        # Create Starlette app
        app = Starlette(
            routes=[
                Route("/", self.handle_sse, methods=["GET", "POST"]),
                Route("/health", lambda r: {"status": "healthy", "service": "Artribune MCP Vertex"})
            ]
        )
        
        # Add CORS middleware
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config['security']['allowed_origins'],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        logger.info(f"""
╔══════════════════════════════════════════════════════════╗
║         🚀 Artribune MCP Vertex AI Search Server        ║
╠══════════════════════════════════════════════════════════╣
║  Host: {self.config['server_settings']['host']:45} ║
║  Port: {self.config['server_settings']['port']:45} ║
║  Datastore: artribune-datastore_1761561578135           ║
║  Documents: 123,545 articoli arte contemporanea         ║
║  Transport: SSE (Server-Sent Events)                    ║
╚══════════════════════════════════════════════════════════╝
        """)
        
        # Run server
        uvicorn.run(
            app,
            host=self.config['server_settings']['host'],
            port=self.config['server_settings']['port'],
            log_level="info"
        )

if __name__ == "__main__":
    server = ArtribuneMCPServer(config)
    server.run()