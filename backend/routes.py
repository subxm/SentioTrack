import os
import re
import urllib.parse
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from database import get_db, Topic, Post, Sentiment, User
from scraper import Scraper
from sentiment import SentimentPipeline
from auth import (
    get_current_user,
    exchange_google_code_for_token,
    get_google_user_profile,
    create_access_token,
    GOOGLE_CLIENT_ID,
    REDIRECT_URI
)

router = APIRouter()
scraper = Scraper()
pipeline = SentimentPipeline()

# Standard stop words for cleaning keyword frequency
STOPWORDS = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", 
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", 
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves", "what", "which", 
    "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", 
    "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", 
    "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", 
    "for", "with", "about", "against", "between", "into", "through", "during", "before", 
    "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", 
    "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", 
    "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", 
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", 
    "will", "just", "don", "should", "now", "d", "ll", "m", "o", "re", "ve", "y", "ain", 
    "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven", "isn", "ma", "mightn", 
    "mustn", "needn", "shan", "shouldn", "wasn", "weren", "won", "wouldn", "like", "get", 
    "one", "would", "think", "people", "make", "good", "see", "really", "know", "amp", "new", 
    "back", "go", "get", "time", "day", "still", "much", "even", "first", "years", "way", 
    "many", "right", "see", "look", "take", "said", "say"
}

class AnalyzeRequest(BaseModel):
    keyword: str
    source: str = "both"  # 'reddit', 'news', or 'both'
    limit: Optional[int] = 20

class MockLoginRequest(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None

# --- AUTHENTICATION ROUTERS ---

@router.get("/auth/login")
def google_login():
    """Generates Google login URL and returns it to the client."""
    if not GOOGLE_CLIENT_ID:
        # Return flag showing OAuth keys are not configured, so frontend can fallback to Mock Login
        return {"url": None, "message": "Google Client ID is not configured."}
    
    scope = "openid email profile"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "select_account"
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return {"url": url}

@router.get("/auth/callback")
def google_callback(code: str, db: Session = Depends(get_db)):
    """Handles Google OAuth callback redirect, logs user in, and returns session token."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # 1. Exchange auth code for google access token
    tokens = exchange_google_code_for_token(code)
    if not tokens or "access_token" not in tokens:
        return RedirectResponse(url=f"{frontend_url}/?error=google_auth_failed")
        
    access_token = tokens["access_token"]
    
    # 2. Get profile details
    profile = get_google_user_profile(access_token)
    if not profile or "email" not in profile:
        return RedirectResponse(url=f"{frontend_url}/?error=profile_fetch_failed")
        
    email = profile["email"]
    name = profile.get("name", email.split("@")[0])
    picture = profile.get("picture")
    
    # 3. Create or Sync user profile
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=name, picture=picture)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.name = name
        user.picture = picture
        db.commit()
        
    # 4. Generate local session JWT
    token = create_access_token(data={"sub": user.email, "id": user.id})
    return RedirectResponse(url=f"{frontend_url}/?token={token}")

@router.post("/auth/mock-login")
def mock_login(req: MockLoginRequest, db: Session = Depends(get_db)):
    """Mock Login Fallback: signs a local JWT session token for testing without Google keys."""
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
        
    name = req.name.strip() or email.split("@")[0]
    picture = req.picture or f"https://api.dicebear.com/7.x/bottts/svg?seed={email}"
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=name, picture=picture)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.name = name
        user.picture = picture
        db.commit()
        
    token = create_access_token(data={"sub": user.email, "id": user.id})
    return {
        "token": token,
        "user": {
            "email": user.email,
            "name": user.name,
            "picture": user.picture
        }
    }

@router.get("/auth/me")
def get_me(current_user: Optional[User] = Depends(get_current_user)):
    """Returns currently authenticated user details, if token is valid."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    return {
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture
    }

# --- METRIC ROUTERS ---

