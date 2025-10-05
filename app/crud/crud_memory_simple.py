from app.db.session_simple import memory_store
from typing import List, Dict, Any

def add_memory(character_id: int, memory_text: str, event_type: str, metadata: Dict[str, Any] = None) -> str:
    """为角色添加记忆"""
    return memory_store.add_memory(character_id, memory_text, event_type, metadata)

def search_memories(character_id: int, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """搜索角色相关记忆"""
    return memory_store.search_memories(character_id, query, n_results)

def get_all_memories(character_id: int) -> List[Dict[str, Any]]:
    """获取角色的所有记忆"""
    return memory_store.get_all_memories(character_id)

def delete_memory(character_id: int, memory_id: str) -> bool:
    """删除特定记忆（简化版本暂不实现）"""
    return True

def clear_character_memories(character_id: int) -> bool:
    """清空角色的所有记忆"""
    return memory_store.clear_character_memories(character_id)
