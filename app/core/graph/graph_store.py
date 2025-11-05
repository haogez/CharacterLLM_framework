# app/core/graph/graph_store.py

"""
图谱存储模块 (Neo4j 自部署版) - 使用统一 CSV 格式
"""

import os
import json
import uuid
import csv
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
                node_properties["is_main_character"] = node_properties.get("is_main_character", False)

                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (c:Character {name: $char_name})
                    SET c = $properties
                    """,
                    char_name=char_name,
                    properties=node_properties
                )
                print(f"--- 角色节点 '{char_name}' 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建角色节点 '{char_name}' 失败: {e}")
                return False

    def create_general_entity_node(self, entity_data: Dict[str, Any]) -> bool:
        """
        创建通用实体节点。
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

                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                label = f"{ent_type}"

                session.run(
                    f"""
                    MERGE (e:{label} {{name: $ent_name}})
                    SET e = $properties
                    """,
                    ent_name=ent_name,
                    properties=node_properties
                )
                print(f"--- 实体节点 '{ent_name}' ({ent_type}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建实体节点 '{ent_name}' 失败: {e}")
                return False

    def create_memory_node_and_connect(self, memory_data: Dict[str, Any], character_id: str) -> bool:
        """
        创建记忆节点并连接到指定角色。
        记忆节点使用 'app_id' 作为唯一标识。
        """
        mem_app_id = memory_data.get("id", str(uuid.uuid4()))
        memory_data["id"] = mem_app_id
        participants = memory_data.get("participants", [])

        if not participants:
            print(f"警告：记忆 {mem_app_id} 没有参与者，无法建立连接。")
            return self._create_memory_node_only(memory_data)

        with self.driver.session(database=self.database) as session:
            try:
                success = self._create_memory_node_only(memory_data)
                if not success:
                    return False

                for char_id in participants:
                    result = session.run(
                        """
                        MATCH (c:Character) WHERE c.app_id = $char_id
                        RETURN c
                        """,
                        char_id=char_id
                    ).single()

                    if not result:
                        print(f"警告：未找到应用ID为 {char_id} 的角色，跳过连接。")
                        continue

                    char_node = result["c"]
                    char_name = char_node["name"]

                    session.run(
                        """
                        MATCH (c:Character {name: $char_name}), (m:Memory {app_id: $mem_app_id})
                        MERGE (c)-[:HAS_MEMORY]->(m)
                        """,
                        char_name=char_name, mem_app_id=mem_app_id
                    )
                    print(f"--- 记忆 {mem_app_id} 已连接到角色 '{char_name}' ---")

                return True
            except Exception as e:
                print(f"为记忆 {mem_app_id} 创建节点并建立连接失败: {e}")
                return False

    def _create_memory_node_only(self, memory_data: Dict[str, Any]) -> bool:
        """
        仅创建记忆节点，不建立连接。
        """
        mem_app_id = memory_data.get("id")
        if not mem_app_id:
            print("错误：记忆数据必须包含 'id' 字段。")
            return False

        with self.driver.session(database=self.database) as session:
            try:
                memory_properties = memory_data.copy()
                memory_properties.pop("id", None)
                memory_properties["app_id"] = mem_app_id

                for key, value in memory_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        memory_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (m:Memory {app_id: $mem_app_id})
                    SET m = $properties
                    """,
                    mem_app_id=mem_app_id,
                    properties=memory_properties
                )
                print(f"--- 记忆节点 {mem_app_id} 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建记忆节点 {mem_app_id} 失败: {e}")
                return False

    def get_related_characters(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取与指定角色相关的角色列表。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c1:Character {app_id: $char_id})-[:HAS_MEMORY|:KNOWS|:CHILD_OF|:MENTORS|:INTERACTS_WITH]->(rel)-[:HAS_MEMORY|:KNOWS|:CHILD_OF|:MENTORS|:INTERACTS_WITH]->(c2:Character)
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
        获取与指定角色关联的所有记忆片段。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[:HAS_MEMORY]->(m:Memory)
                    RETURN m
                    """,
                    char_id=character_id
                )

                memories = []
                for record in result:
                    mem_node = record["m"]
                    mem_props = dict(mem_node)
                    for key, value in mem_props.items():
                        if isinstance(value, str):
                            try:
                                mem_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    memories.append(mem_props)

                print(f"--- 获取到 {len(memories)} 条角色 {character_id} 的关联记忆片段 ---")
                return memories
            except Exception as e:
                print(f"获取角色 {character_id} 的记忆片段失败: {e}")
                return []

    def delete_character_graph(self, character_id: str) -> bool:
        """
        删除指定角色及其关联的图谱数据。
        """
        with self.driver.session(database=self.database) as session:
            try:
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[r:HAS_MEMORY]->(m:Memory)
                    DELETE r, m
                    """,
                    char_id=character_id
                )
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})
                    DELETE c
                    """,
                    char_id=character_id
                )
                print(f"--- 角色 {character_id} 及其直接关联的记忆节点已删除 ---")
                print(f"--- 角色 {character_id} 及其关联的记忆和关系已删除 ---")
                return True
            except Exception as e:
                print(f"删除角色 {character_id} 的图谱数据失败: {e}")
                return False

    def create_relationship_edge(self, relationship_data: Dict[str, Any]) -> bool:
        """
        创建实体间的关系边。
        保留此方法用于兼容性，但实际逻辑将通过 CSV 导入。
        """
        rel_app_id = relationship_data.get("id")
        source_app_id = relationship_data.get("source_entity_app_id")
        target_app_id = relationship_data.get("target_entity_app_id")
        rel_type = relationship_data.get("type")

        if not all([rel_app_id, source_app_id, target_app_id, rel_type]):
            print("错误：关系数据必须包含 'id', 'source_entity_app_id', 'target_entity_app_id', 'type' 字段。")
            return False

        print(f"--- 关系 {rel_app_id} ({rel_type}) 数据已验证，准备写入CSV ---")
        return True

    def add_memory_to_character(self, character_id: str, memory_data: Dict[str, Any]) -> bool:
        """
        将记忆添加到角色。
        """
        participants = memory_data.get("participants", [])
        if character_id not in participants:
            participants.append(character_id)
            memory_data["participants"] = participants
        return self.create_memory_node_and_connect(memory_data, character_id)

    def update_relationship_strength(self, character1_id: str, character2_id: str, new_strength: int) -> bool:
        """
        更新两个角色之间的关系强度。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c1:Character {app_id: $char1_id})-[r:KNOWS|CHILD_OF|MENTORS|INTERACTS_WITH]->(c2:Character {app_id: $char2_id})
                    SET r.strength = $new_strength
                    RETURN r
                    """,
                    char1_id=character1_id, char2_id=character2_id, new_strength=new_strength
                )
                if result.peek():
                    print(f"--- 关系 {character1_id}-{character2_id} 的强度已更新为 {new_strength} ---")
                    return True

                print(f"错误：未找到角色 {character1_id} 和 {character2_id} 之间的关系。")
                return False

            except Exception as e:
                print(f"更新关系 {character1_id}-{character2_id} 的强度失败: {e}")
                return False

    # --- 修改：保存统一格式的 CSV 文件 ---
    def save_entities_and_relationships_to_csv(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]], memories: List[Dict[str, Any]], character_id: str) -> Dict[str, str]:
        """
        将所有数据（主角色、关联角色、实体、关系、记忆）保存为统一格式的 CSV 文件。
        """
        print(f"--- 开始将数据保存为统一格式的 CSV ---")
        
        nodes_filename = os.path.join(self.temp_csv_dir, f"story_nodes_{character_id}.csv")
        relationships_filename = os.path.join(self.temp_csv_dir, f"story_relationships_{character_id}.csv")

        # --- 保存节点 CSV ---
        with open(nodes_filename, 'w', newline='', encoding='utf-8') as csvfile:
            # 定义所有可能的字段
            fieldnames = [
                'node_id', 'label', 'name', 'app_id', 'age', 'gender', 'occupation', 'hobby', 'skill',
                'values', 'living_habit', 'dislike', 'language_style', 'appearance', 'family_status',
                'education', 'social_pattern', 'favorite_thing', 'usual_place', 'past_experience',
                'speech_style', 'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism',
                'is_protagonist', 'entity_type', 'description', 'memory_title', 'memory_content', 'memory_age', 'memory_importance', 'properties'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            # 1. 写入主角色节点
            main_char_node_id = str(uuid.uuid4())
            main_char_props = {
                'node_id': main_char_node_id,
                'label': 'Person',
                'name': main_character.get('name', ''),
                'app_id': main_character.get('id', ''),
                'age': main_character.get('age', ''),
                'gender': main_character.get('gender', ''),
                'occupation': main_character.get('occupation', ''),
                'hobby': main_character.get('hobby', ''),
                'skill': main_character.get('skill', ''),
                'values': main_character.get('values', ''),
                'living_habit': main_character.get('living_habit', ''),
                'dislike': main_character.get('dislike', ''),
                'language_style': main_character.get('language_style', ''),
                'appearance': main_character.get('appearance', ''),
                'family_status': main_character.get('family_status', ''),
                'education': main_character.get('education', ''),
                'social_pattern': main_character.get('social_pattern', ''),
                'favorite_thing': main_character.get('favorite_thing', ''),
                'usual_place': main_character.get('usual_place', ''),
                'past_experience': main_character.get('past_experience', ''),
                'speech_style': main_character.get('speech_style', ''),
                'openness': main_character.get('personality', {}).get('openness', ''),
                'conscientiousness': main_character.get('personality', {}).get('conscientiousness', ''),
                'extraversion': main_character.get('personality', {}).get('extraversion', ''),
                'agreeableness': main_character.get('personality', {}).get('agreeableness', ''),
                'neuroticism': main_character.get('personality', {}).get('neuroticism', ''),
                'is_protagonist': 'True', # 主角色标记
                'entity_type': 'Person',
                'description': main_character.get('background', '')
            }
            # properties 字段
            props_to_exclude = set(fieldnames) - {'node_id', 'label', 'name', 'app_id', 'age', 'gender', 'occupation', 'hobby', 'skill', 'values', 'living_habit', 'dislike', 'language_style', 'appearance', 'family_status', 'education', 'social_pattern', 'favorite_thing', 'usual_place', 'past_experience', 'speech_style', 'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism', 'is_protagonist', 'entity_type', 'description', 'memory_title', 'memory_content', 'memory_age', 'memory_importance', 'properties'}
            dynamic_props = {k: v for k, v in main_character.items() if k not in props_to_exclude and k not in main_char_props}
            main_char_props['properties'] = json.dumps(dynamic_props, ensure_ascii=False)
            writer.writerow(main_char_props)

            # 2. 写入关联角色节点
            related_char_node_map = {} # 用于后续建立关系
            for i, rc in enumerate(related_characters):
                rc_node_id = str(uuid.uuid4())
                related_char_node_map[rc.get('id')] = rc_node_id # 建立旧ID到新node_id的映射
                rc_props = {
                    'node_id': rc_node_id,
                    'label': 'Person',
                    'name': rc.get('name', ''),
                    'app_id': rc.get('id', ''),
                    'age': rc.get('age', ''),
                    'gender': rc.get('gender', ''),
                    'occupation': rc.get('occupation', ''),
                    'hobby': rc.get('hobby', ''),
                    'skill': rc.get('skill', ''),
                    'values': rc.get('values', ''),
                    'living_habit': rc.get('living_habit', ''),
                    'dislike': rc.get('dislike', ''),
                    'language_style': rc.get('language_style', ''),
                    'appearance': rc.get('appearance', ''),
                    'family_status': rc.get('family_status', ''),
                    'education': rc.get('education', ''),
                    'social_pattern': rc.get('social_pattern', ''),
                    'favorite_thing': rc.get('favorite_thing', ''),
                    'usual_place': rc.get('usual_place', ''),
                    'past_experience': rc.get('past_experience', ''),
                    'speech_style': rc.get('speech_style', ''),
                    'openness': rc.get('personality', {}).get('openness', ''),
                    'conscientiousness': rc.get('personality', {}).get('conscientiousness', ''),
                    'extraversion': rc.get('personality', {}).get('extraversion', ''),
                    'agreeableness': rc.get('personality', {}).get('agreeableness', ''),
                    'neuroticism': rc.get('personality', {}).get('neuroticism', ''),
                    'is_protagonist': 'False', # 关联角色标记
                    'entity_type': 'Person',
                    'description': rc.get('background', '')
                }
                dynamic_props_rc = {k: v for k, v in rc.items() if k not in props_to_exclude and k not in rc_props}
                rc_props['properties'] = json.dumps(dynamic_props_rc, ensure_ascii=False)
                writer.writerow(rc_props)

            # 3. 写入非人物实体节点
            entity_node_map = {} # 用于后续建立关系
            for entity in entities:
                ent_node_id = str(uuid.uuid4())
                entity_node_map[entity.get('app_id')] = ent_node_id
                ent_props = {
                    'node_id': ent_node_id,
                    'label': entity.get('type', 'Entity').capitalize(), # e.g., Place, Object, Event
                    'name': entity.get('name', ''),
                    'app_id': entity.get('app_id', ''),
                    'entity_type': entity.get('type', 'Entity').upper(),
                    'description': entity.get('description', '')
                }
                # properties 字段
                dynamic_props_ent = entity.get('properties', {})
                ent_props['properties'] = json.dumps(dynamic_props_ent, ensure_ascii=False)
                writer.writerow(ent_props)

            # 4. 写入记忆节点
            memory_node_map = {} # 用于后续建立关系
            for memory in memories:
                mem_node_id = str(uuid.uuid4())
                memory_node_map[memory.get('id')] = mem_node_id
                mem_props = {
                    'node_id': mem_node_id,
                    'label': 'Memory',
                    'name': memory.get('title', ''),
                    'app_id': memory.get('id', ''),
                    'entity_type': 'Memory', # 虽然label是Memory，也保留entity_type
                    'memory_title': memory.get('title', ''),
                    'memory_content': memory.get('content', ''),
                    'memory_age': memory.get('time', {}).get('age', ''),
                    'memory_importance': memory.get('importance', {}).get('score', ''),
                    'description': memory.get('content', '')[:100] # 作为描述
                }
                # properties 字段
                dynamic_props_mem = {k: v for k, v in memory.items() if k not in ['title', 'content', 'time', 'importance', 'id', 'app_id', 'node_id', 'label', 'name', 'entity_type', 'memory_title', 'memory_content', 'memory_age', 'memory_importance', 'description', 'properties']}
                mem_props['properties'] = json.dumps(dynamic_props_mem, ensure_ascii=False)
                writer.writerow(mem_props)

        print(f"--- 节点 CSV 文件已保存至: {nodes_filename} ---")

        # --- 保存关系 CSV ---
        with open(relationships_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['relation_id', 'start_node_id', 'end_node_id', 'relationship_type', 'app_id', 'strength', 'description', 'memory_id', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            # 1. 写入原始关系 (人物-人物, 人物-实体等)
            for relationship in relationships:
                source_app_id = relationship.get('source_entity_app_id')
                target_app_id = relationship.get('target_entity_app_id')
                rel_type = relationship.get('type')

                # 从映射中查找对应的 node_id
                start_node_id = related_char_node_map.get(source_app_id) or entity_node_map.get(source_app_id)
                end_node_id = related_char_node_map.get(target_app_id) or entity_node_map.get(target_app_id)

                if start_node_id and end_node_id:
                    rel_props = {
                        'relation_id': str(uuid.uuid4()), # 生成新的关系ID
                        'start_node_id': start_node_id,
                        'end_node_id': end_node_id,
                        'relationship_type': rel_type,
                        'app_id': relationship.get('app_id', ''),
                        'strength': relationship.get('properties', {}).get('strength', 50), # 假设strength在properties中
                        'description': relationship.get('description', ''),
                        'memory_id': '', # 普通关系不直接关联记忆
                    }
                    dynamic_props_rel = {k: v for k, v in relationship.items() if k not in ['source_entity_app_id', 'target_entity_app_id', 'type', 'app_id', 'description', 'properties', 'relation_id', 'start_node_id', 'end_node_id', 'relationship_type', 'strength', 'memory_id', 'properties']}
                    rel_props['properties'] = json.dumps(dynamic_props_rel, ensure_ascii=False)
                    writer.writerow(rel_props)
                else:
                    print(f"警告：关系 {rel_type} ({source_app_id} -> {target_app_id}) 中的节点未找到，跳过。")

            # 2. 写入记忆关系 (人物-HAS_MEMORY-记忆, 记忆-MEMORY_AT-地点等)
            for memory in memories:
                mem_node_id = memory_node_map.get(memory.get('id'))
                if not mem_node_id:
                    continue

                # 人物 - HAS_MEMORY - 记忆
                for participant_id in memory.get('participants', []):
                    char_node_id = main_char_node_id if participant_id == character_id else related_char_node_map.get(participant_id)
                    if char_node_id:
                        has_mem_rel_props = {
                            'relation_id': str(uuid.uuid4()),
                            'start_node_id': char_node_id,
                            'end_node_id': mem_node_id,
                            'relationship_type': 'HAS_MEMORY',
                            'app_id': str(uuid.uuid4()), # 生成新的app_id
                            'strength': 90, # 记忆关联强度较高
                            'description': f"{character_id}拥有{memory.get('title')}",
                            'memory_id': mem_node_id,
                        }
                        has_mem_rel_props['properties'] = json.dumps({"recall_frequency": memory.get('importance', {}).get('frequency', '')}, ensure_ascii=False)
                        writer.writerow(has_mem_rel_props)

                # 记忆 - MEMORY_AT - 地点 (如果记忆中有location信息)
                mem_location = memory.get('location')
                if mem_location:
                    # 假设location是实体名称，需要在entities中找到对应的app_id
                    location_entity_app_id = None
                    for ent in entities:
                        if ent.get('name') == mem_location:
                            location_entity_app_id = ent.get('app_id')
                            break
                    if location_entity_app_id:
                        loc_node_id = entity_node_map.get(location_entity_app_id)
                        if loc_node_id:
                            mem_at_rel_props = {
                                'relation_id': str(uuid.uuid4()),
                                'start_node_id': mem_node_id,
                                'end_node_id': loc_node_id,
                                'relationship_type': 'MEMORY_AT',
                                'app_id': str(uuid.uuid4()),
                                'strength': 100, # 记忆发生地关联度最高
                                'description': f"{memory.get('title')} 发生在 {mem_location}",
                                'memory_id': mem_node_id,
                            }
                            mem_at_rel_props['properties'] = json.dumps({"location_detail": mem_location}, ensure_ascii=False)
                            writer.writerow(mem_at_rel_props)

        print(f"--- 关系 CSV 文件已保存至: {relationships_filename} ---")

        return {
            "nodes_file": os.path.basename(nodes_filename), # 返回文件名，用于 LOAD CSV
            "relationships_file": os.path.basename(relationships_filename) # 返回文件名，用于 LOAD CSV
        }
    # ---

    # --- 修改：从 CSV 文件导入节点到 Neo4j ---
    def import_nodes_from_csv(self, csv_filename: str) -> bool:
        """
        从统一格式的 CSV 文件导入节点到 Neo4j。
        修正查询，处理 properties 字段中的复杂结构，包括嵌套 Map 和 List。
        """
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从统一 CSV 文件导入节点: {csv_filename} ---")
        
        # 使用 Neo4j 服务器内部的 import 目录路径
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"
        
        with self.driver.session(database=self.database) as session:
            try:
                # 修正后的查询：
                # 1. 创建节点，设置预定义属性
                # 2. 解析 properties JSON
                # 3. 使用 FOREACH 遍历 properties 的键
                # 4. 在 FOREACH 内部，检查值的类型，如果是 Map/List，则转换为 JSON 字符串
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL {{
                    WITH row
                    // 创建节点，仅包含已知的、简单的属性
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
                        memory_title: row.memory_title,
                        memory_content: row.memory_content,
                        memory_age: CASE row.memory_age WHEN '' THEN null ELSE toInteger(row.memory_age) END,
                        memory_importance: CASE row.memory_importance WHEN '' THEN null ELSE toInteger(row.memory_importance) END
                    }}) YIELD node
                    
                    // 处理 properties 字段：尝试解析 JSON
                    WITH node, row
                    WITH node, row, CASE row.properties WHEN '' THEN {{}} ELSE apoc.convert.fromJsonMap(row.properties) END AS propsMap
                    WITH node, keys(propsMap) AS keys, propsMap
                    
                    // 使用 FOREACH 遍历 properties 的键
                    FOREACH(key IN keys |
                        // 获取值
                        WITH node, key, propsMap[key] AS value
                        // 检查值的类型，如果是 Map 或 List，则转换为 JSON 字符串
                        WITH node, key, CASE 
                            WHEN value IS NOT null AND (value IS MAP OR value IS LIST) THEN apoc.convert.toJson(value)
                            ELSE value
                        END AS finalValue
                        // 设置属性
                        SET node.` + key + ` = finalValue
                    )
                    
                    RETURN node
                }}
                RETURN count(node) AS importedNodes;
                """
                
                result = session.run(query)
                count = result.single()["importedNodes"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 个节点 (主查询) ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入节点失败 (主查询): {e}")
                # 如果主查询失败，尝试更基础的查询，不处理 properties 字段
                try:
                    query_basic = f"""
                    LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                    CALL {{
                        WITH row
                        CALL apoc.create.node([row.label], {{
                            node_id: row.node_id,
                            name: row.name,
                            app_id: row.app_id,
                            is_protagonist: CASE row.is_protagonist WHEN 'True' THEN true WHEN 'False' THEN false ELSE null END,
                            description: row.description
                        }}) YIELD node
                        RETURN node
                    }}
                    RETURN count(node) AS importedNodes;
                    """
                    result_basic = session.run(query_basic)
                    count_basic = result_basic.single()["importedNodes"]
                    print(f"--- 使用基础查询成功从 {csv_filename} 导入 {count_basic} 个节点 ---")
                    return True
                except Exception as e2:
                    print(f"基础查询从 {csv_filename} 导入节点也失败: {e2}")
                    return False
    # ---

    # --- 修改：从 CSV 文件导入关系到 Neo4j ---
    def import_relationships_from_csv(self, csv_filename: str) -> bool:
        """
        从统一格式的 CSV 文件导入关系到 Neo4j。
        修正查询，处理 properties 字段中的复杂结构。
        """
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从统一 CSV 文件导入关系: {csv_filename} ---")
        
        # 修正：使用 Neo4j 服务器内部的 import 目录路径
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"
        
        with self.driver.session(database=self.database) as session:
            try:
                # 修正后的查询：
                # 1. 查找节点
                # 2. 创建关系，设置预定义属性
                # 3. 解析并设置 properties 属性
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (a {{node_id: row.start_node_id}}), (b {{node_id: row.end_node_id}})
                CALL {{
                    WITH a, b, row
                    CALL apoc.create.relationship(a, row.relationship_type, {{
                        relation_id: row.relation_id,
                        app_id: row.app_id,
                        strength: toInteger(row.strength),
                        description: row.description,
                        memory_id: CASE row.memory_id WHEN '' THEN null ELSE row.memory_id END
                        // 注意：properties 字段在此处处理
                    }}, b) YIELD rel
                    
                    // 处理 properties 字段：尝试解析 JSON 并设置为关系属性
                    WITH rel, row
                    WITH rel, row, CASE row.properties WHEN '' THEN {{}} ELSE apoc.convert.fromJsonMap(row.properties) END AS propsMap
                    WITH rel, keys(propsMap) AS keys, propsMap
                    
                    // 使用 FOREACH 避免变量重复声明，为每个 key 设置关系属性
                    FOREACH(key IN keys |
                        // 获取值
                        WITH rel, key, propsMap[key] AS value
                        // 检查值的类型，如果是 Map 或 List，则转换为 JSON 字符串
                        WITH rel, key, CASE 
                            WHEN value IS NOT null AND (value IS MAP OR value IS LIST) THEN apoc.convert.toJson(value)
                            ELSE value
                        END AS finalValue
                        // 设置属性
                        SET rel.` + key + ` = finalValue
                    )
                    
                    RETURN rel
                }}
                RETURN count(rel) AS importedRelationships;
                """
                
                result = session.run(query)
                count = result.single()["importedRelationships"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 条关系 (主查询) ---")
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入关系失败 (主查询): {e}")
                # 如果主查询失败，尝试更基础的查询，不处理 properties 字段
                try:
                    query_basic = f"""
                    LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                    MATCH (a {{node_id: row.start_node_id}}), (b {{node_id: row.end_node_id}})
                    CALL apoc.create.relationship(a, row.relationship_type, {{
                        app_id: row.app_id,
                        strength: toInteger(row.strength),
                        memory_id: CASE row.memory_id WHEN '' THEN null ELSE row.memory_id END
                    }}, b) YIELD rel
                    RETURN count(rel) AS importedRelationships;
                    """
                    result_basic = session.run(query_basic)
                    count_basic = result_basic.single()["importedRelationships"]
                    print(f"--- 使用基础查询成功从 {csv_filename} 导入 {count_basic} 条关系 ---")
                    return True
                except Exception as e2:
                    print(f"基础查询从 {csv_filename} 导入关系也失败: {e2}")
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
