#include "jpbb_board.h"
#include "jpbb_protocol.h"
#include "jpbb_usb.h"

static bool drive_rc_valid(void) {
  return jpbb_rc_get(0U).valid && jpbb_rc_get(1U).valid;
}

int main(void) {
  char line[96];
  char response[256];
  bool auto_requested = false;
  uint32_t last_heartbeat_ms = 0U;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_rc_init();
  jpbb_pwm_init();
  jpbb_pwm_set(JPBB_PWM_NEUTRAL_US, JPBB_PWM_NEUTRAL_US);
  jpbb_adc_init();
  jpbb_usb_init();
  jpbb_watchdog_init();

  while (1) {
    jpbb_command_t command = {0};
    const uint32_t now = jpbb_millis();

    jpbb_rc_poll();
    jpbb_usb_poll();
    const uint16_t vbec_mv = jpbb_vbec_read_mv();
    const bool rc_valid = drive_rc_valid();
    const bool heartbeat_ok = (now - last_heartbeat_ms) <= 500U;
    const bool usb_ok = jpbb_usb_vbus_present() &&
                        jpbb_usb_is_configured() && heartbeat_ok;

    if (!jpbb_vbec_is_healthy(vbec_mv)) {
      jpbb_manual_force();
      auto_requested = false;
    } else if (!rc_valid) {
      /*
       * RC喪失時はMANUAL側にも有効信号がないため、MCUの安全PWMを
       * AUTO経路から出します。VBEC異常時はU5がMUXを無効化します。
       */
      jpbb_pwm_set(JPBB_PWM_NEUTRAL_US, JPBB_PWM_NEUTRAL_US);
      (void)jpbb_auto_select(true);
    } else if (auto_requested && usb_ok) {
      const jpbb_rc_channel_t steering = jpbb_rc_get(0U);
      const jpbb_rc_channel_t throttle = jpbb_rc_get(1U);
      jpbb_pwm_set(steering.pulse_us, throttle.pulse_us);
      (void)jpbb_auto_select(true);
    } else {
      jpbb_manual_force();
    }

    if (jpbb_usb_read_line(line, sizeof(line))) {
      if (!jpbb_protocol_parse(line, &command)) {
        (void)jpbb_usb_write("ERR command\r\n");
      } else if (command.kind == JPBB_COMMAND_HEARTBEAT ||
                 command.kind == JPBB_COMMAND_PING) {
        last_heartbeat_ms = now;
        (void)jpbb_usb_write("PONG\r\n");
      } else if (command.kind == JPBB_COMMAND_AUTO) {
        auto_requested = true;
        last_heartbeat_ms = now;
        (void)jpbb_usb_write(
            "OK AUTO requested; send HEARTBEAT at least every 500 ms\r\n");
      } else if (command.kind == JPBB_COMMAND_MANUAL) {
        auto_requested = false;
        jpbb_manual_force();
        (void)jpbb_usb_write("OK MANUAL\r\n");
      } else if (command.kind == JPBB_COMMAND_STATUS) {
        (void)jpbb_protocol_status(response, sizeof(response));
        (void)jpbb_usb_write(response);
      }
    }

    jpbb_watchdog_refresh();
  }
}
