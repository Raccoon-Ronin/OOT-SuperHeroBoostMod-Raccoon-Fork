/* Assembly side of the manual shield feature.
 *
 * Stock instructions are replaced by branches to these wrappers. They
 * keep the original register contract and jump back to the stock continuation
 * (or to the stock function body), so the game's own guard/target logic stays
 * in charge of locomotion and animation.
 */
.text

/* main+0x37BA100: the AS Bool array setter, first instruction `tbnz w1,#31`.
 * Scope Bool14 (guard) writes to our player interface and follow g_ms_allowed. */
.global hook_guard_setter
.type hook_guard_setter, %function
hook_guard_setter:
    tbnz w1, #31, 2f
    adrp x9, g_ms_active
    add  x9, x9, :lo12:g_ms_active
    ldrb w9, [x9]
    cbz  w9, 1f
    adrp x9, g_ms_iface
    add  x9, x9, :lo12:g_ms_iface
    ldr  x9, [x9]
    cbz  x9, 1f
    cmp  x0, x9
    b.ne 1f
    cmp  w1, #14
    b.ne 1f
    adrp x9, g_ms_allowed
    add  x9, x9, :lo12:g_ms_allowed
    ldrb w9, [x9]
    cbz  w9, 3f
    mov  w2, #1
    b    1f
3:
    mov  w2, #0
1:
    b GUARD_SETTER_BODY
2:
    b GUARD_SETTER_EARLY
.size hook_guard_setter, . - hook_guard_setter

/* The name-based setter resolves the index in w8 and writes the bool inline,
 * bypassing hook_guard_setter. At this point x0 is the AS interface and w9
 * is the destination of the displaced instruction. Preserve w2 and NZCV. */
.global hook_guard_named_value
.type hook_guard_named_value, %function
hook_guard_named_value:
    eor  w9, w8, #14
    cbnz w9, 1f
    adrp x9, g_ms_active
    ldrb w9, [x9, :lo12:g_ms_active]
    cbz  w9, 1f
    adrp x9, g_ms_iface
    ldr  x9, [x9, :lo12:g_ms_iface]
    eor  x9, x9, x0
    cbnz x9, 1f
    adrp x9, g_ms_allowed
    ldrb w9, [x9, :lo12:g_ms_allowed]
    b    GUARD_NAMED_RESUME
1:
    and  w9, w2, #1
    b    GUARD_NAMED_RESUME
.size hook_guard_named_value, . - hook_guard_named_value

/* main+0x972E18: `orr w8,w8,w9` writing the player's target/guard flags.
 * The stock path sets the 0x80000 target-guard bit; when the guard is not
 * allowed for our player state, clear it before the store at +4. */
.global hook_guard_flags
.type hook_guard_flags, %function
hook_guard_flags:
    stp x16, x17, [sp, #-16]!
    adrp x16, g_ms_active
    add  x16, x16, :lo12:g_ms_active
    ldrb w17, [x16]
    cbz  w17, 1f
    adrp x16, g_ms_state
    add  x16, x16, :lo12:g_ms_state
    ldr  x16, [x16]
    cbz  x16, 1f
    cmp  x20, x16
    b.ne 1f
    adrp x16, g_ms_allowed
    add  x16, x16, :lo12:g_ms_allowed
    ldrb w17, [x16]
    cbnz w17, 1f
    bic  w8, w8, #0x80000
    bic  w9, w9, #0x80000
1:
    ldp x16, x17, [sp], #16
    orr  w8, w8, w9
    b GUARD_FLAGS_RESUME
.size hook_guard_flags, . - hook_guard_flags

/* main+0x97320C: `orr w9,w9,#0x80000` for the same flags from the update path.
 * Set it for other actors/native states, clear it for our player when the guard
 * is not allowed, then continue with the store at +4. */
.global hook_guard_update
.type hook_guard_update, %function
hook_guard_update:
    stp x16, x17, [sp, #-16]!
    adrp x16, g_ms_active
    add  x16, x16, :lo12:g_ms_active
    ldrb w17, [x16]
    cbz  w17, 2f
    adrp x16, g_ms_state
    add  x16, x16, :lo12:g_ms_state
    ldr  x16, [x16]
    cbz  x16, 2f
    cmp  x21, x16
    b.ne 2f
    adrp x16, g_ms_allowed
    add  x16, x16, :lo12:g_ms_allowed
    ldrb w17, [x16]
    cbnz w17, 2f
    bic  w9, w9, #0x80000
    b    1f
2:
    orr  w9, w9, #0x80000
1:
    ldp x16, x17, [sp], #16
    b GUARD_UPDATE_RESUME
.size hook_guard_update, . - hook_guard_update
