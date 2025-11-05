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
"""

import os
import json
import uuid
import csv
import base64
from datetime import datetime
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
        使用角色名称作为唯一标识，避免重复创建。
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

                # **关键修改**：在设置到数据库之前，将所有嵌套结构转为JSON字符串
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
        根据实体类型创建不同标签的节点，并使用 name 作为唯一标识。
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

                # **关键修改**：在设置到数据库之前，将所有嵌套结构转为JSON字符串
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
        创建事件节点。
        """
        event_app_id = event_data.get("id", str(uuid.uuid4()))
        event_data["id"] = event_app_id
        event_title = event_data.get("title", "未命名事件")

        with self.driver.session(database=self.database) as session:
            try:
                event_properties = event_data.copy()
                event_properties.pop("id", None)
                event_properties["app_id"] = event_app_id

                # **关键修改**：在设置到数据库之前，将所有嵌套结构转为JSON字符串
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

    def create_impression_node(self, impression_data: Dict[str, Any]) -> bool:
        """
        创建印象节点。
        """
        impression_app_id = impression_data.get("id", str(uuid.uuid4()))
        impression_data["id"] = impression_app_id
        # 确保 impression_data 包含 source_character_app_id 和 event_app_id
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

                # **关键修改**：在设置到数据库之前，将所有嵌套结构转为JSON字符串
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
                print(f"--- 印象节点 ({impression_app_id}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建印象节点 '{impression_app_id}' 失败: {e}")
                return False

    def connect_character_to_event_via_impression(self, character_app_id: str, event_app_id: str, impression_data: Dict[str, Any]) -> bool:
        """
        连接角色 -> 印象 -> 事件。
        如果印象已存在，则更新印象。
        """
        # 1. 创建或更新印象节点
        impression_success = self.create_impression_node(impression_data)
        if not impression_success:
            print("连接角色到事件失败：印象节点创建失败。")
            return False

        impression_app_id = impression_data.get("id")
        if not impression_app_id:
            print("错误：印象数据必须包含 'id' 字段。")
            return False

        with self.driver.session(database=self.database) as session:
            try:
                # 2. 确保角色和事件节点存在
                char_result = session.run(
                    """
                    MATCH (c:Character) WHERE c.app_id = $char_app_id
                    RETURN c
                    """,
                    char_app_id=character_app_id
                ).single()
                if not char_result:
                    print(f"错误：未找到角色 app_id 为 {character_app_id} 的节点。")
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

                # 3. 连接角色 -> 印象
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_app_id}), (i:Impression {app_id: $impression_app_id})
                    MERGE (c)-[:HAS_IMPRESSION]->(i)
                    """,
                    char_app_id=character_app_id,
                    impression_app_id=impression_app_id
                )
                print(f"--- 角色 {character_app_id} -> 印象 {impression_app_id} 连接成功 ---")

                # 4. 连接印象 -> 事件
                session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id}), (e:Event {app_id: $event_app_id})
                    MERGE (i)-[:OF_EVENT]->(e)
                    """,
                    impression_app_id=impression_app_id,
                    event_app_id=event_app_id
                )
                print(f"--- 印象 {impression_app_id} -> 事件 {event_app_id} 连接成功 ---")

                return True
            except Exception as e:
                print(f"连接角色 {character_app_id} -> 印象 -> 事件 {event_app_id} 失败: {e}")
                return False

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

    def get_memories_for_character(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取与指定角色关联的所有记忆片段（通过印象节点）。
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

                memories = []
                for record in result:
                    impression_node = record["i"]
                    event_node = record["e"]
                    impression_props = dict(impression_node)
                    event_props = dict(event_node)

                    # 合并印象和事件信息作为记忆
                    memory_props = impression_props.copy()
                    # event_props 中的字段可能覆盖 impression_props 中的同名字段
                    memory_props.update(event_props)
                    # 但保留 impression 的特定属性，如 impression_content
                    memory_props['original_event_content'] = event_props.get('content', '')
                    memory_props['character_impression_content'] = impression_props.get('impression_content', impression_props.get('content', ''))

                    # **关键修改**：如果 properties 是 Base64 字符串，则进行解码
                    if 'properties' in memory_props and isinstance(memory_props['properties'], str):
                        try:
                            decoded_bytes = base64.b64decode(memory_props['properties'])
                            decoded_str = decoded_bytes.decode('utf-8')
                            # 将解码后的 JSON 字符串转换回字典
                            decoded_dict = json.loads(decoded_str)
                            # 更新 memory_props
                            memory_props['properties'] = decoded_dict
                        except (base64.binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
                            # 如果解码失败，保留原始值
                            pass

                    for key, value in memory_props.items():
                        if isinstance(value, str):
                            try:
                                memory_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    memories.append(memory_props)

                print(f"--- 获取到 {len(memories)} 条角色 {character_id} 的关联记忆片段 ---")
                return memories
            except Exception as e:
                print(f"获取角色 {character_id} 的记忆片段失败: {e}")
                return []

    def delete_character_graph(self, character_id: str) -> bool:
        """
        删除指定角色及其关联的图谱数据（印象、事件、关系）。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 1. 删除角色 -> 印象 -> 事件 的路径
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[r1:HAS_IMPRESSION]->(i:Impression)-[r2:OF_EVENT]->(e:Event)
                    DELETE r1, r2, i, e
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
                print(f"--- 角色 {character_id} 及其关联的印象、事件节点已删除 ---")
                return True
            except Exception as e:
                print(f"删除角色 {character_id} 的图谱数据失败: {e}")
                return False

    def update_impression_over_time(self, impression_app_id: str, new_content: str, decay_factor: float = 0.9) -> bool:
        """
        模拟印象随时间变化（淡忘）。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 获取当前印象内容
                result = session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id})
                    RETURN i.impression_content AS current_content, i.strength AS current_strength
                    """,
                    impression_app_id=impression_app_id
                ).single()

                if not result:
                    print(f"错误：未找到印象 ID 为 {impression_app_id} 的节点。")
                    return False

                current_content = result["current_content"] or ""
                current_strength = result["current_strength"] or 100

                # 简单的淡忘逻辑：内容长度按衰减因子减少，强度也减少
                new_strength = int(current_strength * decay_factor)
                content_length = len(current_content)
                new_content_length = max(1, int(content_length * decay_factor)) # 确保内容不为空
                new_content = current_content[:new_content_length]

                session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id})
                    SET i.impression_content = $new_content, i.strength = $new_strength
                    """,
                    impression_app_id=impression_app_id,
                    new_content=new_content,
                    new_strength=new_strength
                )
                print(f"--- 印象 {impression_app_id} 已更新 (强度: {new_strength}, 内容长度: {len(new_content)}) ---")
                return True
            except Exception as e:
                print(f"更新印象 {impression_app_id} 失败: {e}")
                return False

    # --- 保存统一格式的 CSV 文件 (使用 Base64 编码 properties) ---
    def save_entities_and_relationships_to_csv(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]], memories: List[Dict[str, Any]], character_id: str) -> Dict[str, str]:
        """
        将所有数据（主角色、关联角色、实体、关系、记忆）保存为统一格式的 CSV 文件。
        修改逻辑以支持新的节点模型，并确保所有属性值都是字符串、数字或布尔值。
        使用 Base64 编码 properties 字段以避免 CSV 引号问题。
        修复重复角色节点问题。
        """
        print(f"--- 开始将数据保存为统一格式的 CSV (新模型, 修复类型和引号 - 使用Base64) ---")
        
        nodes_filename = os.path.join(self.temp_csv_dir, f"story_nodes_{character_id}.csv")
        relationships_filename = os.path.join(self.temp_csv_dir, f"story_relationships_{character_id}.csv")
        impressions_filename = os.path.join(self.temp_csv_dir, f"story_impressions_{character_id}.csv")
        temporal_chain_filename = os.path.join(self.temp_csv_dir, f"temporal_chain_{character_id}.csv")

        # **关键修改**：创建一个角色ID映射表，用于去重
        # 收集所有需要创建的角色ID
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
                    # 如果从记忆中来的参与者ID不在主角色或关联角色中，我们仍然需要创建它
                    # 为了简化，这里我们假设所有参与者ID都应在 character_map 中
                    continue

                char_node_id = str(uuid.uuid4())
                char_props = {
                    'node_id': char_node_id,
                    'label': 'Character', # 统一标签
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
                    'entity_type': 'Character', # 统一类型
                    'description': char_data.get('background', '')
                }
                props_to_exclude = set(fieldnames) - {'node_id', 'label', 'name', 'app_id', 'age', 'gender', 'occupation', 'hobby', 'skill', 'values', 'living_habit', 'dislike', 'language_style', 'appearance', 'family_status', 'education', 'social_pattern', 'favorite_thing', 'usual_place', 'past_experience', 'speech_style', 'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism', 'is_protagonist', 'entity_type', 'description', 'event_title', 'event_content', 'event_age', 'event_importance', 'properties'}
                # **关键修改**：将所有动态属性（如 personality）预先转为JSON字符串
                dynamic_props = {k: v for k, v in char_data.items() if k not in props_to_exclude and k not in char_props}
                for k, v in dynamic_props.items():
                    if isinstance(v, (dict, list)):
                        # **关键修改**：使用 json.dumps 确保引号被正确转义
                        dynamic_props[k] = json.dumps(v, ensure_ascii=False)
                # **关键修改**：将 properties 字段的 JSON 字符串进行 Base64 编码
                json_str = json.dumps(dynamic_props, ensure_ascii=False)
                char_props['properties'] = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                writer.writerow(char_props)

            # 2. 写入事件节点 (从记忆中提取)
            event_node_map = {}
            for memory in memories:
                event_node_id = str(uuid.uuid4())
                event_node_map[memory.get('id')] = event_node_id # memory id 作为 event id
                event_props = {
                    'node_id': event_node_id,
                    'label': 'Event',
                    'name': memory.get('title', ''),
                    'app_id': memory.get('id', ''), # memory id
                    'entity_type': 'Event',
                    'event_title': memory.get('title', ''),
                    'event_content': memory.get('content', ''),
                    'event_age': memory.get('time', {}).get('age', ''),
                    'event_importance': memory.get('importance', {}).get('score', ''),
                    'description': memory.get('content', '')[:100]
                }
                # **关键修改**：将所有动态属性预先转为JSON字符串
                dynamic_props_mem = {k: v for k, v in memory.items() if k not in ['title', 'content', 'time', 'importance', 'id', 'app_id', 'node_id', 'label', 'name', 'entity_type', 'event_title', 'event_content', 'event_age', 'event_importance', 'description', 'properties']}
                for k, v in dynamic_props_mem.items():
                    if isinstance(v, (dict, list)):
                        # **关键修改**：使用 json.dumps 确保引号被正确转义
                        dynamic_props_mem[k] = json.dumps(v, ensure_ascii=False)
                # **关键修改**：将 properties 字段的 JSON 字符串进行 Base64 编码
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
                # **关键修改**：将所有动态属性预先转为JSON字符串
                dynamic_props_ent = entity.get('properties', {})
                for k, v in dynamic_props_ent.items():
                    if isinstance(v, (dict, list)):
                        # **关键修改**：使用 json.dumps 确保引号被正确转义
                        dynamic_props_ent[k] = json.dumps(v, ensure_ascii=False)
                # **关键修改**：将 properties 字段的 JSON 字符串进行 Base64 编码
                json_str_ent = json.dumps(dynamic_props_ent, ensure_ascii=False)
                ent_props['properties'] = base64.b64encode(json_str_ent.encode('utf-8')).decode('utf-8')
                writer.writerow(ent_props)

        print(f"--- 节点 CSV 文件已保存至: {nodes_filename} ---")

        # --- 保存印象关系 CSV (Character -> Impression -> Event) ---
        with open(impressions_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['impression_id', 'character_app_id', 'event_app_id', 'impression_content', 'strength', 'timestamp', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for memory in memories:
                event_app_id = memory.get('id')
                if not event_app_id:
                    continue
                participants = memory.get('participants', [])
                # 假设 memory 的 content 就是角色对事件的印象
                impression_content = memory.get('content', '')
                timestamp = memory.get('time', {}).get('specific', datetime.now().isoformat())
                # 从 memory 中提取强度或其他 impression 相关信息
                strength = memory.get('importance', {}).get('score', 50)

                for participant_id in participants:
                    # 映射 participant_id 到 character_app_id
                    # 我们直接使用 participant_id 作为 character_app_id
                    char_app_id = participant_id
                    if not char_app_id:
                        continue

                    impression_id = str(uuid.uuid4())
                    impression_props = {
                        'impression_id': impression_id,
                        'character_app_id': char_app_id,
                        'event_app_id': event_app_id,
                        'impression_content': impression_content,
                        'strength': strength,
                        'timestamp': timestamp,
                    }
                    # **关键修改**：将所有动态属性预先转为JSON字符串
                    dynamic_props_imp = {k: v for k, v in memory.items() if k not in ['id', 'participants', 'content', 'time', 'importance', 'impression_id', 'character_app_id', 'event_app_id', 'impression_content', 'strength', 'timestamp', 'properties']}
                    for k, v in dynamic_props_imp.items():
                        if isinstance(v, (dict, list)):
                            # **关键修改**：使用 json.dumps 确保引号被正确转义
                            dynamic_props_imp[k] = json.dumps(v, ensure_ascii=False)
                    # **关键修改**：将 properties 字段的 JSON 字符串进行 Base64 编码
                    json_str_imp = json.dumps(dynamic_props_imp, ensure_ascii=False)
                    impression_props['properties'] = base64.b64encode(json_str_imp.encode('utf-8')).decode('utf-8')
                    writer.writerow(impression_props)

        print(f"--- 印象关系 CSV 文件已保存至: {impressions_filename} ---")

        # --- 保存非人物实体到事件的关系 CSV ---
        with open(relationships_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['relation_id', 'entity_app_id', 'event_app_id', 'relationship_type', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for memory in memories:
                event_app_id = memory.get('id')
                if not event_app_id:
                    continue
                # 假设 memory 中的 location, tags 等可以作为实体关联
                mem_location = memory.get('location')
                if mem_location:
                    # 尝试找到对应的实体 app_id
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
                        # **关键修改**：properties 也转为JSON字符串并Base64编码
                        json_str_rel = json.dumps({}, ensure_ascii=False)
                        rel_props['properties'] = base64.b64encode(json_str_rel.encode('utf-8')).decode('utf-8')
                        writer.writerow(rel_props)

                # 可以根据 tags, etc. 添加更多实体关系
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
                        # **关键修改**：properties 也转为JSON字符串并Base64编码
                        json_str_rel = json.dumps({}, ensure_ascii=False)
                        rel_props['properties'] = base64.b64encode(json_str_rel.encode('utf-8')).decode('utf-8')
                        writer.writerow(rel_props)

        print(f"--- 实体-事件关系 CSV 文件已保存至: {relationships_filename} ---")

        # --- 保存时间链 CSV ---
        # 按时间排序
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

        return {
            "nodes_file": os.path.basename(nodes_filename),
            "impressions_file": os.path.basename(impressions_filename),
            "entity_event_relationships_file": os.path.basename(relationships_filename),
            "temporal_chain_file": os.path.basename(temporal_chain_filename)
        }
    # ---

    # --- 从 CSV 导入节点 (不使用 APOC 解码) ---
    def import_nodes_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从统一 CSV 文件导入节点: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # **关键修改**：使用 app_id 作为唯一标识，移除 APOC 解码
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
                        properties: row.properties // 存储为原始 Base64 字符串
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
                # 尝试不使用 APOC 的基础查询
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
                            // 不设置 properties
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
    # ---

    # --- 从 CSV 导入印象关系 (不使用 APOC 解码) ---
    def import_impressions_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入印象关系: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建印象节点 (properties 作为字符串，不进行解码)
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    CALL apoc.create.node(['Impression'], {{
                        app_id: row.impression_id,
                        impression_content: row.impression_content,
                        strength: toInteger(row.strength),
                        timestamp: row.timestamp,
                        properties: row.properties // 存储为原始 Base64 字符串
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
    # ---

    # --- 从 CSV 导入实体-事件关系 ---
    def import_entity_event_relationships_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入实体-事件关系: {csv_filename} ---")
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # **关键修改**：不再尝试解码 properties，直接存储 Base64 字符串
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
    # ---

    # --- 从 CSV 导入时间链 ---
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
    # ---


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