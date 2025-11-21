import os
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, field_validator
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LogoRequest(BaseModel):
    url: HttpUrl

class LogoResponse(BaseModel):
    success: bool
    logo_url: Optional[str] = None
    fallback_used: bool = False
    message: Optional[str] = None


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.post("/api/extract-logo", response_model=LogoResponse)
def extract_logo(payload: LogoRequest):
    """Try to extract a website logo URL from the given homepage.
    Strategy:
    - Look for <link rel="icon"|"shortcut icon"|"apple-touch-icon"|"mask-icon"> tags
    - Look for <meta property="og:image"> or <meta name="twitter:image">
    - Look for <img> tags with common logo class/id names
    Returns an absolute URL if found.
    """
    try:
        resp = requests.get(str(payload.url), timeout=10)
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Site returned {resp.status_code}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fetch error: {e}")

    soup = BeautifulSoup(resp.text, 'html.parser')

    base = str(payload.url).rstrip('/')

    def absolutize(src: str) -> str:
        if src.startswith('http://') or src.startswith('https://'):
            return src
        if src.startswith('//'):
            scheme = 'https:' if base.startswith('https') else 'http:'
            return scheme + src
        if src.startswith('/'):
            # root-relative
            from urllib.parse import urlparse
            p = urlparse(base)
            return f"{p.scheme}://{p.netloc}{src}"
        # relative path
        return base + '/' + src

    # 1) link rel icons
    rel_queries = [
        'link[rel="icon"]',
        'link[rel="shortcut icon"]',
        'link[rel="apple-touch-icon"]',
        'link[rel="mask-icon"]',
    ]
    for q in rel_queries:
        for tag in soup.select(q):
            href = (tag.get('href') or '').strip()
            if href:
                return LogoResponse(success=True, logo_url=absolutize(href))

    # 2) OpenGraph/Twitter
    meta_queries = [
        'meta[property="og:image"]',
        'meta[name="twitter:image"]'
    ]
    for q in meta_queries:
        tag = soup.select_one(q)
        if tag:
            content = (tag.get('content') or '').strip()
            if content:
                return LogoResponse(success=True, logo_url=absolutize(content))

    # 3) img with logo-like hints
    logo_like = ['logo', 'brand', 'branding', 'site-logo', 'navbar-brand']
    for img in soup.find_all('img'):
        attrs = ' '.join(filter(None, [img.get('id'), img.get('class') and ' '.join(img.get('class'))]))
        src = (img.get('src') or '').strip()
        if any(k in attrs.lower() for k in logo_like) and src:
            return LogoResponse(success=True, logo_url=absolutize(src))

    return LogoResponse(success=False, fallback_used=True, message='No logo discovered')


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
