from enocean_async_tui.app import EnOceanApp


async def test_app_starts() -> None:
    async with EnOceanApp().run_test() as pilot:
        assert pilot.app is not None
