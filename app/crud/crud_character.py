from sqlalchemy.orm import Session
from app.models.character import Character
from app.schemas.character import CharacterCreate, CharacterUpdate
from typing import List, Optional

def create_character(db: Session, character: CharacterCreate) -> Character:
    """创建新角色"""
    db_character = Character(**character.dict())
    db.add(db_character)
    db.commit()
    db.refresh(db_character)
    return db_character

def get_character(db: Session, character_id: int) -> Optional[Character]:
    """根据ID获取角色"""
    return db.query(Character).filter(Character.id == character_id).first()

def get_characters(db: Session, skip: int = 0, limit: int = 100) -> List[Character]:
    """获取角色列表"""
    return db.query(Character).offset(skip).limit(limit).all()

def update_character(db: Session, character_id: int, character_update: CharacterUpdate) -> Optional[Character]:
    """更新角色信息"""
    db_character = db.query(Character).filter(Character.id == character_id).first()
    if db_character:
        update_data = character_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_character, field, value)
        db.commit()
        db.refresh(db_character)
    return db_character

def delete_character(db: Session, character_id: int) -> bool:
    """删除角色"""
    db_character = db.query(Character).filter(Character.id == character_id).first()
    if db_character:
        db.delete(db_character)
        db.commit()
        return True
    return False
