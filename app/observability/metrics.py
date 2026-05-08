from time import perf_counter


class Timer:
    def __init__(self) -> None:
        self.start = perf_counter()

    def stop_ms(self) -> float:
        return round((perf_counter() - self.start) * 1000, 2)
