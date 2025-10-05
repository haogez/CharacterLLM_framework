from app.db.session import get_character_memory_collection
from typing import List, Dict, Any
import uuid
from datetime import datetime

def add_memory(character_id: int, memory_text: str, event_type: str, metadata: Dict[str, Any] = None) -> str:
    """为角色添加记忆"""
    collection = get_character_memory_collection(character_id)
    
    memory_id = str(uuid.uuid4())
    memory_metadata = {
        "character_id": character_id,
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        **(metadata or {})
    }
    
    collection.add(
        documents=[memory_text],
        metadatas=[memory_metadata],
        ids=[memory_id]
    )
    
    return memory_id

def search_memories(character_id: int, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """搜索角色相关记忆"""
    collection = get_character_memory_collection(character_id)
    
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        memories = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                memory = {
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0
                }
                memories.append(memory)
        
        return memories
    except Exception as e:
        print(f"搜索记忆时出错: {e}")
        return []

def get_all_memories(character_id: int) -> List[Dict[str, Any]]:
    """获取角色的所有记忆"""
    collection = get_character_memory_collection(character_id)
    
    try:
        results = collection.get(include=["documents", "metadatas"])
        
        memories = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                memory = {
                    "text": doc,
                    "metadata": results["metadatas"][i] if results["metadatas"] else {}
                }
                memories.append(memory)
        
        return memories
    except Exception as e:
        print(f"获取记忆时出错: {e}")
        return []

def delete_memory(character_id: int, memory_id: str) -> bool:
    """删除特定记忆"""
    collection = get_character_memory_collection(character_id)
    
    try:
        collection.delete(ids=[memory_id])
        return True
    except Exception as e:
        print(f"删除记忆时出错: {e}")
        return False

def clear_character_memories(character_id: int) -> bool:
    """清空角色的所有记忆"""
    try:
        from app.db.session import get_chroma_client
        client = get_chroma_client()
        collection_name = f"character_{character_id}_memories"
        client.delete_collection(name=collection_name)
        return True
    except Exception as e:
        print(f"清空记忆时出错: {e}")
        return False
