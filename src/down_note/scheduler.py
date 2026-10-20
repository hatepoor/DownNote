"""APScheduler 注册表：只把后台任务挂到时间表上。

任务实现全部在 core/tasks；主动陪伴的判定在 core/companion。
两个定时任务都在启动时先跑一次（next_run_time=now）——用户的用法多是"开一会儿就关"，
首次执行排在 30 分钟后会永远等不到（见 docx/v0.1.2/modules/12-日整合即时补跑.md）。
对应开发文档：docx/v0.1.0/modules/05-分析管线.md、07-长期记忆.md、11-日整合与交互修订.md、
docx/v0.1.2/modules/02-分析提速.md、docx/v0.1.2/modules/12-日整合即时补跑.md
"""

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from down_note.core import companion, tasks

SCAN_INTERVAL_MINUTES = 30
MAINTENANCE_INTERVAL_MINUTES = 30
COMPANION_PATROL_MINUTES = 5  # 主动陪伴巡检（表一）：5 分钟一次，判定全是轻量程序

_scheduler: BackgroundScheduler | None = None


def startScheduler() -> None:
    """启动兜底扫描与记忆维护调度器；重复调用幂等（lifespan 与测试环境多次创建应用）。

    任务都设 next_run_time=now——应用打开就先在后台补跑一次（不阻塞窗口显示），
    否则"开一会儿就关"的用法永远等不到首次执行（2026-10-12 用户实测：四天没出整合日记）。
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    tasks.recoverInterruptedAnalyses()
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
            tasks.scanAndConsolidate,
            "interval",
            minutes=SCAN_INTERVAL_MINUTES,
            id="scan-and-consolidate",
            next_run_time=datetime.now(),
        )
    _scheduler.add_job(
            tasks.maintainMemories,
            "interval",
            minutes=MAINTENANCE_INTERVAL_MINUTES,
            id="maintain-memories",
            next_run_time=datetime.now(),
        )
    _scheduler.add_job(
            companion.patrol,
            "interval",
            minutes=COMPANION_PATROL_MINUTES,
            id="companion-patrol",
            next_run_time=datetime.now(),
        )
    _scheduler.start()


def stopScheduler() -> None:
    """停止调度器并复位全局（应用退出与测试收尾用；未启动时为空操作）。"""
    global _scheduler
    if _scheduler is None:
        return
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None