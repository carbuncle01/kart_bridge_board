#include "jpbb_board.h"
#include "jpbb_protocol.h"
#include "jpbb_usb.h"

#include <stdio.h>

static bool drive_rc_valid(void) {
  return jpbb_rc_get(0U).valid && jpbb_rc_get(1U).valid;
}

int main(void) {
  char line[96];
  char response[192];
  bool auto_requested = false;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_rc_init();
  jpbb_pwm_init();
  jpbb_pwm_set(JPBB_PWM_NEUTRAL_US, JPBB_PWM_NEUTRAL_US);
  jpbb_usb_init();

  while (1) {
    jpbb_command_t command = {0};
    jpbb_rc_channel_t steering;
    jpbb_rc_channel_t throttle;

    jpbb_rc_poll();
    jpbb_usb_poll();
    steering = jpbb_rc_get(0U);
    throttle = jpbb_rc_get(1U);

    if (steering.valid && throttle.valid) {
      jpbb_pwm_set(steering.pulse_us, throttle.pulse_us);
    }

    if (!auto_requested || !drive_rc_valid()) {
      jpbb_manual_force();
    } else {
      (void)jpbb_auto_select(true);
    }

    if (!jpbb_usb_read_line(line, sizeof(line))) {
      continue;
    }
    if (!jpbb_protocol_parse(line, &command)) {
      (void)jpbb_usb_write("ERR command\r\n");
      continue;
    }

    if (command.kind == JPBB_COMMAND_AUTO) {
      if (drive_rc_valid()) {
        auto_requested = true;
        (void)jpbb_usb_write(
            "OK AUTO pending; switch occurs during PWM low window\r\n");
      } else {
        (void)jpbb_usb_write("ERR AUTO refused: RC1/RC2 invalid\r\n");
      }
    } else if (command.kind == JPBB_COMMAND_MANUAL) {
      auto_requested = false;
      jpbb_manual_force();
      (void)jpbb_usb_write("OK MANUAL\r\n");
    } else if (command.kind == JPBB_COMMAND_STATUS) {
      (void)snprintf(
          response, sizeof(response),
          "STATUS mode=%s requested=%u rc1=%u/%u rc2=%u/%u\r\n",
          jpbb_auto_is_selected() ? "AUTO" : "MANUAL",
          auto_requested ? 1U : 0U, steering.pulse_us,
          steering.valid ? 1U : 0U, throttle.pulse_us,
          throttle.valid ? 1U : 0U);
      (void)jpbb_usb_write(response);
    } else {
      (void)jpbb_usb_write("ERR this step supports AUTO/MANUAL/STATUS\r\n");
    }
  }
}
