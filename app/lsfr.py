from .model import r

def lfsr64_step(state: int) -> int:
    tap = ((state >> 0) ^ (state >> 1) ^ (state >> 3) ^ (state >> 4)) & 1
    return ((state >> 1) | (tap << 63)) & 0xFFFFFFFFFFFFFFFF


def next_order_id_64(r, state_key: str) -> str:
    state = r.get(state_key)
    if state is None:
        state = 0xF23456789ABCDEFF  # random nonzero seed
    else:
        state = int(state)

    new_state = lfsr64_step(state)
    r.set(state_key, new_state)

    # 16 hex chars = 64 bits, or format however you want
    return f"{new_state:016x}"
