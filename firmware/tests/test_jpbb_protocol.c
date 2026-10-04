#include "jpbb_protocol.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "jpbb_board.h"

void jpbb_status_snapshot(jpbb_status_t *status) {
  memset(status, 0, sizeof(*status));
}

void jpbb_pwm_get(uint16_t *servo_us, uint16_t *esc_us) {
  *servo_us = 1500U;
  *esc_us = 1500U;
}

static void append_crc(char *frame, size_t capacity, const char *payload) {
  const uint16_t crc = jpbb_protocol_crc16(payload, strlen(payload));
  const int count = snprintf(frame, capacity, "%s,%04X\n", payload, crc);
  assert(count > 0 && (size_t)count < capacity);
}

static void test_crc_check_value(void) {
  assert(jpbb_protocol_crc16("123456789", 9U) == 0x29B1U);
}

static void test_host_frame_and_pwm(void) {
  char frame[128];
  jpbb_command_t command = {0};
  uint16_t servo_us = 0U;
  uint16_t esc_us = 0U;

  append_crc(frame, sizeof(frame), "JPB1,C,42,-500,750,0,0,3");
  assert(jpbb_protocol_parse(frame, &command));
  assert(command.kind == JPBB_COMMAND_HOST_FRAME);
  assert(command.sequence == 42U);
  assert(command.steering_milli == -500);
  assert(command.throttle_milli == 750U);
  assert(command.flags == 3U);
  assert(jpbb_protocol_host_pwm(&command, &servo_us, &esc_us));
  assert(servo_us == 1250U);
  assert(esc_us == 1125U);
}

static void test_vehicle_esc_polarity(void) {
  char frame[128];
  jpbb_command_t command = {0};
  uint16_t servo_us = 0U;
  uint16_t esc_us = 0U;

  append_crc(frame, sizeof(frame), "JPB1,C,1,0,1000,0,0,3");
  assert(jpbb_protocol_parse(frame, &command));
  assert(jpbb_protocol_host_pwm(&command, &servo_us, &esc_us));
  assert(esc_us == 1000U);

  append_crc(frame, sizeof(frame), "JPB1,C,2,0,0,1000,0,3");
  assert(jpbb_protocol_parse(frame, &command));
  assert(jpbb_protocol_host_pwm(&command, &servo_us, &esc_us));
  assert(esc_us == 2000U);

  append_crc(frame, sizeof(frame), "JPB1,C,3,0,0,0,1000,3");
  assert(jpbb_protocol_parse(frame, &command));
  assert(jpbb_protocol_host_pwm(&command, &servo_us, &esc_us));
  assert(esc_us == 2000U);
}

static void test_rejects_crc_and_drive_conflict(void) {
  char frame[128];
  jpbb_command_t command = {0};
  uint16_t servo_us = 0U;
  uint16_t esc_us = 0U;

  append_crc(frame, sizeof(frame), "JPB1,C,1,0,500,500,0,3");
  assert(jpbb_protocol_parse(frame, &command));
  assert(!jpbb_protocol_host_pwm(&command, &servo_us, &esc_us));
  frame[strlen(frame) - 2U] = frame[strlen(frame) - 2U] == '0' ? '1' : '0';
  assert(!jpbb_protocol_parse(frame, &command));
}

static void test_rejects_sequence_overflow(void) {
  char frame[128];
  jpbb_command_t command = {0};

  append_crc(frame, sizeof(frame),
             "JPB1,C,999999999999999999999999,0,0,0,0,1");
  assert(!jpbb_protocol_parse(frame, &command));
}

int main(void) {
  test_crc_check_value();
  test_host_frame_and_pwm();
  test_vehicle_esc_polarity();
  test_rejects_crc_and_drive_conflict();
  test_rejects_sequence_overflow();
  puts("jpbb_protocol tests: PASS");
  return 0;
}
