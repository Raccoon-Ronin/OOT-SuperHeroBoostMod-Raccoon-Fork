/* Host regression for the production HID and scheduler handlers. Run with an
 * x86-64 C compiler, linking core/hid.c and features/manual_shield/manual_shield.c.
 * The arrays stand in for the small subset of game objects used by the handlers. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../core/config.h"
#include "../core/hid.h"

void manual_shield_on_input(u32, void *, void *, void *, u32);
void manual_shield_on_frame(void *);
extern unsigned char g_ms_allowed;
extern u64 g_ms_iface;
volatile ShbConfig g_shbcfg;
u32 g_sw_cancel_frame;
_Alignas(u64) char GAMEDATA_MGR[sizeof(u64)];

static u64 state[0x1000/8], actor[0x280/8], table[0x300/8], anim[4], layer[4], owner[9];
static u64 iface[1], vtable[0x90/8], component[5], equipment;
static u64 manager[0xc30/8], entry[4], lifter[0x2b8/8];
static u32 map[2] = {0x834d9d9eu, 0}, target_mode;
static int ingame = 1, dead, locked, child, shield, busy, have_component = 1;
static u32 draws, writes, last_bool;

static void put32(void *p, size_t offset, u32 value) {
    memcpy((char *)p + offset, &value, sizeof value);
}
static u32 get32(const void *p, size_t offset) {
    u32 value;
    memcpy(&value, (const char *)p + offset, sizeof value);
    return value;
}
int player_dead(void) { return dead; }
u64 player_get(void) { return (u64)state; }
int hud_ingame(void) { return ingame; }
int hud_is_child(void) { return child; }
const char *player_state_name(void) { return "Wait"; }
int player_state_starts(const char *s) { (void)s; return 0; }
int player_state_is(const char *s) { return !strcmp(s, "Wait"); }
u32 hud_frame_count(void) { return 1; }
u64 attention_locked_actor(void) { return locked ? (u64)actor : 0; }
void *resolve_player(void *scheduler) { (void)scheduler; return state; }
u64 get_guard_component(void *a) { assert(a == actor); return have_component ? (u64)component : 0; }
u32 read_enum(void *mgr, u32 *out, void *desc, u32 field) {
    assert(mgr == manager && desc && field == 0xc713c7dau);
    *out = target_mode;
    return 1;
}
u32 as_bool(void *a, u32 id) { assert(a == iface); return id == 62 && busy; }
u32 as_int(void *a, u32 id) { assert(a == iface); return id == 2 ? shield : 0; }
void native_draw_equipment(void *e, u32 kind) { assert(e == &equipment && kind == 4); draws++; }
static void setter(void *a, u32 id, u32 value) {
    assert(a == iface && id == 14);
    last_bool = value;
    writes++;
}

static u64 input(u64 buttons) {
    u64 sample[HID_STRIDE / 8] = {0};
    sample[HID_BUTTON_OFFSET / 8] = buttons;
    manual_shield_on_input(3, sample, (void *)1, NULL, 1);
    return sample[HID_BUTTON_OFFSET / 8];
}
static void frame(void) { manual_shield_on_frame(state); }
static void expect_guard(u32 up) {
    frame();
    assert(g_ms_allowed == up && last_bool == up);
    assert(!!(get32(state, 0xe50) & 0x80000) == up);
    assert(!!(get32(component, 0x24) & 0x20) == up);
    assert(get32(state, 0xe50) & 0x100);  /* stock target bit survives release */
}
static void start(int hold) {
    g_shbcfg.manual_shield = 0;
    frame();
    target_mode = hold ? 0x60fc6939u : 0x212dc0e7u;
    g_shbcfg.manual_shield = 1;
    frame();
    draws = 0;
}
int main(void) {
    u64 manager_address = (u64)manager;
    memcpy(GAMEDATA_MGR, &manager_address, sizeof manager_address);
    manager[0xc20/8] = (u64)map;
    manager[0xc18/8] = (u64)entry;
    put32(manager, 0xc2c, 1);
    put32(manager, 0xc10, 1);
    state[0x18/8] = (u64)actor;
    put32(state, 0xe50, 0x100);
    actor[0x270/8] = (u64)table;
    table[0x40/8] = (u64)anim;
    table[0x200/8] = (u64)&equipment;
    anim[3] = (u64)layer;
    layer[3] = (u64)owner;
    owner[8] = (u64)iface;
    iface[0] = (u64)vtable;
    vtable[0x88/8] = (u64)setter;

    start(1);
    child = 1;
    shield = 2;
    assert(input(BTN_ZL) == BTN_ZL);
    expect_guard(0);
    assert(input(BTN_ZL | BTN_L | BTN_R) == (BTN_ZL | BTN_R));
    expect_guard(1);
    expect_guard(1);
    assert(draws == 0);  /* native turtle guard, no extra equipment draw */
    assert(input(BTN_ZL) == BTN_ZL);
    expect_guard(0);
    input(BTN_ZL | BTN_L);
    input(BTN_ZL);  /* both edges between scheduler frames */
    expect_guard(1);
    expect_guard(0);
    input(BTN_ZL | BTN_L);
    input(0);       /* lost targeting before the pending press could be used */
    expect_guard(0);
    assert(input(BTN_L | BTN_ZR) == (BTN_L | BTN_ZR));
    expect_guard(0);

    start(0);
    assert(input(BTN_ZL) == BTN_ZL);
    expect_guard(0);
    locked = 1;
    for (int age = -1; age <= 1; age++) {
        child = age;
        shield = age == 1 ? 1 : 2;
        assert(input(BTN_L) == 0);
        expect_guard(1);
        expect_guard(1);
        assert(draws == (u32)(age + 2));  /* one draw per entry */
        assert(input(0) == 0);
        expect_guard(0);
    }
    busy = 1;
    input(BTN_L);
    input(0);
    expect_guard(0);
    busy = 0;
    expect_guard(0);
    table[0x2c8/8] = (u64)lifter;
    put32(lifter, 0x2b0, 1);
    input(BTN_L);
    expect_guard(0);
    input(0);
    put32(lifter, 0x2b0, 0);
    expect_guard(0);
    input(BTN_L);
    ingame = 0;
    assert(input(BTN_L | BTN_ZL) == (BTN_L | BTN_ZL));
    expect_guard(0);
    ingame = 1;
    expect_guard(0);
    dead = 1;
    assert(input(BTN_L) == BTN_L);
    expect_guard(0);
    dead = 0;
    have_component = 0;
    frame();
    assert(g_ms_iface == (u64)iface && !g_ms_allowed);
    have_component = 1;
    g_shbcfg.manual_shield = 0;
    u32 before = writes;
    assert(input(BTN_ZL | BTN_L) == (BTN_ZL | BTN_L));
    frame();
    assert(writes == before);
    g_shbcfg.auto_target = 1;
    assert(input(BTN_ZL | BTN_L) == (BTN_ZL | BTN_L));
    frame();
    assert(writes == before);
    puts("PASS manual guard input, scheduler, and equipment regression");
    return 0;
}
