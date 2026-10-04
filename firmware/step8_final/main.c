#include "jpbb_board.h"
#include "jpbb_control.h"
#include "jpbb_protocol.h"
#include "jpbb_usb.h"

#include <stdio.h>
#include <string.h>

#define JPBB_STATUS_PERIOD_MS 50U

enum {
  JPBB_FAULT_VBEC = 1UL << 0,
  JPBB_FAULT_USB = 1UL << 1,
  JPBB_FAULT_RECEIVER = 1UL << 2,
  JPBB_FAULT_CH3 = 1UL << 3,
  JPBB_FAULT_RC_SIGNAL = 1UL << 4,
  JPBB_FAULT_COMMAND_TIMEOUT = 1UL << 5,
  JPBB_FAULT_HEARTBEAT_TIMEOUT = 1UL << 6,
  JPBB_FAULT_COMMAND_VALUE = 1UL << 7,
};

static bool any_rc_present(const jpbb_control_inputs_t *inputs) {
  return inputs->rc1_valid || inputs->rc2_valid || inputs->rc3_valid;
}

static const char *receiver_state_name(const jpbb_control_t *control,
                                       const jpbb_control_inputs_t *inputs) {
  if (!any_rc_present(inputs)) {
    return control->receiver_latched ? "LOST" : "NONE";
  }
  if (inputs->rc1_valid && inputs->rc2_valid && inputs->rc3_valid) {
    return "READY";
  }
  if (inputs->rc1_valid && inputs->rc2_valid) {
    return "NO_CH3";
  }
  return "PARTIAL";
}

static const char *failsafe_reason(const jpbb_control_t *control,
                                   const jpbb_control_inputs_t *inputs,
                                   jpbb_authority_t authority) {
  if (authority != JPBB_AUTHORITY_SAFE) {
    return "NONE";
  }
  if (!inputs->vbec_healthy) {
    return "VBEC";
  }
  if (control->receiver_latched && !inputs->rc3_valid) {
    return "RECEIVER_LOSS";
  }
  if (control->ch3_request == JPBB_CH3_REQUEST_RC &&
      !(inputs->rc1_valid && inputs->rc2_valid)) {
    return "RC_SIGNAL";
  }
  if (any_rc_present(inputs) &&
      control->ch3_request != JPBB_CH3_REQUEST_PC) {
    return "CH3";
  }
  if (!inputs->usb_healthy) {
    return "USB";
  }
  if (!control->command_received) {
    return "NO_COMMAND";
  }
  if ((inputs->now_ms - control->last_command_ms) >
      JPBB_HOST_COMMAND_TIMEOUT_MS) {
    return "COMMAND_TIMEOUT";
  }
  if (!control->heartbeat_received) {
    return "NO_HEARTBEAT";
  }
  if ((inputs->now_ms - control->last_heartbeat_ms) >
      JPBB_HOST_HEARTBEAT_TIMEOUT_MS) {
    return "HEARTBEAT_TIMEOUT";
  }
  if (!control->pc_armed) {
    return "DISARMED";
  }
  return "INTERLOCK";
}

static bool host_command_is_neutral(const jpbb_command_t *command) {
  return command->steering_milli == 0 && command->throttle_milli == 0U &&
         command->reverse_milli == 0U && command->brake_milli == 0U;
}

static uint32_t fault_bits(const jpbb_control_t *control,
                           const jpbb_control_inputs_t *inputs,
                           bool command_value_fault) {
  uint32_t faults = command_value_fault ? JPBB_FAULT_COMMAND_VALUE : 0U;

  if (!inputs->vbec_healthy) {
    faults |= JPBB_FAULT_VBEC;
  }
  if (!inputs->usb_healthy && control->pc_armed) {
    faults |= JPBB_FAULT_USB;
  }
  if (control->receiver_latched && !inputs->rc3_valid) {
    faults |= JPBB_FAULT_RECEIVER;
  }
  if (any_rc_present(inputs) &&
      control->ch3_request == JPBB_CH3_UNKNOWN) {
    faults |= JPBB_FAULT_CH3;
  }
  if (control->ch3_request == JPBB_CH3_REQUEST_RC &&
      !(inputs->rc1_valid && inputs->rc2_valid)) {
    faults |= JPBB_FAULT_RC_SIGNAL;
  }
  if (control->command_received &&
      (inputs->now_ms - control->last_command_ms) >
          JPBB_HOST_COMMAND_TIMEOUT_MS) {
    faults |= JPBB_FAULT_COMMAND_TIMEOUT;
  }
  if (control->heartbeat_received &&
      (inputs->now_ms - control->last_heartbeat_ms) >
          JPBB_HOST_HEARTBEAT_TIMEOUT_MS) {
    faults |= JPBB_FAULT_HEARTBEAT_TIMEOUT;
  }
  return faults;
}

