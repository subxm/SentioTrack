import datetime
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sentiment_tracker.db")

# SQLAlchemy requires postgresql+psycopg2:// for postgres
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# SQLite requires connect_args, but PostgreSQL does not
if "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    topics = relationship("Topic", back_populates="user", cascade="all, delete-orphan")

class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, unique=True, index=True)
    source = Column(String)  # 'reddit', 'news', or 'both'
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="topics")
    posts = relationship("Post", back_populates="topic", cascade="all, delete-orphan")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String)
    text = Column(String)
    author = Column(String, nullable=True)
    source = Column(String)  # 'reddit' or 'news'
    url = Column(String, nullable=True)
    published_at = Column(DateTime, default=datetime.datetime.utcnow)

    topic = relationship("Topic", back_populates="posts")
    sentiment = relationship("Sentiment", back_populates="post", uselist=False, cascade="all, delete-orphan")

class Sentiment(Base):
    __tablename__ = "sentiments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    
    # VADER metrics
    vader_label = Column(String)  # 'positive', 'neutral', 'negative'
    vader_compound = Column(Float)
    vader_pos = Column(Float)
    vader_neu = Column(Float)
    vader_neg = Column(Float)

    # Hugging Face Transformer metrics
    transformer_label = Column(String)  # 'positive', 'neutral', 'negative'
    transformer_score = Column(Float)  # Confidence of winning label
    transformer_pos = Column(Float)
    transformer_neu = Column(Float)
    transformer_neg = Column(Float)

    post = relationship("Post", back_populates="sentiment")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
