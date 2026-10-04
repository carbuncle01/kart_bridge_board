#include "jpbb_board.h"
#include "jpbb_usb.h"

#include <stdio.h>

int main(void) {
  char line[96];
  char response[128];
  bool announced = false;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_usb_init();

  while (1) {
    jpbb_manual_force();
    jpbb_usb_poll();

    if (jpbb_usb_is_configured() && !announced) {
      if (jpbb_usb_write(
              "JPBB step2_usb_cdc ready; type PING or any text\r\n")) {
        announced = true;
      }
    } else if (!jpbb_usb_is_configured()) {
      announced = false;
    }

    if (jpbb_usb_read_line(line, sizeof(line))) {
      if (line[0] == 'P' && line[1] == 'I' && line[2] == 'N' &&
          line[3] == 'G' && line[4] == '\0') {
        (void)jpbb_usb_write("PONG\r\n");
      } else {
        (void)snprintf(response, sizeof(response), "ECHO %s\r\n", line);
        (void)jpbb_usb_write(response);
      }
    }
  }
}