static void write_jpb1_status(char *buffer, size_t capacity,
                              uint32_t sequence,
                              const jpbb_control_t *control,
                              const jpbb_control_inputs_t *inputs,
                              jpbb_authority_t authority,
                              const jpbb_rc_channel_t *rc1,
                              const jpbb_rc_channel_t *rc2,
                              const jpbb_rc_channel_t *rc3,
                              uint16_t vbec_mv, bool command_value_fault) {
  uint16_t servo_us;
  uint16_t esc_us;
  uint8_t selector;
  uint8_t active_path;
  uint32_t faults;
  int payload_length;
  int frame_length;

  if (buffer == NULL || capacity == 0U) {
    return;
  }
  jpbb_pwm_get(&servo_us, &esc_us);
  selector = (control->ch3_request == JPBB_CH3_REQUEST_PC ||
              (!control->receiver_latched && !any_rc_present(inputs)))
                 ? 1U
                 : 0U;
  faults = fault_bits(control, inputs, command_value_fault);
  if (authority == JPBB_AUTHORITY_RC) {
    active_path = 1U;
  } else if (authority == JPBB_AUTHORITY_PC) {
    active_path = 2U;
  } else {
    active_path = faults == 0U ? 0U : 3U;
  }

  payload_length = snprintf(
      buffer, capacity,
      "JPB1,S,%lu,%u,%u,%u,%u,%u,%u,%u,%u,%lu",
      (unsigned long)sequence, (unsigned int)rc1->pulse_us,
      (unsigned int)rc2->pulse_us, (unsigned int)rc3->pulse_us,
      (unsigned int)servo_us, (unsigned int)esc_us,
      (unsigned int)vbec_mv, (unsigned int)selector,
      (unsigned int)active_path, (unsigned long)faults);
  if (payload_length < 0 || (size_t)payload_length >= capacity) {
    buffer[0] = '\0';
    return;
  }
  const uint16_t crc =
      jpbb_protocol_crc16(buffer, (size_t)payload_length);
  frame_length = snprintf(buffer + payload_length,
                          capacity - (size_t)payload_length,
                          ",%04X\r\n", (unsigned int)crc);
  if (frame_length < 0 ||
      (size_t)frame_length >= capacity - (size_t)payload_length) {
    buffer[0] = '\0';
    return;
  }
  (void)jpbb_usb_write(buffer);
}

static void apply_authority(jpbb_authority_t authority,
                            const jpbb_control_inputs_t *inputs,
                            uint16_t desired_servo_us,
                            uint16_t desired_esc_us) {
  if (authority == JPBB_AUTHORITY_RC) {
    jpbb_manual_force();
    return;
  }

  if (authority == JPBB_AUTHORITY_PC) {
    jpbb_pwm_set(desired_servo_us, desired_esc_us);
    (void)jpbb_auto_select(true);
    return;
  }

  if (inputs->vbec_healthy) {
    /*
     * SAFE always requests the explicit MCU neutral output.  This works both
     * with and without a receiver.  If VBEC is too low, U5 independently
     * disables U2 and the firmware leaves the selector at its MANUAL default.
     */
    jpbb_pwm_set(JPBB_SERVO_SAFE_US, JPBB_ESC_SAFE_US);
    (void)jpbb_auto_select(true);
  } else {
    jpbb_manual_force();
  }
}

