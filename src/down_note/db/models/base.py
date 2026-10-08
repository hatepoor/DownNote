"""SQLAlchemy 声明式基类：单独立文件，供各实体模块与建表共用（避免包内循环导入）。

对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
