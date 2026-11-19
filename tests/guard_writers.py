"""Run the assembled AS hooks with synthetic registers. Requires Unicorn and
the standalone build's module.elf, subsdk9 and IPS. Run after build_core.py.
"""
import itertools
import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn import arm64_const as arm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_core import MAIN_BUILD_ID, OUT, STOCK_MAIN, symbol_table
from lib.nso import parse_ips32, text_bytes


def main():
    symbols = symbol_table(OUT / "module.elf")
    exefs = OUT / "exefs"
    code = text_bytes((exefs / "subsdk9").read_bytes())
    patches = {offset - 0x100: data for offset, data, _ in
               parse_ips32((exefs / (MAIN_BUILD_ID + ".ips")).read_bytes())}
    base = symbols["__base"]
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(base, (len(code) + 4095) & ~4095)
    uc.mem_write(base, code)
    pages = {symbols[name] & ~4095 for name in ("g_ms_iface", "g_ms_active", "g_ms_allowed")}
    pages.add(0x37ba000)
    for page in pages:
        uc.mem_map(page, 4096)
    player = 0x200000
    cases = 0
    for named, active, iface, param, allowed, value in itertools.product(
            (False, True), (0, 1), (0, player, player + 8), (2, 14, 50), (0, 1), (0, 1, 2, 3)):
        site = 0x37ba094 if named else 0x37ba100
        result = allowed if active and iface == player and param == 14 else value
        uc.mem_write(site, patches[site])  # enter through the IPS branch
        uc.mem_write(symbols["g_ms_iface"], struct.pack("<Q", iface))
        uc.mem_write(symbols["g_ms_allowed"], bytes([allowed]))
        uc.mem_write(symbols["g_ms_active"], bytes([active]))
        regs = [arm.UC_ARM64_REG_X0 + i for i in range(29)]
        before = [0x110000 + i for i in range(29)]
        before[0], before[2] = player, value
        before[8 if named else 1] = param
        for reg, initial in zip(regs, before):
            uc.reg_write(reg, initial)
        uc.reg_write(arm.UC_ARM64_REG_NZCV, 0xa0000000)
        uc.emu_start(site, site + 4, count=48)
        assert uc.reg_read(arm.UC_ARM64_REG_PC) == site + 4
        if named:
            before[9] = result & 1
            assert [uc.reg_read(reg) for reg in regs] == before
            assert uc.reg_read(arm.UC_ARM64_REG_NZCV) == 0xa0000000
        else:
            assert uc.reg_read(arm.UC_ARM64_REG_W2) == result
        cases += 1
    print(f"PASS {cases} assembled guard-writer cases")

    # Replay the stock name setter from the point where it has resolved Bool14.
    # Compare the old hook coverage with the branch patch. A write also bumps
    # a per-parameter counter, which the game must still see in both cases.
    stock = text_bytes(STOCK_MAIN.read_bytes())
    start, site, end = 0x37ba08c, 0x37ba094, 0x37ba0cc
    assert stock[site:site + 4] == bytes.fromhex("49 00 00 12")
    uc.mem_write(start, stock[start:end])
    uc.mem_map(player, 0x3000)
    for offset, address in ((0x30, player + 0x1000), (0x60, player + 0x2000)):
        uc.mem_write(player + offset, struct.pack("<Q", address))
        uc.mem_write(address, struct.pack("<I", 32))
    uc.mem_write(symbols["g_ms_active"], b"\x01")
    uc.mem_write(symbols["g_ms_allowed"], b"\x00")
    uc.mem_write(symbols["g_ms_iface"], struct.pack("<Q", player))
    value_addr = player + 0x1000 + 4 + 14
    count_addr = player + 0x2000 + 4 + 14
    for patched in (False, True):
        if patched:
            uc.mem_write(site, patches[site])
        uc.ctl_remove_cache(start, end)
        uc.reg_write(arm.UC_ARM64_REG_X0, player)
        uc.reg_write(arm.UC_ARM64_REG_W2, 1)
        uc.reg_write(arm.UC_ARM64_REG_W8, 14)
        uc.mem_write(value_addr, b"\x00")
        uc.mem_write(count_addr, b"\x07")
        uc.emu_start(start, end, count=64)
        assert uc.reg_read(arm.UC_ARM64_REG_PC) == end
        assert uc.mem_read(value_addr, 1)[0] == (0 if patched else 1)
        assert uc.mem_read(count_addr, 1)[0] == 8
    print("PASS stock named-writer replay, baseline and patched")


if __name__ == "__main__":
    main()
