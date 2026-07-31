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


def test_scheduler_stop_prevents_another_market_collection() -> None:
    scheduler = IntervalScheduler(interval_seconds=0.01)
    collection_count = 0

    def collect_market_quotes() -> None:
        nonlocal collection_count
        collection_count += 1
        scheduler.stop()

    scheduler.add_task("market-collection", collect_market_quotes)
    scheduler.run()

    assert collection_count == 1
