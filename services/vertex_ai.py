"""
Vertex AI Discovery Engine Integration
"""

import os
from typing import List, Dict, Any
from google.cloud import discoveryengine

class VertexAISearch:
    """Vertex AI Discovery Engine client for semantic search"""
    
    def __init__(self):
        self.client = discoveryengine.SearchServiceClient()
        self.project = os.getenv('VERTEX_PROJECT')
        self.location = os.getenv('VERTEX_LOCATION')
        self.datastore = os.getenv('VERTEX_DATASTORE')
        
        # Build serving config path
        self.serving_config = (
            f"projects/{self.project}/locations/{self.location}/"
            f"collections/default_collection/dataStores/{self.datastore}/"
            f"servingConfigs/default_config"
        )
    
    async def semantic_search(self, query: str, page_size: int = 10) -> List[Dict[str, Any]]:
        """Perform semantic search on Artribune articles"""
        try:
            # Create search request
            request = discoveryengine.SearchRequest(
                serving_config=self.serving_config,
                query=query,
                page_size=page_size,
                # Enable content extraction
                content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                    snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                        return_snippet=True
                    ),
                    summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                        summary_result_count=3,
                        include_citations=True
                    )
                ),
                # Boost recency
                boost_spec=discoveryengine.SearchRequest.BoostSpec(
                    condition_boost_specs=[
                        discoveryengine.SearchRequest.BoostSpec.ConditionBoostSpec(
                            condition="published_date > '2020-01-01'",
                            boost=1.2
                        )
                    ]
                )
            )
            
            # Execute search
            response = self.client.search(request=request)
            
            # Process results
            results = []
            for result in response.results:
                doc_data = {
                    "id": result.id,
                    "score": result.document.derived_struct_data.get("score", 0),
                    "title": "",
                    "url": "",
                    "snippet": "",
                    "content": ""
                }
                
                # Extract document content
                if hasattr(result.document, 'struct_data') and result.document.struct_data:
                    struct_data = dict(result.document.struct_data)
                    doc_data.update({
                        "title": struct_data.get("title", ""),
                        "url": struct_data.get("url", ""),
                        "description": struct_data.get("description", ""),
                        "published_date": struct_data.get("published_date", "")
                    })
                
                # Extract snippet
                if hasattr(result, 'document') and hasattr(result.document, 'derived_struct_data'):
                    snippet_info = result.document.derived_struct_data.get("snippets", [])
                    if snippet_info:
                        doc_data["snippet"] = snippet_info[0].get("snippet", "")
                
                results.append(doc_data)
            
            return results
            
        except Exception as e:
            print(f"Vertex AI search error: {e}")
            return []
    
    async def get_search_suggestions(self, query: str) -> List[str]:
        """Get search suggestions/completions"""
        try:
            # Note: This would require Completion API setup
            # For now, return basic suggestions
            suggestions = [
                f"{query} artista",
                f"{query} mostra",
                f"{query} galleria",
                f"{query} museo",
                f"{query} Biennale"
            ]
            return suggestions[:3]
        except Exception as e:
            print(f"Suggestions error: {e}")
            return []

# Global Vertex AI instance
vertex_search = VertexAISearch()