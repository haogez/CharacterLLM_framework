from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.character import Base
import json
from typing import Dict, List, Any
import uuid
from datetime import datetime

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

# 简化的内存记忆存储
class SimpleMemoryStore:
    def __init__(self):
        self.memories: Dict[int, List[Dict[str, Any]]] = {}
    
    def add_memory(self, character_id: int, memory_text: str, event_type: str, metadata: Dict[str, Any] = None) -> str:
        """为角色添加记忆"""
        if character_id not in self.memories:
            self.memories[character_id] = []
        
        memory_id = str(uuid.uuid4())
        memory = {
            "id": memory_id,
            "text": memory_text,
            "event_type": event_type,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.memories[character_id].append(memory)
        return memory_id
    
    def search_memories(self, character_id: int, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """搜索角色相关记忆（简单的关键词匹配）"""
        if character_id not in self.memories:
            return []
        
        memories = self.memories[character_id]
        query_lower = query.lower()
        
        # 简单的关键词匹配
        relevant_memories = []
        for memory in memories:
            if query_lower in memory["text"].lower():
                relevant_memories.append({
                    "text": memory["text"],
                    "metadata": memory["metadata"],
                    "distance": 0.5  # 模拟相似度分数
                })
        
        return relevant_memories[:n_results]
    
    def get_all_memories(self, character_id: int) -> List[Dict[str, Any]]:
        """获取角色的所有记忆"""
        if character_id not in self.memories:
            return []
        
        return [
            {
                "text": memory["text"],
                "metadata": memory["metadata"]
            }
            for memory in self.memories[character_id]
        ]
    
    def clear_character_memories(self, character_id: int) -> bool:
        """清空角色的所有记忆"""
        if character_id in self.memories:
            del self.memories[character_id]
        return True

# 全局内存存储实例
memory_store = SimpleMemoryStore()
