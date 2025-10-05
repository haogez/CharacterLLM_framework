import random
from typing import Dict, Any
from app.schemas.character import CharacterCreate

class SimpleCharacterGenerator:
    """简化版角色人设生成器（使用模拟数据）"""
    
    def __init__(self):
        # 预定义的角色模板
        self.name_templates = [
            "李明", "王芳", "张伟", "刘娟", "陈强", "赵丽", "孙涛", "周敏",
            "吴刚", "郑红", "冯磊", "何静", "朱勇", "许琳", "邓超", "苏雅"
        ]
        
        self.occupations = [
            "教师", "医生", "工程师", "律师", "记者", "设计师", "程序员", "销售员",
            "厨师", "司机", "护士", "会计", "翻译", "艺术家", "警察", "消防员"
        ]
        
        self.regions = [
            "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "西安",
            "武汉", "重庆", "天津", "青岛", "大连", "厦门", "苏州", "无锡"
        ]
        
        self.language_styles = [
            "说话温和，喜欢用比喻",
            "语言简洁，直接了当",
            "幽默风趣，经常开玩笑",
            "文雅有礼，用词考究",
            "热情开朗，语速较快",
            "沉稳内敛，措辞谨慎"
        ]
        
        self.values_templates = [
            "重视家庭和睦，崇尚诚实守信",
            "追求公平正义，关爱弱势群体",
            "注重个人成长，勇于接受挑战",
            "珍惜友谊，乐于助人",
            "热爱学习，保持好奇心",
            "尊重传统，同时拥抱创新"
        ]
        
        self.boundaries_templates = [
            "不说谎话，不做违法的事",
            "尊重他人隐私，不传播谣言",
            "保持专业操守，不滥用职权",
            "维护家庭和谐，不背叛亲友",
            "坚持原则底线，不妥协道德",
            "保护环境，不浪费资源"
        ]
    
    def generate_character(self, description: str) -> CharacterCreate:
        """从自然语言描述生成结构化角色人设"""
        
        # 简单的关键词匹配来调整生成结果
        description_lower = description.lower()
        
        # 根据描述调整年龄
        if "年轻" in description_lower or "青年" in description_lower:
            age = random.randint(20, 35)
        elif "中年" in description_lower:
            age = random.randint(35, 55)
        elif "老" in description_lower or "退休" in description_lower:
            age = random.randint(55, 75)
        else:
            age = random.randint(25, 60)
        
        # 根据描述选择职业
        occupation = random.choice(self.occupations)
        if "教师" in description_lower or "老师" in description_lower:
            occupation = "教师"
        elif "医生" in description_lower:
            occupation = "医生"
        elif "工程师" in description_lower:
            occupation = "工程师"
        
        # 根据描述选择地区
        region = random.choice(self.regions)
        if "上海" in description_lower:
            region = "上海"
        elif "北京" in description_lower:
            region = "北京"
        elif "广州" in description_lower:
            region = "广州"
        
        # 生成OCEAN人格特征
        ocean_traits = self._generate_ocean_traits(description_lower)
        
        character_data = {
            "name": random.choice(self.name_templates),
            "age": age,
            "occupation": occupation,
            "region": region,
            "ocean_openness": ocean_traits["openness"],
            "ocean_conscientiousness": ocean_traits["conscientiousness"],
            "ocean_extraversion": ocean_traits["extraversion"],
            "ocean_agreeableness": ocean_traits["agreeableness"],
            "ocean_neuroticism": ocean_traits["neuroticism"],
            "language_style": random.choice(self.language_styles),
            "values_and_taboos": random.choice(self.values_templates),
            "behavioral_boundaries": random.choice(self.boundaries_templates)
        }
        
        return CharacterCreate(**character_data)
    
    def _generate_ocean_traits(self, description: str) -> Dict[str, float]:
        """根据描述生成OCEAN人格特征"""
        traits = {
            "openness": 0.5,
            "conscientiousness": 0.5,
            "extraversion": 0.5,
            "agreeableness": 0.5,
            "neuroticism": 0.5
        }
        
        # 根据关键词调整特征
        if "开放" in description or "创新" in description:
            traits["openness"] = random.uniform(0.7, 0.9)
        elif "保守" in description or "传统" in description:
            traits["openness"] = random.uniform(0.2, 0.4)
        
        if "严谨" in description or "认真" in description:
            traits["conscientiousness"] = random.uniform(0.7, 0.9)
        elif "随意" in description or "自由" in description:
            traits["conscientiousness"] = random.uniform(0.2, 0.4)
        
        if "外向" in description or "活泼" in description:
            traits["extraversion"] = random.uniform(0.7, 0.9)
        elif "内向" in description or "安静" in description:
            traits["extraversion"] = random.uniform(0.2, 0.4)
        
        if "友善" in description or "温和" in description:
            traits["agreeableness"] = random.uniform(0.7, 0.9)
        elif "严厉" in description or "冷漠" in description:
            traits["agreeableness"] = random.uniform(0.2, 0.4)
        
        if "敏感" in description or "焦虑" in description:
            traits["neuroticism"] = random.uniform(0.6, 0.8)
        elif "稳定" in description or "冷静" in description:
            traits["neuroticism"] = random.uniform(0.1, 0.3)
        
        # 添加随机性
        for trait in traits:
            traits[trait] += random.uniform(-0.1, 0.1)
            traits[trait] = max(0.0, min(1.0, traits[trait]))
        
        return traits
