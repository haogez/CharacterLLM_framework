# app/core/graph/graph_store.py
"""
图谱存储模块 (Neo4j 版)

提供对人物关系图谱的存储和管理功能，使用 Neo4j 图数据库。
"""

import os
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase
import json
import uuid


class GraphStore:
    """
    Neo4j 图谱存储类

    使用 Neo4j 图数据库存储角色节点和关系边。
    """

    def __init__(self, uri: str = "bolt://zhouyuhao-neo4j:7687", user: str = "neo4j", password: str = "zyh123456"):
        """
        初始化图谱存储，连接到 Neo4j。

        Args:
            uri (str): Neo4j 数据库 URI
            user (str): 用户名
            password (str): 密码
        """
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # 测试连接
            with self.driver.session() as session:
                session.run("RETURN 1")
            print("--- 成功连接到 Neo4j 数据库 ---")
            # 确保节点和关系上有索引以提高查询效率
            self._create_indices()
        except Exception as e:
            print(f"连接 Neo4j 数据库失败: {e}")
            raise e

    def _create_indices(self):
        """创建必要的索引以优化查询"""
        with self.driver.session() as session:
            # 为 Character 节点的 id 属性创建索引
            session.run("CREATE INDEX character_id_index IF NOT EXISTS FOR (n:Character) ON (n.id)")
            # 为 Relationship 的 relationship_id 属性创建索引
            session.run("CREATE INDEX relationship_id_index IF NOT EXISTS FOR (r:Relationship) ON (r.relationship_id)")
            # 为 Memory 的 id 属性创建索引
            session.run("CREATE INDEX memory_id_index IF NOT EXISTS FOR (m:Memory) ON (m.id)")
            print("--- Neo4j 索引检查/创建完成 ---")

    def close(self):
        """关闭数据库连接"""
        if self.driver:
            self.driver.close()
            print("--- Neo4j 连接已关闭 ---")

    def create_character_node(self, character_data: Dict[str, Any]) -> bool:
        """
        创建角色节点。

        Args:
            character_data (Dict[str, Any]): 角色数据字典，必须包含 'id' 字段。

        Returns:
            bool: 是否创建成功
        """
        char_id = character_data.get("id")
        if not char_id:
            print("错误：角色数据必须包含 'id' 字段。")
            return False

        with self.driver.session() as session:
            try:
                # 使用 MERGE 以防万一节点已存在（虽然理想情况下不应重复创建）
                # 将字典中可能包含复杂对象（如字典）的字段序列化为 JSON 字符串存储
                # 例如 personality, time, emotion 等
                # 这里假设 character_data 中的复杂对象需要序列化
                # 对于简单类型（str, int, float, bool, list of primitives），Neo4j 可以直接存储
                # 但对于嵌套字典，序列化是常见做法
                # 我们将序列化所有可能的复杂对象，除了 id, name, age 等基本字段
                node_properties = character_data.copy()
                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (c:Character {id: $char_id})
                    SET c = $properties
                    """,
                    char_id=char_id,
                    properties=node_properties
                )
                print(f"--- 角色节点 {char_id} 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建角色节点 {char_id} 失败: {e}")
                return False

    def create_relationship_with_memories(self, relationship_data: Dict[str, Any]) -> bool:
        """
        创建关系边并存储其关联的记忆。
        在 Neo4j 中，关系本身不能直接存储列表属性（如 memories）。
        我们创建一个中间节点来代表关系，并通过关系连接主角色、中间节点和记忆节点。

        Args:
            relationship_data (Dict[str, Any]): 关系数据字典，必须包含 'relationship_id', 'character1_id', 'character2_id'。

        Returns:
            bool: 是否创建成功
        """
        rel_id = relationship_data.get("relationship_id")
        char1_id = relationship_data.get("character1_id")
        char2_id = relationship_data.get("character2_id")
        memories_data = relationship_data.get("memories", [])

        if not all([rel_id, char1_id, char2_id]):
            print("错误：关系数据必须包含 'relationship_id', 'character1_id', 'character2_id' 字段。")
            return False

        with self.driver.session() as session:
            try:
                # 1. 创建关系节点 (RELATIONSHIP)
                # 将关系的属性（除了ID和连接的节点ID）存储在 RELATIONSHIP 节点上
                rel_properties = {k: v for k, v in relationship_data.items() if k not in ['relationship_id', 'character1_id', 'character2_id', 'memories']}
                # 序列化复杂对象
                for key, value in rel_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        rel_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (r:Relationship {relationship_id: $rel_id})
                    SET r = $properties
                    """,
                    rel_id=rel_id,
                    properties=rel_properties
                )

                # 2. 确保角色节点存在（虽然通常在创建关系前已创建，但这里也尝试创建以防万一）
                session.run("MERGE (c1:Character {id: $char1_id})", char1_id=char1_id)
                session.run("MERGE (c2:Character {id: $char2_id})", char2_id=char2_id)

                # 3. 创建连接：Character1 -[:HAS_RELATIONSHIP]-> Relationship <-[:BELONGS_TO]- Character2
                # 为了方便查询，我们创建两个方向的关系
                session.run(
                    """
                    MATCH (c1:Character {id: $char1_id}), (c2:Character {id: $char2_id}), (r:Relationship {relationship_id: $rel_id})
                    MERGE (c1)-[:HAS_RELATIONSHIP]->(r)
                    MERGE (c2)-[:BELONGS_TO_RELATIONSHIP]->(r)
                    """,
                    char1_id=char1_id, char2_id=char2_id, rel_id=rel_id
                )

                # 4. 为该关系创建记忆节点
                for mem_data in memories_data:
                    mem_id = mem_data.get("id", str(uuid.uuid4()))
                    # 确保 memory 有 id
                    mem_data["id"] = mem_id
                    # 序列化 memory 的复杂对象
                    memory_properties = mem_data.copy()
                    for key, value in memory_properties.items():
                        if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                            memory_properties[key] = json.dumps(value, ensure_ascii=False)

                    # 创建 Memory 节点
                    session.run(
                        """
                        MERGE (m:Memory {id: $mem_id})
                        SET m = $properties
                        """,
                        mem_id=mem_id,
                        properties=memory_properties
                    )
                    # 创建连接：Relationship -[:HAS_MEMORY]-> Memory
                    session.run(
                        """
                        MATCH (r:Relationship {relationship_id: $rel_id}), (m:Memory {id: $mem_id})
                        MERGE (r)-[:HAS_MEMORY]->(m)
                        """,
                        rel_id=rel_id, mem_id=mem_id
                    )

                print(f"--- 关系边 {rel_id} 创建/更新成功，包含 {len(memories_data)} 条记忆 ---")
                return True
            except Exception as e:
                print(f"创建关系边 {rel_id} 失败: {e}")
                return False

    def add_memory_to_relationship(self, relationship_id: str, memory_data: Dict[str, Any]) -> bool:
        """
        向已有的关系边添加新记忆。
        在 Neo4j 中，这意味着创建一个新的 Memory 节点，并将其连接到代表关系的节点上。

        Args:
            relationship_id (str): 关系边ID
            memory_data (Dict[str, Any]): 记忆数据字典

        Returns:
            bool: 是否添加成功
        """
        # 为记忆生成唯一ID
        memory_id = memory_data.get("id", str(uuid.uuid4()))
        memory_data["id"] = memory_id

        with self.driver.session() as session:
            try:
                # 序列化 memory 的复杂对象
                memory_properties = memory_data.copy()
                for key, value in memory_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        memory_properties[key] = json.dumps(value, ensure_ascii=False)

                # 创建 Memory 节点
                session.run(
                    """
                    MERGE (m:Memory {id: $mem_id})
                    SET m = $properties
                    """,
                    mem_id=memory_id,
                    properties=memory_properties
                )
                # 创建连接：Relationship -[:HAS_MEMORY]-> Memory
                session.run(
                    """
                    MATCH (r:Relationship {relationship_id: $rel_id}), (m:Memory {id: $mem_id})
                    MERGE (r)-[:HAS_MEMORY]->(m)
                    """,
                    rel_id=relationship_id, mem_id=memory_id
                )
                print(f"--- 记忆 {memory_id} 已添加到关系 {relationship_id} ---")
                return True
            except Exception as e:
                print(f"向关系 {relationship_id} 添加记忆 {memory_id} 失败: {e}")
                return False

    def get_related_characters(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取与指定角色相关的所有角色。

        Args:
            character_id (str): 角色ID

        Returns:
            List[Dict[str, Any]]: 相关角色信息列表
        """
        with self.driver.session() as session:
            try:
                # 查询与 character_id 直接相关的角色
                # 通过 HAS_RELATIONSHIP 和 BELONGS_TO_RELATIONSHIP 两种关系查找
                result = session.run(
                    """
                    MATCH (c1:Character {id: $char_id})-[r1:HAS_RELATIONSHIP]->(rel:Relationship)<-[r2:BELONGS_TO_RELATIONSHIP]-(c2:Character)
                    RETURN c2, rel
                    UNION
                    MATCH (c1:Character {id: $char_id})-[r2:BELONGS_TO_RELATIONSHIP]->(rel:Relationship)<-[r1:HAS_RELATIONSHIP]-(c2:Character)
                    RETURN c2, rel
                    """,
                    char_id=character_id
                )

                related_chars = []
                for record in result:
                    char_node = record["c2"]
                    rel_node = record["rel"]

                    # 反序列化从 Neo4j 获取的 JSON 字符串
                    char_props = dict(char_node)
                    for key, value in char_props.items():
                        if isinstance(value, str):
                            try:
                                char_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass # 如果不是 JSON 字符串，则保留原值

                    # 提取关系信息
                    rel_props = dict(rel_node)
                    for key, value in rel_props.items():
                        if isinstance(value, str):
                            try:
                                rel_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass

                    # 将关系信息附带在角色数据中
                    char_props["_relationship_info"] = {
                        "relationship_id": rel_props.get("relationship_id"),
                        "relationship_type": rel_props.get("relationship_type"),
                        "strength": rel_props.get("strength"),
                        "description": rel_props.get("description")
                    }
                    related_chars.append(char_props)

                print(f"--- 获取到 {len(related_chars)} 个与角色 {character_id} 相关的角色 ---")
                return related_chars
            except Exception as e:
                print(f"获取角色 {character_id} 的相关角色失败: {e}")
                return []

    def get_relationship_memories(self, character1_id: str, character2_id: str) -> List[Dict[str, Any]]:
        """
        获取特定关系上的所有记忆。
        在 Neo4j 中，我们需要先找到连接这两个角色的关系节点，然后查找其关联的记忆。

        Args:
            character1_id (str): 角色1 ID
            character2_id (str): 角色2 ID

        Returns:
            List[Dict[str, Any]]: 记忆列表
        """
        with self.driver.session() as session:
            try:
                # 查询连接 c1 和 c2 的关系节点，然后获取其记忆
                result = session.run(
                    """
                    MATCH (c1:Character {id: $char1_id})-[r1:HAS_RELATIONSHIP]->(rel:Relationship)<-[r2:BELONGS_TO_RELATIONSHIP]-(c2:Character {id: $char2_id})-[:HAS_MEMORY]->(m:Memory)
                    RETURN m
                    UNION
                    MATCH (c1:Character {id: $char1_id})-[r2:BELONGS_TO_RELATIONSHIP]->(rel:Relationship)<-[r1:HAS_RELATIONSHIP]-(c2:Character {id: $char2_id})-[:HAS_MEMORY]->(m:Memory)
                    RETURN m
                    """,
                    char1_id=character1_id, char2_id=character2_id
                )

                memories = []
                for record in result:
                    mem_node = record["m"]
                    # 反序列化从 Neo4j 获取的 JSON 字符串
                    mem_props = dict(mem_node)
                    for key, value in mem_props.items():
                        if isinstance(value, str):
                            try:
                                mem_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass # 如果不是 JSON 字符串，则保留原值
                    memories.append(mem_props)

                print(f"--- 获取到 {len(memories)} 条角色 {character1_id} 和 {character2_id} 之间的关系记忆 ---")
                return memories
            except Exception as e:
                print(f"获取角色 {character1_id} 和 {character2_id} 的关系记忆失败: {e}")
                return []

    def get_all_memories_for_character(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取与指定角色相关的所有关系上的所有记忆。
        在 Neo4j 中，我们需要找到所有与该角色关联的关系节点，然后获取这些关系的所有记忆。

        Args:
            character_id (str): 角色ID

        Returns:
            List[Dict[str, Any]]: 所有记忆列表
        """
        with self.driver.session() as session:
            try:
                # 查询与 character_id 关联的所有关系，然后获取这些关系的记忆
                # 使用 OPTIONAL MATCH 来处理可能没有记忆的关系
                result = session.run(
                    """
                    MATCH (c:Character {id: $char_id})-[:HAS_RELATIONSHIP|BELONGS_TO_RELATIONSHIP]-(rel:Relationship)-[:HAS_MEMORY]->(m:Memory)
                    RETURN m, rel.relationship_id AS rel_id, CASE WHEN rel.character1_id = $char_id THEN rel.character2_id ELSE rel.character1_id END AS other_char_id
                    """,
                    char_id=character_id
                )

                all_memories = []
                for record in result:
                    mem_node = record["m"]
                    rel_id = record["rel_id"]
                    other_char_id = record["other_char_id"]

                    # 反序列化从 Neo4j 获取的 JSON 字符串
                    mem_props = dict(mem_node)
                    for key, value in mem_props.items():
                        if isinstance(value, str):
                            try:
                                mem_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass # 如果不是 JSON 字符串，则保留原值

                    # 添加来源信息
                    mem_props["_source_relationship"] = rel_id
                    mem_props["_related_character_id"] = other_char_id
                    all_memories.append(mem_props)

                print(f"--- 获取到角色 {character_id} 的 {len(all_memories)} 条关联记忆 ---")
                return all_memories
            except Exception as e:
                print(f"获取角色 {character_id} 的所有关联记忆失败: {e}")
                return []

    def update_relationship_strength(self, character1_id: str, character2_id: str, new_strength: int) -> bool:
        """
        更新关系强度。
        找到连接两个角色的关系节点并更新其 strength 属性。

        Args:
            character1_id (str): 角色1 ID
            character2_id (str): 角色2 ID
            new_strength (int): 新的关系强度

        Returns:
            bool: 是否更新成功
        """
        with self.driver.session() as session:
            try:
                # 尝试更新两种可能的关系路径
                result1 = session.run(
                    """
                    MATCH (c1:Character {id: $char1_id})-[r1:HAS_RELATIONSHIP]->(rel:Relationship)<-[r2:BELONGS_TO_RELATIONSHIP]-(c2:Character {id: $char2_id})
                    SET rel.strength = $new_strength
                    RETURN rel
                    """,
                    char1_id=character1_id, char2_id=character2_id, new_strength=new_strength
                )
                # 检查是否有匹配项
                if result1.peek():
                    print(f"--- 关系 {char1_id}-{char2_id} 的强度已更新为 {new_strength} ---")
                    return True

                result2 = session.run(
                    """
                    MATCH (c1:Character {id: $char1_id})-[r2:BELONGS_TO_RELATIONSHIP]->(rel:Relationship)<-[r1:HAS_RELATIONSHIP]-(c2:Character {id: $char2_id})
                    SET rel.strength = $new_strength
                    RETURN rel
                    """,
                    char1_id=character1_id, char2_id=character2_id, new_strength=new_strength
                )
                if result2.peek():
                    print(f"--- 关系 {char1_id}-{char2_id} 的强度已更新为 {new_strength} ---")
                    return True

                print(f"错误：未找到角色 {character1_id} 和 {character2_id} 之间的关系。")
                return False

            except Exception as e:
                print(f"更新关系 {character1_id}-{character2_id} 的强度失败: {e}")
                return False

    def delete_character_graph(self, character_id: str) -> bool:
        """
        删除角色及其相关关系和记忆。
        在 Neo4j 中，删除节点会自动删除其所有关系。

        Args:
            character_id (str): 角色ID

        Returns:
            bool: 是否删除成功
        """
        with self.driver.session() as session:
            try:
                # 删除与该角色关联的所有关系节点及其记忆
                # 由于 Memory 节点通过 Relationship 节点连接，删除 Relationship 会断开连接
                # 为了彻底删除孤立的 Memory 节点，我们可以先找到它们，再删除
                session.run(
                    """
                    MATCH (c:Character {id: $char_id})-[r1:HAS_RELATIONSHIP|BELONGS_TO_RELATIONSHIP]-(rel:Relationship)-[:HAS_MEMORY]->(m:Memory)
                    DETACH DELETE c, rel, m
                    """,
                    char_id=character_id
                )
                # 如果上面的 DETACH DELETE 没有完全删除孤立的 Memory，
                # 可以添加一个清理步骤，删除没有关系连接的 Memory 节点
                # 但通常 DETACH DELETE c, rel, m 应该足够了，因为 c 和 rel 都被删除了
                # 如果 Memory 节点还可能通过其他方式连接，则需要更复杂的清理逻辑
                # 这里假设 Memory 只通过 Relationship 连接
                print(f"--- 角色 {character_id} 及其关联的关系和记忆已删除 ---")
                return True
            except Exception as e:
                print(f"删除角色 {character_id} 的图谱数据失败: {e}")
                return False

# --- 可选：在模块加载时创建一个全局实例 ---
# global_graph_store = GraphStore()
# ---


if __name__ == "__main__":
    # 示例用法
    try:
        graph_store = GraphStore(uri="bolt://zhouyuhao-neo4j:7687", user="neo4j", password="zyh123456")
        # ... 可以在这里测试方法 ...
        graph_store.close()
    except Exception as e:
        print(f"初始化 GraphStore 失败: {e}")
