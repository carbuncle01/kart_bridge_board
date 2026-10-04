#ifndef JPBB_CONTROL_H
#define JPBB_CONTROL_H

#include <stdbool.h>
#include <stdint.h>

/*
 * CH3 is a two-position authority request, not an exact 1000/2000 us value.
 * The gap provides hysteresis for receiver jitter and switch transitions.
 */
#define JPBB_CH3_RC_MAX_US 1300U
#define JPBB_CH3_PC_MIN_US 1700U
#define JPBB_CH3_RC_CONFIRM_MS 40U
#define JPBB_CH3_PC_CONFIRM_MS 100U
#define JPBB_CH3_LOSS_CONFIRM_MS 100U

/*
 * A heartbeat only proves that the host connection is alive.  A recent
 * control command is also required so a stalled joystick/control loop cannot
 * leave an old actuator command active.
 */
#define JPBB_HOST_COMMAND_TIMEOUT_MS 200U
#define JPBB_HOST_HEARTBEAT_TIMEOUT_MS 500U

typedef enum {
  JPBB_AUTHORITY_SAFE = 0,
  JPBB_AUTHORITY_RC,
  JPBB_AUTHORITY_PC
} jpbb_authority_t;

typedef enum {
  JPBB_CH3_UNKNOWN = 0,
  JPBB_CH3_REQUEST_RC,
  JPBB_CH3_REQUEST_PC
} jpbb_ch3_request_t;

typedef struct {
  uint32_t now_ms;
  uint16_t ch3_us;
  bool vbec_healthy;
  bool usb_healthy;
  bool rc1_valid;
  bool rc2_valid;
  bool rc3_valid;
} jpbb_control_inputs_t;

typedef struct {
  jpbb_ch3_request_t ch3_request;
  jpbb_ch3_request_t ch3_candidate;
  uint32_t ch3_candidate_since_ms;
  bool receiver_latched;
  bool pc_armed;
  bool command_received;
  bool heartbeat_received;
  uint32_t last_command_ms;
  uint32_t last_heartbeat_ms;
} jpbb_control_t;

void jpbb_control_init(jpbb_control_t *control);
void jpbb_control_note_command(jpbb_control_t *control, uint32_t now_ms);
void jpbb_control_note_heartbeat(jpbb_control_t *control, uint32_t now_ms);
bool jpbb_control_arm_pc(jpbb_control_t *control,
                         const jpbb_control_inputs_t *inputs);
void jpbb_control_disarm_pc(jpbb_control_t *control);
jpbb_authority_t jpbb_control_update(jpbb_control_t *control,
                                     const jpbb_control_inputs_t *inputs);
bool jpbb_control_host_ready(const jpbb_control_t *control,
                             const jpbb_control_inputs_t *inputs);
const char *jpbb_authority_name(jpbb_authority_t authority);
const char *jpbb_ch3_request_name(jpbb_ch3_request_t request);

#endif
