#include "jpbb_protocol.h"

#include <errno.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "jpbb_board.h"

#define JPBB_HOST_FIELD_COUNT 8U
#define JPBB_HOST_MAX_FIELDS 10U

uint16_t jpbb_protocol_crc16(const char *data, size_t length) {
  uint16_t crc = 0xFFFFU;

  if (data == NULL) {
    return crc;
  }
  for (size_t index = 0U; index < length; ++index) {
    crc ^= (uint16_t)((uint16_t)(uint8_t)data[index] << 8);
    for (uint8_t bit = 0U; bit < 8U; ++bit) {
      crc = (crc & 0x8000U) != 0U
                ? (uint16_t)((uint16_t)(crc << 1) ^ 0x1021U)
                : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

static bool parse_unsigned(const char *text, unsigned long maximum,
                           unsigned long *value) {
  char *end = NULL;
  unsigned long parsed;

  if (text == NULL || *text == '\0' || value == NULL || *text == '-') {
    return false;
  }
  errno = 0;
  parsed = strtoul(text, &end, 10);
  if (errno == ERANGE || end == text || *end != '\0' || parsed > maximum) {
    return false;
  }
  *value = parsed;
  return true;
}

static bool parse_signed(const char *text, long minimum, long maximum,
                         long *value) {
  char *end = NULL;
  long parsed;

  if (text == NULL || *text == '\0' || value == NULL) {
    return false;
  }
  errno = 0;
  parsed = strtol(text, &end, 10);
  if (errno == ERANGE || end == text || *end != '\0' || parsed < minimum ||
      parsed > maximum) {
    return false;
  }
  *value = parsed;
  return true;
}

static bool parse_host_frame(const char *line, jpbb_command_t *command) {
  char frame[96];
  char *fields[JPBB_HOST_MAX_FIELDS] = {0};
  char *crc_separator;
  char *cursor;
  size_t field_count = 0U;
  size_t length;
  char *crc_end = NULL;
  unsigned long received_crc;
  unsigned long sequence;
  unsigned long throttle;
  unsigned long reverse;
  unsigned long brake;
  unsigned long flags;
  long steering;

  if (line == NULL || command == NULL) {
    return false;
  }
  length = strcspn(line, "\r\n");
  if (length == 0U || length >= sizeof(frame)) {
    return false;
  }
  memcpy(frame, line, length);
  frame[length] = '\0';

  crc_separator = strrchr(frame, ',');
  if (crc_separator == NULL || strlen(crc_separator + 1) != 4U) {
    return false;
  }
  received_crc = strtoul(crc_separator + 1, &crc_end, 16);
  if (crc_end == crc_separator + 1 || *crc_end != '\0' ||
      received_crc > 0xFFFFUL) {
    return false;
  }
  *crc_separator = '\0';
  if ((uint16_t)received_crc !=
      jpbb_protocol_crc16(frame, (size_t)(crc_separator - frame))) {
    return false;
  }

  cursor = frame;
  while (field_count < JPBB_HOST_MAX_FIELDS) {
    fields[field_count++] = cursor;
    cursor = strchr(cursor, ',');
    if (cursor == NULL) {
      break;
    }
    *cursor++ = '\0';
  }
  if (field_count != JPBB_HOST_FIELD_COUNT || cursor != NULL ||
      strcmp(fields[0], "JPB1") != 0 || strcmp(fields[1], "C") != 0 ||
      !parse_unsigned(fields[2], 0xFFFFFFFFUL, &sequence) ||
      !parse_signed(fields[3], -1000L, 1000L, &steering) ||
      !parse_unsigned(fields[4], 1000UL, &throttle) ||
      !parse_unsigned(fields[5], 1000UL, &reverse) ||
      !parse_unsigned(fields[6], 1000UL, &brake) ||
      !parse_unsigned(fields[7], 0xFFFFUL, &flags) ||
      (flags & ~(unsigned long)(JPBB_HOST_FLAG_COMMAND_VALID |
                                JPBB_HOST_FLAG_HOST_REQUEST)) != 0UL) {
    return false;
  }

  command->kind = JPBB_COMMAND_HOST_FRAME;
  command->sequence = (uint32_t)sequence;
  command->steering_milli = (int16_t)steering;
  command->throttle_milli = (uint16_t)throttle;
  command->reverse_milli = (uint16_t)reverse;
  command->brake_milli = (uint16_t)brake;
  command->flags = (uint16_t)flags;
  return true;
}

static void normalize(char *destination, size_t capacity, const char *source) {
  size_t index = 0U;
  bool previous_space = true;

  while (*source != '\0' && index + 1U < capacity) {
    const unsigned char value = (unsigned char)*source++;
    if (isspace(value) != 0) {
      if (!previous_space) {
        destination[index++] = ' ';
        previous_space = true;
      }
      continue;
    }
    destination[index++] = (char)toupper(value);
    previous_space = false;
  }
  if (index > 0U && destination[index - 1U] == ' ') {
    --index;
  }
  destination[index] = '\0';
}

static bool parse_pwm_pair(const char *text, uint16_t *servo_us,
                           uint16_t *esc_us) {
  char *end = NULL;
  const unsigned long servo = strtoul(text, &end, 10);
  if (end == text || *end != ' ') {
    return false;
  }
  const char *second = end + 1;
  const unsigned long esc = strtoul(second, &end, 10);
  if (end == second || *end != '\0') {
    return false;
  }
  if (servo < JPBB_PWM_MIN_US || servo > JPBB_PWM_MAX_US ||
      esc < JPBB_PWM_MIN_US || esc > JPBB_PWM_MAX_US) {
    return false;
  }
  *servo_us = (uint16_t)servo;
  *esc_us = (uint16_t)esc;
  return true;
}

bool jpbb_protocol_parse(const char *line, jpbb_command_t *command) {
  char normalized[80];

  if (line == NULL || command == NULL) {
    return false;
  }

  command->kind = JPBB_COMMAND_INVALID;
  command->servo_us = JPBB_PWM_NEUTRAL_US;
  command->esc_us = JPBB_PWM_NEUTRAL_US;
  command->sequence = 0U;
  command->steering_milli = 0;
  command->throttle_milli = 0U;
  command->reverse_milli = 0U;
  command->brake_milli = 0U;
  command->flags = 0U;

  if (strncmp(line, "JPB1,C,", 7U) == 0) {
    return parse_host_frame(line, command);
  }
  normalize(normalized, sizeof(normalized), line);

  if (strcmp(normalized, "STATUS") == 0) {
    command->kind = JPBB_COMMAND_STATUS;
  } else if (strcmp(normalized, "MANUAL") == 0) {
    command->kind = JPBB_COMMAND_MANUAL;
  } else if (strcmp(normalized, "AUTO") == 0) {
    command->kind = JPBB_COMMAND_AUTO;
  } else if (strcmp(normalized, "PING") == 0) {
    command->kind = JPBB_COMMAND_PING;
  } else if (strcmp(normalized, "HEARTBEAT") == 0) {
    command->kind = JPBB_COMMAND_HEARTBEAT;
  } else if (strcmp(normalized, "HELP") == 0) {
    command->kind = JPBB_COMMAND_HELP;
  } else if (strncmp(normalized, "SET ", 4U) == 0 &&
             parse_pwm_pair(&normalized[4], &command->servo_us,
                            &command->esc_us)) {
    command->kind = JPBB_COMMAND_SET;
  } else if (strncmp(normalized, "STREAM ", 7U) == 0 &&
             parse_pwm_pair(&normalized[7], &command->servo_us,
                            &command->esc_us)) {
    command->kind = JPBB_COMMAND_STREAM;
  } else if (normalized[0] == '\0') {
    command->kind = JPBB_COMMAND_NONE;
  }

  return command->kind != JPBB_COMMAND_INVALID;
}

bool jpbb_protocol_host_pwm(const jpbb_command_t *command,
                            uint16_t *servo_us, uint16_t *esc_us) {
  int32_t servo;
  int32_t esc;

  if (command == NULL || servo_us == NULL || esc_us == NULL ||
      command->kind != JPBB_COMMAND_HOST_FRAME ||
      command->steering_milli < -1000 || command->steering_milli > 1000 ||
      command->throttle_milli > 1000U || command->reverse_milli > 1000U ||
      command->brake_milli > 1000U) {
    return false;
  }
  if (command->throttle_milli > 0U && command->reverse_milli > 0U) {
    return false;
  }

  servo = 1500L + (int32_t)command->steering_milli / 2L;
  /*
   * The vehicle ESC polarity is opposite to the conventional RC mapping:
   * decreasing pulse width commands forward throttle, while increasing pulse
   * width commands brake/reverse.  Keep brake on the reverse side so it
   * produces the ESC's forward-running brake response.
   */
  if (command->brake_milli > 0U) {
    esc = 1500L + (int32_t)command->brake_milli / 2L;
  } else if (command->reverse_milli > 0U) {
    esc = 1500L + (int32_t)command->reverse_milli / 2L;
  } else {
    esc = 1500L - (int32_t)command->throttle_milli / 2L;
  }
  if (servo < (int32_t)JPBB_PWM_MIN_US ||
      servo > (int32_t)JPBB_PWM_MAX_US ||
      esc < (int32_t)JPBB_PWM_MIN_US || esc > (int32_t)JPBB_PWM_MAX_US) {
    return false;
  }
  *servo_us = (uint16_t)servo;
  *esc_us = (uint16_t)esc;
  return true;
}

size_t jpbb_protocol_status(char *buffer, size_t capacity) {
  jpbb_status_t status = {0};
  uint16_t servo = 0U;
  uint16_t esc = 0U;
  int result;

  if (buffer == NULL || capacity == 0U) {
    return 0U;
  }
  jpbb_status_snapshot(&status);
  jpbb_pwm_get(&servo, &esc);

  result = snprintf(
      buffer, capacity,
      "STATUS mode=%s usb=%u vbec_mv=%u "
      "rc1=%u/%u rc2=%u/%u rc3=%u/%u servo=%u esc=%u\r\n",
      status.auto_selected ? "AUTO" : "MANUAL",
      status.usb_present ? 1U : 0U, status.vbec_mv,
      status.channel[0].pulse_us, status.channel[0].valid ? 1U : 0U,
      status.channel[1].pulse_us, status.channel[1].valid ? 1U : 0U,
      status.channel[2].pulse_us, status.channel[2].valid ? 1U : 0U,
      servo, esc);
  if (result < 0) {
    buffer[0] = '\0';
    return 0U;
  }
  return ((size_t)result < capacity) ? (size_t)result : capacity - 1U;
}

size_t jpbb_protocol_help(char *buffer, size_t capacity) {
  static const char help[] =
      "PING | HEARTBEAT | STATUS | MANUAL | AUTO | "
      "SET/STREAM <servo_us> <esc_us> | JPB1,C,...,CRC | HELP\r\n";
  if (buffer == NULL || capacity == 0U) {
    return 0U;
  }
  const size_t source_length = sizeof(help) - 1U;
  const size_t length =
      (source_length < capacity - 1U) ? source_length : capacity - 1U;
  memcpy(buffer, help, length);
  buffer[length] = '\0';
  return length;
}
