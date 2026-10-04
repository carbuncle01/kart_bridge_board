#include "jpbb_control.h"

#include <assert.h>
#include <stdio.h>

static jpbb_control_inputs_t inputs_at(uint32_t now_ms) {
  jpbb_control_inputs_t inputs = {
      .now_ms = now_ms,
      .ch3_us = 0U,
      .vbec_healthy = true,
      .usb_healthy = true,
      .rc1_valid = false,
      .rc2_valid = false,
      .rc3_valid = false,
  };
  return inputs;
}

static void confirm_ch3(jpbb_control_t *control,
                        jpbb_control_inputs_t *inputs, uint16_t pulse_us,
                        uint32_t duration_ms) {
  inputs->rc3_valid = true;
  inputs->ch3_us = pulse_us;
  (void)jpbb_control_update(control, inputs);
  inputs->now_ms += duration_ms;
  (void)jpbb_control_update(control, inputs);
}

static void test_pc_only_without_receiver(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(1000U);

  jpbb_control_init(&control);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.now_ms += JPBB_HOST_COMMAND_TIMEOUT_MS + 1U;
  jpbb_control_note_heartbeat(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(!control.pc_armed);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(jpbb_control_arm_pc(&control, &inputs));
}

static void test_rc_manual_override(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(2000U);

  jpbb_control_init(&control);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.rc1_valid = true;
  inputs.rc2_valid = true;
  confirm_ch3(&control, &inputs, 1000U, JPBB_CH3_RC_CONFIRM_MS);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_RC);
  assert(!control.pc_armed);

  inputs.rc1_valid = false;
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
}

static void test_ch3_pc_request_and_jitter(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(3000U);

  jpbb_control_init(&control);
  inputs.rc1_valid = true;
  inputs.rc2_valid = true;
  confirm_ch3(&control, &inputs, 1992U, JPBB_CH3_PC_CONFIRM_MS);
  assert(control.ch3_request == JPBB_CH3_REQUEST_PC);

  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.now_ms += 20U;
  inputs.ch3_us = 2010U;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.now_ms += 20U;
  inputs.ch3_us = 1500U;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.now_ms += JPBB_CH3_LOSS_CONFIRM_MS;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(control.ch3_request == JPBB_CH3_UNKNOWN);
  assert(!control.pc_armed);
}

static void test_receiver_requires_ch3_pc_permission(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(4000U);

  jpbb_control_init(&control);
  inputs.rc1_valid = true;
  inputs.rc2_valid = true;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(!jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
}

static void test_pc_stops_after_latched_receiver_disappears(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(5000U);

  jpbb_control_init(&control);
  inputs.rc1_valid = true;
  inputs.rc2_valid = true;
  confirm_ch3(&control, &inputs, 2000U, JPBB_CH3_PC_CONFIRM_MS);
  assert(control.receiver_latched);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));

  inputs.rc1_valid = false;
  inputs.rc2_valid = false;
  inputs.rc3_valid = false;
  inputs.now_ms += 50U;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.now_ms += JPBB_CH3_LOSS_CONFIRM_MS;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(!control.pc_armed);
}

static void test_vbec_fault_disarms_pc(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(6000U);

  jpbb_control_init(&control);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  inputs.vbec_healthy = false;
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(!control.pc_armed);
}

static void test_heartbeat_fault_disarms_pc(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(7000U);

  jpbb_control_init(&control);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));

  inputs.now_ms += JPBB_HOST_HEARTBEAT_TIMEOUT_MS + 1U;
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(!control.pc_armed);
}

static void test_usb_fault_disarms_and_requires_rearm(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(8000U);

  jpbb_control_init(&control);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.usb_healthy = false;
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(!control.pc_armed);

  inputs.usb_healthy = true;
  inputs.now_ms += 10U;
  jpbb_control_note_command(&control, inputs.now_ms);
  jpbb_control_note_heartbeat(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);
}

static void test_ch3_switch_requires_explicit_pc_rearm(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(9000U);

  jpbb_control_init(&control);
  inputs.rc1_valid = true;
  inputs.rc2_valid = true;
  confirm_ch3(&control, &inputs, 2000U, JPBB_CH3_PC_CONFIRM_MS);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  confirm_ch3(&control, &inputs, 1000U, JPBB_CH3_RC_CONFIRM_MS);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_RC);
  assert(!control.pc_armed);

  confirm_ch3(&control, &inputs, 2000U, JPBB_CH3_PC_CONFIRM_MS);
  jpbb_control_note_command(&control, inputs.now_ms);
  jpbb_control_note_heartbeat(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);
}

static void test_connecting_receiver_disarms_pc_only_mode(void) {
  jpbb_control_t control;
  jpbb_control_inputs_t inputs = inputs_at(10000U);

  jpbb_control_init(&control);
  jpbb_control_note_command(&control, inputs.now_ms);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);

  inputs.rc1_valid = true;
  inputs.rc2_valid = true;
  inputs.rc3_valid = true;
  inputs.ch3_us = 2000U;
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(control.receiver_latched);
  assert(!control.pc_armed);

  inputs.now_ms += JPBB_CH3_PC_CONFIRM_MS;
  jpbb_control_note_command(&control, inputs.now_ms);
  jpbb_control_note_heartbeat(&control, inputs.now_ms);
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_SAFE);
  assert(control.ch3_request == JPBB_CH3_REQUEST_PC);
  assert(jpbb_control_arm_pc(&control, &inputs));
  assert(jpbb_control_update(&control, &inputs) == JPBB_AUTHORITY_PC);
}

int main(void) {
  test_pc_only_without_receiver();
  test_rc_manual_override();
  test_ch3_pc_request_and_jitter();
  test_receiver_requires_ch3_pc_permission();
  test_pc_stops_after_latched_receiver_disappears();
  test_vbec_fault_disarms_pc();
  test_heartbeat_fault_disarms_pc();
  test_usb_fault_disarms_and_requires_rearm();
  test_ch3_switch_requires_explicit_pc_rearm();
  test_connecting_receiver_disarms_pc_only_mode();
  puts("jpbb_control tests: PASS");
  return 0;
}
