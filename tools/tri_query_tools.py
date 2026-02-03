"""
Tri-Query Tools for Artribune MCP Server
Combina Semantic (Gemini) + Graph (Neo4j) + Relational (PostgreSQL)
con chunking intelligente per gestire context window limits
"""

import os
import json
import psycopg2
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi_mcp import MCPTool
from database.connection import db
import google.generativeai as genai
from neo4j import GraphDatabase
from datetime import datetime, timedelta

# Setup Gemini
genai.configure(api_key=os.getenv('GOOGLE_AI_API_KEY'))

class TriQueryParams(BaseModel):
    """Parametri per tri-query con controllo chunking"""
    query: str = Field(..., description="Domanda in linguaggio naturale")
    
    # Sistema da utilizzare
    use_semantic: bool = Field(default=True, description="Attiva analisi semantica Gemini")
    use_graph: bool = Field(default=False, description="Attiva ricerca network Neo4j")
    use_dates: bool = Field(default=False, description="Attiva analisi temporali PostgreSQL")
    
    # Controlli chunking e limiti
    chunk_size: int = Field(default=2000, description="Dimensione chunk testo (caratteri) - 2000 per arte, 1000 per summary, 4000 per analisi dettagliate")
    max_results: int = Field(default=10, description="Massimo risultati per sistema")
    date_range: str = Field(default="all", description="Range temporale: 'all', 'last_year', '2020-2024', etc")
    smart_chunking: bool = Field(default=True, description="Chunking intelligente che preserva entità artistiche")
    
    # Output format
    output_format: str = Field(default="summary", description="Formato output: 'summary', 'detailed', 'chunks'")


class TriQueryResult(BaseModel):
    """Risultato tri-query strutturato"""
    query: str
    systems_used: List[str]
    semantic_analysis: Optional[Dict] = None
    graph_data: Optional[Dict] = None
    temporal_data: Optional[Dict] = None
    combined_summary: str
    context_usage: Dict[str, int]  # Token/char count per sistema


