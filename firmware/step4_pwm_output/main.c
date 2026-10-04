#include "jpbb_board.h"
#include "jpbb_protocol.h"
#include "jpbb_usb.h"

#include <stdio.h>

int main(void) {
  char line[96];
  char response[128];
  uint16_t servo_us = JPBB_PWM_NEUTRAL_US;
  uint16_t esc_us = JPBB_PWM_NEUTRAL_US;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_pwm_init();
  jpbb_pwm_set(servo_us, esc_us);
  jpbb_usb_init();

  while (1) {
    jpbb_command_t command = {0};

    jpbb_manual_force();
    jpbb_usb_poll();
    if (!jpbb_usb_read_line(line, sizeof(line))) {
      continue;
    }

    if (!jpbb_protocol_parse(line, &command)) {
      (void)jpbb_usb_write("ERR command; use SET 1500 1500 or STATUS\r\n");
      continue;
    }

    if (command.kind == JPBB_COMMAND_SET) {
      servo_us = command.servo_us;
      esc_us = command.esc_us;
      jpbb_pwm_set(servo_us, esc_us);
      (void)jpbb_usb_write("OK PWM updated; MUX remains MANUAL\r\n");
    } else if (command.kind == JPBB_COMMAND_STATUS) {
      (void)snprintf(response, sizeof(response),
                     "PWM servo=%u esc=%u manual_locked=1\r\n",
                     servo_us, esc_us);
      (void)jpbb_usb_write(response);
    } else if (command.kind == JPBB_COMMAND_HELP) {
      (void)jpbb_protocol_help(response, sizeof(response));
      (void)jpbb_usb_write(response);
    } else {
      (void)jpbb_usb_write("ERR this step only supports SET/STATUS/HELP\r\n");
    }
  }
}
