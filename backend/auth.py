import os
import datetime
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import requests
from sqlalchemy.orm import Session
from database import get_db, User

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-fallback-sentiotrack")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# OAuth Credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/api/auth/callback")

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)), db: Session = Depends(get_db)) -> Optional[User]:
    """FastAPI Dependency: extracts current authenticated user from Bearer Token."""
    if not credentials:
        return None
        
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        return None
        
    email = payload.get("sub")
    if not email:
        return None
        
    user = db.query(User).filter(User.email == email).first()
    return user

def exchange_google_code_for_token(code: str) -> Optional[dict]:
    """Exchanges Google authorization code for access token."""
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    try:
        res = requests.post(token_url, data=payload, timeout=10)
        if res.status_code == 200:
            return res.json()
        print(f"Google Token Exchange error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Error exchanging Google code: {e}")
    return None

def get_google_user_profile(access_token: str) -> Optional[dict]:
    """Queries Google userinfo endpoint using OAuth access token."""
    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        res = requests.get(userinfo_url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
        print(f"Google Profile Query error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Error querying Google profile: {e}")
    return None
