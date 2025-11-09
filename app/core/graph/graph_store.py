# app/core/graph/graph_store.py

"""
图谱存储模块 (Neo4j 自部署版) - 使用统一 CSV 格式
修改以支持：
1. 统一的 Character 节点 (基于 app_id)
2. 印象节点 (Impression) 和事件节点 (Event)
3. 时间顺序链
4. 印象随时间变化和事件间影响
5. 修复 Cypher 语法错误和类型错误
6. 修复注释语法错误
7. 修复 CSV 中 JSON 字符串引号转义问题 - 使用 Base64 编码
8. 修复重复角色节点问题
9. 修复 Cypher 弃用警告
10. 为所有角色（包括关联角色）添加完整的印象结构
11. 基于多因素的印象强度计算
12. 事件细节节点（物品、动作、对话）
13. 优化节点结构，确保清晰无重复
"""

import os
import json
import uuid
import re
import csv
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase
from app.core.utils.log_utils import log_error, log_success, log_warning, log_info, log_debug

class GraphStore:
    def __init__(self,
                 uri: str = "bolt://neo4j-latest:7687", # 使用网络别名连接
                 user: str = "neo4j",
                 password: str = "zyh123456",
                 database: str = "neo4j"):
        self.uri = os.environ.get("NEO4J_URI", uri)
        self.user = os.environ.get("NEO4J_USERNAME", user)
        self.password = os.environ.get("NEO4J_PASSWORD", password)
        self.database = os.environ.get("NEO4J_DATABASE", database)

        # 使用通过挂载卷共享的目录
        self.temp_csv_dir = "/zhouyuhao/zhouyuhao_data/import"
        os.makedirs(self.temp_csv_dir, exist_ok=True)

        AUTH = (self.user, self.password)

        print(f"=== Neo4j 连接调试 ===")
        print(f"URI: {self.uri}")
        print(f"User: {self.user}")
        print(f"Database: {self.database}")
        print(f"======================")

        try:
            self.driver = GraphDatabase.driver(self.uri, auth=AUTH)
            self.driver.verify_connectivity()
            print(f"--- 成功连接到 Neo4j '{self.database}' ---")
            print(f"--- URI: {self.uri} ---")
            print("--- Neo4j 连接初始化完成 ---")
        except Exception as e:
            print(f"连接 Neo4j 失败: {e}")
            import traceback
            traceback.print_exc()
            raise e

    def close(self):
        if self.driver:
            self.driver.close()
            print("--- Neo4j 连接已关闭 ---")


    def create_character_node(self, character_data: Dict[str, Any]) -> bool:
        """
        创建或更新角色节点。
        使用 app_id 作为唯一标识，避免重复创建。
        """
        char_name = character_data.get("name")
        if not char_name:
            print("错误：角色数据必须包含 'name' 字段。")
            return False

        app_id = character_data.get("id", str(uuid.uuid4()))

        with self.driver.session(database=self.database) as session:
            try:
                node_properties = character_data.copy()
                node_properties.pop("id", None)
                node_properties["app_id"] = app_id
                # 确保标签为 Character
                node_properties["is_main_character"] = node_properties.get("is_main_character", False)

                # 将所有嵌套结构转为JSON字符串
                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (c:Character {app_id: $app_id}) // 使用 app_id 作为唯一标识
                    SET c = $properties
                    """,
                    app_id=app_id,
                    properties=node_properties
                )
                print(f"--- 角色节点 '{char_name}' (app_id: {app_id}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建角色节点 '{char_name}' 失败: {e}")
                return False

    def create_general_entity_node(self, entity_data: Dict[str, Any]) -> bool:
        """
        创建通用实体节点 (非人物)。
        根据实体类型创建不同标签的节点，并使用 app_id 作为唯一标识。
        """
        ent_name = entity_data.get("name")
        ent_type = entity_data.get("type", "Entity").upper()
        if not all([ent_name, ent_type]):
            print("错误：实体数据必须包含 'name' 和 'type' 字段。")
            return False

        app_id = entity_data.get("id", str(uuid.uuid4()))

        with self.driver.session(database=self.database) as session:
            try:
                node_properties = entity_data.copy()
                node_properties.pop("id", None)
                node_properties["app_id"] = app_id

                # 将所有嵌套结构转为JSON字符串
                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                # 为非人物实体创建标签
                label = f"{ent_type}"

                session.run(
                    f"""
                    MERGE (e:{label} {{app_id: $app_id}}) // 使用 app_id 作为唯一标识
                    SET e = $properties
                    """,
                    app_id=app_id,
                    properties=node_properties
                )
                print(f"--- 实体节点 '{ent_name}' ({ent_type}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建实体节点 '{ent_name}' 失败: {e}")
                return False

    def create_event_node(self, event_data: Dict[str, Any]) -> bool:
        """
        创建事件节点，包含事件的真实内容。
        """
        event_app_id = event_data.get("id", str(uuid.uuid4()))
        event_data["id"] = event_app_id
        event_title = event_data.get("title", "未命名事件")

        with self.driver.session(database=self.database) as session:
            try:
                event_properties = event_data.copy()
                event_properties.pop("id", None)
                event_properties["app_id"] = event_app_id
                # 存储事件的原始内容作为context
                event_properties["context"] = event_data.get("content", "")

                # 将所有嵌套结构转为JSON字符串
                for key, value in event_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        event_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (e:Event {app_id: $event_app_id})
                    SET e = $properties
                    """,
                    event_app_id=event_app_id,
                    properties=event_properties
                )
                print(f"--- 事件节点 '{event_title}' ({event_app_id}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建事件节点 '{event_app_id}' 失败: {e}")
                return False

    def create_event_detail_node(self, event_app_id: str, detail_data: Dict[str, Any]) -> bool:
        """
        创建事件细节节点（物品、动作、对话等）。
        detail_type: "object", "action", "dialogue"
        """
        detail_app_id = detail_data.get("id", str(uuid.uuid4()))
        detail_type = detail_data.get("type", "DETAIL")
        detail_content = detail_data.get("content", "")
        
        if not all([event_app_id, detail_type, detail_content]):
            print("错误：细节数据必须包含 'type' 和 'content' 字段，且需要事件ID")
            return False

        with self.driver.session(database=self.database) as session:
            try:
                detail_properties = detail_data.copy()
                detail_properties.pop("id", None)
                detail_properties["app_id"] = detail_app_id
                detail_properties["event_app_id"] = event_app_id

                # 将所有嵌套结构转为JSON字符串
                for key, value in detail_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        detail_properties[key] = json.dumps(value, ensure_ascii=False)

                # 创建特定类型的细节节点
                session.run(
                    f"""
                    MERGE (d:{detail_type} {{app_id: $detail_app_id}})
                    SET d = $properties
                    """,
                    detail_app_id=detail_app_id,
                    properties=detail_properties
                )
                
                # 连接到事件节点
                session.run(
                    """
                    MATCH (d) WHERE d.app_id = $detail_app_id
                    MATCH (e:Event) WHERE e.app_id = $event_app_id
                    MERGE (e)-[:HAS_DETAIL]->(d)
                    """,
                    detail_app_id=detail_app_id,
                    event_app_id=event_app_id
                )
                
                print(f"--- 事件细节节点 ({detail_type}: {detail_app_id}) 创建并关联到事件 {event_app_id} 成功 ---")
                return True
            except Exception as e:
                print(f"创建事件细节节点 '{detail_app_id}' 失败: {e}")
                return False

    def calculate_impression_strength(self, character_data: Dict[str, Any], event_data: Dict[str, Any]) -> int:
        """
        根据多因素计算印象强度:
        1. 事件发生时间（越近强度越高）
        2. 事件影响程度（正面/负面/重大程度）
        3. 角色性格特质（敏感性等）
        """
        # 基础强度
        base_strength = 70
        
        # 1. 时间因素（假设事件有timestamp字段）
        event_time_str = event_data.get("time", {}).get("specific", "")
        try:
            event_time = datetime.fromisoformat(event_time_str)
            days_since = (datetime.now() - event_time).days
            # 时间衰减：每过30天衰减10%，最低保留30%
            time_factor = max(0.3, 1 - (days_since / 300))  # 300天约衰减70%
        except:
            time_factor = 1.0  # 无法解析时间则不衰减
        
        # 2. 事件影响因素
        impact_score = event_data.get("importance", {}).get("score", 5) / 5.0  # 归一化到0-1
        event_type = event_data.get("type", "")
        if event_type in ["trauma", "achievement"]:  # 重大事件额外加成
            impact_factor = impact_score * 1.5
        else:
            impact_factor = impact_score
        
        # 3. 角色性格因素（神经质/开放性越高，记忆越深刻）
        personality = character_data.get("personality", {})
        neuroticism = personality.get("neuroticism", 50) / 100.0  # 归一化到0-1
        openness = personality.get("openness", 50) / 100.0
        personality_factor = 0.5 + (neuroticism + openness) / 4  # 范围0.5-1.0
        
        # 计算最终强度（0-100）
        final_strength = int(base_strength * time_factor * impact_factor * personality_factor)
        return max(10, min(100, final_strength))  # 确保在10-100之间

    def create_impression_node(self, impression_data: Dict[str, Any], character_data: Dict[str, Any], event_data: Dict[str, Any]) -> bool:
        """
        创建印象节点，基于角色性格、事件重要性和时间计算强度。
        """
        impression_app_id = impression_data.get("id", str(uuid.uuid4()))
        impression_data["id"] = impression_app_id
        
        # 确保印象数据包含必要字段
        source_char_id = impression_data.get("source_character_app_id")
        event_id = impression_data.get("event_app_id")
        if not source_char_id or not event_id:
            print(f"错误：印象数据必须包含 'source_character_app_id' 和 'event_app_id'。")
            return False

        with self.driver.session(database=self.database) as session:
            try:
                impression_properties = impression_data.copy()
                impression_properties.pop("id", None)
                impression_properties["app_id"] = impression_app_id
                
                # 计算印象强度
                impression_properties["strength"] = self.calculate_impression_strength(character_data, event_data)
                
                # 根据强度决定细节保留程度
                full_content = impression_data.get("content", "")
                if impression_properties["strength"] < 30:
                    # 强度低，保留更少细节
                    content_length = max(5, int(len(full_content) * 0.3))
                    impression_properties["content"] = full_content[:content_length] + "..."
                    impression_properties["is_faded"] = True
                elif impression_properties["strength"] < 70:
                    # 强度中等，保留部分细节
                    content_length = max(10, int(len(full_content) * 0.7))
                    impression_properties["content"] = full_content[:content_length]
                    impression_properties["is_faded"] = False
                else:
                    # 强度高，保留完整细节
                    impression_properties["content"] = full_content
                    impression_properties["is_faded"] = False

                # 将所有嵌套结构转为JSON字符串
                for key, value in impression_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        impression_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (i:Impression {app_id: $impression_app_id})
                    SET i = $properties
                    """,
                    impression_app_id=impression_app_id,
                    properties=impression_properties
                )
                print(f"--- 印象节点 ({impression_app_id}) 创建/更新成功 (强度: {impression_properties['strength']}) ---")
                return True
            except Exception as e:
                print(f"创建印象节点 '{impression_app_id}' 失败: {e}")
                return False

    def create_character_event_impression_triple(self, character_data: Dict[str, Any], event_data: Dict[str, Any], impression_content: str) -> bool:
        """
        为单个角色创建完整的"角色->印象->事件"结构
        impression_content: 已经根据角色视角、性格、时间等处理过的印象内容
        """
        character_app_id = character_data.get("id")
        event_app_id = event_data.get("id")
        if not all([character_app_id, event_app_id, impression_content]):
            print("错误：创建角色-印象-事件三元组缺少必要数据")
            return False
        # 1. 确保角色和事件节点存在
        if not self.create_character_node(character_data):
            return False
        if not self.create_event_node(event_data): # 事件节点将包含原始内容
            return False
        # 2. 创建印象数据 (impression_content 应该已经是处理过的)
        impression_data = {
            "id": str(uuid.uuid4()),
            "source_character_app_id": character_app_id,
            "event_app_id": event_app_id,
            "content": impression_content, # 使用已处理的内容
            "timestamp": datetime.now().isoformat()
        }
        # 3. 创建印象节点（使用新的带强度计算的方法）
        if not self.create_impression_node(impression_data, character_data, event_data):
            return False
        # 4. 建立关系
        with self.driver.session(database=self.database) as session:
            try:
                # 角色 -> 印象
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_app_id}), (i:Impression {app_id: $impression_app_id})
                    MERGE (c)-[:HAS_IMPRESSION]->(i)
                    """,
                    char_app_id=character_app_id,
                    impression_app_id=impression_data["id"]
                )
                # 印象 -> 事件
                session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id}), (e:Event {app_id: $event_app_id})
                    MERGE (i)-[:OF_EVENT]->(e)
                    """,
                    impression_app_id=impression_data["id"],
                    event_app_id=event_app_id
                )
                print(f"--- 角色 {character_app_id} -> 印象 -> 事件 {event_app_id} 三元组创建成功 ---")
                return True
            except Exception as e:
                print(f"创建角色-印象-事件三元组失败: {e}")
                return False

    def create_all_character_event_impressions(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], event_data: Dict[str, Any], impression_contents: Dict[str, str]) -> bool:
        """
        为所有角色（主角色+关联角色）创建"角色->印象->事件"结构
        impression_contents: 字典，键为角色ID，值为该角色对事件的印象内容
        """
        # 为主角色创建印象
        main_char_id = main_character.get("id")
        if main_char_id in impression_contents:
            if not self.create_character_event_impression_triple(
                main_character, 
                event_data, 
                impression_contents[main_char_id]
            ):
                print(f"警告：主角色 {main_char_id} 的印象创建失败")
        
        # 为所有关联角色创建印象
        for char in related_characters:
            char_id = char.get("id")
            if char_id and char_id in impression_contents:
                if not self.create_character_event_impression_triple(
                    char, 
                    event_data, 
                    impression_contents[char_id]
                ):
                    print(f"警告：关联角色 {char_id} 的印象创建失败")
        
        return True


    def connect_entity_to_event(self, entity_app_id: str, event_app_id: str, relationship_type: str = "RELATED_TO") -> bool:
        """
        连接非人物实体到事件。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 确保实体和事件节点存在
                ent_result = session.run(
                    """
                    MATCH (ent) WHERE ent.app_id = $entity_app_id
                    RETURN ent
                    """,
                    entity_app_id=entity_app_id
                ).single()
                if not ent_result:
                    print(f"错误：未找到实体 app_id 为 {entity_app_id} 的节点。")
                    return False

                event_result = session.run(
                    """
                    MATCH (e:Event) WHERE e.app_id = $event_app_id
                    RETURN e
                    """,
                    event_app_id=event_app_id
                ).single()
                if not event_result:
                    print(f"错误：未找到事件 app_id 为 {event_app_id} 的节点。")
                    return False

                # 连接实体 -> 事件
                session.run(
                    f"""
                    MATCH (ent) WHERE ent.app_id = $entity_app_id
                    MATCH (e:Event {{app_id: $event_app_id}})
                    MERGE (ent)-[:{relationship_type}]->(e)
                    """,
                    entity_app_id=entity_app_id,
                    event_app_id=event_app_id
                )
                print(f"--- 实体 {entity_app_id} -> 事件 {event_app_id} (关系: {relationship_type}) 连接成功 ---")
                return True
            except Exception as e:
                print(f"连接实体 {entity_app_id} -> 事件 {event_app_id} 失败: {e}")
                return False

    def create_temporal_chain(self, sorted_events: List[Dict[str, Any]]) -> bool:
        """
        创建事件的时间顺序链。
        sorted_events: 按时间戳排序的事件列表。
        """
        if len(sorted_events) < 2:
            print("事件数量少于2，无需创建时间链。")
            return True

        with self.driver.session(database=self.database) as session:
            try:
                for i in range(len(sorted_events) - 1):
                    current_event_id = sorted_events[i].get("id")
                    next_event_id = sorted_events[i+1].get("id")
                    if not current_event_id or not next_event_id:
                        print(f"警告：事件列表中存在缺失ID，跳过连接。")
                        continue

                    session.run(
                        """
                        MATCH (e1:Event {app_id: $current_event_id}), (e2:Event {app_id: $next_event_id})
                        MERGE (e1)-[:FOLLOWS]->(e2)
                        """,
                        current_event_id=current_event_id,
                        next_event_id=next_event_id
                    )
                    print(f"--- 时间链连接：事件 {current_event_id} -> 事件 {next_event_id} ---")
                print("--- 时间顺序链创建完成 ---")
                return True
            except Exception as e:
                print(f"创建时间顺序链失败: {e}")
                return False

    def get_related_characters(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取与指定角色相关的角色列表。
        通过事件关联。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c1:Character {app_id: $char_id})-[:HAS_IMPRESSION]->(:Impression)-[:OF_EVENT]->(e:Event)<-[:OF_EVENT]-(:Impression)<-[:HAS_IMPRESSION]-(c2:Character)
                    WHERE c1 <> c2
                    RETURN DISTINCT c2
                    """,
                    char_id=character_id
                )

                related_chars = []
                for record in result:
                    char_node = record["c2"]
                    char_props = dict(char_node)
                    for key, value in char_props.items():
                        if isinstance(value, str):
                            try:
                                char_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    related_chars.append(char_props)

                print(f"--- 获取到 {len(related_chars)} 个与角色 {character_id} 相关的角色 ---")
                return related_chars
            except Exception as e:
                print(f"获取角色 {character_id} 的相关角色失败: {e}")
                return []

    def get_character_impressions(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取指定角色的所有印象及其关联的事件。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[:HAS_IMPRESSION]->(i:Impression)-[:OF_EVENT]->(e:Event)
                    RETURN i, e
                    """,
                    char_id=character_id
                )

                impressions = []
                for record in result:
                    impression_node = record["i"]
                    event_node = record["e"]
                    impression_props = dict(impression_node)
                    event_props = dict(event_node)

                    # 合并印象和事件信息
                    combined = {
                        "impression": impression_props,
                        "event": event_props,
                        "event_app_id": event_props.get("app_id"),
                        "impression_app_id": impression_props.get("app_id")
                    }

                    # 解析JSON字段
                    for key, value in combined["impression"].items():
                        if isinstance(value, str):
                            try:
                                combined["impression"][key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    
                    for key, value in combined["event"].items():
                        if isinstance(value, str):
                            try:
                                combined["event"][key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass

                    impressions.append(combined)

                print(f"--- 获取到 {len(impressions)} 条角色 {character_id} 的印象 ---")
                return impressions
            except Exception as e:
                print(f"获取角色 {character_id} 的印象失败: {e}")
                return []

    def get_event_details(self, event_id: str) -> List[Dict[str, Any]]:
        """
        获取事件的所有细节节点（物品、动作、对话等）
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (e:Event {app_id: $event_id})-[:HAS_DETAIL]->(d)
                    RETURN d
                    """,
                    event_id=event_id
                )

                details = []
                for record in result:
                    detail_node = record["d"]
                    detail_props = dict(detail_node)
                    
                    # 解析JSON字段
                    for key, value in detail_props.items():
                        if isinstance(value, str):
                            try:
                                detail_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    
                    details.append(detail_props)

                print(f"--- 获取到 {len(details)} 个事件 {event_id} 的细节 ---")
                return details
            except Exception as e:
                print(f"获取事件 {event_id} 的细节失败: {e}")
                return []

    def delete_character_graph(self, character_id: str) -> bool:
        """
        删除指定角色及其关联的图谱数据（印象、关系）。
        保留事件和细节节点，因为它们可能与其他角色相关。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 1. 删除角色 -> 印象的关系和印象节点
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[r:HAS_IMPRESSION]->(i:Impression)
                    DELETE r, i
                    """,
                    char_id=character_id
                )
                # 2. 删除角色本身
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})
                    DELETE c
                    """,
                    char_id=character_id
                )
                print(f"--- 角色 {character_id} 及其关联的印象节点已删除 ---")
                return True
            except Exception as e:
                print(f"删除角色 {character_id} 的图谱数据失败: {e}")
                return False

    def update_impression_over_time(self, impression_app_id: str) -> bool:
        """
        模拟印象随时间自然变化（淡忘）。
        根据当前强度应用不同的衰减因子
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 获取当前印象内容和强度
                result = session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id})
                    RETURN i.impression_content AS current_content, i.content AS content, i.strength AS current_strength
                    """,
                    impression_app_id=impression_app_id
                ).single()

                if not result:
                    print(f"错误：未找到印象 ID 为 {impression_app_id} 的节点。")
                    return False

                current_content = result["content"] or result["current_content"] or ""
                current_strength = result["current_strength"] or 100

                # 根据当前强度应用不同的衰减因子
                if current_strength < 30:
                    decay_factor = 0.8  # 弱记忆衰减更快
                elif current_strength < 70:
                    decay_factor = 0.9  # 中等记忆正常衰减
                else:
                    decay_factor = 0.95  # 强记忆衰减较慢

                # 计算新的强度和内容
                new_strength = max(5, int(current_strength * decay_factor))
                content_length = max(5, int(len(current_content) * decay_factor))
                new_content = current_content[:content_length] + ("..." if len(current_content) > content_length else "")

                session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id})
                    SET i.content = $new_content, i.strength = $new_strength, i.last_updated = $timestamp
                    """,
                    impression_app_id=impression_app_id,
                    new_content=new_content,
                    new_strength=new_strength,
                    timestamp=datetime.now().isoformat()
                )
                print(f"--- 印象 {impression_app_id} 已更新 (强度: {new_strength}, 内容长度: {len(new_content)}) ---")
                return True
            except Exception as e:
                print(f"更新印象 {impression_app_id} 失败: {e}")
                return False

    def save_entities_and_relationships_to_csv(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]], memories: List[Dict[str, Any]], character_id: str, character_to_character_relationships: List[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        将所有数据（主角色、关联角色、实体、关系、记忆）保存为统一格式的 CSV 文件。
        """
        print(f"--- 开始将数据保存为统一格式的 CSV (新模型, 修复类型和引号 - 使用Base64) ---")
        nodes_filename = os.path.join(self.temp_csv_dir, f"story_nodes_{character_id}.csv")
        relationships_filename = os.path.join(self.temp_csv_dir, f"story_relationships_{character_id}.csv") # 非人物实体-事件关系
        impressions_filename = os.path.join(self.temp_csv_dir, f"story_impressions_{character_id}.csv")
        temporal_chain_filename = os.path.join(self.temp_csv_dir, f"temporal_chain_{character_id}.csv")
        details_filename = os.path.join(self.temp_csv_dir, f"event_details_{character_id}.csv")
        # --- 新增：角色间关系 CSV 文件名 ---
        char_to_char_relationships_filename = os.path.join(self.temp_csv_dir, f"character_to_character_relationships_{character_id}.csv")
        # ---
        # 创建一个角色ID映射表，用于去重
        all_character_ids = set()
        all_character_ids.add(main_character.get('id'))
        for rc in related_characters:
            all_character_ids.add(rc.get('id'))
        # 从记忆中收集所有参与者ID
        for memory in memories:
            participants = memory.get('participants', [])
            for pid in participants:
                all_character_ids.add(pid)
        # 创建一个角色字典，键为 app_id，值为角色数据
        character_map = {}
        character_map[main_character.get('id')] = main_character
        for rc in related_characters:
            character_map[rc.get('id')] = rc
        # --- 保存节点 CSV (Character, Event, 其他实体) ---
        # ... (节点CSV保存逻辑，保持不变)
        with open(nodes_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'node_id', 'label', 'name', 'app_id', 'age', 'gender', 'occupation', 'hobby', 'skill',
                'values', 'living_habit', 'dislike', 'language_style', 'appearance', 'family_status',
                'education', 'social_pattern', 'favorite_thing', 'usual_place', 'past_experience',
                'speech_style', 'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism',
                'is_protagonist', 'entity_type', 'description', 'event_title', 'event_content', 'event_age', 'event_importance', 'properties'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            # 1. 写入所有角色节点 (去重后)
            for char_id in all_character_ids:
                char_data = character_map.get(char_id)
                if not char_data:
                    continue
                char_node_id = str(uuid.uuid4())
                char_props = {
                    'node_id': char_node_id,
                    'label': 'Character',
                    'name': char_data.get('name', ''),
                    'app_id': char_data.get('id', ''),
                    'age': char_data.get('age', ''),
                    'gender': char_data.get('gender', ''),
                    'occupation': char_data.get('occupation', ''),
                    'hobby': char_data.get('hobby', ''),
                    'skill': char_data.get('skill', ''),
                    'values': char_data.get('values', ''),
                    'living_habit': char_data.get('living_habit', ''),
                    'dislike': char_data.get('dislike', ''),
                    'language_style': char_data.get('language_style', ''),
                    'appearance': char_data.get('appearance', ''),
                    'family_status': char_data.get('family_status', ''),
                    'education': char_data.get('education', ''),
                    'social_pattern': char_data.get('social_pattern', ''),
                    'favorite_thing': char_data.get('favorite_thing', ''),
                    'usual_place': char_data.get('usual_place', ''),
                    'past_experience': char_data.get('past_experience', ''),
                    'speech_style': char_data.get('speech_style', ''),
                    'openness': char_data.get('personality', {}).get('openness', ''),
                    'conscientiousness': char_data.get('personality', {}).get('conscientiousness', ''),
                    'extraversion': char_data.get('personality', {}).get('extraversion', ''),
                    'agreeableness': char_data.get('personality', {}).get('agreeableness', ''),
                    'neuroticism': char_data.get('personality', {}).get('neuroticism', ''),
                    'is_protagonist': 'True' if char_id == main_character.get('id') else 'False',
                    'entity_type': 'Character',
                    'description': char_data.get('background', '')
                }
                props_to_exclude = set(fieldnames) - {'node_id', 'label', 'name', 'app_id', 'age', 'gender', 'occupation', 'hobby', 'skill', 'values', 'living_habit', 'dislike', 'language_style', 'appearance', 'family_status', 'education', 'social_pattern', 'favorite_thing', 'usual_place', 'past_experience', 'speech_style', 'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism', 'is_protagonist', 'entity_type', 'description', 'event_title', 'event_content', 'event_age', 'event_importance', 'properties'}
                dynamic_props = {k: v for k, v in char_data.items() if k not in props_to_exclude and k not in char_props}
                for k, v in dynamic_props.items():
                    if isinstance(v, (dict, list)):
                        dynamic_props[k] = json.dumps(v, ensure_ascii=False)
                json_str = json.dumps(dynamic_props, ensure_ascii=False)
                char_props['properties'] = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                writer.writerow(char_props)
            # 2. 写入事件节点 (从记忆中提取)
            event_node_map = {}
            for memory in memories:
                event_node_id = str(uuid.uuid4())
                event_node_map[memory.get('id')] = event_node_id
                event_props = {
                    'node_id': event_node_id,
                    'label': 'Event',
                    'name': memory.get('title', ''),
                    'app_id': memory.get('id', ''),
                    'entity_type': 'Event',
                    'event_title': memory.get('title', ''),
                    'event_content': memory.get('content', ''), # **事件节点使用原文**
                    'event_age': memory.get('time', {}).get('age', ''),
                    'event_importance': memory.get('importance', {}).get('score', ''),
                    'description': memory.get('content', '')[:100] # **事件节点的描述也使用原文**
                }
                dynamic_props_mem = {k: v for k, v in memory.items() if k not in ['title', 'content', 'time', 'importance', 'id', 'app_id', 'node_id', 'label', 'name', 'entity_type', 'event_title', 'event_content', 'event_age', 'event_importance', 'description', 'properties']}
                for k, v in dynamic_props_mem.items():
                    if isinstance(v, (dict, list)):
                        dynamic_props_mem[k] = json.dumps(v, ensure_ascii=False)
                json_str_mem = json.dumps(dynamic_props_mem, ensure_ascii=False)
                event_props['properties'] = base64.b64encode(json_str_mem.encode('utf-8')).decode('utf-8')
                writer.writerow(event_props)
            # 3. 写入非人物实体节点
            entity_node_map = {}
            for entity in entities:
                ent_node_id = str(uuid.uuid4())
                entity_node_map[entity.get('app_id')] = ent_node_id
                ent_props = {
                    'node_id': ent_node_id,
                    'label': entity.get('type', 'Entity').capitalize(),
                    'name': entity.get('name', ''),
                    'app_id': entity.get('app_id', ''),
                    'entity_type': entity.get('type', 'Entity').upper(),
                    'description': entity.get('description', '')
                }
                dynamic_props_ent = entity.get('properties', {})
                for k, v in dynamic_props_ent.items():
                    if isinstance(v, (dict, list)):
                        dynamic_props_ent[k] = json.dumps(v, ensure_ascii=False)
                json_str_ent = json.dumps(dynamic_props_ent, ensure_ascii=False)
                ent_props['properties'] = base64.b64encode(json_str_ent.encode('utf-8')).decode('utf-8')
                writer.writerow(ent_props)
        print(f"--- 节点 CSV 文件已保存至: {nodes_filename} ---")

        # --- 保存事件细节 CSV ---
        # ... (事件细节CSV保存逻辑，保持不变)
        with open(details_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['detail_id', 'event_app_id', 'type', 'content', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for memory in memories:
                event_app_id = memory.get('id')
                if not event_app_id:
                    continue
                # 提取事件细节（假设在memory的details字段中）
                details = memory.get('details', [])
                for detail in details:
                    detail_id = str(uuid.uuid4())
                    detail_props = {
                        'detail_id': detail_id,
                        'event_app_id': event_app_id,
                        'type': detail.get('type', 'DETAIL'),
                        'content': detail.get('content', '')
                    }
                    dynamic_props = {k: v for k, v in detail.items() if k not in ['type', 'content', 'detail_id', 'event_app_id', 'properties']}
                    for k, v in dynamic_props.items():
                        if isinstance(v, (dict, list)):
                            dynamic_props[k] = json.dumps(v, ensure_ascii=False)
                    json_str = json.dumps(dynamic_props, ensure_ascii=False)
                    detail_props['properties'] = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                    writer.writerow(detail_props)
        print(f"--- 事件细节 CSV 文件已保存至: {details_filename} ---")

        # --- 保存印象关系 CSV (Character -> Impression -> Event) ---
        # ... (印象关系CSV保存逻辑，**修改**如下) ...
        with open(impressions_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['impression_id', 'character_app_id', 'event_app_id', 'impression_content', 'strength', 'timestamp', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for memory in memories:
                event_app_id = memory.get('id')
                if not event_app_id:
                    continue
                participants = memory.get('participants', [])
                original_content = memory.get('content', '') # 获取原始事件内容
                timestamp = memory.get('time', {}).get('specific', datetime.now().isoformat())
                # **修改：为每个参与者生成一个印象**
                for participant_id in participants:
                    char_app_id = participant_id
                    if not char_app_id:
                        continue
                    # 获取角色数据
                    char_data = character_map.get(char_app_id, {})
                    # **调用新方法处理印象内容**
                    processed_impression_content = self._process_impression_content(original_content, char_data, memory)
                    # 计算强度
                    calculated_strength = self.calculate_impression_strength(char_data, memory)
                    impression_id = str(uuid.uuid4())
                    impression_props = {
                        'impression_id': impression_id,
                        'character_app_id': char_app_id,
                        'event_app_id': event_app_id,
                        'impression_content': processed_impression_content, # **使用处理后的内容**
                        'strength': calculated_strength,
                        'timestamp': timestamp,
                    }
                    dynamic_props_imp = {k: v for k, v in memory.items() if k not in ['id', 'participants', 'content', 'time', 'importance', 'impression_id', 'character_app_id', 'event_app_id', 'impression_content', 'strength', 'timestamp', 'properties']}
                    for k, v in dynamic_props_imp.items():
                        if isinstance(v, (dict, list)):
                            dynamic_props_imp[k] = json.dumps(v, ensure_ascii=False)
                    json_str_imp = json.dumps(dynamic_props_imp, ensure_ascii=False)
                    impression_props['properties'] = base64.b64encode(json_str_imp.encode('utf-8')).decode('utf-8')
                    writer.writerow(impression_props)
        print(f"--- 印象关系 CSV 文件已保存至: {impressions_filename} ---")

        # --- 保存非人物实体到事件的关系 CSV ---
        # ... (实体-事件关系CSV保存逻辑，保持不变)
        with open(relationships_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['relation_id', 'entity_app_id', 'event_app_id', 'relationship_type', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for memory in memories:
                event_app_id = memory.get('id')
                if not event_app_id:
                    continue
                mem_location = memory.get('location')
                if mem_location:
                    location_entity_app_id = None
                    for ent in entities:
                        if ent.get('name') == mem_location:
                            location_entity_app_id = ent.get('app_id')
                            break
                    if location_entity_app_id:
                        rel_id = str(uuid.uuid4())
                        rel_props = {
                            'relation_id': rel_id,
                            'entity_app_id': location_entity_app_id,
                            'event_app_id': event_app_id,
                            'relationship_type': 'HAPPENED_AT',
                        }
                        json_str_rel = json.dumps({}, ensure_ascii=False)
                        rel_props['properties'] = base64.b64encode(json_str_rel.encode('utf-8')).decode('utf-8')
                        writer.writerow(rel_props)
                for tag in memory.get('tags', []):
                    tag_entity_app_id = None
                    for ent in entities:
                        if ent.get('name') == tag:
                            tag_entity_app_id = ent.get('app_id')
                            break
                    if tag_entity_app_id:
                        rel_id = str(uuid.uuid4())
                        rel_props = {
                            'relation_id': rel_id,
                            'entity_app_id': tag_entity_app_id,
                            'event_app_id': event_app_id,
                            'relationship_type': 'TAGGED_AS',
                        }
                        json_str_rel = json.dumps({}, ensure_ascii=False)
                        rel_props['properties'] = base64.b64encode(json_str_rel.encode('utf-8')).decode('utf-8')
                        writer.writerow(rel_props)
        print(f"--- 实体-事件关系 CSV 文件已保存至: {relationships_filename} ---")

        # --- 新增：保存角色间关系 CSV ---
        if character_to_character_relationships:
            with open(char_to_char_relationships_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['relationship_id', 'from_character_app_id', 'to_character_app_id', 'relationship_type', 'description', 'strength', 'properties']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for rel in character_to_character_relationships:
                    rel_props = {
                        'relationship_id': rel.get('relationship_id', str(uuid.uuid4())),
                        'from_character_app_id': rel.get('from_character_app_id'),
                        'to_character_app_id': rel.get('to_character_app_id'),
                        'relationship_type': rel.get('relationship_type', 'UNKNOWN'),
                        'description': rel.get('description', ''),
                        'strength': rel.get('strength', 50)
                    }
                    # 可以将其他关系属性存入properties
                    dynamic_props_rel = {k: v for k, v in rel.items() if k not in ['relationship_id', 'from_character_app_id', 'to_character_app_id', 'relationship_type', 'description', 'strength', 'properties']}
                    for k, v in dynamic_props_rel.items():
                        if isinstance(v, (dict, list)):
                            dynamic_props_rel[k] = json.dumps(v, ensure_ascii=False)
                    json_str_rel = json.dumps(dynamic_props_rel, ensure_ascii=False)
                    rel_props['properties'] = base64.b64encode(json_str_rel.encode('utf-8')).decode('utf-8')
                    writer.writerow(rel_props)
            print(f"--- 角色间关系 CSV 文件已保存至: {char_to_char_relationships_filename} ---")
        else:
            print("--- 没有角色间关系需要保存 ---")
        # ---

        # --- 保存时间链 CSV ---
        # ... (时间链CSV保存逻辑，保持不变)
        sorted_memories = sorted(memories, key=lambda m: (m.get('time', {}).get('age', 0), m.get('time', {}).get('specific', '')))
        with open(temporal_chain_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['current_event_app_id', 'next_event_app_id']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for i in range(len(sorted_memories) - 1):
                current_event_id = sorted_memories[i].get('id')
                next_event_id = sorted_memories[i+1].get('id')
                if current_event_id and next_event_id:
                    writer.writerow({
                        'current_event_app_id': current_event_id,
                        'next_event_app_id': next_event_id
                    })
        print(f"--- 时间链 CSV 文件已保存至: {temporal_chain_filename} ---")

        # --- 修改返回值，包含角色间关系文件名 ---
        result = {
            "nodes_file": os.path.basename(nodes_filename),
            "impressions_file": os.path.basename(impressions_filename),
            "entity_event_relationships_file": os.path.basename(relationships_filename),
            "temporal_chain_file": os.path.basename(temporal_chain_filename),
            "details_file": os.path.basename(details_filename)
        }
        if character_to_character_relationships:
            result["char_to_char_relationships_file"] = os.path.basename(char_to_char_relationships_filename)
        # ---
        return result




    def import_nodes_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从统一 CSV 文件导入节点: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    CALL apoc.create.node([row.label], {{
                        node_id: row.node_id,
                        name: row.name,
                        app_id: row.app_id,
                        age: CASE row.age WHEN '' THEN null ELSE toInteger(row.age) END,
                        gender: row.gender,
                        occupation: row.occupation,
                        hobby: row.hobby,
                        skill: row.skill,
                        values: row.values,
                        living_habit: row.living_habit,
                        dislike: row.dislike,
                        language_style: row.language_style,
                        appearance: row.appearance,
                        family_status: row.family_status,
                        education: row.education,
                        social_pattern: row.social_pattern,
                        favorite_thing: row.favorite_thing,
                        usual_place: row.usual_place,
                        past_experience: row.past_experience,
                        speech_style: row.speech_style,
                        openness: CASE row.openness WHEN '' THEN null ELSE toInteger(row.openness) END,
                        conscientiousness: CASE row.conscientiousness WHEN '' THEN null ELSE toInteger(row.conscientiousness) END,
                        extraversion: CASE row.extraversion WHEN '' THEN null ELSE toInteger(row.extraversion) END,
                        agreeableness: CASE row.agreeableness WHEN '' THEN null ELSE toInteger(row.agreeableness) END,
                        neuroticism: CASE row.neuroticism WHEN '' THEN null ELSE toInteger(row.neuroticism) END,
                        is_protagonist: CASE row.is_protagonist WHEN 'True' THEN true WHEN 'False' THEN false ELSE null END,
                        entity_type: row.entity_type,
                        description: row.description,
                        event_title: row.event_title,
                        event_content: row.event_content,
                        event_age: CASE row.event_age WHEN '' THEN null ELSE toInteger(row.event_age) END,
                        event_importance: CASE row.event_importance WHEN '' THEN null ELSE toInteger(row.event_importance) END,
                        properties: row.properties
                    }}) YIELD node
                    RETURN node
                }}
                RETURN count(node) AS importedNodes;
                """
                result = session.run(query)
                count = result.single()["importedNodes"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 个节点 ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入节点失败: {e}")
                try:
                    query_basic_simple = f"""
                    LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                    CALL (row) {{
                        WITH row
                        CALL apoc.create.node([row.label], {{
                            node_id: row.node_id,
                            name: row.name,
                            app_id: row.app_id,
                            age: CASE row.age WHEN '' THEN null ELSE toInteger(row.age) END,
                            gender: row.gender,
                            occupation: row.occupation,
                            hobby: row.hobby,
                            skill: row.skill,
                            values: row.values,
                            living_habit: row.living_habit,
                            dislike: row.dislike,
                            language_style: row.language_style,
                            appearance: row.appearance,
                            family_status: row.family_status,
                            education: row.education,
                            social_pattern: row.social_pattern,
                            favorite_thing: row.favorite_thing,
                            usual_place: row.usual_place,
                            past_experience: row.past_experience,
                            speech_style: row.speech_style,
                            openness: CASE row.openness WHEN '' THEN null ELSE toInteger(row.openness) END,
                            conscientiousness: CASE row.conscientiousness WHEN '' THEN null ELSE toInteger(row.conscientiousness) END,
                            extraversion: CASE row.extraversion WHEN '' THEN null ELSE toInteger(row.extraversion) END,
                            agreeableness: CASE row.agreeableness WHEN '' THEN null ELSE toInteger(row.agreeableness) END,
                            neuroticism: CASE row.neuroticism WHEN '' THEN null ELSE toInteger(row.neuroticism) END,
                            is_protagonist: CASE row.is_protagonist WHEN 'True' THEN true WHEN 'False' THEN false ELSE null END,
                            entity_type: row.entity_type,
                            description: row.description,
                            event_title: row.event_title,
                            event_content: row.event_content,
                            event_age: CASE row.event_age WHEN '' THEN null ELSE toInteger(row.event_age) END,
                            event_importance: CASE row.event_importance WHEN '' THEN null ELSE toInteger(row.event_importance) END
                        }}) YIELD node
                        RETURN node
                    }}
                    RETURN count(node) AS importedNodes;
                    """
                    result_basic = session.run(query_basic_simple)
                    count_basic = result_basic.single()["importedNodes"]
                    print(f"--- 使用基础查询成功从 {csv_filename} 导入 {count_basic} 个节点 ---")
                    return True
                except Exception as e2:
                    print(f"基础查询从 {csv_filename} 导入节点也失败: {e2}")
                    return False

    def import_event_details_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入事件细节: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建细节节点
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    CALL apoc.create.node([row.type], {{
                        app_id: row.detail_id,
                        content: row.content,
                        event_app_id: row.event_app_id,
                        properties: row.properties
                    }}) YIELD node
                    RETURN node
                }}
                RETURN count(node) AS createdDetails;
                """
                result_create = session.run(query_create)
                count_create = result_create.single()["createdDetails"]
                print(f"--- 成功创建 {count_create} 个事件细节节点 ---")

                # 2. 连接事件到细节
                query_connect = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (e:Event {{app_id: row.event_app_id}}), (d) WHERE d.app_id = row.detail_id
                CALL apoc.create.relationship(e, 'HAS_DETAIL', {{}}, d) YIELD rel
                RETURN count(rel) AS connectedDetails;
                """
                result_connect = session.run(query_connect)
                count_connect = result_connect.single()["connectedDetails"]
                print(f"--- 成功连接 {count_connect} 条事件-细节关系 ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入事件细节失败: {e}")
                return False

    def import_impressions_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入印象关系: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建印象节点
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    CALL apoc.create.node(['Impression'], {{
                        app_id: row.impression_id,
                        impression_content: row.impression_content,
                        strength: toInteger(row.strength),
                        timestamp: row.timestamp,
                        properties: row.properties
                    }}) YIELD node
                    RETURN node
                }}
                RETURN count(node) AS createdImpressions;
                """
                result_create = session.run(query_create)
                count_create = result_create.single()["createdImpressions"]
                print(f"--- 成功创建 {count_create} 个印象节点 ---")

                # 2. 连接 Character -> Impression -> Event
                query_connect = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (c:Character {{app_id: row.character_app_id}}), (i:Impression {{app_id: row.impression_id}}), (e:Event {{app_id: row.event_app_id}})
                CALL apoc.create.relationship(c, 'HAS_IMPRESSION', {{}}, i) YIELD rel AS rel1
                CALL apoc.create.relationship(i, 'OF_EVENT', {{}}, e) YIELD rel AS rel2
                RETURN count(rel1) AS connectedCharacterToImpression, count(rel2) AS connectedImpressionToEvent;
                """
                result_connect = session.run(query_connect)
                counts = result_connect.single()
                print(f"--- 成功连接 {counts['connectedCharacterToImpression']} 条 Character->Impression 关系 ---")
                print(f"--- 成功连接 {counts['connectedImpressionToEvent']} 条 Impression->Event 关系 ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入印象关系失败: {e}")
                return False

    def import_entity_event_relationships_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入实体-事件关系: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (ent) WHERE ent.app_id = row.entity_app_id
                MATCH (e:Event {{app_id: row.event_app_id}})
                CALL apoc.create.relationship(ent, row.relationship_type, {{properties: row.properties}}, e) YIELD rel
                RETURN count(rel) AS importedRelationships;
                """
                result = session.run(query)
                count = result.single()["importedRelationships"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 条实体-事件关系 ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入实体-事件关系失败: {e}")
                return False

    def import_temporal_chain_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入时间链: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (e1:Event {{app_id: row.current_event_app_id}}), (e2:Event {{app_id: row.next_event_app_id}})
                CALL apoc.create.relationship(e1, 'FOLLOWS', {{}}, e2) YIELD rel
                RETURN count(rel) AS importedChains;
                """
                result = session.run(query)
                count = result.single()["importedChains"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 条时间链关系 ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入时间链失败: {e}")
                return False

    def import_character_to_character_relationships_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False
        print(f"--- 开始从 CSV 文件导入角色间关系: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"
        with self.driver.session(database=self.database) as session:
            try:
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    // 确保两端的角色节点存在
                    MERGE (from_char:Character {{app_id: row.from_character_app_id}})
                    MERGE (to_char:Character {{app_id: row.to_character_app_id}})
                    // 创建或更新关系
                    MERGE (from_char)-[r:HAS_RELATIONSHIP {{to_character_app_id: row.to_character_app_id}}]->(to_char)
                    SET r.type = row.relationship_type,
                        r.description = row.description,
                        r.strength = toInteger(row.strength),
                        r.last_updated = $timestamp,
                        r.properties = row.properties
                }}
                RETURN count(*) AS importedRelationships; /* 使用 count(*) 替代 count(r) */
                """
                result = session.run(query, timestamp=datetime.now().isoformat())
                count = result.single()["importedRelationships"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 条角色间关系 ---")
                return True
            except Exception as e:
                print(f"使用复杂查询从 CSV {csv_filename} 导入角色间关系失败: {e}")
                import traceback
                traceback.print_exc()
                # 尝试一个更简单的查询，如果上面的因为其他原因失败
                try:
                    query_simple = f"""
                    LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                    MATCH (from_char:Character {{app_id: row.from_character_app_id}}), (to_char:Character {{app_id: row.to_character_app_id}})
                    CALL apoc.create.relationship(from_char, 'HAS_RELATIONSHIP', {{
                        type: row.relationship_type,
                        description: row.description,
                        strength: toInteger(row.strength),
                        last_updated: $timestamp,
                        properties: row.properties,
                        to_character_app_id: row.to_character_app_id
                    }}, to_char) YIELD rel
                    RETURN count(rel) AS importedRelationships;
                    """
                    result_simple = session.run(query_simple, timestamp=datetime.now().isoformat())
                    count_simple = result_simple.single()["importedRelationships"]
                    print(f"--- 使用简化查询成功从 CSV {csv_filename} 导入 {count_simple} 条角色间关系 ---")
                    return True
                except Exception as e2:
                    print(f"简化查询从 CSV {csv_filename} 导入角色间关系也失败: {e2}")
                    return False

    def get_relationship_between_characters(self, from_char_id: str, to_char_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 from_char_id 角色对 to_char_id 角色的关系信息。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c1:Character {app_id: $from_char_id})-[r:HAS_RELATIONSHIP {to_character_app_id: $to_char_id}]->(c2:Character {app_id: $to_char_id})
                    RETURN r
                    """,
                    from_char_id=from_char_id,
                    to_char_id=to_char_id
                )
                record = result.single()
                if record:
                    rel_props = dict(record["r"])
                    # 解析JSON字段（如果有的话）
                    for key, value in rel_props.items():
                        if isinstance(value, str):
                            try:
                                rel_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    return rel_props
                else:
                    print(f"--- 未找到角色 {from_char_id} 对 {to_char_id} 的关系 ---")
                    return None
            except Exception as e:
                print(f"获取角色 {from_char_id} -> {to_char_id} 的关系失败: {e}")
                return None

    # --- 新增：处理印象内容的辅助方法 ---
    # --- 修改：根据角色性格、事件性质、时间因素处理印象内容的方法 ---
    def _process_impression_content(self, original_content: str, character_data: Dict[str, Any], memory_data: Dict[str, Any]) -> str:
        """
        根据角色性格、事件性质、时间因素处理原始事件内容，生成角色对事件的印象（含压缩、细节遗忘、印象扭曲）。
        核心逻辑：性格特质与事件性质为主要影响因素，时间作为衰减调节因素，通过多层量化模型实现印象生成。
        """
        # -------------------------- 1. 基础参数提取 --------------------------
        # 1.1 角色性格特质（基于大五人格模型，0-100分，从character_data获取）
        personality = character_data.get('personality', {})
        neuroticism = personality.get('neuroticism', 50)  # 神经质（情绪敏感度）
        conscientiousness = personality.get('conscientiousness', 50)  # 尽责性（严谨程度）
        openness = personality.get('openness', 50)  # 开放性（细节关注度）
        extraversion = personality.get('extraversion', 50)  # 外向性（大大咧咧程度）

        # 1.2 事件性质参数（从memory_data获取，0-10分）
        event_nature = memory_data.get('event_nature', {})
        emotional_intensity = event_nature.get('emotional_intensity', memory_data.get('emotion', {}).get('intensity', 5))
        importance = memory_data.get('importance', {}).get('score', 5)
        event_type = event_nature.get('type', 'neutral')

        # 1.3 时间参数（从memory_data获取）
        # **修改：优先使用 age 差计算天数**
        memory_time_info = memory_data.get('time', {})
        event_age_at_occurrence = memory_time_info.get('age', character_data.get('age', 0)) # 事件发生时角色年龄
        current_character_age = character_data.get('age', 0) # 角色当前设定年龄
        # 计算年龄差（年）
        age_difference_years = current_character_age - event_age_at_occurrence
        # 将年龄差转换为天数（假设一年约365天）
        # 这是一个估算，但比解析字符串更可靠
        days_passed = max(0, int(age_difference_years * 365))
        print(f"  [DEBUG] 计算时间衰减: 事件时年龄 {event_age_at_occurrence}, 当前年龄 {current_character_age}, 年龄差 {age_difference_years}, 估算天数 {days_passed}")

        # **备选：如果 memory.time.age 不存在或无效，再尝试使用 specific_time_str**
        if days_passed <= 0:
            specific_time_str = memory_time_info.get('specific', '').strip()
            if specific_time_str:
                try:
                    # 尝试解析 specific_time_str 为 datetime 对象
                    # 这里需要一个更灵活的解析器，但为了通用性，我们先尝试 ISO 格式
                    # 如果不是 ISO 格式，解析会失败，然后使用 importance 作为 fallbac
                    iso_time_str = specific_time_str.replace('年', '-').replace('月', '-').replace('日', 'T') + '00:00:00'
                    event_time = datetime.fromisoformat(iso_time_str)
                    current_time = datetime.now()
                    calculated_days_passed = (current_time - event_time).days
                    calculated_days_passed = max(0, calculated_days_passed) # 确保不为负数
                    # 如果通过 specific_time_str 计算出的天数更合理，则使用它
                    if calculated_days_passed > 0:
                        days_passed = calculated_days_passed
                        print(f"  [DEBUG] 通过 specific_time 重新计算天数: {days_passed}")
                except ValueError:
                    # 如果解析失败，使用 importance 估算作为备选
                    days_passed = max(0, int((10 - importance) * 365 / 9))
                    print(f"  [DEBUG] 无法解析 specific_time: '{specific_time_str}', 使用基于 importance 的估算: {days_passed} 天")
            else:
                # 如果 specific_time_str 也为空，使用 importance 估算
                days_passed = max(0, int((10 - importance) * 365 / 9))
                print(f"  [DEBUG] 未找到 specific_time, 使用基于 importance 的估算: {days_passed} 天")


        # -------------------------- 2. 核心影响指标计算 --------------------------
        # 2.1 性格特质量化：细致度（反应该人是否容易记住细节，0-1）
        detail_orientation = (
            0.3 * neuroticism +
            0.4 * conscientiousness +
            0.2 * openness -
            0.1 * extraversion
        ) / 100
        detail_orientation = max(0.1, min(detail_orientation, 0.9))

        # 2.2 事件性质量化：事件显著性（反应该事件本身是否容易被记住，0-1）
        event_saliency = (0.6 * emotional_intensity + 0.4 * importance) / 10
        event_saliency = max(0.1, min(event_saliency, 0.9))

        # 2.3 时间衰减量化：记忆留存衰减系数（0-1）
        time_decay = min(1.0, max(0.05, float(2.71828 **(-0.005 * days_passed))))

        # 2.4 综合记忆保留强度（决定整体细节保留比例，0-1）
        retention_strength = (0.5 * detail_orientation + 0.5 * event_saliency) * time_decay


        # -------------------------- 3. 内容基础压缩（基于保留强度） --------------------------
        compression_ratio = 0.2 + 0.8 * retention_strength
        original_length = len(original_content)
        base_retain_length = int(original_length * compression_ratio)
        base_retain_length = max(10, min(base_retain_length, original_length))

        core_pattern = re.compile(r'(.*?[，。；？！])')
        sentences = core_pattern.findall(original_content)
        if not sentences:
            sentences = [original_content]
        sorted_sentences = sorted(sentences, key=lambda x: len(x), reverse=True)  # 长句更可能含核心信息
        core_content = ''.join(sorted_sentences[:int(len(sentences)*compression_ratio)])
        compressed_content = core_content[:base_retain_length]


        # -------------------------- 4. 细节类型筛选（基于性格特质） --------------------------
        detail_types = {
            'dialogue': re.compile(r'“.*?”|‘.*?’'),
            'objects': re.compile(r'[那这某]+[一-龥a-zA-Z0-9]*[个只件台辆]{1}[一-龥a-zA-Z0-9]*'),
            'scene': re.compile(r'[早中晚昨今明]{1}.*?[处地场合]{1}|[0-9]{1,2}[点分]{1}'),
            'emotion': re.compile(r'[开心|难过|生气|害怕|惊讶]{1}')
        }

        detail_retain_probs = {
            'dialogue': 0.3 + detail_orientation * 0.6,
            'objects': 0.2 + detail_orientation * 0.7,
            'scene': 0.6 + detail_orientation * 0.3,
            'emotion': 0.4 + event_saliency * 0.5
        }

        filtered_content = compressed_content
        for detail_name, pattern in detail_types.items():
            if detail_retain_probs[detail_name] < 0.5:
                replacement = {
                    'dialogue': '说了些话',
                    'objects': '某个东西',
                    'scene': '某个时候',
                    'emotion': '有些情绪'
                }[detail_name]
                filtered_content = pattern.sub(replacement, filtered_content)


        # -------------------------- 5. 印象扭曲（基于性格与事件类型） --------------------------
        distortion_factor = (0.4 * neuroticism + 0.3 * (100 - conscientiousness) + 0.3 * openness) / 100

        distorted_content = filtered_content
        if distortion_factor > 0.6:
            if event_type == 'negative':
                distorted_content = re.sub(r'有点', '非常', distorted_content)
                distorted_content = re.sub(r'可能', '肯定', distorted_content)
            elif event_type == 'positive':
                distorted_content = re.sub(r'还不错', '特别好', distorted_content)
            distorted_content = f"好像{distorted_content}，我记得大概是这样..."
        elif 0.3 < distortion_factor <= 0.6:
            if extraversion > 70:
                distorted_content = re.sub(r'，.*?[。；]', '。', distorted_content)

        return distorted_content

if __name__ == "__main__":
    try:
        graph_store = GraphStore(
            uri="bolt://neo4j-latest:7687",
            user="neo4j",
            password="zyh123456",
            database="neo4j"
        )
        graph_store.close()
    except Exception as e:
        print(f"初始化 GraphStore 失败: {e}")