#include "jpbb_board.h"
#include "jpbb_usb.h"

#include <stdio.h>

int main(void) {
  char report[192];
  uint32_t previous_report = 0U;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_rc_init();
  jpbb_usb_init();

  while (1) {
    jpbb_rc_channel_t channel[3];
    const uint32_t now = jpbb_millis();

    jpbb_manual_force();
    jpbb_rc_poll();
    jpbb_usb_poll();

    if ((now - previous_report) >= 250U && jpbb_usb_is_configured()) {
      previous_report = now;
      for (size_t i = 0U; i < 3U; ++i) {
        channel[i] = jpbb_rc_get(i);
      }
      (void)snprintf(
          report, sizeof(report),
          "RC manual_locked=1 ch1=%u valid=%u ch2=%u valid=%u "
          "ch3=%u valid=%u\r\n",
          channel[0].pulse_us, channel[0].valid ? 1U : 0U,
          channel[1].pulse_us, channel[1].valid ? 1U : 0U,
          channel[2].pulse_us, channel[2].valid ? 1U : 0U);
      (void)jpbb_usb_write(report);
    }
  }
}
