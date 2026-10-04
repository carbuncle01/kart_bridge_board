/*
 * KiCad 10.0.4 / macOS 26 CLI DRC compatibility shim.
 *
 * When a DRC job commits its marker update, BOARD_COMMIT::Push asks wxWidgets
 * for the current mouse position.  A command-line process has no AppKit
 * application, so wxGetMousePosition() aborts in _RegisterApplication before
 * the official DRC report can be written.  The returned position is only an
 * interactive tool-event coordinate and is not consumed by the DRC engine.
 * Interposing a neutral wxPoint therefore leaves every board/rule check intact
 * while avoiding the macOS-only UI registration crash.
 */
typedef struct {
    int x;
    int y;
} wx_point_layout;

/* Mach-O symbol spelling as exported by KiCad's wxWidgets build. */
extern wx_point_layout wx_get_mouse_position(void)
    __asm__("__Z18wxGetMousePositionv");

static wx_point_layout jpbb_wx_get_mouse_position(void)
{
    wx_point_layout point = { 0, 0 };
    return point;
}

__attribute__((used, section("__DATA,__interpose")))
static const struct {
    const void *replacement;
    const void *replacee;
} interpose_wx_get_mouse_position = {
    (const void *) jpbb_wx_get_mouse_position,
    (const void *) wx_get_mouse_position,
};
