"""ORM 模型与数据访问函数：一实体一文件，汇总导出保持 models.xxx 调用不变。

SQLAlchemy 2.0 声明式映射（ADR-0006）。列名与 ORM 属性用 snake_case
（编码规范的"数据库约定字段"例外），API 层 JSON 输出再转驼峰。
表设计见 docx/v0.1.0/02-架构设计.md。
对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md
"""

from down_note.db.models.base import Base
from down_note.db.models.entry import (
        ANALYZE_DONE,
        ANALYZE_FAILED,
        ANALYZE_PENDING,
        ANALYZE_RUNNING,
        Entry,
        addDailyEntry,
        addEntry,
        claimForAnalysis,
        getDailyEntry,
        getEntry,
        listDayEntries,
        listDaysNeedingDiaryMemory,
        listEntriesWithMood,
        listEntryDays,
        listPastDaysMissingDigest,
        listUnanalyzedIds,
        markEntryAnalyzed,
        mergeDayBlocks,
        resetStaleRunning,
        searchEntries,
        setAnalyzeState,
        updateEntryContent,
    )
from down_note.db.models.memory import (
        LongTermMemory,
        addLongTermMemory,
        deleteLongTermMemory,
        getLongTermMemory,
        listLongTermMemories,
        updateLongTermMemory,
    )
from down_note.db.models.message import Message, addMessage, firstUserMessage, listMessages
from down_note.db.models.mood import Mood, clearMood, getMoodByEntry, listRecentMoods, upsertMood
from down_note.db.models.session import (
        ChatSession,
        listRecentSessions,
        listSessionsNeedingMaintenance,
        markSessionMaintained,
        upsertChatSession,
    )
from down_note.db.models.setting import DIARY_MEMORY_DONE_PREFIX, Setting, getSetting, setSetting