@router.get("/topics")
def get_topics(db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    # If user is authenticated, query user-owned topics. If guest, query anonymous topics.
    if current_user:
        topics = db.query(Topic).filter(Topic.user_id == current_user.id).all()
    else:
        topics = db.query(Topic).filter(Topic.user_id == None).all()
        
    results = []
    for t in topics:
        post_count = db.query(Post).filter(Post.topic_id == t.id).count()
        results.append({
            "id": t.id,
            "keyword": t.keyword,
            "source": t.source,
            "created_at": t.created_at.isoformat(),
            "post_count": post_count
        })
    return results

@router.post("/analyze")
def analyze_topic(req: AnalyzeRequest, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    keyword_clean = req.keyword.strip()
    if not keyword_clean:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    user_id = current_user.id if current_user else None

    # Check if topic already exists for this scope; if so, overwrite
    if user_id:
        existing_topic = db.query(Topic).filter(
            Topic.keyword.ilike(keyword_clean),
            Topic.user_id == user_id
        ).first()
    else:
        existing_topic = db.query(Topic).filter(
            Topic.keyword.ilike(keyword_clean),
            Topic.user_id == None
        ).first()

    if existing_topic:
        db.delete(existing_topic)
        db.commit()

    # Create new Topic
    topic = Topic(keyword=keyword_clean, source=req.source, user_id=user_id)
    db.add(topic)
    db.commit()
    db.refresh(topic)

    # Scrape posts
    scraped_posts = []
    
    if req.source in ["news", "both"]:
        news = scraper.scrape_news(keyword_clean, limit=req.limit)
        scraped_posts.extend(news)
        
    if req.source in ["reddit", "both"]:
        # Safety fallback since we are mostly news-focused now
        reddit = scraper.scrape_reddit(keyword_clean, limit=req.limit)
        scraped_posts.extend(reddit)

    if not scraped_posts:
        news = scraper._generate_mock_news(keyword_clean, req.limit)
        scraped_posts.extend(news)

    # Run sentiment analysis and save to DB
    for sp in scraped_posts:
        post = Post(
            topic_id=topic.id,
            title=sp["title"],
            text=sp["text"],
            author=sp["author"],
            source=sp["source"],
            url=sp["url"],
            published_at=sp["published_at"]
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        full_text = f"{sp['title']}. {sp['text']}"
        vader_res = pipeline.analyze_vader(full_text)
        roberta_res = pipeline.analyze_roberta(full_text, vader_fallback_scores=vader_res)

        sentiment = Sentiment(
            post_id=post.id,
            vader_label=vader_res["label"],
            vader_compound=vader_res["compound"],
            vader_pos=vader_res["pos"],
            vader_neu=vader_res["neu"],
            vader_neg=vader_res["neg"],
            transformer_label=roberta_res["label"],
            transformer_score=roberta_res["score"],
            transformer_pos=roberta_res["pos"],
            transformer_neu=roberta_res["neu"],
            transformer_neg=roberta_res["neg"]
        )
        db.add(sentiment)
        db.commit()

    return {"status": "success", "topic_id": topic.id, "posts_count": len(scraped_posts)}

@router.get("/dashboard/{topic_id}")
def get_dashboard_data(topic_id: int, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Authorize Access: User can only read their own topics or anonymous/guest topics
    if topic.user_id is not None:
        if not current_user or current_user.id != topic.user_id:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permission to access this search history dashboard."
            )

    posts = db.query(Post).filter(Post.topic_id == topic_id).all()
    
    # 1. Trend Data (group by date/hour)
    sorted_posts = sorted(posts, key=lambda p: p.published_at)
    
    trend_dict = {}
    for p in sorted_posts:
        date_str = p.published_at.strftime("%Y-%m-%d %H:00")
        if date_str not in trend_dict:
            trend_dict[date_str] = {"vader": [], "transformer": []}
            
        sent = p.sentiment
        if sent:
            v_val = 1 if sent.vader_label == "positive" else (-1 if sent.vader_label == "negative" else 0)
            t_val = 1 if sent.transformer_label == "positive" else (-1 if sent.transformer_label == "negative" else 0)
            trend_dict[date_str]["vader"].append(v_val)
            trend_dict[date_str]["transformer"].append(t_val)

    trend_data = []
    for dt, scores in trend_dict.items():
        v_avg = sum(scores["vader"]) / len(scores["vader"]) if scores["vader"] else 0
        t_avg = sum(scores["transformer"]) / len(scores["transformer"]) if scores["transformer"] else 0
        trend_data.append({
            "time": dt,
            "vader_sentiment": round(v_avg, 3),
            "transformer_sentiment": round(t_avg, 3),
            "count": len(scores["vader"])
        })

    # 2. Live Feed & Model Comparison Panel
    live_feed = []
    model_comparison = []
    
    vader_counts = {"positive": 0, "neutral": 0, "negative": 0}
    trans_counts = {"positive": 0, "neutral": 0, "negative": 0}
    
    word_counters = {
        "positive": Counter(),
        "neutral": Counter(),
        "negative": Counter()
    }

    for p in sorted_posts:
        sent = p.sentiment
        if not sent:
            continue
            
        vader_counts[sent.vader_label] += 1
        trans_counts[sent.transformer_label] += 1
        
        combined_text = f"{p.title} {p.text}".lower()
        words = re.findall(r"\b[a-z]{3,15}\b", combined_text)
        cleaned_words = [w for w in words if w not in STOPWORDS]
        word_counters[sent.transformer_label].update(cleaned_words)

        post_data = {
            "id": p.id,
            "title": p.title,
            "text": p.text,
            "author": p.author,
            "source": p.source,
            "url": p.url,
            "published_at": p.published_at.isoformat(),
            "vader": {
                "label": sent.vader_label,
                "compound": round(sent.vader_compound, 3),
                "pos": round(sent.vader_pos, 3),
                "neu": round(sent.vader_neu, 3),
                "neg": round(sent.vader_neg, 3)
            },
            "transformer": {
                "label": sent.transformer_label,
                "score": round(sent.transformer_score, 3),
                "pos": round(sent.transformer_pos, 3),
                "neu": round(sent.transformer_neu, 3),
                "neg": round(sent.transformer_neg, 3)
            }
        }
        
        live_feed.append(post_data)
        model_comparison.append({
            "id": p.id,
            "title": p.title,
            "source": p.source,
            "vader_label": sent.vader_label,
            "vader_score": round(sent.vader_compound, 3),
            "transformer_label": sent.transformer_label,
            "transformer_score": round((sent.transformer_pos - sent.transformer_neg), 3)
        })

    live_feed.reverse()

    heatmap_data = {
        "positive": [{"word": w, "count": c} for w, c in word_counters["positive"].most_common(15)],
        "neutral": [{"word": w, "count": c} for w, c in word_counters["neutral"].most_common(15)],
        "negative": [{"word": w, "count": c} for w, c in word_counters["negative"].most_common(15)]
    }

    total_posts = len(posts)
    summary = {
        "total_posts": total_posts,
        "vader_breakdown": {k: round(v / total_posts * 100, 1) if total_posts else 0 for k, v in vader_counts.items()},
        "transformer_breakdown": {k: round(v / total_posts * 100, 1) if total_posts else 0 for k, v in trans_counts.items()}
    }

    return {
        "topic": {
            "id": topic.id,
            "keyword": topic.keyword,
            "source": topic.source,
            "created_at": topic.created_at.isoformat()
        },
        "summary": summary,
        "trend_data": trend_data,
        "model_comparison": model_comparison,
        "heatmap_data": heatmap_data,
        "live_feed": live_feed
    }
