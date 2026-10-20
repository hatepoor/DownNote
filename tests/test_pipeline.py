"""条目处理编排测试：分析成功才生成回应、分析无产出不回应、回应失败不影响分析结果。"""

from down_note.core import pipeline
from down_note.core.analysis import MoodResult


def _mood() -> MoodResult:
    return MoodResult(labels=["平静"], intensity=4, summary="还行", crisis=False)


def test_analyzeAndReplyCallsReplyOnSuccess(monkeypatch):
    """分析有产出 → 尝试生成条目回应（开关与类型判断由回应模块自己负责）。"""
    calls: list[int] = []
    monkeypatch.setattr(pipeline.analysis, "analyzeEntry", lambda entryId: _mood())
    monkeypatch.setattr(pipeline.entryReply, "generateEntryReply", lambda entryId: calls.append(entryId))

    result = pipeline.analyzeAndReply(7)

    assert result is not None
    assert calls == [7]


def test_analyzeAndReplySkipsReplyWhenAnalysisProducesNothing(monkeypatch):
    """分析未产出（降级 / 认领失败 / 非法 JSON）→ 不进入回应步骤。"""
    calls: list[int] = []
    monkeypatch.setattr(pipeline.analysis, "analyzeEntry", lambda entryId: None)
    monkeypatch.setattr(pipeline.entryReply, "generateEntryReply", lambda entryId: calls.append(entryId))

    assert pipeline.analyzeAndReply(7) is None
    assert calls == []


def test_analyzeAndReplySwallowsReplyFailure(monkeypatch):
    """回应步骤抛异常不得影响已经成功的分析结果。"""
    def boom(entryId: int):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline.analysis, "analyzeEntry", lambda entryId: _mood())
    monkeypatch.setattr(pipeline.entryReply, "generateEntryReply", boom)

    assert pipeline.analyzeAndReply(7) is not None