class ArtribuneTriQueryTool(MCPTool):
    """Tool tri-sistema con chunking intelligente"""
    
    name = "tri_query_search"
    description = "Ricerca ibrida che combina analisi semantica, network graph e dati temporali con controllo chunking"
    
    def __init__(self):
        super().__init__()
        # Setup connessioni
        self.neo4j_driver = None
        self.pg_conn = None
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
    def _setup_connections(self):
        """Setup connessioni database"""
        if not self.neo4j_driver:
            self.neo4j_driver = GraphDatabase.driver(
                'bolt://localhost:7687', 
                auth=('neo4j', 'password123')
            )
        
        if not self.pg_conn:
            self.pg_conn = psycopg2.connect(
                host='localhost',
                database='scraper_artribune_com',
                user='castos',
                password='CastosSecure2025!'
            )
    
    def _chunk_text(self, text: str, chunk_size: int, smart_chunking: bool = True) -> str:
        """Chunking intelligente per contenuto artistico"""
        if len(text) <= chunk_size:
            return text
        
        if not smart_chunking:
            # Chunking semplice
            first_part = int(chunk_size * 0.6)
            last_part = int(chunk_size * 0.4)
            return text[:first_part] + "..." + text[-last_part:]
        
        # Smart chunking per arte contemporanea
        # Preserva: titoli, nomi artisti, date, luoghi, tecniche
        art_keywords = [
            'mostra', 'exhibition', 'galleria', 'museo', 'biennale', 'triennale',
            'artista', 'artist', 'curatore', 'curator', 'critico',
            'palazzo', 'fondazione', 'centro', 'spazio',
            'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
            'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre',
            '2020', '2021', '2022', '2023', '2024', '2025'
        ]
        
        # Trova frasi con parole chiave artistiche
        sentences = text.split('. ')
        important_sentences = []
        regular_sentences = []
        
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in art_keywords):
                important_sentences.append(sentence)
            else:
                regular_sentences.append(sentence)
        
        # Costruisci chunk: sempre importanti + riempi con regolari
        important_text = '. '.join(important_sentences)
        
        if len(important_text) >= chunk_size:
            # Troppo contenuto importante, chunka quello
            return important_text[:chunk_size - 3] + "..."
        
        # Aggiungi contenuto regolare fino al limite
        remaining_space = chunk_size - len(important_text) - 10  # buffer
        regular_text = '. '.join(regular_sentences)
        
        if len(regular_text) <= remaining_space:
            return important_text + '. ' + regular_text
        else:
            return important_text + '. ' + regular_text[:remaining_space] + "..."
    
    def _semantic_analysis(self, query: str, chunk_size: int) -> Dict[str, Any]:
        """Analisi semantica Gemini con input minimale"""
        prompt = f"""
        Analizza brevemente questa domanda di arte contemporanea:
        "{query}"
        
        Rispondi in max 200 caratteri con:
        ENTITÀ: [artisti/luoghi principali]
        TIPO: [ricerca|network|timeline]
        FOCUS: [termine principale]
        """
        
        try:
            response = self.model.generate_content(prompt)
            analysis_text = self._chunk_text(response.text, chunk_size, smart_chunking=True)
            
            # Parse semplice
            entities = []
            query_type = "ricerca"
            focus = query.split()[0] if query else ""
            
            return {
                "entities": entities,
                "query_type": query_type,
                "focus": focus,
                "analysis": analysis_text,
                "tokens_used": len(prompt) + len(analysis_text)
            }
        except Exception as e:
            return {"error": str(e), "tokens_used": 0}
    
    def _graph_analysis(self, query: str, max_results: int, chunk_size: int) -> Dict[str, Any]:
        """Analisi network Neo4j con risultati limitati"""
        self._setup_connections()
        
        # Query semplificata per top collaborazioni
        cypher_query = f"""
        MATCH (a:Artist)-[:COLLABORATES_WITH]-(b:Artist)
        WHERE a.mentions > 100 AND b.mentions > 100
        RETURN a.name as artist1, b.name as artist2, 
               a.mentions as mentions1, b.mentions as mentions2
        ORDER BY (a.mentions + b.mentions) DESC
        LIMIT {max_results}
        """
        
        results = []
        with self.neo4j_driver.session() as session:
            try:
                result = session.run(cypher_query)
                for record in result:
                    # Chunking per singolo risultato
                    artist_info = f"{record['artist1']} ↔ {record['artist2']} ({record['mentions1']}+{record['mentions2']} menzioni)"
                    chunked_info = self._chunk_text(artist_info, chunk_size // max_results, smart_chunking=True)
                    results.append(chunked_info)
            except Exception as e:
                return {"error": str(e), "char_used": 0}
        
        return {
            "collaborations": results,
            "total_found": len(results),
            "query_executed": cypher_query[:100] + "...",
            "char_used": sum(len(r) for r in results)
        }
    
    def _temporal_analysis(self, query: str, date_range: str, max_results: int, chunk_size: int) -> Dict[str, Any]:
        """Analisi temporale PostgreSQL con aggregazioni"""
        self._setup_connections()
        
        # Determina range temporale
        if date_range == "last_year":
            date_filter = f"published_date >= '{(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')}'"
        elif date_range == "2020-2024":
            date_filter = "published_date >= '2020-01-01' AND published_date < '2025-01-01'"
        else:
            date_filter = "published_date IS NOT NULL"
        
        # Query temporale aggregata
        temporal_query = f"""
        SELECT 
            EXTRACT(YEAR FROM published_date) as anno,
            COUNT(*) as articoli,
            COUNT(CASE WHEN is_event = true THEN 1 END) as eventi
        FROM mcp_articles 
        WHERE {date_filter}
        GROUP BY EXTRACT(YEAR FROM published_date)
        ORDER BY anno DESC
        LIMIT {max_results}
        """
        
        results = []
        with self.pg_conn.cursor() as cur:
            try:
                cur.execute(temporal_query)
                for row in cur.fetchall():
                    year, articles, events = row
                    year_info = f"{int(year)}: {articles} articoli, {events} eventi"
                    results.append(year_info)
            except Exception as e:
                return {"error": str(e), "char_used": 0}
        
        return {
            "timeline": results,
            "date_range": date_range,
            "total_years": len(results),
            "char_used": sum(len(r) for r in results)
        }
    
    async def execute(self, params: TriQueryParams) -> Dict[str, Any]:
        """Esecuzione tri-query con chunking"""
        
        systems_used = []
        context_usage = {}
        
        # STEP 1: Semantic Analysis (se richiesto)
        semantic_result = None
        if params.use_semantic:
            semantic_result = self._semantic_analysis(params.query, params.chunk_size)
            systems_used.append("semantic")
            context_usage["semantic"] = semantic_result.get("tokens_used", 0)
        
        # STEP 2: Graph Analysis (se richiesto)
        graph_result = None
        if params.use_graph:
            graph_result = self._graph_analysis(params.query, params.max_results, params.chunk_size)
            systems_used.append("graph")
            context_usage["graph"] = graph_result.get("char_used", 0)
        
        # STEP 3: Temporal Analysis (se richiesto)
        temporal_result = None
        if params.use_dates:
            temporal_result = self._temporal_analysis(params.query, params.date_range, params.max_results, params.chunk_size)
            systems_used.append("temporal")
            context_usage["temporal"] = temporal_result.get("char_used", 0)
        
        # STEP 4: Combined Summary (chunked)
        summary_parts = []
        
        if semantic_result:
            summary_parts.append(f"🧠 Semantico: {semantic_result.get('analysis', 'N/A')[:100]}")
        
        if graph_result and graph_result.get('collaborations'):
            summary_parts.append(f"🕸️ Network: {len(graph_result['collaborations'])} collaborazioni trovate")
        
        if temporal_result and temporal_result.get('timeline'):
            summary_parts.append(f"📊 Temporale: {len(temporal_result['timeline'])} anni analizzati")
        
        combined_summary = " | ".join(summary_parts) if summary_parts else "Nessun sistema attivato"
        
        # Return con chunk control
        return {
            "query": params.query,
            "systems_used": systems_used,
            "semantic_analysis": semantic_result,
            "graph_data": graph_result,
            "temporal_data": temporal_result,
            "combined_summary": combined_summary,
            "context_usage": context_usage,
            "chunking_applied": {
                "chunk_size": params.chunk_size,
                "max_results": params.max_results,
                "total_chars": sum(context_usage.values())
            }
        }
    
    def __del__(self):
        """Cleanup connessioni"""
        if self.neo4j_driver:
            self.neo4j_driver.close()
        if self.pg_conn:
            self.pg_conn.close()