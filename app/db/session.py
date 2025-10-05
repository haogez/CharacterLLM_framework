from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.character import Base
import chromadb
import os

# SQLite数据库配置
SQLALCHEMY_DATABASE_URL = "sqlite:///./character_llm.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建数据库表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 数据库依赖
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ChromaDB客户端
def get_chroma_client():
    """获取ChromaDB客户端"""
    client = chromadb.PersistentClient(path="./chroma_db")
    return client

def get_character_memory_collection(character_id: int):
    """获取角色专属的记忆集合"""
    client = get_chroma_client()
    collection_name = f"character_{character_id}_memories"
    
    try:
        collection = client.get_collection(name=collection_name)
    except ValueError:
        # 如果集合不存在，创建新集合
        collection = client.create_collection(
            name=collection_name,
            metadata={"character_id": character_id}
        )
    
    return collection
