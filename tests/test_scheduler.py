from app.core.scheduler import IntervalScheduler


def test_scheduler_stops_and_isolates_task_exception() -> None:
    scheduler = IntervalScheduler(interval_seconds=0.01)
    completed: list[str] = []

    def failing_task() -> None:
        raise RuntimeError("模拟单任务异常")

    def successful_task() -> None:
        completed.append("done")
        scheduler.stop()

    scheduler.add_task("failing", failing_task)
    scheduler.add_task("successful", successful_task)
    scheduler.run()

    assert completed == ["done"]
