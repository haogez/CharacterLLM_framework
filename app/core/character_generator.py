import openai
import json
import re
from typing import Dict, Any
from app.schemas.character import CharacterCreate

class CharacterGenerator:
    """角色人设生成器"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def generate_character(self, description: str) -> CharacterCreate:
        """从自然语言描述生成结构化角色人设"""
        
        prompt = f"""
你是一个专业的角色设计师。请根据以下描述，生成一个详细的角色人设。

角色描述: {description}

请按照以下JSON格式输出角色信息：
{{
    "name": "角色姓名",
    "age": 年龄数字,
    "occupation": "职业",
    "region": "地域",
    "ocean_openness": 0.0-1.0之间的数字,
    "ocean_conscientiousness": 0.0-1.0之间的数字,
    "ocean_extraversion": 0.0-1.0之间的数字,
    "ocean_agreeableness": 0.0-1.0之间的数字,
    "ocean_neuroticism": 0.0-1.0之间的数字,
    "language_style": "详细描述角色的语言风格、口头禅、说话习惯等",
    "values_and_taboos": "描述角色的价值观、信念和禁忌",
    "behavioral_boundaries": "描述角色的行为准则和限制"
}}

OCEAN五维人格说明：
- openness (开放性): 对新体验的开放程度，创造力和想象力
- conscientiousness (尽责性): 自律性、组织性和目标导向
- extraversion (外向性): 社交性、活力和积极情绪
- agreeableness (宜人性): 合作性、信任和同情心
- neuroticism (神经质): 情绪稳定性的反面，焦虑和负面情绪

请确保生成的角色人设与描述一致，并且各个维度都有合理的数值。
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "你是一个专业的角色设计师，擅长创建详细、一致的角色人设。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                character_data = json.loads(json_str)
                
                # 验证和清理数据
                character_data = self._validate_character_data(character_data)
                
                return CharacterCreate(**character_data)
            else:
                raise ValueError("无法从响应中提取有效的JSON")
                
        except Exception as e:
            print(f"生成角色时出错: {e}")
            # 返回默认角色
            return self._create_default_character(description)
    
    def _validate_character_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证和清理角色数据"""
        # 确保OCEAN值在0-1范围内
        ocean_fields = [
            "ocean_openness", "ocean_conscientiousness", 
            "ocean_extraversion", "ocean_agreeableness", "ocean_neuroticism"
        ]
        
        for field in ocean_fields:
            if field in data:
                value = data[field]
                if isinstance(value, (int, float)):
                    data[field] = max(0.0, min(1.0, float(value)))
                else:
                    data[field] = 0.5  # 默认值
            else:
                data[field] = 0.5
        
        # 确保必需字段存在
        if "name" not in data or not data["name"]:
            data["name"] = "未命名角色"
        
        return data
    
    def _create_default_character(self, description: str) -> CharacterCreate:
        """创建默认角色（当生成失败时使用）"""
        return CharacterCreate(
            name="默认角色",
            age=30,
            occupation="未知",
            region="未知",
            ocean_openness=0.5,
            ocean_conscientiousness=0.5,
            ocean_extraversion=0.5,
            ocean_agreeableness=0.5,
            ocean_neuroticism=0.5,
            language_style="普通的说话方式",
            values_and_taboos="基本的道德准则",
            behavioral_boundaries="遵守法律和社会规范"
        )
