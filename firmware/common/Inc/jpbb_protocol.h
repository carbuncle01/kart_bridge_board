#ifndef JPBB_PROTOCOL_H
#define JPBB_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
  JPBB_COMMAND_NONE = 0,
  JPBB_COMMAND_STATUS,
  JPBB_COMMAND_MANUAL,
  JPBB_COMMAND_AUTO,
  JPBB_COMMAND_SET,
  JPBB_COMMAND_STREAM,
  JPBB_COMMAND_PING,
  JPBB_COMMAND_HEARTBEAT,
  JPBB_COMMAND_HOST_FRAME,
  JPBB_COMMAND_HELP,
  JPBB_COMMAND_INVALID
} jpbb_command_kind_t;

typedef struct {
  jpbb_command_kind_t kind;
  uint16_t servo_us;
  uint16_t esc_us;
  uint32_t sequence;
  int16_t steering_milli;
  uint16_t throttle_milli;
  uint16_t reverse_milli;
  uint16_t brake_milli;
  uint16_t flags;
} jpbb_command_t;

#define JPBB_HOST_FLAG_COMMAND_VALID (1U << 0)
#define JPBB_HOST_FLAG_HOST_REQUEST (1U << 1)

bool jpbb_protocol_parse(const char *line, jpbb_command_t *command);
uint16_t jpbb_protocol_crc16(const char *data, size_t length);
bool jpbb_protocol_host_pwm(const jpbb_command_t *command,
                            uint16_t *servo_us, uint16_t *esc_us);
size_t jpbb_protocol_status(char *buffer, size_t capacity);
size_t jpbb_protocol_help(char *buffer, size_t capacity);

#endif