int main(void) {
  char line[96];
  char response[384];
  uint16_t desired_servo_us = JPBB_SERVO_SAFE_US;
  uint16_t desired_esc_us = JPBB_ESC_SAFE_US;
  jpbb_control_t control;
  jpbb_authority_t authority = JPBB_AUTHORITY_SAFE;
  uint32_t status_sequence = 0U;
  uint32_t last_status_ms = 0U;
  bool jpb1_active = false;
  bool command_value_fault = false;

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
    bool status_requested = false;
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

    if (!inputs.usb_healthy) {
      jpb1_active = false;
      command_value_fault = false;
    }

    /* Update CH3 filtering and enforce already-expired safety conditions. */
    authority = jpbb_control_update(&control, &inputs);

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
      } else if (command.kind == JPBB_COMMAND_HOST_FRAME) {
        uint16_t host_servo_us = JPBB_SERVO_SAFE_US;
        uint16_t host_esc_us = JPBB_ESC_SAFE_US;
        const bool command_valid =
            (command.flags & JPBB_HOST_FLAG_COMMAND_VALID) != 0U;
        const bool host_requested =
            (command.flags & JPBB_HOST_FLAG_HOST_REQUEST) != 0U;

        jpb1_active = true;
        jpbb_control_note_heartbeat(&control, now);
        command_value_fault =
            command_valid && !jpbb_protocol_host_pwm(
                                 &command, &host_servo_us, &host_esc_us);
        if (command_valid && !command_value_fault) {
          /* A valid neutral/disarm frame is also a fresh command.  This lets
           * the host clear a historic timeout after USB reconnect without
           * granting output authority or automatically re-arming. */
          jpbb_control_note_command(&control, now);
        }
        if (!command_valid || command_value_fault || !host_requested) {
          desired_servo_us = JPBB_SERVO_SAFE_US;
          desired_esc_us = JPBB_ESC_SAFE_US;
          jpbb_control_disarm_pc(&control);
        } else {
          if (!control.pc_armed) {
            desired_servo_us = JPBB_SERVO_SAFE_US;
            desired_esc_us = JPBB_ESC_SAFE_US;
            if (host_command_is_neutral(&command)) {
              (void)jpbb_control_arm_pc(&control, &inputs);
            }
          } else {
            desired_servo_us = host_servo_us;
            desired_esc_us = host_esc_us;
          }
        }
      } else if (command.kind == JPBB_COMMAND_AUTO) {
        if (!control.command_received) {
          (void)jpbb_usb_write("ERR send SET before AUTO\r\n");
        } else if (desired_servo_us != JPBB_SERVO_SAFE_US ||
                   desired_esc_us != JPBB_ESC_SAFE_US) {
          (void)jpbb_usb_write(
              "ERR send neutral SET before AUTO\r\n");
        } else if ((now - control.last_command_ms) >
                   JPBB_HOST_COMMAND_TIMEOUT_MS) {
          (void)jpbb_usb_write("ERR send a fresh SET before AUTO\r\n");
        } else if (!inputs.vbec_healthy) {
          (void)jpbb_usb_write("ERR PC refused: VBEC unhealthy\r\n");
        } else if ((control.receiver_latched || any_rc_present(&inputs)) &&
                   control.ch3_request != JPBB_CH3_REQUEST_PC) {
          (void)jpbb_usb_write(
              "ERR PC refused: CH3 must be near 2000 us\r\n");
        } else if (jpbb_control_arm_pc(&control, &inputs)) {
          (void)jpbb_usb_write(
              "OK PC armed; STREAM <=200 ms, HEARTBEAT <=500 ms\r\n");
        } else {
          (void)jpbb_usb_write("ERR PC refused: USB not ready\r\n");
        }
      } else if (command.kind == JPBB_COMMAND_MANUAL) {
        jpbb_control_disarm_pc(&control);
        (void)jpbb_usb_write(
            "OK PC disarmed; CH3 near 1000 us selects receiver\r\n");
      } else if (command.kind == JPBB_COMMAND_STATUS) {
        status_requested = true;
      } else if (command.kind == JPBB_COMMAND_HELP) {
        (void)jpbb_protocol_help(response, sizeof(response));
        (void)jpbb_usb_write(response);
      }
    }

    /* Apply commands immediately, then select RC, PC, or explicit SAFE. */
    authority = jpbb_control_update(&control, &inputs);
    apply_authority(authority, &inputs, desired_servo_us, desired_esc_us);

    if (jpb1_active &&
        (now - last_status_ms) >= JPBB_STATUS_PERIOD_MS) {
      last_status_ms = now;
      write_jpb1_status(response, sizeof(response), status_sequence++,
                        &control, &inputs, authority, &rc1, &rc2, &rc3,
                        vbec_mv, command_value_fault);
    }

    if (status_requested) {
      uint16_t servo_us;
      uint16_t esc_us;
      jpbb_pwm_get(&servo_us, &esc_us);
      (void)snprintf(
          response, sizeof(response),
          "STATUS step=8 authority=%s receiver=%s failsafe=%s "
          "mux=%s pc_armed=%u host_ready=%u ch3_request=%s ch3=%u/%u "
          "usb=%u vbec_mv=%u rc1=%u/%u rc2=%u/%u servo=%u esc=%u\r\n",
          jpbb_authority_name(authority),
          receiver_state_name(&control, &inputs),
          failsafe_reason(&control, &inputs, authority),
          jpbb_auto_is_selected() ? "MCU" : "RC",
          control.pc_armed ? 1U : 0U,
          jpbb_control_host_ready(&control, &inputs) ? 1U : 0U,
          jpbb_ch3_request_name(control.ch3_request), rc3.pulse_us,
          rc3.valid ? 1U : 0U, inputs.usb_healthy ? 1U : 0U, vbec_mv,
          rc1.pulse_us, rc1.valid ? 1U : 0U, rc2.pulse_us,
          rc2.valid ? 1U : 0U, servo_us, esc_us);
      (void)jpbb_usb_write(response);
    }

    jpbb_watchdog_refresh();
  }
}
