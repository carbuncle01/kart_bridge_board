#include "jpbb_board.h"
#include "jpbb_control.h"
#include "jpbb_protocol.h"
#include "jpbb_usb.h"

#include <stdio.h>

static bool any_rc_present(const jpbb_control_inputs_t *inputs) {
  return inputs->rc1_valid || inputs->rc2_valid || inputs->rc3_valid;
}

int main(void) {
  char line[96];
  char response[256];
  uint16_t desired_servo_us = JPBB_SERVO_SAFE_US;
  uint16_t desired_esc_us = JPBB_ESC_SAFE_US;
  jpbb_control_t control;
  jpbb_authority_t authority = JPBB_AUTHORITY_SAFE;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_control_init(&control);
  jpbb_rc_init();
  jpbb_pwm_init();
  jpbb_pwm_set(JPBB_SERVO_SAFE_US, JPBB_ESC_SAFE_US);
  jpbb_adc_init();
  jpbb_usb_init();
  jpbb_watchdog_init();

  while (1) {
    jpbb_command_t command = {0};
    const uint32_t now = jpbb_millis();

    jpbb_rc_poll();
    jpbb_usb_poll();
    const uint16_t vbec_mv = jpbb_vbec_read_mv();
    const jpbb_rc_channel_t rc1 = jpbb_rc_get(0U);
    const jpbb_rc_channel_t rc2 = jpbb_rc_get(1U);
    const jpbb_rc_channel_t rc3 = jpbb_rc_get(2U);
    const jpbb_control_inputs_t inputs = {
        .now_ms = now,
        .ch3_us = rc3.pulse_us,
        .vbec_healthy = jpbb_vbec_is_healthy(vbec_mv),
        .usb_healthy =
            jpbb_usb_vbus_present() && jpbb_usb_is_configured(),
        .rc1_valid = rc1.valid,
        .rc2_valid = rc2.valid,
        .rc3_valid = rc3.valid,
    };

    authority = jpbb_control_update(&control, &inputs);
    if (authority == JPBB_AUTHORITY_RC) {
      jpbb_manual_force();
    } else if (authority == JPBB_AUTHORITY_PC) {
      jpbb_pwm_set(desired_servo_us, desired_esc_us);
      (void)jpbb_auto_select(true);
    } else if (inputs.vbec_healthy) {
      /*
       * SAFE uses the MCU path because the MANUAL path may be absent or stale.
       * U5 independently disables the MUX when VBEC is below its valid range.
       */
      jpbb_pwm_set(JPBB_SERVO_SAFE_US, JPBB_ESC_SAFE_US);
      (void)jpbb_auto_select(true);
    } else {
      jpbb_manual_force();
    }

    if (jpbb_usb_read_line(line, sizeof(line))) {
      if (!jpbb_protocol_parse(line, &command)) {
        (void)jpbb_usb_write("ERR invalid command; type HELP\r\n");
      } else if (command.kind == JPBB_COMMAND_PING ||
                 command.kind == JPBB_COMMAND_HEARTBEAT) {
        jpbb_control_note_heartbeat(&control, now);
        (void)jpbb_usb_write("PONG\r\n");
      } else if (command.kind == JPBB_COMMAND_SET ||
                 command.kind == JPBB_COMMAND_STREAM) {
        desired_servo_us = command.servo_us;
        desired_esc_us = command.esc_us;
        jpbb_control_note_command(&control, now);
        if (command.kind == JPBB_COMMAND_SET) {
          (void)jpbb_usb_write("OK SET\r\n");
        }
      } else if (command.kind == JPBB_COMMAND_AUTO) {
        if (!control.command_received) {
          (void)jpbb_usb_write("ERR send SET before AUTO\r\n");
        } else if ((now - control.last_command_ms) >
                   JPBB_HOST_COMMAND_TIMEOUT_MS) {
          (void)jpbb_usb_write("ERR send a fresh SET before AUTO\r\n");
        } else if (!inputs.vbec_healthy) {
          (void)jpbb_usb_write("ERR PC refused: VBEC unhealthy\r\n");
        } else if (any_rc_present(&inputs) &&
                   control.ch3_request != JPBB_CH3_REQUEST_PC) {
          (void)jpbb_usb_write(
              "ERR PC refused: set CH3 to PC and wait for confirmation\r\n");
        } else if (jpbb_control_arm_pc(&control, &inputs)) {
          (void)jpbb_usb_write(
              "OK PC armed; stream SET within 200 ms and HEARTBEAT "
              "within 500 ms\r\n");
        } else {
          (void)jpbb_usb_write("ERR PC refused: USB not ready\r\n");
        }
      } else if (command.kind == JPBB_COMMAND_MANUAL) {
        jpbb_control_disarm_pc(&control);
        (void)jpbb_usb_write(
            "OK PC disarmed; CH3 RC selects receiver control\r\n");
      } else if (command.kind == JPBB_COMMAND_STATUS) {
        uint16_t servo_us;
        uint16_t esc_us;
        jpbb_pwm_get(&servo_us, &esc_us);
        (void)snprintf(
            response, sizeof(response),
            "STATUS authority=%s mux=%s pc_armed=%u host_ready=%u "
            "ch3_request=%s ch3=%u/%u usb=%u vbec_mv=%u "
            "rc1=%u/%u rc2=%u/%u servo=%u esc=%u\r\n",
            jpbb_authority_name(authority),
            jpbb_auto_is_selected() ? "MCU" : "RC",
            control.pc_armed ? 1U : 0U,
            jpbb_control_host_ready(&control, &inputs) ? 1U : 0U,
            jpbb_ch3_request_name(control.ch3_request), rc3.pulse_us,
            rc3.valid ? 1U : 0U, inputs.usb_healthy ? 1U : 0U, vbec_mv,
            rc1.pulse_us, rc1.valid ? 1U : 0U, rc2.pulse_us,
            rc2.valid ? 1U : 0U, servo_us, esc_us);
        (void)jpbb_usb_write(response);
      } else if (command.kind == JPBB_COMMAND_HELP) {
        (void)jpbb_protocol_help(response, sizeof(response));
        (void)jpbb_usb_write(response);
      }
    }

    jpbb_watchdog_refresh();
  }
}
