#!/usr/bin/env python3
"""
Run MCP Vertex AI Search Server for Artribune
Using the mcp-vertexai-search package
"""

import asyncio
import logging
from pathlib import Path
import yaml

from mcp_vertexai_search.server import (
    Config,
    VertexAISearchAgent,
    run_sse_server,
    run_stdio_server
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/search.sighele.it/web/artribune/mcp/mcp_vertex.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_config():
    """Load and adapt configuration for Artribune"""
    
    # Use the config structure expected by mcp-vertexai-search
    config = Config(
        model_name="gemini-1.5-flash",
        project="controradio-vortex",  # Project ID: 168722272633
        location="global",  # Use global for Vertex AI (Discovery Engine uses 'eu')
        service_account_key_path="/var/www/search.sighele.it/web/artribune/mcp/gcloud_credentials.json",
        data_stores=[
            {
                "data_store_id": "artribune-datastore_1761561578135",
                "location": "eu"  # Discovery Engine location
            }
        ],
        temperature=0.3,
        max_output_tokens=2048,
        top_p=0.95,
        top_k=40
    )
    
    return config

async def main():
    """Main entry point"""
    
    logger.info("""
╔══════════════════════════════════════════════════════════╗
║        🚀 Starting Artribune MCP Vertex AI Server       ║
╠══════════════════════════════════════════════════════════╣
║  Mode: SSE (Server-Sent Events)                         ║
║  Port: 8585                                             ║
║  Datastore: artribune-datastore_1761561578135          ║
║  Documents: 123,545 articoli arte contemporanea        ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    try:
        # Load configuration
        config = get_config()
        
        # Create the agent
        agent = VertexAISearchAgent(config)
        
        # Run SSE server on port 8585
        await run_sse_server(
            agent=agent,
            host="0.0.0.0",  # Listen on all interfaces
            port=8585,
            log_level="INFO"
        )
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())