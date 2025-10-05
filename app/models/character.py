from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Character(Base):
    """角色人设模型"""
    __tablename__ = 'characters'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="角色姓名")
    age = Column(Integer, comment="年龄")
    occupation = Column(String(100), comment="职业")
    region = Column(String(100), comment="地域")
    
    # OCEAN五维人格模型 (0-1之间的浮点数)
    ocean_openness = Column(Float, default=0.5, comment="开放性")
    ocean_conscientiousness = Column(Float, default=0.5, comment="尽责性")
    ocean_extraversion = Column(Float, default=0.5, comment="外向性")
    ocean_agreeableness = Column(Float, default=0.5, comment="宜人性")
    ocean_neuroticism = Column(Float, default=0.5, comment="神经质")
    
    # 角色特征
    language_style = Column(Text, comment="语言风格")
    values_and_taboos = Column(Text, comment="价值观与禁忌")
    behavioral_boundaries = Column(Text, comment="行为边界")
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}', occupation='{self.occupation}')>"
