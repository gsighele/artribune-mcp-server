"""
API Key Authentication for Artribune MCP Server
Format: artr-<24 characters>
"""

import os
import re
from typing import List
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def validate_api_key_format(key: str) -> bool:
    """Validate API key format: artr-<24 characters>"""
    pattern = r'^artr-[a-zA-Z0-9]{24}$'
    return bool(re.match(pattern, key))

def get_valid_api_keys() -> List[str]:
    """Get valid API keys from environment"""
    keys_str = os.getenv("MCP_API_KEYS", "")
    keys = [key.strip() for key in keys_str.split(",") if key.strip()]
    # Validate all keys have correct format
    valid_keys = [key for key in keys if validate_api_key_format(key)]
    return valid_keys

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify API key and return it if valid"""
    
    # Check format first
    if not validate_api_key_format(credentials.credentials):
        raise HTTPException(
            status_code=401, 
            detail="Invalid API key format. Required: artr-<24 characters>"
        )
    
    # Check against valid keys
    valid_keys = get_valid_api_keys()
    if not valid_keys:
        raise HTTPException(
            status_code=500,
            detail="No valid API keys configured"
        )
    
    if credentials.credentials not in valid_keys:
        raise HTTPException(
            status_code=401, 
            detail="API key required or invalid"
        )
    
    return credentials.credentials